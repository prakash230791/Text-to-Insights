"""
Tests for Module 5 — SQL Validator

Verifies all 6 validation rules defined in the design spec:
  Rule 1: Read-only enforcement
  Rule 2: Table whitelist
  Rule 3: Row cap (LIMIT enforcement)
  Rule 4: Subquery depth limit
  Rule 5: No SET operations without approval
  Rule 6: (executor-level, not tested here)
"""
import pytest

from core.sql_validator import SQLValidator


@pytest.fixture
def validator():
    return SQLValidator(
        allowed_tables=frozenset({"customer_accounts", "trouble_tickets", "call_logs", "revenue_metrics"}),
        max_rows=1000,
        max_subquery_depth=3,
        allow_set_operations=False,
    )


# ── Rule 1: Read-only ──────────────────────────────────────────────────────────

class TestRule1ReadOnly:
    def test_select_is_valid(self, validator):
        r = validator.validate("SELECT * FROM customer_accounts LIMIT 100")
        assert r.is_valid

    def test_insert_is_rejected(self, validator):
        r = validator.validate("INSERT INTO customer_accounts (status) VALUES ('X')")
        assert not r.is_valid
        assert any("Rule 1" in e for e in r.errors)

    def test_update_is_rejected(self, validator):
        r = validator.validate("UPDATE customer_accounts SET status='X' WHERE 1=1")
        assert not r.is_valid
        assert any("Rule 1" in e for e in r.errors)

    def test_delete_is_rejected(self, validator):
        r = validator.validate("DELETE FROM customer_accounts WHERE status='I'")
        assert not r.is_valid
        assert any("Rule 1" in e for e in r.errors)

    def test_drop_is_rejected(self, validator):
        r = validator.validate("DROP TABLE customer_accounts")
        assert not r.is_valid
        assert any("Rule 1" in e for e in r.errors)


# ── Rule 2: Table whitelist ────────────────────────────────────────────────────

class TestRule2Whitelist:
    def test_whitelisted_table_passes(self, validator):
        r = validator.validate("SELECT COUNT(*) FROM customer_accounts LIMIT 10")
        assert r.is_valid

    def test_non_whitelisted_table_rejected(self, validator):
        r = validator.validate("SELECT * FROM secret_table LIMIT 10")
        assert not r.is_valid
        assert any("Rule 2" in e for e in r.errors)

    def test_multiple_whitelisted_tables_passes(self, validator):
        r = validator.validate("""
            SELECT ca.status, COUNT(*) as cnt
            FROM customer_accounts ca
            JOIN trouble_tickets tt ON ca.customer_id = tt.customer_id
            GROUP BY ca.status
            LIMIT 100
        """)
        assert r.is_valid

    def test_mixed_tables_rejected(self, validator):
        r = validator.validate("""
            SELECT * FROM customer_accounts
            JOIN unauthorized_table ON 1=1
            LIMIT 10
        """)
        assert not r.is_valid
        assert any("Rule 2" in e for e in r.errors)


# ── Rule 3: Row cap ────────────────────────────────────────────────────────────

class TestRule3RowCap:
    def test_missing_limit_gets_injected(self, validator):
        r = validator.validate("SELECT * FROM customer_accounts")
        assert r.is_valid
        assert "LIMIT 1000" in r.sql
        assert any("automatically added" in w for w in r.warnings)

    def test_limit_within_cap_passes(self, validator):
        r = validator.validate("SELECT * FROM customer_accounts LIMIT 500")
        assert r.is_valid
        assert not r.errors

    def test_limit_at_cap_passes(self, validator):
        r = validator.validate("SELECT * FROM customer_accounts LIMIT 1000")
        assert r.is_valid

    def test_limit_exceeding_cap_rejected(self, validator):
        r = validator.validate("SELECT * FROM customer_accounts LIMIT 50000")
        assert not r.is_valid
        assert any("Rule 3" in e for e in r.errors)


# ── Rule 4: Subquery depth ─────────────────────────────────────────────────────

class TestRule4SubqueryDepth:
    def test_no_subquery_passes(self, validator):
        r = validator.validate("SELECT COUNT(*) FROM customer_accounts LIMIT 10")
        assert r.is_valid

    def test_one_level_subquery_passes(self, validator):
        r = validator.validate("""
            SELECT * FROM (
                SELECT status, COUNT(*) as cnt
                FROM customer_accounts GROUP BY status
            ) sub
            LIMIT 10
        """)
        assert r.is_valid

    def test_deeply_nested_subquery_rejected(self, validator):
        r = validator.validate("""
            SELECT * FROM (
                SELECT * FROM (
                    SELECT * FROM (
                        SELECT * FROM (
                            SELECT * FROM customer_accounts LIMIT 10
                        ) d4
                    ) d3
                ) d2
            ) d1
            LIMIT 10
        """)
        assert not r.is_valid
        assert any("Rule 4" in e for e in r.errors)


# ── Rule 5: Set operations ─────────────────────────────────────────────────────

class TestRule5SetOperations:
    def test_union_rejected_by_default(self, validator):
        r = validator.validate("""
            SELECT customer_id FROM customer_accounts WHERE status='A'
            UNION
            SELECT customer_id FROM customer_accounts WHERE status='I'
            LIMIT 100
        """)
        assert not r.is_valid
        assert any("Rule 5" in e for e in r.errors)

    def test_union_allowed_with_flag(self):
        v = SQLValidator(
            allowed_tables=frozenset({"customer_accounts"}),
            max_rows=1000,
            allow_set_operations=True,
        )
        r = v.validate("""
            SELECT customer_id FROM customer_accounts WHERE status='A'
            UNION
            SELECT customer_id FROM customer_accounts WHERE status='I'
            LIMIT 100
        """)
        assert r.is_valid


# ── Edge cases ─────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_sql_rejected(self, validator):
        r = validator.validate("")
        assert not r.is_valid

    def test_invalid_sql_rejected(self, validator):
        r = validator.validate("THIS IS NOT SQL AT ALL @@##")
        assert not r.is_valid

    def test_aggregate_query_passes(self, validator):
        r = validator.validate("""
            SELECT region, COUNT(*) as total, AVG(mrr) as avg_mrr
            FROM customer_accounts
            WHERE status = 'A'
            GROUP BY region
            ORDER BY total DESC
            LIMIT 50
        """)
        assert r.is_valid

    def test_sql_with_semicolon_handled(self, validator):
        r = validator.validate("SELECT COUNT(*) FROM customer_accounts LIMIT 10;")
        assert r.is_valid

    def test_multiple_errors_collected(self, validator):
        r = validator.validate(
            "UPDATE secret_table SET col=1"
        )
        assert not r.is_valid
        assert len(r.errors) >= 2  # Rule 1 + Rule 2
