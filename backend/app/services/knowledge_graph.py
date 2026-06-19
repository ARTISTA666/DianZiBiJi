from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

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
from app.core.config import get_settings


STRUCTURED_ALIASES: dict[KnowledgeEntityType, tuple[str, ...]] = {
    KnowledgeEntityType.REAGENT: ("reagent", "reagents", "试剂", "材料", "药品"),
    KnowledgeEntityType.INSTRUMENT: ("instrument", "instruments", "仪器", "设备"),
    KnowledgeEntityType.SAMPLE: ("sample", "samples", "样本", "样品"),
    KnowledgeEntityType.RESULT: ("result", "results", "结果", "观察", "结论"),
}

TEXT_PATTERNS: dict[KnowledgeEntityType, tuple[str, ...]] = {
    KnowledgeEntityType.REAGENT: (r"(?:reagents?|试剂|材料|药品)[:：]\s*([^\n。；;]+)",),
    KnowledgeEntityType.INSTRUMENT: (r"(?:instruments?|仪器|设备)[:：]\s*([^\n。；;]+)",),
    KnowledgeEntityType.SAMPLE: (r"(?:samples?|样本|样品)[:：]\s*([^\n。；;]+)",),
    KnowledgeEntityType.RESULT: (r"(?:results?|结果|观察|结论)[:：]\s*([^\n]+)",),
}

RELATION_LABELS = {
    KnowledgeRelationType.HAS_NOTE.value: "包含笔记",
    KnowledgeRelationType.CREATED_BY.value: "创建者",
    KnowledgeRelationType.HAS_ATTACHMENT.value: "关联附件",
    KnowledgeRelationType.HAS_EXPERIMENT_TYPE.value: "实验类型",
    KnowledgeRelationType.USES_REAGENT.value: "使用试剂",
    KnowledgeRelationType.USES_INSTRUMENT.value: "使用仪器",
    KnowledgeRelationType.USES_SAMPLE.value: "使用样本",
    KnowledgeRelationType.PRODUCES_RESULT.value: "产生结果",
}

ENTITY_LABELS = {
    KnowledgeEntityType.PROJECT.value: "项目",
    KnowledgeEntityType.NOTE.value: "实验笔记",
    KnowledgeEntityType.USER.value: "人员",
    KnowledgeEntityType.FILE.value: "附件资料",
    KnowledgeEntityType.EXPERIMENT_TYPE.value: "实验类型",
    KnowledgeEntityType.REAGENT.value: "试剂",
    KnowledgeEntityType.INSTRUMENT.value: "仪器",
    KnowledgeEntityType.SAMPLE.value: "样本",
    KnowledgeEntityType.RESULT.value: "实验结果",
}

QUERY_RELATION_HINTS = {
    KnowledgeRelationType.HAS_NOTE.value: ("笔记", "记录", "已审核", "包含", "note", "notes"),
    KnowledgeRelationType.USES_REAGENT.value: ("试剂", "材料", "药品", "reagent", "reagents"),
    KnowledgeRelationType.USES_INSTRUMENT.value: ("仪器", "设备", "instrument", "instruments"),
    KnowledgeRelationType.USES_SAMPLE.value: ("样本", "样品", "sample", "samples"),
    KnowledgeRelationType.PRODUCES_RESULT.value: ("结果", "观察", "结论", "result", "results"),
    KnowledgeRelationType.HAS_ATTACHMENT.value: ("附件", "资料", "文件", "attachment", "file"),
    KnowledgeRelationType.CREATED_BY.value: ("谁", "人员", "创建", "负责人", "user", "creator"),
    KnowledgeRelationType.HAS_EXPERIMENT_TYPE.value: ("类型", "实验类型", "type"),
}


