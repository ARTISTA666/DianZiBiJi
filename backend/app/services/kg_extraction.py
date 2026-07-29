"""Knowledge-graph extraction logic.

Contains all functions related to extracting entities and relations from
experiment notes and persisting them into the graph schema.
"""

from __future__ import annotations

import re

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.file import StoredFile
from app.models.knowledge_graph import (
    KnowledgeEntity,
    KnowledgeEntityType,
    KnowledgeExtractionRun,
    KnowledgeExtractionStatus,
    KnowledgeRelation,
    KnowledgeRelationType,
)
from app.models.note import ExperimentNote, NoteVersion
from app.models.project import Project
from app.models.user import User

from app.services.kg_constants import (
    STRUCTURED_ALIASES,
    STRUCTURED_FIELD_ROLES,
    STRUCTURED_FIELD_TYPES,
    TEXT_PATTERNS,
    clean_label,
    dedupe_labels,
    flatten_text,
    normalize_entity_label,
    normalize_text,
    source_natural_key,
    split_terms,
)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def clear_note(db: Session, note_id: int) -> None:
    """Remove all extraction artefacts for a single note."""
    _clear_note_extraction(db, note_id)


def extract_note(
    db: Session,
    note: ExperimentNote,
    triggered_by: int,
    rebuild: bool = True,
) -> KnowledgeExtractionRun:
    """Run full KG extraction for *note* and return the run record."""
    if rebuild:
        _clear_note_extraction(db, note.id)

    touched_entities: set[int] = set()
    touched_relations: set[int] = set()

    project = db.get(Project, note.project_id)
    if project is None:
        return _record_run(db, note, triggered_by, 0, 0, KnowledgeExtractionStatus.FAILED.value, "Project not found")

    version = db.get(NoteVersion, note.current_version_id) if note.current_version_id else None
    fixed_fields = version.fixed_fields_json if version else {}
    content = version.content_json if version else {}

    # ------------------------------------------------------------------
    # Phase 1: Create / update all entities, then flush once to obtain IDs
    # ------------------------------------------------------------------
    project_entity = _upsert_entity(
        db,
        note.project_id,
        KnowledgeEntityType.PROJECT,
        project.name,
        source_type="project",
        source_id=project.id,
        properties={"project_id": project.id},
    )
    note_entity = _upsert_entity(
        db,
        note.project_id,
        KnowledgeEntityType.NOTE,
        note.title,
        source_type="note",
        source_id=note.id,
        properties={
            "note_id": note.id,
            "status": str(note.status.value if hasattr(note.status, "value") else note.status),
            "experiment_date": note.experiment_date.isoformat() if note.experiment_date else None,
        },
    )
    touched_entities.update({project_entity.id, note_entity.id})

    owner_entity = None
    owner = db.get(User, note.owner_user_id)
    if owner is not None:
        owner_entity = _upsert_entity(
            db,
            note.project_id,
            KnowledgeEntityType.USER,
            owner.display_name or owner.username,
            source_type="user",
            source_id=owner.id,
            properties={"user_id": owner.id, "username": owner.username},
        )
        touched_entities.add(owner_entity.id)

    experiment_type_entity = None
    if note.experiment_type:
        experiment_type_entity = _upsert_entity(
            db,
            note.project_id,
            KnowledgeEntityType.EXPERIMENT_TYPE,
            note.experiment_type,
            properties={"experiment_type": note.experiment_type},
        )
        touched_entities.add(experiment_type_entity.id)

    file_entities: list[KnowledgeEntity] = []
    for stored_file in db.query(StoredFile).filter(StoredFile.project_id == note.project_id, StoredFile.note_id == note.id).all():
        file_entity = _upsert_entity(
            db,
            note.project_id,
            KnowledgeEntityType.FILE,
            stored_file.original_filename,
            source_type="file",
            source_id=stored_file.id,
            properties={
                "file_id": stored_file.id,
                "category": str(stored_file.file_category.value if hasattr(stored_file.file_category, "value") else stored_file.file_category),
                "status": str(stored_file.status.value if hasattr(stored_file.status, "value") else stored_file.status),
            },
        )
        file_entities.append(file_entity)
        touched_entities.add(file_entity.id)

    # Extracted entities from rule-based text extraction
    extracted = extract_terms(fixed_fields, content)
    extracted_entity_list: list[tuple[KnowledgeEntityType, KnowledgeEntity, list[str]]] = []
    for entity_type, labels in extracted.items():
        for label in labels:
            roles = _inferred_roles(entity_type, label)
            entity = _upsert_entity(
                db,
                note.project_id,
                entity_type,
                label,
                properties={"extraction": "rule_based"},
            )
            extracted_entity_list.append((entity_type, entity, roles))
            touched_entities.add(entity.id)

    # Structured-field entities
    structured_entity_list: list[tuple[KnowledgeEntityType, KnowledgeEntity, set[str]]] = []
    for entity_type, role_items in _structured_roles(fixed_fields).items():
        for label, roles in role_items.items():
            entity = _upsert_entity(db, note.project_id, entity_type, label)
            structured_entity_list.append((entity_type, entity, roles))
            touched_entities.add(entity.id)

    # Single flush for all entities — populates auto-generated IDs
    db.flush()

    # ------------------------------------------------------------------
    # Phase 2: Create / update all relations, then flush once
    # ------------------------------------------------------------------
    relation_by_type = {
        KnowledgeEntityType.REAGENT: KnowledgeRelationType.USES_REAGENT,
        KnowledgeEntityType.INSTRUMENT: KnowledgeRelationType.USES_INSTRUMENT,
        KnowledgeEntityType.SAMPLE: KnowledgeRelationType.USES_SAMPLE,
        KnowledgeEntityType.RESULT: KnowledgeRelationType.PRODUCES_RESULT,
        KnowledgeEntityType.BIOLOGICAL_SOURCE: KnowledgeRelationType.HAS_BIOLOGICAL_SOURCE,
        KnowledgeEntityType.CONDITION: KnowledgeRelationType.HAS_CONDITION,
        KnowledgeEntityType.SOFTWARE: KnowledgeRelationType.USES_SOFTWARE,
        KnowledgeEntityType.IDENTIFIER: KnowledgeRelationType.HAS_IDENTIFIER,
    }

    # In-memory tracker for relation dedup (avoids per-relation flush)
    _pending_rels: dict[tuple[int, int, int, str], KnowledgeRelation] = {}
    _relation_objects: list[KnowledgeRelation] = []

    # Source relations
    _relation_objects.append(
        _upsert_relation(
            db, note.project_id, project_entity, note_entity,
            KnowledgeRelationType.HAS_NOTE,
            source_type="note", source_id=note.id,
            _pending=_pending_rels,
        )
    )
    if owner_entity is not None:
        _relation_objects.append(
            _upsert_relation(
                db, note.project_id, note_entity, owner_entity,
                KnowledgeRelationType.CREATED_BY,
                source_type="note", source_id=note.id,
                _pending=_pending_rels,
            )
        )
    if experiment_type_entity is not None:
        _relation_objects.append(
            _upsert_relation(
                db, note.project_id, note_entity, experiment_type_entity,
                KnowledgeRelationType.HAS_EXPERIMENT_TYPE,
                source_type="note", source_id=note.id,
                _pending=_pending_rels,
            )
        )
    for file_entity in file_entities:
        _relation_objects.append(
            _upsert_relation(
                db, note.project_id, note_entity, file_entity,
                KnowledgeRelationType.HAS_ATTACHMENT,
                source_type="note", source_id=note.id,
                _pending=_pending_rels,
            )
        )

    # Rule-based extraction relations
    for entity_type, entity, roles in extracted_entity_list:
        _relation_objects.append(
            _upsert_relation(
                db, note.project_id, note_entity, entity,
                relation_by_type[entity_type],
                source_type="note_extraction", source_id=note.id,
                confidence=0.7,
                properties={"method": "rule_based", "roles": roles},
                _pending=_pending_rels,
            )
        )

    # Structured-field relations
    for entity_type, entity, roles in structured_entity_list:
        _relation_objects.append(
            _upsert_relation(
                db, note.project_id, note_entity, entity,
                relation_by_type[entity_type],
                source_type="note_extraction", source_id=note.id,
                confidence=0.8,
                properties={"method": "structured_field", "roles": sorted(roles)},
                _pending=_pending_rels,
            )
        )

    # Single flush for all relations — populates auto-generated IDs
    db.flush()

    # Now that IDs are populated, collect them for the run record
    touched_relations.update(r.id for r in _relation_objects if r.id is not None)

    run = _record_run(
        db,
        note,
        triggered_by,
        len(touched_entities),
        len(touched_relations),
        KnowledgeExtractionStatus.COMPLETED.value,
        "Knowledge graph extraction completed",
    )
    db.flush()
    return run


