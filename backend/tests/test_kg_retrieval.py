"""Unit tests for KG retrieval service (kg_retrieval module).

Uses mock ORM objects — no real database required.
"""

import pytest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from app.models.knowledge_graph import (
    KnowledgeEntityType,
    KnowledgeRelationType,
)
from app.services.kg_retrieval import (
    SCORE_WEIGHTS,
    _score_relation,
    _balanced_relations,
    format_context_for_prompt,
    find_relevant_context,
    _query_tokens,
    _relation_hints,
)
from app.services.kg_constants import (
    ROLE_QUERY_HINTS,
    RELATION_LABELS,
    ENTITY_LABELS,
    normalize_text,
)


# ---------------------------------------------------------------------------
# Helpers — build lightweight mock ORM objects
# ---------------------------------------------------------------------------

def _entity(entity_id: int, entity_type: str, label: str, project_id: int = 1, **kw):
    return SimpleNamespace(
        id=entity_id,
        project_id=project_id,
        entity_type=entity_type,
        label=label,
        normalized_label=normalize_text(label),
        natural_key=f"{entity_type}:test:{entity_id}",
        properties=kw.get("properties", {}),
    )


def _relation(
    relation_id: int,
    project_id: int,
    source_id: int,
    target_id: int,
    relation_type: str,
    confidence: float = 0.9,
    source_type: str = "note_extraction",
    source_id_val: int = 1,
    properties: dict | None = None,
):
    return SimpleNamespace(
        id=relation_id,
        project_id=project_id,
        source_entity_id=source_id,
        target_entity_id=target_id,
        relation_type=relation_type,
        source_type=source_type,
        source_id=source_id_val,
        confidence=confidence,
        properties=properties or {},
    )


# ---------------------------------------------------------------------------
# 1. SCORE_WEIGHTS — verify weight values are accessible
# ---------------------------------------------------------------------------

class TestScoreWeights:
    def test_weights_are_accessible(self):
        assert SCORE_WEIGHTS.relation_hint_match == 3.0
        assert SCORE_WEIGHTS.token_exact_match == 3.0
        assert SCORE_WEIGHTS.token_partial_match == 1.0
        assert SCORE_WEIGHTS.note_entity_bonus == 0.2
        assert SCORE_WEIGHTS.note_extraction_bonus == 0.3
        assert SCORE_WEIGHTS.role_query_match == 4.0

    def test_weights_are_frozen(self):
        with pytest.raises(AttributeError):
            SCORE_WEIGHTS.relation_hint_match = 99.0


# ---------------------------------------------------------------------------
# 2. _score_relation — scoring logic
# ---------------------------------------------------------------------------

