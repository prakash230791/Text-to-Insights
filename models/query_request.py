"""Pydantic models for query API requests."""
from pydantic import BaseModel, Field, field_validator


class QueryRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=5,
        max_length=1000,
        description="Natural language business question",
        examples=["How many active customers are in the DFW region?"],
    )
    domain: str | None = Field(
        default=None,
        description="Optional domain filter to narrow table retrieval (e.g. 'billing', 'network')",
    )
    top_k_tables: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Number of tables to retrieve for context (1-5)",
    )
    allow_set_operations: bool = Field(
        default=False,
        description="Allow UNION/INTERSECT/EXCEPT in generated SQL",
    )

    @field_validator("question")
    @classmethod
    def sanitize_question(cls, v: str) -> str:
        return v.strip()