def extract_terms(fixed_fields: dict, content: dict) -> dict[KnowledgeEntityType, list[str]]:
    """Extract entity terms from structured + free-text note content."""
    result: dict[KnowledgeEntityType, list[str]] = {entity_type: [] for entity_type in STRUCTURED_ALIASES}
    _collect_from_structured(fixed_fields, result)
    _collect_from_structured(content, result)
    text = "\n".join(flatten_text([fixed_fields, content]))
    for entity_type, patterns in TEXT_PATTERNS.items():
        for pattern in patterns:
            for match in re.findall(pattern, text, flags=re.IGNORECASE):
                result[entity_type].extend(split_terms(match, keep_sentence=entity_type == KnowledgeEntityType.RESULT))
    normalized = normalize_text(text)
    if "htseq 生成基因级原始计数" in normalized or "raw gene-level count" in normalized:
        result[KnowledgeEntityType.RESULT].extend(["基因级 HTSeq 计数矩阵", "不是原始 FASTQ"])
    if "不据此进行差异表达显著性推断" in normalized:
        result[KnowledgeEntityType.RESULT].append("不据此进行差异表达显著性推断")
    return {entity_type: dedupe_labels(labels) for entity_type, labels in result.items() if labels}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _upsert_entity(
    db: Session,
    project_id: int,
    entity_type: KnowledgeEntityType,
    label: str,
    source_type: str | None = None,
    source_id: int | None = None,
    properties: dict | None = None,
) -> KnowledgeEntity:
    cl = clean_label(label)
    normalized = normalize_entity_label(cl)
    uses_source_key = source_type in {"project", "note", "user", "file"} and source_id is not None
    natural_key = (
        source_natural_key(entity_type, source_type, source_id)
        if uses_source_key
        else f"{entity_type.value}:{normalized}"
    )
    entity = (
        db.query(KnowledgeEntity)
        .filter(KnowledgeEntity.project_id == project_id, KnowledgeEntity.natural_key == natural_key)
        .first()
    )
    if entity is None and not uses_source_key:
        candidates = (
            db.query(KnowledgeEntity)
            .filter(
                KnowledgeEntity.project_id == project_id,
                KnowledgeEntity.entity_type == entity_type.value,
                KnowledgeEntity.source_type.is_(None),
            )
            .all()
        )
        entity = next(
            (
                candidate
                for candidate in candidates
                if normalize_entity_label(candidate.label) == normalized
            ),
            None,
        )
    if entity is None:
        entity = KnowledgeEntity(
            project_id=project_id,
            entity_type=entity_type.value,
            label=cl,
            normalized_label=normalized,
            natural_key=natural_key,
            source_type=source_type,
            source_id=source_id,
            properties=properties or {},
        )
        db.add(entity)
        db.flush()
        return entity
    entity.label = cl
    entity.normalized_label = normalized
    entity.natural_key = natural_key
    entity.properties = {**(entity.properties or {}), **(properties or {})}
    db.flush()
    return entity


