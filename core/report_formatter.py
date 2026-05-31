"""
Module 7 — Report Formatter  (core/report_formatter.py)

Takes raw SQL result rows and converts them into a human-readable report
via a second Ollama call.  The report contains:
  • A narrative summary paragraph
  • A Markdown table of the data
  • 2-3 key business insights

Uses a separate model from the SQL Generator so each can be tuned independently.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import ollama

from config.settings import get_settings
from core.sql_executor import ExecutionResult

logger = logging.getLogger(__name__)

_MAX_ROWS_IN_PROMPT = 50   # cap rows sent to LLM to stay within context window

_REPORT_PROMPT = """\
You are a senior telecom business analyst. A user asked the following question and the database returned the data below.

### User Question
{question}

### Query Results ({row_count} rows{truncated_note})
{data_table}

### Instructions
Write a concise business report with exactly three sections:

**Summary**: One paragraph explaining what the data shows in plain English.

**Key Insights**:
- Insight 1 (specific number or trend from the data)
- Insight 2
- Insight 3

**Recommended Actions**: One or two sentences suggesting what the business should do based on these results.

Be factual. Use exact numbers from the data. Do not invent data not present in the results.
"""


@dataclass
class ReportResult:
    narrative: str
    markdown_table: str
    full_report: str
    model: str
    row_count: int


class ReportFormatter:
    """
    Usage:
        formatter = ReportFormatter()
        report = formatter.format(
            question="How many active customers are in DFW?",
            exec_result=execution_result,
        )
        print(report.full_report)
    """

    def __init__(self) -> None:
        cfg = get_settings()
        self._model = cfg.ollama_report_model
        self._timeout = cfg.ollama_timeout_seconds
        self._client = ollama.Client(host=cfg.ollama_base_url)

    def format(self, question: str, exec_result: ExecutionResult) -> ReportResult:
        """
        Convert raw SQL results into a narrative report.

        Args:
            question:    The original user question.
            exec_result: The ExecutionResult from SQLExecutor.

        Returns:
            ReportResult with narrative, markdown table, and full report text.
        """
        md_table = self._build_markdown_table(exec_result)
        truncated_note = f", truncated to {_MAX_ROWS_IN_PROMPT}" if exec_result.truncated else ""

        rows_for_prompt = exec_result.rows[:_MAX_ROWS_IN_PROMPT]
        data_table = self._build_prompt_table(exec_result.columns, rows_for_prompt)

        prompt = _REPORT_PROMPT.format(
            question=question,
            row_count=exec_result.row_count,
            truncated_note=truncated_note,
            data_table=data_table,
        )

        logger.debug(
            "ReportFormatter: calling model=%s, rows=%d", self._model, exec_result.row_count
        )

        try:
            response = self._client.chat(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.3, "num_predict": 1024},
            )
            narrative = response["message"]["content"].strip()
        except Exception as exc:
            logger.error("ReportFormatter: Ollama call failed — %s", exc)
            # Graceful degradation: return structured table even without narrative
            narrative = f"Report generation failed: {exc}"

        full_report = f"{narrative}\n\n---\n\n{md_table}"

        return ReportResult(
            narrative=narrative,
            markdown_table=md_table,
            full_report=full_report,
            model=self._model,
            row_count=exec_result.row_count,
        )

    @staticmethod
    def _build_markdown_table(exec_result: ExecutionResult) -> str:
        if not exec_result.rows:
            return "_No results returned._"
        cols = exec_result.columns
        header = "| " + " | ".join(cols) + " |"
        sep = "| " + " | ".join(["---"] * len(cols)) + " |"
        data_rows = []
        for row in exec_result.rows:
            cells = [str(row.get(c, "")) for c in cols]
            data_rows.append("| " + " | ".join(cells) + " |")
        return "\n".join([header, sep] + data_rows)

    @staticmethod
    def _build_prompt_table(columns: list[str], rows: list[dict]) -> str:
        """Compact text table for the LLM prompt (not Markdown)."""
        if not rows:
            return "(empty result set)"
        lines = ["\t".join(columns)]
        for row in rows:
            lines.append("\t".join(str(row.get(c, "")) for c in columns))
        return "\n".join(lines)