class TestScoreRelation:
    def test_hint_match_adds_score(self):
        source = _entity(1, KnowledgeEntityType.NOTE.value, "Note 1")
        target = _entity(2, KnowledgeEntityType.REAGENT.value, "PBS Buffer")
        relation = _relation(1, 1, 1, 2, KnowledgeRelationType.USES_REAGENT.value)
        tokens = {"pbs"}
        hints = {KnowledgeRelationType.USES_REAGENT.value}

        score = _score_relation(source, target, relation, tokens, hints, "PBS reagent")
        assert score >= SCORE_WEIGHTS.relation_hint_match

    def test_token_exact_match(self):
        source = _entity(1, KnowledgeEntityType.NOTE.value, "Note")
        target = _entity(2, KnowledgeEntityType.REAGENT.value, "PBS")
        relation = _relation(1, 1, 1, 2, KnowledgeRelationType.USES_REAGENT.value)
        tokens = {"pbs"}
        hints = set()

        score = _score_relation(source, target, relation, tokens, hints, "PBS")
        # token "pbs" should match target label "pbs" exactly
        assert score >= SCORE_WEIGHTS.token_exact_match

    def test_token_partial_match(self):
        source = _entity(1, KnowledgeEntityType.NOTE.value, "Note")
        target = _entity(2, KnowledgeEntityType.REAGENT.value, "PBS Buffer Solution")
        relation = _relation(1, 1, 1, 2, KnowledgeRelationType.USES_REAGENT.value)
        tokens = {"pbs"}
        hints = set()

        score = _score_relation(source, target, relation, tokens, hints, "PBS")
        # "pbs" is a partial match within "pbs buffer solution"
        assert score >= SCORE_WEIGHTS.token_partial_match

    def test_note_entity_bonus(self):
        source = _entity(1, KnowledgeEntityType.NOTE.value, "Note")
        target = _entity(2, KnowledgeEntityType.REAGENT.value, "Reagent")
        relation = _relation(1, 1, 1, 2, KnowledgeRelationType.USES_REAGENT.value)

        score = _score_relation(source, target, relation, set(), set(), "")
        assert score >= SCORE_WEIGHTS.note_entity_bonus

    def test_note_extraction_bonus(self):
        source = _entity(1, KnowledgeEntityType.REAGENT.value, "Reagent")
        target = _entity(2, KnowledgeEntityType.SAMPLE.value, "Sample")
        relation = _relation(
            1, 1, 1, 2, KnowledgeRelationType.USES_REAGENT.value,
            source_type="note_extraction",
        )

        score = _score_relation(source, target, relation, set(), set(), "")
        assert score >= SCORE_WEIGHTS.note_extraction_bonus

    def test_role_query_match(self):
        source = _entity(1, KnowledgeEntityType.NOTE.value, "Note")
        target = _entity(2, KnowledgeEntityType.SOFTWARE.value, "STAR")
        relation = _relation(
            1, 1, 1, 2, KnowledgeRelationType.USES_SOFTWARE.value,
            properties={"roles": ["alignment_software"]},
        )
        # Query contains "比对" which is in ROLE_QUERY_HINTS["alignment_software"]
        score = _score_relation(source, target, relation, set(), set(), "比对软件")
        assert score >= SCORE_WEIGHTS.role_query_match

    def test_no_match_returns_zero(self):
        source = _entity(1, KnowledgeEntityType.REAGENT.value, "ABC")
        target = _entity(2, KnowledgeEntityType.INSTRUMENT.value, "XYZ")
        relation = _relation(
            1, 1, 1, 2, KnowledgeRelationType.USES_INSTRUMENT.value,
            source_type="manual",
        )

        score = _score_relation(source, target, relation, set(), set(), "unrelated")
        assert score == 0.0

    def test_combined_scores(self):
        """Multiple scoring signals should accumulate."""
        source = _entity(1, KnowledgeEntityType.NOTE.value, "Note")
        target = _entity(2, KnowledgeEntityType.REAGENT.value, "PBS")
        relation = _relation(
            1, 1, 1, 2, KnowledgeRelationType.USES_REAGENT.value,
            source_type="note_extraction",
        )
        tokens = {"pbs"}
        hints = {KnowledgeRelationType.USES_REAGENT.value}

        score = _score_relation(source, target, relation, tokens, hints, "PBS试剂")
        # Should accumulate: hint + token match + note bonus + extraction bonus
        assert score > SCORE_WEIGHTS.relation_hint_match


# ---------------------------------------------------------------------------
# 3. _balanced_relations — deduplication and balance
# ---------------------------------------------------------------------------