def _upsert_relation(
    db: Session,
    project_id: int,
    source: KnowledgeEntity,
    target: KnowledgeEntity,
    relation_type: KnowledgeRelationType,
    source_type: str | None = None,
    source_id: int | None = None,
    confidence: float = 1.0,
    properties: dict | None = None,
    _pending: dict[tuple[int, int, int, str], KnowledgeRelation] | None = None,
) -> KnowledgeRelation:
    dedup_key = (source.id, target.id, project_id, relation_type.value)

    # Check in-memory pending relations first (avoids DB round-trip)
    if _pending is not None and dedup_key in _pending:
        relation = _pending[dedup_key]
        relation.source_type = source_type or relation.source_type
        relation.source_id = source_id or relation.source_id
        relation.confidence = confidence
        current_properties = relation.properties or {}
        merged_properties = {**current_properties, **(properties or {})}
        roles = set(current_properties.get("roles", [])) | set((properties or {}).get("roles", []))
        if roles:
            merged_properties["roles"] = sorted(roles)
        relation.properties = merged_properties
        return relation

    relation = (
        db.query(KnowledgeRelation)
        .filter(
            KnowledgeRelation.project_id == project_id,
            KnowledgeRelation.source_entity_id == source.id,
            KnowledgeRelation.target_entity_id == target.id,
            KnowledgeRelation.relation_type == relation_type.value,
        )
        .first()
    )
    if relation is None:
        relation = KnowledgeRelation(
            project_id=project_id,
            source_entity_id=source.id,
            target_entity_id=target.id,
            relation_type=relation_type.value,
            source_type=source_type,
            source_id=source_id,
            confidence=confidence,
            properties=properties or {},
        )
        db.add(relation)
        if _pending is not None:
            _pending[dedup_key] = relation
        return relation
    relation.source_type = source_type or relation.source_type
    relation.source_id = source_id or relation.source_id
    relation.confidence = confidence
    current_properties = relation.properties or {}
    merged_properties = {**current_properties, **(properties or {})}
    roles = set(current_properties.get("roles", [])) | set((properties or {}).get("roles", []))
    if roles:
        merged_properties["roles"] = sorted(roles)
    relation.properties = merged_properties
    return relation


