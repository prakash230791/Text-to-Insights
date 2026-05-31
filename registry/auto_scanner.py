"""
Registry Auto-Scanner  (registry/auto_scanner.py)

Connects to the metrics server (read-only) and:
  1. Discovers all tables and columns automatically
  2. Samples distinct values for low-cardinality columns (< threshold)
  3. Populates the Schema Registry without overwriting manually curated labels
  4. Flags new unknown values detected since the last scan

Run on first setup and via nightly cron:
    python -m registry.auto_scanner
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, inspect, text

from config.settings import get_settings
from registry.schema_db import SchemaDB

logger = logging.getLogger(__name__)


class AutoScanner:
    """
    Usage:
        scanner = AutoScanner()
        scanner.scan()
    """

    def __init__(
        self,
        metrics_db_url: Optional[str] = None,
        registry_db_url: Optional[str] = None,
        low_cardinality_threshold: Optional[int] = None,
    ) -> None:
        cfg = get_settings()
        self._metrics_url = metrics_db_url or cfg.metrics_db_url
        self._registry_url = registry_db_url or cfg.registry_db_url
        self._threshold = low_cardinality_threshold or cfg.auto_scan_low_cardinality_threshold
        self._db = SchemaDB(self._registry_url)
        self._db.init_db()

    def scan(self) -> dict[str, int]:
        """
        Full scan of the metrics server.

        Returns:
            Stats dict: {"tables": N, "columns": N, "values": N, "flagged": N}
        """
        logger.info("AutoScanner: connecting to %s", self._metrics_url)
        engine = create_engine(self._metrics_url, echo=False)
        insp = inspect(engine)

        stats = {"tables": 0, "columns": 0, "values": 0, "flagged": 0}

        table_names: list[str] = insp.get_table_names()
        logger.info("AutoScanner: found %d tables", len(table_names))

        for tname in table_names:
            self._process_table(engine, insp, tname, stats)

        logger.info(
            "AutoScanner: scan complete — %s", stats
        )
        return stats

    def _process_table(self, engine, insp, tname: str, stats: dict) -> None:
        try:
            cols_info = insp.get_columns(tname)
        except Exception as exc:
            logger.warning("AutoScanner: could not inspect %s — %s", tname, exc)
            return

        # Register table (don't overwrite existing human descriptions)
        self._db.upsert_table(
            table_name=tname,
            description=f"Auto-discovered table: {tname}",
            keywords=tname.replace("_", " "),
            domain="auto",
        )
        stats["tables"] += 1

        for col in cols_info:
            cname: str = col["name"]
            dtype: str = str(col["type"])
            nullable: bool = col.get("nullable", True)

            self._db.upsert_column(
                table_name=tname,
                column_name=cname,
                data_type=dtype,
                is_nullable=nullable,
            )
            stats["columns"] += 1

            # Sample distinct values for low-cardinality columns
            if self._is_low_cardinality_candidate(dtype):
                flagged = self._sample_values(engine, tname, cname, stats)
                stats["flagged"] += flagged

    def _is_low_cardinality_candidate(self, dtype: str) -> bool:
        dtype_lower = dtype.lower()
        return any(t in dtype_lower for t in ("varchar", "char", "text", "string"))

    def _sample_values(self, engine, tname: str, cname: str, stats: dict) -> int:
        """Sample distinct values; flag any not yet in the registry. Returns flagged count."""
        try:
            with engine.connect() as conn:
                result = conn.execute(
                    text(
                        f"SELECT DISTINCT {cname} FROM {tname} "  # nosec — tname/cname from DB introspection
                        f"WHERE {cname} IS NOT NULL LIMIT {self._threshold + 1}"
                    )
                )
                distinct_vals = [str(row[0]) for row in result]
        except Exception as exc:
            logger.debug("AutoScanner: could not sample %s.%s — %s", tname, cname, exc)
            return 0

        if len(distinct_vals) > self._threshold:
            return 0  # high cardinality — skip

        flagged = 0
        known = {
            v.internal_code
            for v in self._db.get_values_for_column(tname, cname)
        }
        for val in distinct_vals:
            if val not in known:
                self._db.flag_unknown_value(tname, cname, val)
                flagged += 1
                stats["values"] += 1
                logger.debug("AutoScanner: flagged unknown value %s.%s=%r", tname, cname, val)

        return flagged


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    scanner = AutoScanner()
    result = scanner.scan()
    print(f"\nScan complete: {result}")