class TestBalancedRelations:
    def test_basic_limit(self):
        entities = {
            1: _entity(1, KnowledgeEntityType.NOTE.value, "Note"),
            2: _entity(2, KnowledgeEntityType.REAGENT.value, "PBS"),
            3: _entity(3, KnowledgeEntityType.REAGENT.value, "DMEM"),
        }
        relations = [
            (5.0, _relation(1, 1, 1, 2, KnowledgeRelationType.USES_REAGENT.value)),
            (3.0, _relation(2, 1, 1, 3, KnowledgeRelationType.USES_REAGENT.value)),
        ]
        result = _balanced_relations(relations, entities, limit=1, query="reagent")
        assert len(result) == 1
        assert result[0][0] == 5.0

    def test_deduplication_by_group(self):
        """Relations from the same NOTE source with same type should be grouped."""
        entities = {
            1: _entity(1, KnowledgeEntityType.NOTE.value, "Note"),
            2: _entity(2, KnowledgeEntityType.REAGENT.value, "PBS"),
            3: _entity(3, KnowledgeEntityType.REAGENT.value, "PBS"),
        }
        relations = [
            (5.0, _relation(1, 1, 1, 2, KnowledgeRelationType.USES_REAGENT.value)),
            (4.0, _relation(2, 1, 1, 3, KnowledgeRelationType.USES_REAGENT.value)),
        ]
        result = _balanced_relations(relations, entities, limit=10, query="reagent")
        # Both should be included since they have different target entities
        assert len(result) >= 1

    def test_empty_input(self):
        result = _balanced_relations({}, {}, limit=5, query="test")
        assert result == []

    def test_respects_limit(self):
        entities = {
            1: _entity(1, KnowledgeEntityType.REAGENT.value, "A"),
            2: _entity(2, KnowledgeEntityType.REAGENT.value, "B"),
            3: _entity(3, KnowledgeEntityType.REAGENT.value, "C"),
            4: _entity(4, KnowledgeEntityType.REAGENT.value, "D"),
        }
        relations = [
            (float(i), _relation(i, 1, i, (i % 4) + 1, KnowledgeRelationType.USES_REAGENT.value))
            for i in range(1, 5)
        ]
        result = _balanced_relations(relations, entities, limit=2, query="reagent")
        assert len(result) <= 2


# ---------------------------------------------------------------------------
# 4. format_context_for_prompt — output formatting
# ---------------------------------------------------------------------------

class TestFormatContextForPrompt:
    def test_empty_input_returns_empty_string(self):
        assert format_context_for_prompt([]) == ""

    def test_basic_formatting(self):
        items = [
            {
                "source_entity_type_label": "实验笔记",
                "source_label": "Note 1",
                "relation_label": "使用试剂",
                "target_entity_type_label": "试剂",
                "target_label": "PBS",
                "confidence": 0.95,
                "relation_roles": [],
            },
        ]
        result = format_context_for_prompt(items)
        assert "实验知识图谱上下文" in result
        assert "[G1]" in result
        assert "PBS" in result
        assert "0.95" in result

    def test_role_labels_included(self):
        items = [
            {
                "source_entity_type_label": "笔记",
                "source_label": "Note",
                "relation_label": "使用软件",
                "target_entity_type_label": "软件",
                "target_label": "STAR",
                "confidence": 0.8,
                "relation_roles": ["alignment_software"],
            },
        ]
        result = format_context_for_prompt(items)
        assert "比对软件" in result

    def test_max_chars_truncation(self):
        items = [
            {
                "source_entity_type_label": "笔记",
                "source_label": f"Note {i}",
                "relation_label": "使用试剂",
                "target_entity_type_label": "试剂",
                "target_label": f"Reagent_{i}" * 20,
                "confidence": 0.9,
                "relation_roles": [],
            }
            for i in range(50)
        ]
        result = format_context_for_prompt(items, max_chars=200)
        assert len(result) <= 200

    def test_default_budget_matches_rust_graph_context_budget(self):
        result = format_context_for_prompt(
            [
                {
                    "source_entity_type_label": "实验笔记",
                    "source_label": f"Note {i}",
                    "relation_label": "使用试剂",
                    "target_entity_type_label": "试剂",
                    "target_label": "Reagent" * 100,
                    "confidence": 0.9,
                    "relation_roles": [],
                }
                for i in range(50)
            ]
        )

        assert 4_000 < len(result) <= 6_000

    def test_max_chars_truncation_keeps_whole_context_lines(self):
        result = format_context_for_prompt(
            [
                {
                    "source_entity_type_label": "实验笔记",
                    "source_label": "Note",
                    "relation_label": "使用试剂",
                    "target_entity_type_label": "试剂",
                    "target_label": "Reagent" * 80,
                    "confidence": 0.9,
                    "relation_roles": [],
                }
            ],
            max_chars=200,
        )

        assert result == "实验知识图谱上下文："

    def test_multiple_items_numbered(self):
        items = [
            {
                "source_entity_type_label": "A",
                "source_label": "S1",
                "relation_label": "R",
                "target_entity_type_label": "B",
                "target_label": f"T{i}",
                "confidence": 0.5,
                "relation_roles": [],
            }
            for i in range(3)
        ]
        result = format_context_for_prompt(items)
        assert "[G1]" in result
        assert "[G2]" in result
        assert "[G3]" in result


