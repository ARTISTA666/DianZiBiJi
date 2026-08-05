"""Knowledge-graph service – facade layer.

This module re-exports every public name from the three sub-modules so that
existing imports (``from app.services.knowledge_graph import …``) continue to
work unchanged.  The ``KnowledgeGraphService`` class is a thin wrapper that
delegates to the standalone functions in *kg_extraction* and *kg_retrieval*.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Re-export all constants (single-star import is intentional here)
# ---------------------------------------------------------------------------
from app.services.kg_constants import (  # noqa: F401,F403
    COLLECTION_QUERY_KEYWORDS,
    ENTITY_LABELS,
    FOCUS_SYNONYMS,
    GRAPH_SCHEMA_VERSION,
    QUERY_RELATION_HINTS,
    RELATION_LABELS,
    ROLE_LABELS,
    ROLE_QUERY_HINTS,
    STRUCTURED_ALIASES,
    STRUCTURED_FIELD_ROLES,
    STRUCTURED_FIELD_TYPES,
    TEXT_PATTERNS,
    # Shared utility functions (previously methods / module-level helpers)
    clean_label,
    dedupe_labels,
    flatten_text,
    normalize_entity_label,
    normalize_text,
    source_natural_key,
    split_terms,
)

# ---------------------------------------------------------------------------
# Re-export extraction functions
# ---------------------------------------------------------------------------
from app.services.kg_extraction import (  # noqa: F401
    clear_note as _clear_note,
    extract_note as _extract_note,
    extract_terms as _extract_terms,
    _upsert_entity,
    _upsert_relation,
    _inferred_roles,
)

# ---------------------------------------------------------------------------
# Re-export retrieval functions
# ---------------------------------------------------------------------------
from app.services.kg_retrieval import (  # noqa: F401
    MAX_GRAPH_CONTEXT_CHARS,
    find_relevant_context as _find_relevant_context,
    format_context_for_prompt as _format_context_for_prompt,
    get_note_graph as _get_note_graph,
    get_project_graph as _get_project_graph,
)


# ---------------------------------------------------------------------------
# Backward-compatible service class
# ---------------------------------------------------------------------------


class KnowledgeGraphService:
    """Thin facade that preserves the original class-based API.

    All logic lives in ``kg_extraction`` and ``kg_retrieval``; this class
    simply delegates so that existing call-sites remain unchanged.
    """

    def clear_note(self, db, note_id: int) -> None:  # noqa: ANN001
        _clear_note(db, note_id)

    def extract_note(self, db, note, triggered_by: int, rebuild: bool = True):  # noqa: ANN001
        return _extract_note(db, note, triggered_by, rebuild)

    def extract_terms(self, fixed_fields: dict, content: dict):
        return _extract_terms(fixed_fields, content)

    def get_project_graph(self, db, project_id: int):  # noqa: ANN001
        return _get_project_graph(db, project_id)

    def get_note_graph(self, db, note):  # noqa: ANN001
        return _get_note_graph(db, note)

    def find_relevant_context(self, db, project_id: int, query: str, limit: int | None = None):  # noqa: ANN001
        return _find_relevant_context(db, project_id, query, limit)

    def format_context_for_prompt(
        self,
        context_items: list[dict],
        query: str = "",
        max_chars: int = MAX_GRAPH_CONTEXT_CHARS,
    ) -> str:
        return _format_context_for_prompt(context_items, query, max_chars)

    # Expose internal helpers for direct test access
    _upsert_entity = staticmethod(_upsert_entity)
    _upsert_relation = staticmethod(_upsert_relation)
    _split_terms = staticmethod(split_terms)
    _inferred_roles = staticmethod(_inferred_roles)
