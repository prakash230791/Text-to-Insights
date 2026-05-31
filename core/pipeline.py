"""
LangGraph Pipeline Orchestration  (core/pipeline.py)

Wires all 7 processing modules into a directed graph:

  table_retrieval → value_mapper → sql_generator
      → sql_validator → [retry loop] → sql_executor → report_formatter

State flows through a TypedDict; each node mutates the relevant fields.
The validator edge re-routes to sql_generator on first failure (up to 2 retries).
"""
from __future__ import annotations

import logging
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from config.settings import get_settings
from core.report_formatter import ReportFormatter, ReportResult
from core.sql_executor import ExecutionResult, SQLExecutor
from core.sql_generator import SQLGenResult, SQLGenerator
from core.sql_validator import SQLValidator, ValidationResult
from core.table_retriever import TableRetriever
from core.value_mapper import MappingResult, ValueMapper
from registry.schema_db import SchemaDB, TableMeta

logger = logging.getLogger(__name__)

MAX_RETRIES = 2


# ── Pipeline state ─────────────────────────────────────────────────────────────

class PipelineState(TypedDict, total=False):
    question: str
    # Module 2
    selected_tables: list[TableMeta]
    # Module 3
    mapping_result: MappingResult
    # Module 4
    sql_gen_result: SQLGenResult
    ddl_block: str
    # Module 5
    validation_result: ValidationResult
    retry_count: int
    validation_error: str
    # Module 6
    exec_result: ExecutionResult
    # Module 7
    report: ReportResult
    # Terminal error
    error: str


# ── Node functions ─────────────────────────────────────────────────────────────

def _node_table_retrieval(state: PipelineState, retriever: TableRetriever) -> dict:
    question = state["question"]
    tables = retriever.retrieve_with_meta(question, top_k=3)
    logger.info("Pipeline[table_retrieval]: %s", [t.table_name for t in tables])
    return {"selected_tables": tables}


def _node_value_mapper(state: PipelineState, mapper: ValueMapper, db: SchemaDB) -> dict:
    question = state["question"]
    table_names = [t.table_name for t in state.get("selected_tables", [])]
    mapper.refresh()
    result = mapper.map(question, table_names=table_names)
    # Also build the DDL block for selected tables
    ddl = db.build_ddl_block(table_names)
    return {"mapping_result": result, "ddl_block": ddl}


def _node_sql_generator(state: PipelineState, generator: SQLGenerator) -> dict:
    question = state["question"]
    ddl = state.get("ddl_block", "")
    hint = ""
    if state.get("mapping_result"):
        hint = state["mapping_result"].as_hint_block()
    # On retry, append the previous error as guidance
    retry_count = state.get("retry_count", 0)
    if retry_count > 0 and state.get("validation_error"):
        question = (
            f"{question}\n\n"
            f"[Previous attempt failed validation: {state['validation_error']}. "
            f"Please fix the SQL.]"
        )
    try:
        result = generator.generate(question=question, ddl_block=ddl, hint_block=hint)
        return {"sql_gen_result": result}
    except Exception as exc:
        return {"error": str(exc)}


def _node_sql_validator(state: PipelineState, validator: SQLValidator) -> dict:
    if state.get("error"):
        return {}
    sql = state["sql_gen_result"].sql
    result = validator.validate(sql)
    return {
        "validation_result": result,
        "validation_error": result.first_error() if not result.is_valid else "",
    }


def _node_sql_executor(state: PipelineState, executor: SQLExecutor) -> dict:
    if state.get("error"):
        return {}
    sql = state["validation_result"].sql
    try:
        result = executor.execute(sql)
        return {"exec_result": result}
    except Exception as exc:
        return {"error": str(exc)}


def _node_report_formatter(state: PipelineState, formatter: ReportFormatter) -> dict:
    if state.get("error"):
        return {}
    report = formatter.format(
        question=state["question"],
        exec_result=state["exec_result"],
    )
    return {"report": report}


# ── Routing ────────────────────────────────────────────────────────────────────

def _route_after_validation(state: PipelineState) -> str:
    if state.get("error"):
        return END
    result: ValidationResult = state["validation_result"]
    retry_count = state.get("retry_count", 0)
    if result.is_valid:
        return "sql_executor"
    if retry_count < MAX_RETRIES:
        logger.warning(
            "Pipeline: validation failed (retry %d/%d) — %s",
            retry_count + 1,
            MAX_RETRIES,
            result.first_error(),
        )
        return "sql_generator"   # re-generate with error feedback
    # Exhausted retries
    logger.error("Pipeline: validation failed after %d retries", MAX_RETRIES)
    return END


def _increment_retry(state: PipelineState) -> dict:
    return {"retry_count": state.get("retry_count", 0) + 1}


# ── Graph builder ──────────────────────────────────────────────────────────────

def build_pipeline(
    db: SchemaDB,
    retriever: TableRetriever,
    mapper: ValueMapper,
    generator: SQLGenerator,
    validator: SQLValidator,
    executor: SQLExecutor,
    formatter: ReportFormatter,
) -> Any:
    """
    Construct and compile the LangGraph pipeline.

    Returns:
        A compiled LangGraph app callable with .invoke({"question": "..."}).
    """
    graph = StateGraph(PipelineState)

    graph.add_node(
        "table_retrieval",
        lambda s: _node_table_retrieval(s, retriever),
    )
    graph.add_node(
        "value_mapper",
        lambda s: _node_value_mapper(s, mapper, db),
    )
    graph.add_node(
        "sql_generator",
        lambda s: (
            _increment_retry(s) | _node_sql_generator(s, generator)
            if s.get("retry_count", 0) > 0
            else _node_sql_generator(s, generator)
        ),
    )
    graph.add_node("sql_validator", lambda s: _node_sql_validator(s, validator))
    graph.add_node("sql_executor", lambda s: _node_sql_executor(s, executor))
    graph.add_node("report_formatter", lambda s: _node_report_formatter(s, formatter))

    graph.set_entry_point("table_retrieval")
    graph.add_edge("table_retrieval", "value_mapper")
    graph.add_edge("value_mapper", "sql_generator")
    graph.add_edge("sql_generator", "sql_validator")
    graph.add_conditional_edges(
        "sql_validator",
        _route_after_validation,
        {"sql_executor": "sql_executor", "sql_generator": "sql_generator", END: END},
    )
    graph.add_edge("sql_executor", "report_formatter")
    graph.add_edge("report_formatter", END)

    return graph.compile()


# ── Convenience factory ────────────────────────────────────────────────────────

def create_pipeline() -> Any:
    """Create a pipeline with all default dependencies from settings."""
    cfg = get_settings()
    db = SchemaDB(cfg.registry_db_url)
    db.init_db()

    retriever = TableRetriever(db)
    retriever.refresh()

    mapper = ValueMapper(db)
    mapper.refresh()

    generator = SQLGenerator()
    validator = SQLValidator()
    executor = SQLExecutor()
    formatter = ReportFormatter()

    return build_pipeline(db, retriever, mapper, generator, validator, executor, formatter)
