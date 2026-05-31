"""
API Route — POST /query  (api/routes/query.py)

Accepts a natural-language question, runs the full LangGraph pipeline,
and returns a formatted report with audit trail.
"""
from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.auth import UserContext, get_current_user
from api.middleware.audit_logger import AuditLogger
from api.middleware.rate_limiter import limiter
from core.pipeline import create_pipeline
from models.query_request import QueryRequest
from models.report_response import ErrorResponse, MappedValueOut, QueryResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/query", tags=["query"])

# Singletons — built once at module load time
_pipeline = None
_audit = AuditLogger()


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = create_pipeline()
    return _pipeline


@router.post(
    "",
    response_model=QueryResponse,
    responses={
        400: {"model": ErrorResponse},
        429: {"description": "Rate limit exceeded"},
        500: {"model": ErrorResponse},
    },
    summary="Submit a natural language query",
)
@limiter.limit("{rate_limit_per_minute}/minute")
async def submit_query(
    request: Request,
    body: QueryRequest,
    user: Annotated[UserContext, Depends(get_current_user)],
) -> QueryResponse:
    query_id = f"q_{uuid.uuid4().hex[:12]}"
    logger.info("Query[%s] user=%s question=%r", query_id, user.user_id, body.question[:80])

    pipeline = _get_pipeline()

    try:
        state = pipeline.invoke({"question": body.question, "retry_count": 0})
    except Exception as exc:
        logger.exception("Pipeline error for query %s", query_id)
        _audit.log(
            query_id=query_id, user_id=user.user_id, question=body.question,
            selected_tables=[], generated_sql="", row_count=0,
            execution_time_ms=0, status="PIPELINE_ERROR", error_message=str(exc),
        )
        raise HTTPException(status_code=500, detail=str(exc))

    # Handle pipeline-level errors set in state
    if state.get("error"):
        _audit.log(
            query_id=query_id, user_id=user.user_id, question=body.question,
            selected_tables=[t.table_name for t in state.get("selected_tables", [])],
            generated_sql=state.get("sql_gen_result", {}).get("sql", "") if isinstance(state.get("sql_gen_result"), dict) else "",
            row_count=0, execution_time_ms=0,
            status="ERROR", error_message=state["error"],
        )
        raise HTTPException(status_code=400, detail=state["error"])

    if not state.get("validation_result") or not state["validation_result"].is_valid:
        err = state.get("validation_error", "SQL validation failed after retries")
        _audit.log(
            query_id=query_id, user_id=user.user_id, question=body.question,
            selected_tables=[t.table_name for t in state.get("selected_tables", [])],
            generated_sql=state["sql_gen_result"].sql if state.get("sql_gen_result") else "",
            row_count=0, execution_time_ms=0,
            status="VALIDATION_ERROR", error_message=err,
        )
        raise HTTPException(status_code=400, detail=err)

    exec_result = state["exec_result"]
    report = state["report"]
    tables = state.get("selected_tables", [])
    mappings = state.get("mapping_result")

    _audit.log(
        query_id=query_id, user_id=user.user_id, question=body.question,
        selected_tables=[t.table_name for t in tables],
        generated_sql=state["validation_result"].sql,
        row_count=exec_result.row_count,
        execution_time_ms=exec_result.execution_time_ms,
        status="SUCCESS",
    )

    value_outs = []
    if mappings:
        for mv in mappings.mappings:
            value_outs.append(MappedValueOut(
                original_phrase=mv.original_phrase,
                internal_code=mv.internal_code,
                table_name=mv.table_name,
                column_name=mv.column_name,
            ))

    return QueryResponse(
        query_id=query_id,
        question=body.question,
        selected_tables=[t.table_name for t in tables],
        value_mappings=value_outs,
        generated_sql=state["validation_result"].sql,
        validation_warnings=state["validation_result"].warnings,
        row_count=exec_result.row_count,
        execution_time_ms=exec_result.execution_time_ms,
        truncated=exec_result.truncated,
        report=report.full_report,
        markdown_table=report.markdown_table,
    )


@router.get(
    "/history",
    summary="Retrieve past queries for the authenticated user",
)
async def query_history(
    user: Annotated[UserContext, Depends(get_current_user)],
    page: int = 1,
    page_size: int = 20,
):
    total, records = _audit.list_logs(user_id=user.user_id, page=page, page_size=page_size)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "records": [
            {
                "query_id": r.query_id,
                "question": r.question,
                "status": r.status,
                "row_count": r.row_count,
                "created_at": r.created_at.isoformat(),
            }
            for r in records
        ],
    }