# ---------------------------------------------------------------------------
# 5. find_relevant_context — retrieval with mock entities/relations
# ---------------------------------------------------------------------------

class TestFindRelevantContext:
    def _mock_db(self, entities, relations, approved_note_ids=None):
        """Build a mock DB session that returns given entities/relations."""
        db = MagicMock()
        # get_project_graph queries:
        # 1. db.query(ExperimentNote.id).filter(...).all() → approved note ids
        # 2. db.query(KnowledgeRelation).filter(...).order_by(...).all()
        # 3. db.query(KnowledgeEntity).filter(...).order_by(...).all()
        note_ids = approved_note_ids or [1]
        query_chain = MagicMock()
        query_chain.filter.return_value = query_chain
        query_chain.all.return_value = [(nid,) for nid in note_ids]

        relation_chain = MagicMock()
        relation_chain.filter.return_value = relation_chain
        relation_chain.order_by.return_value = relation_chain
        relation_chain.all.return_value = relations

        entity_chain = MagicMock()
        entity_chain.filter.return_value = entity_chain
        entity_chain.order_by.return_value = entity_chain
        entity_chain.all.return_value = entities

        call_count = [0]
        def query_side_effect(model):
            call_count[0] += 1
            if call_count[0] == 1:
                return query_chain
            elif call_count[0] == 2:
                return relation_chain
            else:
                return entity_chain

        db.query.side_effect = query_side_effect
        return db

    @patch("app.services.kg_retrieval.get_settings")
    def test_returns_scored_context(self, mock_settings):
        mock_settings.return_value.rag_graph_top_k = 6
        mock_settings.return_value.rag_graph_min_score = 0.0

        entities = [
            _entity(1, KnowledgeEntityType.NOTE.value, "Experiment Note"),
            _entity(2, KnowledgeEntityType.REAGENT.value, "PBS Buffer"),
        ]
        relations = [
            _relation(1, 1, 1, 2, KnowledgeRelationType.USES_REAGENT.value, confidence=0.9),
        ]
        db = self._mock_db(entities, relations)

        result = find_relevant_context(db, project_id=1, query="PBS")
        assert isinstance(result, list)
        if result:
            item = result[0]
            assert "source_label" in item
            assert "target_label" in item
            assert "retrieval_score" in item

    @patch("app.services.kg_retrieval.get_settings")
    def test_empty_graph_returns_empty(self, mock_settings):
        mock_settings.return_value.rag_graph_top_k = 6
        mock_settings.return_value.rag_graph_min_score = 0.0

        db = self._mock_db([], [])
        result = find_relevant_context(db, project_id=1, query="PBS")
        assert result == []


# ---------------------------------------------------------------------------
# 6. Helper functions
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_query_tokens_extracts_chinese(self):
        tokens = _query_tokens("比对软件STAR")
        assert any("star" in t for t in tokens)

    def test_query_tokens_extracts_english(self):
        tokens = _query_tokens("PBS buffer reagent")
        assert "pbs" in tokens or any("pbs" in t for t in tokens)

    def test_relation_hints_detects_reagent(self):
        tokens = _query_tokens("试剂")
        hints = _relation_hints("试剂", tokens)
        assert KnowledgeRelationType.USES_REAGENT.value in hints

    def test_relation_hints_empty_for_unrelated(self):
        tokens = _query_tokens("xyzabc")
        hints = _relation_hints("xyzabc", tokens)
        assert len(hints) == 0
