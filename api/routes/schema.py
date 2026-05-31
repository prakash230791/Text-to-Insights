"""
API Route — Schema endpoints  (api/routes/schema.py)

GET /schema/tables          — Browse all registered tables
GET /schema/values/{table}  — View value mappings for a specific table
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from api.auth import UserContext, get_current_user
from config.settings import get_settings
from registry.schema_db import SchemaDB

router = APIRouter(prefix="/schema", tags=["schema"])


def _get_db() -> SchemaDB:
    cfg = get_settings()
    db = SchemaDB(cfg.registry_db_url)
    db.init_db()
    return db


@router.get("/tables", summary="Browse all registered tables and their metadata")
async def list_tables(
    user: Annotated[UserContext, Depends(get_current_user)],
    domain: str | None = None,
) -> dict:
    db = _get_db()
    tables = db.list_tables(domain=domain)
    result = []
    for stub in tables:
        meta = db.get_table_meta(stub.table_name)
        result.append({
            "table_name": stub.table_name,
            "description": stub.description,
            "domain": stub.domain,
            "keywords": stub.keywords,
            "column_count": len(meta.columns) if meta else 0,
            "columns": [
                {
                    "name": c.column_name,
                    "type": c.data_type,
                    "description": c.description,
                    "is_metric": c.is_metric,
                    "is_dimension": c.is_dimension,
                }
                for c in (meta.columns if meta else [])
            ],
        })
    return {"tables": result, "total": len(result)}


@router.get(
    "/values/{table_name}",
    summary="View value mappings for a specific table",
)
async def get_table_values(
    table_name: str,
    user: Annotated[UserContext, Depends(get_current_user)],
    column_name: str | None = None,
) -> dict:
    db = _get_db()
    meta = db.get_table_meta(table_name)
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{table_name}' not found in the Schema Registry",
        )

    values = meta.values
    if column_name:
        values = [v for v in values if v.column_name == column_name]

    flagged = db.get_flagged_values()
    flagged_for_table = [
        f for f in flagged if f.table_name == table_name
    ]

    return {
        "table_name": table_name,
        "curated_values": [
            {
                "column_name": v.column_name,
                "internal_code": v.internal_code,
                "human_label": v.human_label,
            }
            for v in values
        ],
        "flagged_unknown": [
            {
                "column_name": f.column_name,
                "internal_code": f.internal_code,
                "note": "Needs manual curation",
            }
            for f in flagged_for_table
        ],
    }
