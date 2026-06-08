from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from time import perf_counter

from sqlalchemy.orm import Session

from app.models.ai import AgentGenerationRun, AgentRunStatus, AgentTaskType
from app.models.file import FileCategory, FileStatus, StoredFile
from app.models.knowledge_graph import KnowledgeEntity, KnowledgeRelation
from app.models.note import ExperimentNote, NoteStatus, NoteVersion
from app.services.knowledge_graph import ENTITY_LABELS, RELATION_LABELS


TASK_LABELS = {
    AgentTaskType.EXPERIMENT_SUMMARY.value: "实验总结",
    AgentTaskType.WEEKLY_REPORT.value: "周报",
    AgentTaskType.STAGE_REPORT.value: "项目阶段报告",
    AgentTaskType.GRAPH_OVERVIEW.value: "实验过程图谱概览",
}


class AgentGenerationService:
    """固定任务型智能体：从笔记、资料和图谱生成可追溯草稿。"""

    def generate(
        self,
        db: Session,
        project_id: int,
        user_id: int,
        task_type: str,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> AgentGenerationRun:
        if task_type not in TASK_LABELS:
            raise ValueError("Unsupported agent task type")
        started = perf_counter()
        date_from, date_to = self._resolve_dates(task_type, date_from, date_to)
        notes = self._load_notes(db, project_id, date_from, date_to)
        attach_current_versions(db, notes)
        files = self._load_source_files(db, project_id)
        entities, relations = self._load_graph(db, project_id)
        relation_ids = self._select_relation_ids(entities, relations, notes, task_type)
        title = self._title(task_type, project_id, date_from, date_to)
        body = self._body(task_type, project_id, notes, files, entities, relations, relation_ids, date_from, date_to)
        message = None if notes or task_type == AgentTaskType.GRAPH_OVERVIEW.value else "No approved notes in selected range"
        run = AgentGenerationRun(
            project_id=project_id,
            user_id=user_id,
            task_type=task_type,
            input_params_json={
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
            },
            title=title,
            body=body,
            source_note_ids_json=[note.id for note in notes],
            source_file_ids_json=[file.id for file in files],
            source_graph_relation_ids_json=relation_ids,
            status=AgentRunStatus.COMPLETED.value,
            response_ms=max(0, int((perf_counter() - started) * 1000)),
            message=message,
        )
        db.add(run)
        db.flush()
        return run

    def _resolve_dates(self, task_type: str, date_from: date | None, date_to: date | None) -> tuple[date | None, date | None]:
        if date_to is None and task_type == AgentTaskType.WEEKLY_REPORT.value:
            date_to = datetime.now(timezone.utc).date()
        if date_from is None and task_type == AgentTaskType.WEEKLY_REPORT.value and date_to is not None:
            date_from = date_to - timedelta(days=7)
        return date_from, date_to

    def _load_notes(self, db: Session, project_id: int, date_from: date | None, date_to: date | None) -> list[ExperimentNote]:
        query = (
            db.query(ExperimentNote)
            .filter(ExperimentNote.project_id == project_id, ExperimentNote.status == NoteStatus.APPROVED)
            .order_by(ExperimentNote.experiment_date.asc(), ExperimentNote.id.asc())
        )
        notes = query.all()
        if date_from is None and date_to is None:
            return notes
        filtered: list[ExperimentNote] = []
        for note in notes:
            if note.experiment_date is None:
                continue
            if date_from and note.experiment_date < date_from:
                continue
            if date_to and note.experiment_date > date_to:
                continue
            filtered.append(note)
        return filtered

    def _load_source_files(self, db: Session, project_id: int) -> list[StoredFile]:
        return (
            db.query(StoredFile)
            .filter(
                StoredFile.project_id == project_id,
                StoredFile.file_category == FileCategory.KNOWLEDGE_DOCUMENT,
                StoredFile.status == FileStatus.APPROVED,
            )
            .order_by(StoredFile.id.asc())
            .limit(12)
            .all()
        )

    def _load_graph(self, db: Session, project_id: int) -> tuple[list[KnowledgeEntity], list[KnowledgeRelation]]:
        entities = db.query(KnowledgeEntity).filter(KnowledgeEntity.project_id == project_id).order_by(KnowledgeEntity.id).all()
        relations = db.query(KnowledgeRelation).filter(KnowledgeRelation.project_id == project_id).order_by(KnowledgeRelation.id).all()
        return entities, relations

    def _select_relation_ids(
        self,
        entities: list[KnowledgeEntity],
        relations: list[KnowledgeRelation],
        notes: list[ExperimentNote],
        task_type: str,
    ) -> list[int]:
        if task_type == AgentTaskType.GRAPH_OVERVIEW.value:
            return [relation.id for relation in relations[:40]]
        note_ids = {note.id for note in notes}
        note_entity_ids = {
            entity.id
            for entity in entities
            if entity.source_type == "note" and entity.source_id in note_ids
        }
        selected = [
            relation.id
            for relation in relations
            if relation.source_entity_id in note_entity_ids or relation.target_entity_id in note_entity_ids
        ]
        return selected[:40]

    def _title(self, task_type: str, project_id: int, date_from: date | None, date_to: date | None) -> str:
        label = TASK_LABELS[task_type]
        if date_from or date_to:
            return f"{label} - 项目 {project_id} ({date_from or '开始'} ~ {date_to or '至今'})"
        return f"{label} - 项目 {project_id}"

    def _body(
        self,
        task_type: str,
        project_id: int,
        notes: list[ExperimentNote],
        files: list[StoredFile],
        entities: list[KnowledgeEntity],
        relations: list[KnowledgeRelation],
        relation_ids: list[int],
        date_from: date | None,
        date_to: date | None,
    ) -> str:
        entity_by_id = {entity.id: entity for entity in entities}
        selected_relations = [relation for relation in relations if relation.id in set(relation_ids)]
        lines = [
            f"## {TASK_LABELS[task_type]}",
            f"- 项目编号：{project_id}",
            f"- 生成范围：{date_from or '全部'} ~ {date_to or '至今'}",
            f"- 来源实验笔记：{len(notes)} 条",
            f"- 来源资料：{len(files)} 份",
            f"- 图谱依据关系：{len(selected_relations)} 条",
            "",
        ]
        if task_type == AgentTaskType.GRAPH_OVERVIEW.value:
            lines.extend(self._graph_overview_lines(entity_by_id, selected_relations))
            return "\n".join(lines)
        if not notes:
            lines.append("当前范围内暂无已审核实验笔记，无法形成正式实验总结。")
            if files:
                lines.append("")
                lines.append("可用资料来源：")
                lines.extend([f"- {file.original_filename}" for file in files])
            return "\n".join(lines)
        lines.append("### 实验记录概览")
        for note in notes:
            version = self._version_snapshot(note)
            lines.append(f"- {note.title}（{note.experiment_type}，{note.experiment_date or '未填日期'}）")
            for key, value in list(version.items())[:4]:
                text = self._short_value(value)
                if text:
                    lines.append(f"  - {key}：{text}")
        lines.append("")
        lines.append("### 主要结论")
        result_lines = self._result_lines(notes)
        lines.extend(result_lines or ["- 已完成实验记录整理，后续可结合评价数据补充效果分析。"])
        lines.append("")
        lines.append("### 知识图谱依据")
        lines.extend(self._relation_lines(entity_by_id, selected_relations[:12]) or ["- 当前范围内未检索到直接关联的图谱关系。"])
        lines.append("")
        lines.append("### 资料来源")
        lines.extend([f"- {file.original_filename}" for file in files] or ["- 当前项目暂无已审核资料库文件。"])
        lines.append("")
        lines.append("### 后续建议")
        lines.append("- 对关键实验结果继续补充附件资料和结果字段，便于图谱抽取与 RAG 问答引用。")
        lines.append("- 对生成内容进行人工确认后，可作为论文实验管理流程截图和案例材料。")
        return "\n".join(lines)

    def _version_snapshot(self, note: ExperimentNote) -> dict:
        version = getattr(note, "_agent_version", None)
        if version is None:
            return {}
        return version.fixed_fields_json or {}

    def _result_lines(self, notes: list[ExperimentNote]) -> list[str]:
        lines: list[str] = []
        for note in notes:
            version = self._version_snapshot(note)
            for key, value in version.items():
                if "result" in str(key).lower() or "结果" in str(key):
                    text = self._short_value(value)
                    if text:
                        lines.append(f"- {note.title}：{text}")
        return lines

    def _graph_overview_lines(self, entity_by_id: dict[int, KnowledgeEntity], relations: list[KnowledgeRelation]) -> list[str]:
        lines = ["### 实验过程关联概览"]
        lines.extend(self._relation_lines(entity_by_id, relations[:24]) or ["- 当前项目暂无知识图谱关系。"])
        lines.append("")
        lines.append("### 说明")
        lines.append("- 该概览基于系统已抽取的实验知识图谱生成，可用于论文中说明实验实体关系组织能力。")
        return lines

    def _relation_lines(self, entity_by_id: dict[int, KnowledgeEntity], relations: list[KnowledgeRelation]) -> list[str]:
        lines: list[str] = []
        for relation in relations:
            source = entity_by_id.get(relation.source_entity_id)
            target = entity_by_id.get(relation.target_entity_id)
            if source is None or target is None:
                continue
            lines.append(
                f"- [{ENTITY_LABELS.get(source.entity_type, source.entity_type)}] {source.label} "
                f"--{RELATION_LABELS.get(relation.relation_type, relation.relation_type)}--> "
                f"[{ENTITY_LABELS.get(target.entity_type, target.entity_type)}] {target.label}"
            )
        return lines

    def _short_value(self, value: object) -> str:
        if isinstance(value, list):
            text = "、".join(str(item) for item in value)
        elif isinstance(value, dict):
            text = "；".join(f"{key}: {val}" for key, val in value.items())
        else:
            text = str(value)
        return text.strip()[:180]


def attach_current_versions(db: Session, notes: list[ExperimentNote]) -> None:
    version_ids = [note.current_version_id for note in notes if note.current_version_id]
    if not version_ids:
        return
    versions = {
        version.id: version
        for version in db.query(NoteVersion).filter(NoteVersion.id.in_(version_ids)).all()
    }
    for note in notes:
        setattr(note, "_agent_version", versions.get(note.current_version_id))
