"""
API Route — Audit Log  (api/routes/audit.py)

GET /audit/log — Admin endpoint: full audit trail with user, SQL, and result.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from api.auth import UserContext, require_admin
from api.middleware.audit_logger import AuditLogger

router = APIRouter(prefix="/audit", tags=["audit"])
_audit = AuditLogger()


@router.get("/log", summary="Full audit trail (admin only)")
async def get_audit_log(
    admin: Annotated[UserContext, Depends(require_admin)],
    user_id: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """
    Returns paginated audit records.
    Filter by user_id to see a specific user's history.
    Requires admin role.
    """
    total, records = _audit.list_logs(user_id=user_id, page=page, page_size=page_size)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "records": [
            {
                "id": r.id,
                "query_id": r.query_id,
                "user_id": r.user_id,
                "question": r.question,
                "selected_tables": r.selected_tables.split(",") if r.selected_tables else [],
                "generated_sql": r.generated_sql,
                "row_count": r.row_count,
                "execution_time_ms": r.execution_time_ms,
                "status": r.status,
                "error_message": r.error_message,
                "created_at": r.created_at.isoformat(),
            }
            for r in records
        ],
    }
