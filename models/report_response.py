"""Pydantic models for API responses."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MappedValueOut(BaseModel):
    original_phrase: str
    internal_code: str
    table_name: str
    column_name: str


class QueryResponse(BaseModel):
    query_id: str = Field(description="Unique identifier for this query execution")
    question: str
    selected_tables: list[str]
    value_mappings: list[MappedValueOut]
    generated_sql: str
    validation_warnings: list[str]
    row_count: int
    execution_time_ms: float
    truncated: bool
    report: str = Field(description="Full narrative report (Markdown)")
    markdown_table: str = Field(description="Data as a Markdown table")

    class Config:
        json_schema_extra = {
            "example": {
                "query_id": "q_20241201_ab12cd",
                "question": "How many active customers are in DFW?",
                "selected_tables": ["customer_accounts"],
                "value_mappings": [
                    {"original_phrase": "active", "internal_code": "A",
                     "table_name": "customer_accounts", "column_name": "status"}
                ],
                "generated_sql": "SELECT COUNT(*) FROM customer_accounts WHERE status='A' AND region='DFW' LIMIT 10000",
                "validation_warnings": [],
                "row_count": 1,
                "execution_time_ms": 42.3,
                "truncated": False,
                "report": "**Summary**: There are 14,832 active customers in the DFW region...",
                "markdown_table": "| count(*) |\n|---|\n| 14832 |",
            }
        }


class ErrorResponse(BaseModel):
    detail: str
    stage: str = Field(description="Pipeline stage where the error occurred")
    query_id: str | None = None
