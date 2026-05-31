"""
Tests for Module 2 — Table Retriever

Verifies the scoring signals defined in the design spec:
  +10  Table name contains query term
  +5   Table keyword matches query term
  +3   Column name in query
  +4   Value human_label in query
"""
import pytest

from core.table_retriever import TableRetriever, _tokenize


# ── Unit tests for tokenizer ───────────────────────────────────────────────────

class TestTokenize:
    def test_removes_stopwords(self):
        tokens = _tokenize("Show me all active customers in the region")
        assert "show" not in tokens
        assert "me" not in tokens
        assert "all" not in tokens
        assert "in" not in tokens
        assert "the" not in tokens

    def test_keeps_business_terms(self):
        tokens = _tokenize("active customers region DFW priority tickets")
        assert "active" in tokens
        assert "customers" in tokens
        assert "region" in tokens
        assert "dfW".lower() in tokens

    def test_lowercases(self):
        tokens = _tokenize("DALLAS DFW Enterprise")
        assert "dallas" in tokens
        assert "dfW".lower() in tokens

    def test_strips_punctuation(self):
        tokens = _tokenize("customers? tickets! priority.")
        assert "customers" in tokens
        assert "tickets" in tokens
        assert "priority" in tokens


# ── Integration tests for TableRetriever ──────────────────────────────────────

class TestTableRetriever:
    @pytest.fixture
    def retriever(self, registry_db):
        r = TableRetriever(registry_db, top_k=3)
        r.refresh()
        return r

    def test_customer_question_retrieves_customer_table(self, retriever):
        tables = retriever.retrieve("How many active customers are in DFW?")
        names = [t.table_name for t in tables]
        assert "customer_accounts" in names

    def test_ticket_question_retrieves_ticket_table(self, retriever):
        tables = retriever.retrieve("Show me open critical priority tickets in New York")
        names = [t.table_name for t in tables]
        assert "trouble_tickets" in names

    def test_dropped_call_retrieves_call_logs(self, retriever):
        tables = retriever.retrieve("How many dropped calls happened last week?")
        names = [t.table_name for t in tables]
        assert "call_logs" in names

    def test_returns_at_most_top_k(self, retriever):
        tables = retriever.retrieve("customers in Dallas", top_k=2)
        assert len(tables) <= 2

    def test_never_returns_empty_on_valid_question(self, retriever):
        tables = retriever.retrieve("show revenue data")
        assert len(tables) >= 1

    def test_table_name_token_match_scores_high(self, retriever):
        """'customer_accounts' should be top result for a customer question."""
        tables = retriever.retrieve("customer status in DFW region", top_k=1)
        assert tables[0].table_name == "customer_accounts"

    def test_retrieve_with_meta_includes_columns(self, retriever):
        tables = retriever.retrieve_with_meta("active customers")
        assert len(tables) > 0
        for tbl in tables:
            assert tbl.columns is not None

    def test_value_label_match_scores_correctly(self, retriever):
        """'Dallas' is a human_label for DFW — should boost customer_accounts score."""
        tables = retriever.retrieve("How many customers are in Dallas?")
        names = [t.table_name for t in tables]
        assert "customer_accounts" in names

    def test_refresh_reloads_index(self, retriever, registry_db):
        """Adding a new table and refreshing should make it retrievable."""
        registry_db.upsert_table(
            "revenue_metrics",
            description="Aggregated monthly revenue by market region",
            keywords="revenue arpu monthly billing income",
            domain="billing",
        )
        registry_db.upsert_column("revenue_metrics", "total_revenue", "REAL",
                                   "Total revenue", is_metric=True)
        retriever.refresh()
        tables = retriever.retrieve("What is the total revenue by region?")
        names = [t.table_name for t in tables]
        assert "revenue_metrics" in names
