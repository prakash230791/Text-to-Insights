"""
Module 2 — Table Retriever  (core/table_retriever.py)

Scores all registered tables against the user question using the scoring
signals defined in the design spec:

  +10  Table name contains a query term
  +5   Table keyword list matches a query term
  +3   Column name appears in the query
  +4   Value human_label matches a query term

Returns the top-2/3 tables as fully populated TableMeta objects.

Phase-2 upgrade path: replace keyword scoring with local sentence-transformer
embeddings by swapping in a vector index inside retrieve().
"""
from __future__ import annotations

import logging
import re
import string
from typing import Optional

from registry.schema_db import SchemaDB, TableMeta

logger = logging.getLogger(__name__)

# Common English stop-words to strip before scoring
_STOPWORDS = frozenset(
    "a an the is are was were be been being have has had do does did "
    "will would could should may might shall can for of in on at to "
    "by with from into through about above and or but not nor so yet "
    "it its this that these those i you he she we they what which who "
    "how when where why me him her us them my your his our their "
    "show list give find what get top all".split()
)


def _tokenize(text: str) -> set[str]:
    text = text.lower().translate(str.maketrans("", "", string.punctuation))
    return {t for t in text.split() if t and t not in _STOPWORDS}


class TableRetriever:
    """
    Usage:
        retriever = TableRetriever(schema_db)
        retriever.refresh()
        tables = retriever.retrieve("active customers in Dallas", top_k=3)
    """

    def __init__(self, db: SchemaDB, top_k: int = 3) -> None:
        self._db = db
        self._top_k = top_k
        self._table_cache: list[TableMeta] = []

    def refresh(self) -> None:
        """Reload all table metadata (including columns and values) from the registry."""
        table_stubs = self._db.list_tables()
        self._table_cache = []
        for stub in table_stubs:
            full = self._db.get_table_meta(stub.table_name)
            if full:
                self._table_cache.append(full)
        logger.info("TableRetriever: indexed %d tables", len(self._table_cache))

    def retrieve(self, question: str, top_k: Optional[int] = None) -> list[TableMeta]:
        """
        Score and return the top-k most relevant tables.

        Scoring (per design spec):
          +10  Table name token found in query
          +5   Table keyword found in query
          +3   Column name found in query
          +4   Value human_label found in query

        Args:
            question: Free-text business question.
            top_k:    Override the instance default (default 3).

        Returns:
            Ordered list of TableMeta (best match first), with full columns + values.
        """
        if not self._table_cache:
            self.refresh()

        k = top_k or self._top_k
        query_tokens = _tokenize(question)

        scored: list[tuple[float, TableMeta]] = []

        for tbl in self._table_cache:
            score = self._score_table(tbl, query_tokens, question.lower())
            scored.append((score, tbl))

        scored.sort(key=lambda x: x[0], reverse=True)

        selected = [t for s, t in scored[:k] if s > 0]

        if not selected and scored:
            # Fallback: return top-1 even if score is 0 to avoid empty pipeline
            selected = [scored[0][1]]

        logger.debug(
            "TableRetriever: question=%r → top-%d: %s (scores: %s)",
            question[:60],
            k,
            [t.table_name for t in selected],
            [round(s, 1) for s, _ in scored[:k]],
        )
        return selected

    def retrieve_with_meta(self, question: str, top_k: Optional[int] = None) -> list[TableMeta]:
        """
        Same as retrieve() — the internal cache already stores full column+value metadata.
        Kept as a named alias for caller clarity.
        """
        return self.retrieve(question, top_k)

    def _score_table(
        self, tbl: TableMeta, query_tokens: set[str], question_lower: str
    ) -> float:
        score = 0.0

        # +10: table name tokens in query
        name_tokens = _tokenize(tbl.table_name.replace("_", " "))
        for token in name_tokens:
            if token in query_tokens:
                score += 10

        # +5: keyword list tokens in query
        for kw in _tokenize(tbl.keywords):
            if kw in query_tokens:
                score += 5

        # +3: column names in query
        for col in tbl.columns:
            col_tokens = _tokenize(col.column_name.replace("_", " "))
            for token in col_tokens:
                if token in query_tokens:
                    score += 3

        # +4: value human_labels in query (check phrase match, not just tokens)
        for val in tbl.values:
            label_lower = val.human_label.lower()
            if label_lower in question_lower:
                score += 4

        return score
