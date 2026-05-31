"""
Registry Delta Detector  (registry/delta_detector.py)

Nightly cron job that:
  1. Re-scans the metrics server for new tables, columns, and distinct values
  2. Compares against the current registry snapshot
  3. Flags any new unknown values for data-team review
  4. Calls AlertService to notify the team

Run via cron: 0 2 * * * python -m registry.delta_detector
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, inspect, text

from config.settings import get_settings
from registry.schema_db import SchemaDB
from registry.alert_service import AlertService

logger = logging.getLogger(__name__)


@dataclass
class DeltaReport:
    run_at: datetime = field(default_factory=datetime.utcnow)
    new_tables: list[str] = field(default_factory=list)
    new_columns: list[str] = field(default_factory=list)
    new_flagged_values: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.new_tables or self.new_columns or self.new_flagged_values)

    def summary(self) -> str:
        lines = [f"Delta Detector run at {self.run_at.isoformat()}"]
        if self.new_tables:
            lines.append(f"  New tables ({len(self.new_tables)}): {', '.join(self.new_tables)}")
        if self.new_columns:
            lines.append(f"  New columns ({len(self.new_columns)}): {', '.join(self.new_columns)}")
        if self.new_flagged_values:
            lines.append(
                f"  Flagged unknown values ({len(self.new_flagged_values)}): "
                + ", ".join(self.new_flagged_values)
            )
        return "\n".join(lines)


class DeltaDetector:
    """
    Usage:
        detector = DeltaDetector()
        report = detector.run()
        print(report.summary())
    """

    def __init__(
        self,
        metrics_db_url: Optional[str] = None,
        registry_db_url: Optional[str] = None,
    ) -> None:
        cfg = get_settings()
        self._metrics_url = metrics_db_url or cfg.metrics_db_url
        self._threshold = cfg.auto_scan_low_cardinality_threshold
        self._db = SchemaDB(registry_db_url or cfg.registry_db_url)
        self._alerter = AlertService()

    def run(self) -> DeltaReport:
        report = DeltaReport()
        logger.info("DeltaDetector: starting run")

        known_tables = {t.table_name for t in self._db.list_tables()}
        engine = create_engine(self._metrics_url, echo=False)
        insp = inspect(engine)

        live_tables = set(insp.get_table_names())

        # New tables
        for tname in live_tables - known_tables:
            self._db.upsert_table(
                tname,
                description=f"Auto-discovered (delta): {tname}",
                keywords=tname.replace("_", " "),
                domain="auto",
            )
            report.new_tables.append(tname)
            logger.info("DeltaDetector: new table %s", tname)

        # New columns and new distinct values
        for tname in live_tables:
            try:
                live_cols = {c["name"]: c for c in insp.get_columns(tname)}
            except Exception:
                continue

            meta = self._db.get_table_meta(tname)
            known_cols = {c.column_name for c in meta.columns} if meta else set()

            for cname, col_info in live_cols.items():
                if cname not in known_cols:
                    self._db.upsert_column(
                        tname, cname,
                        data_type=str(col_info["type"]),
                        is_nullable=col_info.get("nullable", True),
                    )
                    report.new_columns.append(f"{tname}.{cname}")

                # Check for new distinct values in text columns
                dtype = str(col_info["type"]).lower()
                if any(t in dtype for t in ("varchar", "char", "text", "string")):
                    flagged = self._check_new_values(engine, tname, cname)
                    for v in flagged:
                        report.new_flagged_values.append(f"{tname}.{cname}={v!r}")

        if not report.is_empty():
            logger.warning("DeltaDetector: changes detected\n%s", report.summary())
            self._alerter.send(report)
        else:
            logger.info("DeltaDetector: no changes detected")

        return report

    def _check_new_values(self, engine, tname: str, cname: str) -> list[str]:
        try:
            with engine.connect() as conn:
                rows = conn.execute(
                    text(
                        f"SELECT DISTINCT {cname} FROM {tname} "  # nosec
                        f"WHERE {cname} IS NOT NULL LIMIT {self._threshold + 1}"
                    )
                )
                live_vals = {str(r[0]) for r in rows}
        except Exception:
            return []

        if len(live_vals) > self._threshold:
            return []

        known_vals = {
            v.internal_code
            for v in self._db.get_values_for_column(tname, cname)
        }
        new_vals = live_vals - known_vals
        for v in new_vals:
            self._db.flag_unknown_value(tname, cname, v)
        return list(new_vals)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    detector = DeltaDetector()
    rpt = detector.run()
    print(rpt.summary())
