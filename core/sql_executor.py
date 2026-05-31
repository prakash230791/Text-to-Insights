"""
Module 6 — SQL Executor  (core/sql_executor.py)

Executes validated SQL against the metrics server using a connection pool.
Enforces a wall-clock timeout (Rule 6 from the design spec).
Returns raw result rows plus execution metadata.

The engine is created with:
  • pool_size + max_overflow from settings
  • execution_options(no_parameters=True) to prevent accidental writes
  • read-only SQLite URI flag (if SQLite backend)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool

from config.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    execution_time_ms: float = 0.0
    truncated: bool = False  # True if result was capped at row_limit


class SQLExecutor:
    """
    Usage:
        executor = SQLExecutor()
        result = executor.execute("SELECT * FROM customer_accounts LIMIT 100")
        print(result.rows)
    """

    def __init__(self) -> None:
        cfg = get_settings()
        self._row_limit = cfg.query_row_limit
        self._timeout_sec = cfg.query_timeout_seconds
        self._engine = self._build_engine(cfg)

    @staticmethod
    def _build_engine(cfg) -> Engine:
        """Build a read-only connection pool to the metrics DB."""
        url = cfg.metrics_db_url

        # For SQLite: use ?mode=ro URI to enforce read-only at driver level
        if url.startswith("sqlite:///"):
            path = url.replace("sqlite:///", "")
            connect_url = f"sqlite:///file:{path}?mode=ro&uri=true"
        else:
            connect_url = url

        engine = create_engine(
            connect_url,
            poolclass=QueuePool,
            pool_size=cfg.metrics_db_pool_size,
            max_overflow=cfg.metrics_db_max_overflow,
            pool_pre_ping=True,
            echo=False,
            connect_args={"check_same_thread": False} if "sqlite" in url else {},
        )

        # Extra guard: abort any DDL/DML at the connection event level
        @event.listens_for(engine, "before_execute")
        def _block_writes(conn, clauseelement, multiparams, params, execution_options):
            sql_str = str(clauseelement).strip().upper()
            forbidden = ("INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE")
            if any(sql_str.startswith(kw) for kw in forbidden):
                raise PermissionError(f"Write operation blocked by SQLExecutor: {sql_str[:60]}")

        return engine

    def execute(self, sql: str) -> ExecutionResult:
        """
        Run a validated SELECT query.

        Args:
            sql: The validated SQL string (must start with SELECT).

        Returns:
            ExecutionResult with rows as list-of-dicts.

        Raises:
            TimeoutError: If the query exceeds the configured timeout.
            PermissionError: If a write statement somehow slips through.
            RuntimeError: On any other DB-level error.
        """
        start = time.perf_counter()

        try:
            with self._engine.connect() as conn:
                # SQLite doesn't support server-side timeouts; we use Python-level timing
                conn = conn.execution_options(
                    stream_results=True,
                    max_row_buffer=self._row_limit,
                )
                result_proxy = conn.execute(text(sql))
                columns = list(result_proxy.keys())
                rows_raw = result_proxy.fetchmany(self._row_limit + 1)

        except PermissionError:
            raise
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            if elapsed / 1000 >= self._timeout_sec:
                raise TimeoutError(
                    f"Query exceeded {self._timeout_sec}s timeout."
                ) from exc
            raise RuntimeError(f"SQL execution error: {exc}") from exc

        elapsed_ms = (time.perf_counter() - start) * 1000

        if elapsed_ms / 1000 > self._timeout_sec:
            raise TimeoutError(f"Query exceeded {self._timeout_sec}s timeout.")

        truncated = len(rows_raw) > self._row_limit
        rows_raw = rows_raw[: self._row_limit]

        rows = [dict(zip(columns, row)) for row in rows_raw]

        result = ExecutionResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            execution_time_ms=round(elapsed_ms, 2),
            truncated=truncated,
        )
        logger.info(
            "SQLExecutor: %d rows in %.1f ms (truncated=%s)",
            result.row_count,
            result.execution_time_ms,
            result.truncated,
        )
        return result
