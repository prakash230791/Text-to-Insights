"""
Module 3 — Value Mapper  (core/value_mapper.py)

Before SQL generation, scans the user question for known human labels
(from registry_values) and builds a hint block that is injected into
the LLM prompt — so the model generates syntactically correct SQL with
exact internal codes instead of plain-English values.

Examples
--------
    "active customers in Dallas"   →  status='A', region='DFW'
    "high priority tickets"        →  priority='P1'
    "dropped calls in Q3"          →  outcome_code='3'
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from registry.schema_db import SchemaDB, RegistryValue

logger = logging.getLogger(__name__)


@dataclass
class MappedValue:
    original_phrase: str   # as found in the question
    internal_code: str     # exact DB value
    table_name: str
    column_name: str
    human_label: str


@dataclass
class MappingResult:
    mappings: list[MappedValue] = field(default_factory=list)
    enriched_question: str = ""

    def as_hint_block(self) -> str:
        """SQL comment block injected into the LLM prompt."""
        if not self.mappings:
            return ""
        lines = ["-- Value alias hints (use these exact values in WHERE clauses):"]
        seen: set[tuple] = set()
        for m in self.mappings:
            key = (m.table_name, m.column_name, m.internal_code)
            if key in seen:
                continue
            seen.add(key)
            lines.append(
                f"--   '{m.original_phrase}' → "
                f"{m.table_name}.{m.column_name} = '{m.internal_code}'"
            )
        return "\n".join(lines)


class ValueMapper:
    """
    Usage:
        mapper = ValueMapper(schema_db)
        mapper.refresh()
        result = mapper.map("Show active customers in Dallas", table_names=["customer_accounts"])
    """

    def __init__(self, db: SchemaDB) -> None:
        self._db = db
        # human_label.lower() → MappedValue (longest phrase wins on collision)
        self._index: dict[str, MappedValue] = {}

    def refresh(self) -> None:
        """Reload all curated value mappings from the registry."""
        all_vals: list[RegistryValue] = self._db.get_all_values()
        self._index = {}
        for rv in all_vals:
            if rv.is_flagged_unknown:
                continue  # don't map uncurated values
            label = rv.human_label.lower().strip()
            if label:
                self._index[label] = MappedValue(
                    original_phrase=rv.human_label,
                    internal_code=rv.internal_code,
                    table_name=rv.table_name,
                    column_name=rv.column_name,
                    human_label=rv.human_label,
                )
        logger.info("ValueMapper: loaded %d label mappings", len(self._index))

    def map(
        self,
        question: str,
        table_names: Optional[list[str]] = None,
    ) -> MappingResult:
        """
        Scan the question for known human labels and return matched mappings.

        Args:
            question:    Raw user question.
            table_names: When set, restrict matches to these tables only
                         (recommended: pass the TableRetriever results).

        Returns:
            MappingResult with all found mappings and an enriched question string.
        """
        if not self._index:
            self.refresh()

        index = self._index
        if table_names:
            index = {k: v for k, v in index.items() if v.table_name in table_names}

        q_lower = question.lower()

        # Sort longest phrases first so multi-word labels win over sub-words
        candidates = sorted(index.keys(), key=len, reverse=True)

        found: list[MappedValue] = []
        consumed: list[tuple[int, int]] = []

        for label in candidates:
            pattern = r"\b" + re.escape(label) + r"\b"
            for m in re.finditer(pattern, q_lower):
                s, e = m.start(), m.end()
                if any(cs <= s < ce or cs < e <= ce for cs, ce in consumed):
                    continue
                mv = MappedValue(
                    original_phrase=question[s:e],
                    internal_code=index[label].internal_code,
                    table_name=index[label].table_name,
                    column_name=index[label].column_name,
                    human_label=index[label].human_label,
                )
                found.append(mv)
                consumed.append((s, e))

        enriched = question
        for mv in sorted(found, key=lambda x: len(x.original_phrase), reverse=True):
            enriched = re.sub(
                r"\b" + re.escape(mv.original_phrase.lower()) + r"\b",
                f"{mv.original_phrase}[={mv.internal_code}]",
                enriched,
                flags=re.IGNORECASE,
            )

        if found:
            logger.debug(
                "ValueMapper: %d matches — %s",
                len(found),
                [(m.original_phrase, m.internal_code) for m in found],
            )

        return MappingResult(mappings=found, enriched_question=enriched)
