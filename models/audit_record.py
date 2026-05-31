"""Pydantic models for audit log records."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditRecord(BaseModel):
    id: int
    query_id: str
    user_id: str
    question: str
    selected_tables: list[str]
    generated_sql: str
    row_count: int
    execution_time_ms: float
    status: str  # SUCCESS | VALIDATION_ERROR | EXECUTION_ERROR | TIMEOUT
    error_message: str
    created_at: datetime

    class Config:
        from_attributes = True


class AuditListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    records: list[AuditRecord]
