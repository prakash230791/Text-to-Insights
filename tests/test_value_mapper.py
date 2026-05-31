"""
Tests for Module 3 — Value Mapper

Verifies that human labels are correctly translated to internal DB codes,
including multi-word phrases, case insensitivity, and scoped table filtering.
"""
import pytest

from core.value_mapper import ValueMapper, MappingResult


class TestValueMapper:
    @pytest.fixture
    def mapper(self, registry_db):
        m = ValueMapper(registry_db)
        m.refresh()
        return m

    # ── Basic matching ─────────────────────────────────────────────────────────

    def test_maps_active_to_A(self, mapper):
        result = mapper.map("Show active customers in DFW")
        codes = {m.internal_code for m in result.mappings}
        assert "A" in codes

    def test_maps_dallas_to_DFW(self, mapper):
        result = mapper.map("How many customers are in Dallas?")
        codes = {m.internal_code for m in result.mappings}
        assert "DFW" in codes

    def test_maps_critical_to_P1(self, mapper):
        result = mapper.map("List all critical priority tickets")
        codes = {m.internal_code for m in result.mappings}
        assert "P1" in codes

    def test_maps_dropped_call_to_3(self, mapper):
        # human_label is "Dropped Call" (singular) — must use exact phrase
        result = mapper.map("How many dropped call records exist in DFW?")
        codes = {m.internal_code for m in result.mappings}
        assert "3" in codes

    def test_maps_enterprise_to_ENT(self, mapper):
        result = mapper.map("Show Enterprise segment customers")
        codes = {m.internal_code for m in result.mappings}
        assert "ENT" in codes

    # ── Case insensitivity ─────────────────────────────────────────────────────

    def test_case_insensitive_match(self, mapper):
        for variant in ["ACTIVE", "Active", "active", "aCtIvE"]:
            result = mapper.map(f"{variant} customers")
            codes = {m.internal_code for m in result.mappings}
            assert "A" in codes, f"Failed for variant: {variant}"

    # ── Multi-word phrase ──────────────────────────────────────────────────────

    def test_multiword_phrase_small_business(self, mapper):
        result = mapper.map("revenue from Small Business customers")
        codes = {m.internal_code for m in result.mappings}
        assert "SMB" in codes

    # ── Table scoping ──────────────────────────────────────────────────────────

    def test_scope_to_table_restricts_results(self, mapper):
        result = mapper.map(
            "active customers in Dallas with critical tickets",
            table_names=["customer_accounts"],
        )
        for m in result.mappings:
            assert m.table_name == "customer_accounts"

    def test_no_match_returns_empty(self, mapper):
        result = mapper.map("unrelated xyzzy query")
        assert result.mappings == []
        assert result.enriched_question == "unrelated xyzzy query"

    # ── Hint block ────────────────────────────────────────────────────────────

    def test_hint_block_format(self, mapper):
        result = mapper.map("Show active customers in Dallas")
        block = result.as_hint_block()
        assert "-- Value alias hints" in block
        assert "customer_accounts" in block
        assert "status" in block or "region" in block

    def test_empty_hint_block_when_no_mappings(self, mapper):
        result = mapper.map("some random words here")
        assert result.as_hint_block() == ""

    # ── Enriched question ─────────────────────────────────────────────────────

    def test_enriched_question_contains_code_annotation(self, mapper):
        result = mapper.map("Show active customers")
        # enriched should include the [=A] annotation somewhere
        assert "[=A]" in result.enriched_question

    # ── Deduplication ─────────────────────────────────────────────────────────

    def test_no_duplicate_mappings_for_same_span(self, mapper):
        result = mapper.map("active active customers")
        # 'active' appears twice — should map both spans
        codes = [m.internal_code for m in result.mappings]
        # Both occurrences of 'active' should be mapped but as separate entries
        assert codes.count("A") <= 2