class KnowledgeGraphService:
    def extract_note(
        self,
        db: Session,
        note: ExperimentNote,
        triggered_by: int,
        rebuild: bool = True,
    ) -> KnowledgeExtractionRun:
        if rebuild:
            self._clear_note_extraction(db, note.id)

        touched_entities: set[int] = set()
        touched_relations: set[int] = set()

        project = db.get(Project, note.project_id)
        if project is None:
            return self._record_run(db, note, triggered_by, 0, 0, KnowledgeExtractionStatus.FAILED.value, "Project not found")

        project_entity = self._upsert_entity(
            db,
            note.project_id,
            KnowledgeEntityType.PROJECT,
            project.name,
            source_type="project",
            source_id=project.id,
            properties={"project_id": project.id},
        )
        note_entity = self._upsert_entity(
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
        touched_relations.add(
            self._upsert_relation(
                db,
                note.project_id,
                project_entity,
                note_entity,
                KnowledgeRelationType.HAS_NOTE,
                source_type="note",
                source_id=note.id,
            ).id
        )

        owner = db.get(User, note.owner_user_id)
        if owner is not None:
            owner_entity = self._upsert_entity(
                db,
                note.project_id,
                KnowledgeEntityType.USER,
                owner.display_name or owner.username,
                source_type="user",
                source_id=owner.id,
                properties={"user_id": owner.id, "username": owner.username},
            )
            touched_entities.add(owner_entity.id)
            touched_relations.add(
                self._upsert_relation(
                    db,
                    note.project_id,
                    note_entity,
                    owner_entity,
                    KnowledgeRelationType.CREATED_BY,
                    source_type="note",
                    source_id=note.id,
                ).id
            )

        if note.experiment_type:
            experiment_type_entity = self._upsert_entity(
                db,
                note.project_id,
                KnowledgeEntityType.EXPERIMENT_TYPE,
                note.experiment_type,
                properties={"experiment_type": note.experiment_type},
            )
            touched_entities.add(experiment_type_entity.id)
            touched_relations.add(
                self._upsert_relation(
                    db,
                    note.project_id,
                    note_entity,
                    experiment_type_entity,
                    KnowledgeRelationType.HAS_EXPERIMENT_TYPE,
                    source_type="note",
                    source_id=note.id,
                ).id
            )

        for stored_file in db.query(StoredFile).filter(StoredFile.project_id == note.project_id, StoredFile.note_id == note.id).all():
            file_entity = self._upsert_entity(
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
            touched_entities.add(file_entity.id)
            touched_relations.add(
                self._upsert_relation(
                    db,
                    note.project_id,
                    note_entity,
                    file_entity,
                    KnowledgeRelationType.HAS_ATTACHMENT,
                    source_type="note",
                    source_id=note.id,
                ).id
            )

        version = db.get(NoteVersion, note.current_version_id) if note.current_version_id else None
        extracted = self.extract_terms(version.fixed_fields_json if version else {}, version.content_json if version else {})
        relation_by_type = {
            KnowledgeEntityType.REAGENT: KnowledgeRelationType.USES_REAGENT,
            KnowledgeEntityType.INSTRUMENT: KnowledgeRelationType.USES_INSTRUMENT,
            KnowledgeEntityType.SAMPLE: KnowledgeRelationType.USES_SAMPLE,
            KnowledgeEntityType.RESULT: KnowledgeRelationType.PRODUCES_RESULT,
        }
        for entity_type, labels in extracted.items():
            for label in labels:
                entity = self._upsert_entity(
                    db,
                    note.project_id,
                    entity_type,
                    label,
                    properties={"extraction": "rule_based"},
                )
                touched_entities.add(entity.id)
                touched_relations.add(
                    self._upsert_relation(
                        db,
                        note.project_id,
                        note_entity,
                        entity,
                        relation_by_type[entity_type],
                        source_type="note_extraction",
                        source_id=note.id,
                        confidence=0.7,
                        properties={"method": "rule_based"},
                    ).id
                )

        run = self._record_run(
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

    def extract_terms(self, fixed_fields: dict, content: dict) -> dict[KnowledgeEntityType, list[str]]:
        result: dict[KnowledgeEntityType, list[str]] = {entity_type: [] for entity_type in STRUCTURED_ALIASES}
        self._collect_from_structured(fixed_fields, result)
        self._collect_from_structured(content, result)
        text = "\n".join(self._flatten_text([fixed_fields, content]))
        for entity_type, patterns in TEXT_PATTERNS.items():
            for pattern in patterns:
                for match in re.findall(pattern, text, flags=re.IGNORECASE):
                    result[entity_type].extend(self._split_terms(match, keep_sentence=entity_type == KnowledgeEntityType.RESULT))
        return {entity_type: self._dedupe(labels) for entity_type, labels in result.items() if labels}

    def get_project_graph(self, db: Session, project_id: int) -> tuple[list[KnowledgeEntity], list[KnowledgeRelation]]:
        entities = db.query(KnowledgeEntity).filter(KnowledgeEntity.project_id == project_id).order_by(KnowledgeEntity.id).all()
        relations = db.query(KnowledgeRelation).filter(KnowledgeRelation.project_id == project_id).order_by(KnowledgeRelation.id).all()
        return entities, relations

    def find_relevant_context(self, db: Session, project_id: int, query: str, limit: int | None = None) -> list[dict]:
        settings = get_settings()
        limit = limit or settings.rag_graph_top_k
        entities, relations = self.get_project_graph(db, project_id)
        if not entities or not relations:
            return []
        entity_by_id = {entity.id: entity for entity in entities}
        tokens = self._query_tokens(query)
        relation_hints = self._relation_hints(query, tokens)
        scored: list[tuple[float, KnowledgeRelation]] = []
        for relation in relations:
            source = entity_by_id.get(relation.source_entity_id)
            target = entity_by_id.get(relation.target_entity_id)
            if source is None or target is None:
                continue
            score = self._score_relation(source, target, relation, tokens, relation_hints)
            scored.append((score, relation))
        scored.sort(key=lambda item: (item[0], item[1].confidence, item[1].id), reverse=True)
        relevant = [(score, relation) for score, relation in scored if score >= settings.rag_graph_min_score][:limit]
        return [self._context_item(entity_by_id, relation, score) for score, relation in relevant]

    def format_context_for_prompt(self, context_items: list[dict], max_chars: int = 1400) -> str:
        if not context_items:
            return ""
        lines = ["实验知识图谱上下文："]
        for index, item in enumerate(context_items, start=1):
            lines.append(
                f"- [G{index}] "
                f"[{item['source_entity_type_label']}] {item['source_label']} "
                f"--{item['relation_label']}--> "
                f"[{item['target_entity_type_label']}] {item['target_label']} "
                f"(置信度 {item['confidence']:.2f})"
            )
        text = "\n".join(lines)
        return text[:max_chars]

    def get_note_graph(self, db: Session, note: ExperimentNote) -> tuple[list[KnowledgeEntity], list[KnowledgeRelation]]:
        note_key = self._source_natural_key(KnowledgeEntityType.NOTE, "note", note.id)
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

    def _upsert_entity(
        self,
        db: Session,
        project_id: int,
        entity_type: KnowledgeEntityType,
        label: str,
        source_type: str | None = None,
        source_id: int | None = None,
        properties: dict | None = None,
    ) -> KnowledgeEntity:
        clean_label = self._clean_label(label)
        normalized_label = self._normalize_entity_label(clean_label)
        uses_source_key = source_type in {"project", "note", "user", "file"} and source_id is not None
        natural_key = (
            self._source_natural_key(entity_type, source_type, source_id)
            if uses_source_key
            else f"{entity_type.value}:{normalized_label}"
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
                    if self._normalize_entity_label(candidate.label) == normalized_label
                ),
                None,
            )
        if entity is None:
            entity = KnowledgeEntity(
                project_id=project_id,
                entity_type=entity_type.value,
                label=clean_label,
                normalized_label=normalized_label,
                natural_key=natural_key,
                source_type=source_type,
                source_id=source_id,
                properties=properties or {},
            )
            db.add(entity)
            db.flush()
            return entity
        entity.label = clean_label
        entity.normalized_label = normalized_label
        entity.natural_key = natural_key
        entity.properties = {**(entity.properties or {}), **(properties or {})}
        db.flush()
        return entity

    def _upsert_relation(
        self,
        db: Session,
        project_id: int,
        source: KnowledgeEntity,
        target: KnowledgeEntity,
        relation_type: KnowledgeRelationType,
        source_type: str | None = None,
        source_id: int | None = None,
        confidence: float = 1.0,
        properties: dict | None = None,
    ) -> KnowledgeRelation:
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
            db.flush()
            return relation
        relation.source_type = source_type or relation.source_type
        relation.source_id = source_id or relation.source_id
        relation.confidence = confidence
        relation.properties = {**(relation.properties or {}), **(properties or {})}
        db.flush()
        return relation

    def _record_run(
        self,
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

    def _clear_note_extraction(self, db: Session, note_id: int) -> None:
        relations = (
            db.query(KnowledgeRelation)
            .filter(
                KnowledgeRelation.source_type.in_(("note", "note_extraction")),
                KnowledgeRelation.source_id == note_id,
            )
            .all()
        )
        maybe_orphan_entity_ids = {relation.target_entity_id for relation in relations}
        for relation in relations:
            db.delete(relation)
        db.flush()
        for entity_id in maybe_orphan_entity_ids:
            entity = db.get(KnowledgeEntity, entity_id)
            if entity is None or entity.source_type is not None:
                continue
            relation_count = (
                db.query(KnowledgeRelation)
                .filter(or_(KnowledgeRelation.source_entity_id == entity_id, KnowledgeRelation.target_entity_id == entity_id))
                .count()
            )
            if relation_count == 0:
                db.delete(entity)
        db.flush()

    def _context_item(
        self,
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
        }

    def _score_relation(
        self,
        source: KnowledgeEntity,
        target: KnowledgeEntity,
        relation: KnowledgeRelation,
        tokens: set[str],
        relation_hints: set[str],
    ) -> float:
        score = 0.0
        if relation.relation_type in relation_hints:
            score += 3.0
        haystacks = [
            self._normalize(source.label),
            self._normalize(target.label),
            source.entity_type,
            target.entity_type,
            relation.relation_type,
            RELATION_LABELS.get(relation.relation_type, ""),
        ]
        for token in tokens:
            for text in haystacks:
                normalized_text = self._normalize(text)
                if token and token == normalized_text:
                    score += 3.0
                elif token and (token in normalized_text or normalized_text in token):
                    score += 1.0
        if source.entity_type == KnowledgeEntityType.NOTE.value:
            score += 0.2
        if relation.source_type == "note_extraction":
            score += 0.3
        return score

    def _query_tokens(self, query: str) -> set[str]:
        raw_tokens = re.findall(r"[A-Za-z0-9_\-]+|[\u4e00-\u9fff]{2,}", query.lower())
        tokens = {self._normalize(token) for token in raw_tokens if len(self._normalize(token)) >= 2}
        normalized_query = self._normalize(query)
        if normalized_query:
            tokens.add(normalized_query)
        return tokens

    def _relation_hints(self, query: str, tokens: set[str]) -> set[str]:
        normalized_query = self._normalize(query)
        hints: set[str] = set()
        for relation_type, keywords in QUERY_RELATION_HINTS.items():
            if any(keyword.lower() in normalized_query or keyword.lower() in tokens for keyword in keywords):
                hints.add(relation_type)
        return hints

    def _collect_from_structured(self, value: object, result: dict[KnowledgeEntityType, list[str]], parent_key: str = "") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                key_text = str(key).lower()
                for entity_type, aliases in STRUCTURED_ALIASES.items():
                    if any(alias.lower() in key_text for alias in aliases):
                        result[entity_type].extend(
                            self._split_terms(item, keep_sentence=entity_type == KnowledgeEntityType.RESULT)
                        )
                self._collect_from_structured(item, result, key_text)
        elif isinstance(value, list):
            for item in value:
                self._collect_from_structured(item, result, parent_key)

    def _flatten_text(self, values: Iterable[object]) -> list[str]:
        texts: list[str] = []
        for value in values:
            if isinstance(value, str):
                if value.strip():
                    texts.append(value.strip())
            elif isinstance(value, dict):
                for key, item in value.items():
                    texts.extend(self._flatten_text([str(key), item]))
            elif isinstance(value, list):
                texts.extend(self._flatten_text(value))
            elif value is not None:
                texts.append(str(value))
        return texts

    def _split_terms(self, value: object, keep_sentence: bool = False) -> list[str]:
        if isinstance(value, list):
            terms: list[str] = []
            for item in value:
                terms.extend(self._split_terms(item, keep_sentence=keep_sentence))
            return terms
        if not isinstance(value, str):
            return [str(value).strip()] if value is not None and str(value).strip() else []
        text = value.strip()
        if not text:
            return []
        if keep_sentence:
            return [item.strip(" -\t") for item in re.split(r"[\n；;]+", text) if item.strip(" -\t")]
        return [item.strip(" -\t") for item in re.split(r"[,，、/；;\n]+", text) if item.strip(" -\t")]

    def _dedupe(self, labels: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for label in labels:
            clean = self._clean_label(label)
            key = self._normalize_entity_label(clean)
            if clean and key not in seen:
                seen.add(key)
                deduped.append(clean)
        return deduped

    def _clean_label(self, label: str) -> str:
        return re.sub(r"\s+", " ", str(label)).strip()

    def _normalize(self, label: str) -> str:
        return self._clean_label(label).lower()

    def _normalize_entity_label(self, label: str) -> str:
        normalized = unicodedata.normalize("NFKC", self._clean_label(label)).lower()
        without_punctuation = "".join(
            " " if unicodedata.category(character).startswith("P") else character
            for character in normalized
        )
        return re.sub(r"\s+", " ", without_punctuation).strip()

    def _source_natural_key(self, entity_type: KnowledgeEntityType, source_type: str | None, source_id: int | None) -> str:
        return f"{entity_type.value}:{source_type}:{source_id}"
