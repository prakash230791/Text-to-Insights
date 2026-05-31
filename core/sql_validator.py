"""
Module 5 — SQL Validator  (core/sql_validator.py)

Rule-based safety layer that runs BEFORE executing any generated SQL.
Uses sqlglot for AST-level parsing — no regex hacks.

Validation Rules (from design spec):
  Rule 1: Read-only — no INSERT / UPDATE / DELETE / DROP / CREATE / ALTER / TRUNCATE
  Rule 2: Table whitelist — only tables registered in the Schema Registry
  Rule 3: Row cap — LIMIT clause must exist and be ≤ max_rows
  Rule 4: No subquery depth beyond 3 levels
  Rule 5: No UNION / INTERSECT / EXCEPT without explicit approval flag
  Rule 6: (Enforced at executor level) execution time limit

Returns a ValidationResult with pass/fail and all failure reasons.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import sqlglot
import sqlglot.expressions as exp

from config.settings import get_settings
from config.table_whitelist import ALLOWED_TABLES

logger = logging.getLogger(__name__)

_WRITE_STATEMENT_TYPES = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create,
    exp.Alter, exp.TruncateTable,
)

_SET_OP_TYPES = (exp.Union, exp.Intersect, exp.Except)


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # SQL rewritten by the validator (e.g. LIMIT injected)
    sql: str = ""

    def first_error(self) -> str:
        return self.errors[0] if self.errors else ""


class SQLValidator:
    """
    Usage:
        validator = SQLValidator()
        result = validator.validate("SELECT * FROM customer_accounts LIMIT 100")
        if not result.is_valid:
            print(result.errors)
    """

    def __init__(
        self,
        allowed_tables: Optional[frozenset[str]] = None,
        max_rows: Optional[int] = None,
        max_subquery_depth: int = 3,
        allow_set_operations: bool = False,
    ) -> None:
        cfg = get_settings()
        self._allowed = allowed_tables or ALLOWED_TABLES
        self._max_rows = max_rows or cfg.query_row_limit
        self._max_depth = max_subquery_depth
        self._allow_set_ops = allow_set_operations

    def validate(self, sql: str) -> ValidationResult:
        """
        Parse and validate a SQL string.

        Returns:
            ValidationResult — check .is_valid and .sql (possibly rewritten).
        """
        sql = sql.strip().rstrip(";")
        errors: list[str] = []
        warnings: list[str] = []

        # Parse
        try:
            statements = sqlglot.parse(sql, error_level=sqlglot.ErrorLevel.RAISE)
        except sqlglot.errors.ParseError as exc:
            return ValidationResult(
                is_valid=False,
                errors=[f"SQL parse error: {exc}"],
                sql=sql,
            )

        if not statements or statements[0] is None:
            return ValidationResult(is_valid=False, errors=["Empty SQL statement"], sql=sql)

        stmt = statements[0]

        # Rule 1: Read-only enforcement
        for node in stmt.walk():
            if isinstance(node, _WRITE_STATEMENT_TYPES):
                errors.append(
                    f"Rule 1 violation: write operation not permitted "
                    f"({type(node).__name__}). Only SELECT is allowed."
                )

        # Allow set-operation types (Union/Intersect/Except) as top-level — Rule 5 handles approval
        _read_types = (exp.Select, exp.Union, exp.Intersect, exp.Except)
        if not isinstance(stmt, _read_types):
            errors.append("Rule 1 violation: only SELECT statements are permitted.")

        # Rule 5: Set operations (UNION / INTERSECT / EXCEPT)
        if not self._allow_set_ops:
            for node in stmt.walk():
                if isinstance(node, _SET_OP_TYPES):
                    errors.append(
                        f"Rule 5 violation: {type(node).__name__} not permitted "
                        f"without explicit approval."
                    )

        # Rule 2: Table whitelist
        for table_node in stmt.find_all(exp.Table):
            tname = table_node.name.lower() if table_node.name else ""
            if tname and tname not in self._allowed:
                errors.append(
                    f"Rule 2 violation: table '{tname}' is not in the approved table whitelist."
                )

        # Rule 4: Subquery depth
        depth = self._max_subquery_depth(stmt)
        if depth > self._max_depth:
            errors.append(
                f"Rule 4 violation: subquery nesting depth {depth} exceeds maximum {self._max_depth}."
            )

        # Rule 3: Row cap — inject LIMIT if missing, error if over cap
        sql_out, limit_error = self._enforce_limit(stmt, sql)
        if limit_error:
            errors.append(limit_error)
        elif sql_out != sql:
            warnings.append(f"LIMIT {self._max_rows} automatically added.")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            sql=sql_out,
        )

    def _enforce_limit(self, stmt: exp.Expression, original_sql: str) -> tuple[str, str]:
        """Returns (rewritten_sql, error_message_or_empty)."""
        limit_node = stmt.find(exp.Limit)
        if limit_node is None:
            # Inject LIMIT
            new_sql = f"{original_sql} LIMIT {self._max_rows}"
            return new_sql, ""

        # Limit exists — check its value
        limit_expr = limit_node.expression
        try:
            limit_val = int(limit_expr.name)
        except (TypeError, ValueError, AttributeError):
            return original_sql, ""  # dynamic limit, let executor handle it

        if limit_val > self._max_rows:
            return original_sql, (
                f"Rule 3 violation: LIMIT {limit_val} exceeds maximum allowed rows "
                f"({self._max_rows}). Reduce the LIMIT clause."
            )
        return original_sql, ""

    @staticmethod
    def _max_subquery_depth(node: exp.Expression, current: int = 0) -> int:
        """Recursively compute the maximum subquery nesting depth."""
        max_d = current
        for child in node.walk():
            if child is node:
                continue
            if isinstance(child, exp.Subquery):
                d = SQLValidator._max_subquery_depth(child, current + 1)
                max_d = max(max_d, d)
        return max_d
