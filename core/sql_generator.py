"""
Module 4 — SQL Generator  (core/sql_generator.py)

Calls a locally hosted SLM via Ollama to convert the enriched prompt
(schema DDL + value alias hints + user question) into a valid SQL query.

Recommended models (set OLLAMA_SQL_MODEL in .env):
  sqlcoder   — highest Text-to-SQL accuracy, needs 8GB+ VRAM
  mistral    — best general quality + SQL, 8GB+
  phi3       — fastest, runs CPU-only, 4GB minimum

The prompt template follows the SQLCoder / DeFog convention which gives the
best SQL generation accuracy with smaller models.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import ollama

from config.settings import get_settings

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
### Task
Generate a SQL SELECT query that answers the question below.
Use only the tables and columns defined in the schema.
Apply every value alias hint exactly as specified.
Always add LIMIT {row_limit} unless the query already has a more restrictive LIMIT.
Output only the SQL query — no explanations, no markdown fences.

### Database Schema
{ddl_block}

### Value Alias Hints
{hint_block}

### Question
{question}

### SQL Query
"""

_SQL_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


@dataclass
class SQLGenResult:
    sql: str
    raw_response: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class SQLGenerator:
    """
    Usage:
        gen = SQLGenerator()
        result = gen.generate(
            question="How many active customers are in DFW?",
            ddl_block="CREATE TABLE customer_accounts (...);",
            hint_block="-- 'active' → customer_accounts.status = 'A'",
        )
        print(result.sql)
    """

    def __init__(self) -> None:
        cfg = get_settings()
        self._model = cfg.ollama_sql_model
        self._timeout = cfg.ollama_timeout_seconds
        self._row_limit = cfg.query_row_limit
        self._client = ollama.Client(host=cfg.ollama_base_url)

    def generate(
        self,
        question: str,
        ddl_block: str,
        hint_block: str = "",
    ) -> SQLGenResult:
        """
        Generate SQL from a natural-language question.

        Args:
            question:   The user's business question.
            ddl_block:  CREATE TABLE statements for relevant tables.
            hint_block: Value alias comments (from ValueMapper).

        Returns:
            SQLGenResult with the cleaned SQL string.

        Raises:
            RuntimeError: If Ollama returns an empty response.
        """
        prompt = _PROMPT_TEMPLATE.format(
            row_limit=self._row_limit,
            ddl_block=ddl_block or "(no schema provided)",
            hint_block=hint_block or "(no value hints)",
            question=question,
        )

        logger.debug("SQLGenerator: calling model=%s, prompt_len=%d", self._model, len(prompt))

        try:
            response = self._client.chat(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0, "num_predict": 512},
            )
        except Exception as exc:
            logger.error("SQLGenerator: Ollama call failed — %s", exc)
            raise RuntimeError(f"SQL generation failed: {exc}") from exc

        raw = response["message"]["content"].strip()
        sql = self._extract_sql(raw)

        if not sql:
            raise RuntimeError(f"SQL Generator returned empty response. Raw: {raw[:200]}")

        usage = response.get("usage", {})
        result = SQLGenResult(
            sql=sql,
            raw_response=raw,
            model=self._model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )
        logger.info(
            "SQLGenerator: generated SQL (%d chars) via %s", len(sql), self._model
        )
        logger.debug("SQLGenerator: SQL = %s", sql[:300])
        return result

    @staticmethod
    def _extract_sql(raw: str) -> str:
        """Strip markdown fences and leading/trailing whitespace."""
        fence_match = _SQL_FENCE_RE.search(raw)
        if fence_match:
            return fence_match.group(1).strip()
        # No fence — return as-is after stripping common prefixes
        sql = raw.strip()
        for prefix in ("sql:", "SQL:", "Answer:", "Query:"):
            if sql.lower().startswith(prefix.lower()):
                sql = sql[len(prefix):].strip()
        return sql
