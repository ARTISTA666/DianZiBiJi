"""Tests for the unified citation audit utility."""

from __future__ import annotations

import re

import pytest

from app.services.citation_audit import audit_citations


# ---------------------------------------------------------------------------
# [NFR] format — agent.py style
# ---------------------------------------------------------------------------

class TestNFRCitations:
    """Audit behaviour for the [NFR] marker format used by the agent pipeline."""

    ALLOWED = {"N": {1, 2, 3}, "F": {1, 2}, "R": {1}}

    def test_valid_citations_pass(self):
        result = audit_citations("结论见[N1]和[F2]。", self.ALLOWED)
        assert result["passed"] is True
        assert result["citation_count"] == 2
        assert result["invalid_citations"] == []
        assert result["has_evidence"] is True

    def test_out_of_range_citations_fail(self):
        result = audit_citations("参考[N5]和[F9]。", self.ALLOWED)
        assert result["passed"] is False
        assert result["citation_count"] == 2
        assert "[N5]" in result["invalid_citations"]
        assert "[F9]" in result["invalid_citations"]

    def test_mixed_valid_and_invalid(self):
        result = audit_citations("[N1]有效，[N99]无效，[R1]有效。", self.ALLOWED)
        assert result["passed"] is False
        assert result["citation_count"] == 3
        assert result["invalid_citations"] == ["[N99]"]

    def test_malformed_marker_fails_even_with_valid_citation(self):
        result = audit_citations("有效[N1]，伪引用[N系统]和[N1-N2]。", self.ALLOWED)
        assert result["passed"] is False
        assert result["citation_count"] == 3
        assert result["invalid_citations"] == ["[N系统]", "[N1-N2]"]

    def test_empty_answer_with_evidence(self):
        result = audit_citations("没有任何引用。", self.ALLOWED)
        assert result["passed"] is False
        assert result["citation_count"] == 0
        assert result["has_evidence"] is True

    def test_empty_answer_no_evidence(self):
        empty_allowed = {"N": set(), "F": set(), "R": set()}
        result = audit_citations("没有任何引用。", empty_allowed)
        assert result["passed"] is True
        assert result["citation_count"] == 0
        assert result["has_evidence"] is False

    def test_all_three_prefixes(self):
        result = audit_citations("[N1][F1][R1]", self.ALLOWED)
        assert result["passed"] is True
        assert result["citation_count"] == 3
        assert result["invalid_citations"] == []


# ---------------------------------------------------------------------------
# [SG] format — rag/common.py style (case-insensitive)
# ---------------------------------------------------------------------------

class TestSGCitations:
    """Audit behaviour for the [SG] marker format used by the RAG pipeline."""

    ALLOWED = {"S": set(range(1, 4)), "G": set(range(1, 3))}

    def test_valid_citations_pass(self):
        result = audit_citations("来源[S1]和图谱[G2]。", self.ALLOWED, flags=re.IGNORECASE)
        assert result["passed"] is True
        assert result["citation_count"] == 2
        assert result["invalid_citations"] == []

    def test_case_insensitive_matching(self):
        result = audit_citations("来源[s1]和[g2]。", self.ALLOWED, flags=re.IGNORECASE)
        assert result["passed"] is True
        assert result["citation_count"] == 2
        # Markers are normalised to uppercase in the output
        assert result["invalid_citations"] == []

    def test_out_of_range_fails(self):
        result = audit_citations("[S10]不存在。", self.ALLOWED, flags=re.IGNORECASE)
        assert result["passed"] is False
        assert "[S10]" in result["invalid_citations"]

    def test_zero_index_fails(self):
        """Index 0 is outside range(1, n+1) and must be invalid."""
        result = audit_citations("[S0]无效。", self.ALLOWED, flags=re.IGNORECASE)
        assert result["passed"] is False
        assert "[S0]" in result["invalid_citations"]

    def test_empty_answer_with_evidence(self):
        result = audit_citations("无引用。", self.ALLOWED, flags=re.IGNORECASE)
        assert result["passed"] is False
        assert result["has_evidence"] is True

    def test_empty_answer_no_evidence(self):
        empty_allowed = {"S": set(), "G": set()}
        result = audit_citations("无引用。", empty_allowed, flags=re.IGNORECASE)
        assert result["passed"] is True
        assert result["has_evidence"] is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_allowed_dict(self):
        result = audit_citations("[N1]", {})
        assert result["passed"] is True
        assert result["citation_count"] == 0
        assert result["has_evidence"] is False

    def test_custom_pattern(self):
        allowed = {"X": {1, 2}}
        result = audit_citations("see (X1) and (X3)", allowed, pattern=r"\(([A-Z])(\d+)\)")
        assert result["passed"] is False
        assert result["citation_count"] == 2
        assert "[X3]" in result["invalid_citations"]

    def test_multiple_occurrences_same_invalid(self):
        allowed = {"N": {1}}
        result = audit_citations("[N2] again [N2]", allowed)
        assert result["invalid_citations"] == ["[N2]", "[N2]"]
        assert result["citation_count"] == 2
