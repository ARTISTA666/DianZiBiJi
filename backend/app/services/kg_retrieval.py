"""Knowledge-graph retrieval and scoring logic.

Contains all functions related to reading the graph, scoring relevance,
and formatting context for LLM prompts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.knowledge_graph import (
    KnowledgeEntity,
    KnowledgeEntityType,
    KnowledgeRelation,
)
from app.models.note import ExperimentNote, NoteStatus
from app.core.config import get_settings

from app.services.kg_constants import (
    COLLECTION_QUERY_KEYWORDS,
    ENTITY_LABELS,
    FOCUS_SYNONYMS,
    QUERY_RELATION_HINTS,
    RELATION_LABELS,
    ROLE_LABELS,
    ROLE_QUERY_HINTS,
    normalize_text,
    source_natural_key,
)


# ---------------------------------------------------------------------------
# Scoring weights
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ScoreWeights:
    """Tuning knobs for the graph-relation scoring heuristic."""

    relation_hint_match: float = 3.0
    token_exact_match: float = 3.0
    token_partial_match: float = 1.0
    note_entity_bonus: float = 0.2
    note_extraction_bonus: float = 0.3
    role_query_match: float = 4.0


SCORE_WEIGHTS = _ScoreWeights()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_project_graph(
    db: Session,
    project_id: int,
) -> tuple[list[KnowledgeEntity], list[KnowledgeRelation]]:
    """Return entities and relations for approved notes in a project."""
    approved_note_ids = {
        note_id
        for (note_id,) in db.query(ExperimentNote.id)
        .filter(ExperimentNote.project_id == project_id, ExperimentNote.status == NoteStatus.APPROVED)
        .all()
    }
    relations = [
        relation
        for relation in db.query(KnowledgeRelation)
        .filter(KnowledgeRelation.project_id == project_id)
        .order_by(KnowledgeRelation.id)
        .all()
        if relation.source_type not in {"note", "note_extraction"}
        or relation.source_id in approved_note_ids
    ]
    referenced_entity_ids = {
        entity_id
        for relation in relations
        for entity_id in (relation.source_entity_id, relation.target_entity_id)
    }
    entities = (
        db.query(KnowledgeEntity)
        .filter(KnowledgeEntity.id.in_(referenced_entity_ids or {0}))
        .order_by(KnowledgeEntity.id)
        .all()
    )
    return entities, relations


def find_relevant_context(
    db: Session,
    project_id: int,
    query: str,
    limit: int | None = None,
) -> list[dict]:
    """Score and return the most relevant graph relations for *query*."""
    settings = get_settings()
    limit = limit or _context_limit(query, settings.rag_graph_top_k)
    entities, relations = get_project_graph(db, project_id)
    if not entities or not relations:
        return []
    entity_by_id = {entity.id: entity for entity in entities}
    tokens = _query_tokens(query)
    relation_hints = _relation_hints(query, tokens)
    focus_ids = _focus_entity_ids(entities, relations, tokens, query)
    scored: list[tuple[float, KnowledgeRelation]] = []
    for relation in relations:
        source = entity_by_id.get(relation.source_entity_id)
        target = entity_by_id.get(relation.target_entity_id)
        if source is None or target is None:
            continue
        if relation_hints and relation.relation_type not in relation_hints:
            continue
        if focus_ids and not {
            relation.source_entity_id,
            relation.target_entity_id,
        } & focus_ids:
            continue
        score = _score_relation(source, target, relation, tokens, relation_hints, query)
        scored.append((score, relation))
    scored.sort(key=lambda item: (item[0], item[1].confidence, item[1].id), reverse=True)
    relevant = [(score, relation) for score, relation in scored if score >= settings.rag_graph_min_score]
    relevant = _balanced_relations(relevant, entity_by_id, limit, query)
    return [_context_item(entity_by_id, relation, score) for score, relation in relevant]


def get_note_graph(
    db: Session,
    note: ExperimentNote,
) -> tuple[list[KnowledgeEntity], list[KnowledgeRelation]]:
    """Return entities and relations directly connected to *note*."""
    note_key = source_natural_key(KnowledgeEntityType.NOTE, "note", note.id)
    note_entity = (
        db.query(KnowledgeEntity)
        .filter(KnowledgeEntity.project_id == note.project_id, KnowledgeEntity.natural_key == note_key)
        .first()
    )
    if note_entity is None:
        return [], []
    relations = (
        db.query(KnowledgeRelation)
        .filter(
            KnowledgeRelation.project_id == note.project_id,
            or_(KnowledgeRelation.source_entity_id == note_entity.id, KnowledgeRelation.target_entity_id == note_entity.id),
        )
        .order_by(KnowledgeRelation.id)
        .all()
    )
    entity_ids = {note_entity.id}
    for relation in relations:
        entity_ids.add(relation.source_entity_id)
        entity_ids.add(relation.target_entity_id)
    entities = (
        db.query(KnowledgeEntity)
        .filter(KnowledgeEntity.project_id == note.project_id, KnowledgeEntity.id.in_(entity_ids))
        .order_by(KnowledgeEntity.id)
        .all()
    )
    return entities, relations


def format_context_for_prompt(
    context_items: list[dict],
    query: str = "",
    max_chars: int = 4000,
) -> str:
    """Render scored context items into a text block for LLM prompts."""
    if not context_items:
        return ""
    lines = ["实验知识图谱上下文："]
    lines.extend(_numeric_summary_lines(context_items, query))
    for index, item in enumerate(context_items, start=1):
        roles = item.get("relation_roles") or []
        role_text = f"；用途：{'、'.join(ROLE_LABELS.get(role, role) for role in roles)}" if roles else ""
        lines.append(
            f"- [G{index}] "
            f"[{item['source_entity_type_label']}] {item['source_label']} "
            f"--{item['relation_label']}--> "
            f"[{item['target_entity_type_label']}] {item['target_label']} "
            f"(置信度 {item['confidence']:.2f}{role_text})"
        )
    text = "\n".join(lines)
    return text[:max_chars]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _balanced_relations(
    relevant: list[tuple[float, KnowledgeRelation]],
    entity_by_id: dict[int, KnowledgeEntity],
    limit: int,
    query: str,
) -> list[tuple[float, KnowledgeRelation]]:
    selected: list[tuple[float, KnowledgeRelation]] = []
    selected_ids: set[int] = set()
    seen_groups: set[tuple[int, str, str]] = set()
    normalized_query = normalize_text(query)
    for score, relation in relevant:
        source = entity_by_id[relation.source_entity_id]
        matching_role = next(
            (
                role
                for role in (relation.properties or {}).get("roles", [])
                if any(keyword in normalized_query for keyword in ROLE_QUERY_HINTS.get(role, ()))
            ),
            "",
        )
        wants_distinct_targets = matching_role in {"processing_software", "data_boundary"} and any(
            keyword in normalized_query
            for keyword in ("完整", "全部", "所有", "软件链", "流程", "层级", "不能", "不得", "不是", "pipeline", "fastq")
        )
        group_source_id = 0 if wants_distinct_targets else source.id
        target_group = relation.target_entity_id if wants_distinct_targets else 0
        group = (group_source_id, relation.relation_type, matching_role, target_group)
        if source.entity_type == KnowledgeEntityType.NOTE.value and group not in seen_groups:
            selected.append((score, relation))
            selected_ids.add(relation.id)
            seen_groups.add(group)
            if len(selected) == limit:
                return selected
    for score, relation in relevant:
        if relation.id not in selected_ids:
            selected.append((score, relation))
            if len(selected) == limit:
                break
    return selected


def _context_limit(query: str, default_limit: int) -> int:
    normalized_query = normalize_text(query)
    if any(keyword in normalized_query for keyword in COLLECTION_QUERY_KEYWORDS):
        return max(default_limit, 30)
    return default_limit


def _context_item(
    entity_by_id: dict[int, KnowledgeEntity],
    relation: KnowledgeRelation,
    retrieval_score: float = 0,
) -> dict:
    source = entity_by_id[relation.source_entity_id]
    target = entity_by_id[relation.target_entity_id]
    return {
        "relation_id": relation.id,
        "relation_type": relation.relation_type,
        "relation_label": RELATION_LABELS.get(relation.relation_type, relation.relation_type),
        "source_entity_id": source.id,
        "source_label": source.label,
        "source_entity_type": source.entity_type,
        "source_entity_type_label": ENTITY_LABELS.get(source.entity_type, source.entity_type),
        "target_entity_id": target.id,
        "target_label": target.label,
        "target_entity_type": target.entity_type,
        "target_entity_type_label": ENTITY_LABELS.get(target.entity_type, target.entity_type),
        "confidence": relation.confidence,
        "retrieval_score": round(retrieval_score, 4),
        "relation_roles": (relation.properties or {}).get("roles", []),
    }


def _score_relation(
    source: KnowledgeEntity,
    target: KnowledgeEntity,
    relation: KnowledgeRelation,
    tokens: set[str],
    relation_hints: set[str],
    query: str,
) -> float:
    score = 0.0
    if relation.relation_type in relation_hints:
        score += SCORE_WEIGHTS.relation_hint_match
    haystacks = [
        normalize_text(source.label),
        normalize_text(target.label),
        source.entity_type,
        target.entity_type,
        relation.relation_type,
        RELATION_LABELS.get(relation.relation_type, ""),
    ]
    for token in tokens:
        for text in haystacks:
            normalized = normalize_text(text)
            if token and token == normalized:
                score += SCORE_WEIGHTS.token_exact_match
            elif token and (token in normalized or normalized in token):
                score += SCORE_WEIGHTS.token_partial_match
    if source.entity_type == KnowledgeEntityType.NOTE.value:
        score += SCORE_WEIGHTS.note_entity_bonus
    if relation.source_type == "note_extraction":
        score += SCORE_WEIGHTS.note_extraction_bonus
    normalized_query = normalize_text(query)
    for role in (relation.properties or {}).get("roles", []):
        if any(keyword in normalized_query for keyword in ROLE_QUERY_HINTS.get(role, ())):
            score += SCORE_WEIGHTS.role_query_match
    return score


def _query_tokens(query: str) -> set[str]:
    raw_tokens = re.findall(r"[A-Za-z0-9_\-]+|[\u4e00-\u9fff]{2,}", query.lower())
    tokens = {normalize_text(token) for token in raw_tokens if len(normalize_text(token)) >= 2}
    normalized_query = normalize_text(query)
    if normalized_query:
        tokens.add(normalized_query)
    return tokens


def _relation_hints(query: str, tokens: set[str]) -> set[str]:
    normalized_query = normalize_text(query)
    hints: set[str] = set()
    for relation_type, keywords in QUERY_RELATION_HINTS.items():
        if any(keyword.lower() in normalized_query or keyword.lower() in tokens for keyword in keywords):
            hints.add(relation_type)
    return hints


def _focus_entity_ids(
    entities: list[KnowledgeEntity],
    relations: list[KnowledgeRelation],
    tokens: set[str],
    query: str,
) -> set[int]:
    generic_tokens = {
        normalize_text(keyword)
        for keywords in QUERY_RELATION_HINTS.values()
        for keyword in keywords
    } | {normalize_text(keyword) for keyword in COLLECTION_QUERY_KEYWORDS}
    focus_tokens = {token for token in tokens if token not in generic_tokens}
    normalized_query = normalize_text(query)
    synonym_matched = {
        entity.id
        for entity in entities
        if any(
            canonical in normalize_text(entity.label)
            and any(alias in normalized_query for alias in aliases)
            for canonical, aliases in FOCUS_SYNONYMS.items()
        )
    }
    token_matched = {
        entity.id
        for entity in entities
        if any(
            token == normalize_text(entity.label)
            or token in normalize_text(entity.label)
            or normalize_text(entity.label) in token
            for token in focus_tokens
        )
    }
    matched = synonym_matched or token_matched
    if not matched:
        return set()

    entity_by_id = {entity.id: entity for entity in entities}
    focused = set(matched)
    for relation in relations:
        source = entity_by_id.get(relation.source_entity_id)
        target = entity_by_id.get(relation.target_entity_id)
        if source is None or target is None:
            continue
        if relation.source_entity_id in matched and target.entity_type == KnowledgeEntityType.NOTE.value:
            focused.add(target.id)
        if relation.target_entity_id in matched and source.entity_type == KnowledgeEntityType.NOTE.value:
            focused.add(source.id)
    return focused


def _numeric_summary_lines(context_items: list[dict], query: str) -> list[str]:
    normalized_query = normalize_text(query)
    if not any(keyword in normalized_query for keyword in ("计数", "行数", "total", "detected")):
        return []
    records: dict[str, dict[str, int]] = {}
    pattern = re.compile(
        r"(GSM\d+).*?total_count=(\d+).*?detected_gene_rows=(\d+)",
        flags=re.IGNORECASE,
    )
    for item in context_items:
        match = pattern.search(item.get("target_label", ""))
        if match:
            records[match.group(1)] = {
                "total_count": int(match.group(2)),
                "detected_gene_rows": int(match.group(3)),
            }
    if not records:
        return []
    metric = "detected_gene_rows" if any(
        keyword in normalized_query for keyword in ("非零", "行数", "detected")
    ) else "total_count"
    lines = ["结构化数值汇总（系统直接计算）："]
    lines.extend(f"- {accession}: {metric}={values[metric]}" for accession, values in sorted(records.items()))
    if any(keyword in normalized_query for keyword in ("最高", "最大", "highest", "maximum")):
        accession, values = max(records.items(), key=lambda item: item[1][metric])
        lines.append(f"- 比较结果：最高为 {accession}，{metric}={values[metric]}。")
    if any(keyword in normalized_query for keyword in ("最低", "最小", "lowest", "minimum")):
        accession, values = min(records.items(), key=lambda item: item[1][metric])
        lines.append(f"- 比较结果：最低为 {accession}，{metric}={values[metric]}。")
    if any(keyword in normalized_query for keyword in ("相差", "差值", "difference")) and len(records) == 2:
        metric_values = [values[metric] for values in records.values()]
        difference = abs(metric_values[0] - metric_values[1])
        lines.append(f"- 差值：{difference}。")
    return lines