def _record_run(
    db: Session,
    note: ExperimentNote,
    triggered_by: int,
    extracted_entities: int,
    extracted_relations: int,
    status: str,
    message: str,
) -> KnowledgeExtractionRun:
    run = KnowledgeExtractionRun(
        project_id=note.project_id,
        note_id=note.id,
        triggered_by=triggered_by,
        status=status,
        extracted_entities=extracted_entities,
        extracted_relations=extracted_relations,
        message=message,
    )
    db.add(run)
    db.flush()
    return run


def _clear_note_extraction(db: Session, note_id: int) -> None:
    relations = (
        db.query(KnowledgeRelation)
        .filter(
            KnowledgeRelation.source_type.in_(("note", "note_extraction")),
            KnowledgeRelation.source_id == note_id,
        )
        .all()
    )
    note_entity_ids = {
        entity_id
        for (entity_id,) in db.query(KnowledgeEntity.id)
        .filter(KnowledgeEntity.source_type == "note", KnowledgeEntity.source_id == note_id)
        .all()
    }
    maybe_orphan_entity_ids = {relation.target_entity_id for relation in relations} | note_entity_ids
    for relation in relations:
        db.delete(relation)
    db.flush()
    for entity_id in maybe_orphan_entity_ids:
        entity = db.get(KnowledgeEntity, entity_id)
        if entity is None:
            continue
        relation_count = (
            db.query(KnowledgeRelation)
            .filter(or_(KnowledgeRelation.source_entity_id == entity_id, KnowledgeRelation.target_entity_id == entity_id))
            .count()
        )
        if relation_count == 0 and (entity.source_type is None or entity.id in note_entity_ids):
            db.delete(entity)
    db.flush()


def _inferred_roles(entity_type: KnowledgeEntityType, label: str) -> list[str]:
    if entity_type != KnowledgeEntityType.RESULT:
        return []
    normalized = normalize_text(label)
    roles: list[str] = []
    if "total_count" in normalized:
        roles.append("total_count")
    if "detected_gene_rows" in normalized:
        roles.append("detected_gene_rows")
    if "count_matrix_gene_rows" in normalized:
        roles.append("count_matrix_gene_rows")
    if "fastq" in normalized or "差异表达" in normalized or "基因级 htseq 计数矩阵" in normalized:
        roles.append("data_boundary")
    if "rin" in normalized or "quality" in normalized:
        roles.append("quality_result")
    return roles


def _collect_from_structured(value: object, result: dict[KnowledgeEntityType, list[str]], parent_key: str = "") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).lower()
            exact_type = STRUCTURED_FIELD_TYPES.get(key_text)
            if exact_type is not None:
                result[exact_type].extend(
                    split_terms(item, keep_sentence=exact_type == KnowledgeEntityType.RESULT)
                )
            else:
                for entity_type, aliases in STRUCTURED_ALIASES.items():
                    if any(alias.lower() in key_text for alias in aliases):
                        result[entity_type].extend(
                            split_terms(item, keep_sentence=entity_type == KnowledgeEntityType.RESULT)
                        )
            _collect_from_structured(item, result, key_text)
    elif isinstance(value, list):
        for item in value:
            _collect_from_structured(item, result, parent_key)


def _structured_roles(
    fields: dict,
) -> dict[KnowledgeEntityType, dict[str, set[str]]]:
    by_type: dict[KnowledgeEntityType, dict[str, set[str]]] = {}
    for key, role in STRUCTURED_FIELD_ROLES.items():
        if key not in fields:
            continue
        entity_type = STRUCTURED_FIELD_TYPES[key]
        labels = split_terms(fields[key], keep_sentence=entity_type == KnowledgeEntityType.RESULT)
        target = by_type.setdefault(entity_type, {})
        for label in labels:
            target.setdefault(clean_label(label), set()).add(role)
    return by_type
