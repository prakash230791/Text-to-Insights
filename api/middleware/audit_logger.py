"""
API Middleware — Audit Logger  (api/middleware/audit_logger.py)

Persists every query invocation to the audit DB.
Provides AuditLogger class (used directly by the /query route)
and get_audit_db() dependency.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Integer, String, Text, create_engine, func, select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from config.settings import get_settings

logger = logging.getLogger(__name__)
cfg = get_settings()

_engine = create_engine(
    cfg.audit_db_url,
    echo=False,
    connect_args={"check_same_thread": False},
)
_Session = sessionmaker(bind=_engine, expire_on_commit=False)


class _Base(DeclarativeBase):
    pass


class AuditLog(_Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    selected_tables: Mapped[str] = mapped_column(Text, nullable=False, default="")
    generated_sql: Mapped[str] = mapped_column(Text, nullable=False, default="")
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    execution_time_ms: Mapped[float] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="SUCCESS")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def init_audit_db() -> None:
    _Base.metadata.create_all(_engine)
    logger.info("AuditLogger: tables created / verified")


class AuditLogger:
    def log(
        self,
        query_id: str,
        user_id: str,
        question: str,
        selected_tables: list[str],
        generated_sql: str,
        row_count: int,
        execution_time_ms: float,
        status: str = "SUCCESS",
        error_message: str = "",
    ) -> None:
        with _Session() as sess:
            sess.add(AuditLog(
                query_id=query_id,
                user_id=user_id,
                question=question,
                selected_tables=",".join(selected_tables),
                generated_sql=generated_sql,
                row_count=row_count,
                execution_time_ms=int(execution_time_ms),
                status=status,
                error_message=error_message,
            ))
            sess.commit()

    def list_logs(
        self, user_id: str | None = None, page: int = 1, page_size: int = 20
    ) -> tuple[int, list[AuditLog]]:
        with _Session() as sess:
            q = select(AuditLog).order_by(AuditLog.created_at.desc())
            if user_id:
                q = q.where(AuditLog.user_id == user_id)
            total = sess.scalar(
                select(func.count()).select_from(q.subquery())
            ) or 0
            rows = sess.scalars(
                q.offset((page - 1) * page_size).limit(page_size)
            ).all()
            return total, list(rows)
