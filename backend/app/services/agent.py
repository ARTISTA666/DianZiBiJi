from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from time import perf_counter

from sqlalchemy.orm import Session

from app.models.ai import AgentGenerationRun, AgentRunStatus, AgentTaskType
from app.models.file import FileCategory, FileStatus, StoredFile
from app.models.knowledge_graph import KnowledgeEntity, KnowledgeRelation
from app.models.note import ExperimentNote, NoteStatus, NoteVersion
from app.services.knowledge_graph import ENTITY_LABELS, RELATION_LABELS, KnowledgeGraphService
from app.services.citation_audit import audit_citations
from app.services.deepseek import DeepSeekClient, DeepSeekConfigError, DeepSeekRequestError
from app.services.prompts import PROMPTS


TASK_LABELS = {
    AgentTaskType.EXPERIMENT_SUMMARY.value: "实验总结",
    AgentTaskType.WEEKLY_REPORT.value: "周报",
    AgentTaskType.STAGE_REPORT.value: "项目阶段报告",
    AgentTaskType.GRAPH_OVERVIEW.value: "实验过程图谱概览",
}
AGENT_PROMPT_VERSION = PROMPTS["agent_writer"].version

# ── Tuning constants ──────────────────────────────────────────────────────
MAX_SOURCE_FILES = 12              # Max source files loaded for agent context
MAX_RELATIONS_DISPLAY = 24         # Max relations shown in body sections
MAX_OVERVIEW_RELATIONS = 24        # Max relations shown in graph overview
MAX_NOTE_FIELDS_DISPLAY = 4        # Max note fields included in context
MAX_VALUE_DISPLAY_LENGTH = 180     # Truncation length for field values
AGENT_GENERATION_MAX_TOKENS = 2200 # Max tokens for agent LLM calls
WEEKLY_REPORT_DEFAULT_DAYS = 7     # Default look-back window for weekly reports
MAX_AGENT_CONTEXT_CHARS = 18_000   # Keep provider input bounded and reproducible
_CONTEXT_TRUNCATION_SUFFIX = (
    f"\n\n[项目上下文已截断至 {MAX_AGENT_CONTEXT_CHARS} 个字符；未展示的细节不得据此推断。]"
)
_CITATION_LINE = re.compile(r"^\s*-\s+\[([NFR])(\d+)\]")


def _cap_context(context: str) -> str:
    if len(context) <= MAX_AGENT_CONTEXT_CHARS:
        return context
    visible_lines: list[str] = []
    visible_length = 0
    for line in context.splitlines():
        extra = len(line) + (1 if visible_lines else 0)
        if visible_length + extra + len(_CONTEXT_TRUNCATION_SUFFIX) > MAX_AGENT_CONTEXT_CHARS:
            break
        visible_lines.append(line)
        visible_length += extra
    prefix = "\n".join(visible_lines)
    return prefix + _CONTEXT_TRUNCATION_SUFFIX if prefix else _CONTEXT_TRUNCATION_SUFFIX


def _visible_citation_ids(context: str) -> dict[str, set[int]]:
    visible = {"N": set(), "F": set(), "R": set()}
    for line in context.splitlines():
        match = _CITATION_LINE.match(line)
        if match:
            visible[match.group(1)].add(int(match.group(2)))
    return visible


def _inline_text(value: object) -> str:
    return str(value).replace("\r", " ").replace("\n", " ")


def _merge_generation_usage(target: dict, update: dict | None) -> None:
    """Accumulate numeric usage fields and keep the latest metadata fields."""
    for key, value in (update or {}).items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            previous = target.get(key)
            if not isinstance(previous, (int, float)) or isinstance(previous, bool):
                previous = 0
            target[key] = previous + value
        else:
            target[key] = value


@dataclass(frozen=True)
class _NoteWithContext:
    """ORM 对象与其关联版本的不可变组合，避免在 ORM 实例上挂载瞬态属性。"""
    note: ExperimentNote
    version: NoteVersion | None


class AgentGenerationFailure(RuntimeError):
    def __init__(self, message: str, run: AgentGenerationRun, status_code: int) -> None:
        super().__init__(message)
        self.run = run
        self.status_code = status_code


class AgentGenerationService:
    """按资料整理、内容生成、结果检查三个步骤生成可追溯草稿。"""

    async def generate(
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
        raw_notes = self._load_notes(db, project_id, date_from, date_to)
        notes = attach_current_versions(db, raw_notes)
        files = self._load_source_files(db, project_id)
        entities, relations = self._load_graph(db, project_id)
        relation_ids = self._select_relation_ids(entities, relations, notes, task_type)
        title = self._title(task_type, project_id, date_from, date_to)
        source_context = _cap_context(
            self._body(
                task_type,
                project_id,
                notes,
                files,
                entities,
                relations,
                relation_ids,
                date_from,
                date_to,
            )
        )
        visible_citations = _visible_citation_ids(source_context)
        evidence_available = (
            bool(relation_ids)
            if task_type == AgentTaskType.GRAPH_OVERVIEW.value
            else bool(notes or files or relation_ids)
        )
        steps = [
            {
                "key": "evidence",
                "name": "资料整理智能体",
                "status": "completed",
                "message": f"已读取 {len(notes)} 条审核笔记、{len(files)} 份资料和 {len(relation_ids)} 条图谱关系。",
            },
            {
                "key": "writer",
                "name": "内容生成智能体",
                "status": "running",
                "message": "正在调用 DeepSeek 生成草稿。",
            },
        ]
        input_params = {
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "collaboration_steps": steps,
        }
        system_prompt = PROMPTS["agent_writer"].system_prompt
        try:
            client = DeepSeekClient()
            result = await client.generate(
                system_prompt=system_prompt,
                user_prompt=(
                    f"任务类型：{TASK_LABELS[task_type]}\n"
                    f"请将以下可追溯项目数据整理为正式草稿：\n\n{source_context}"
                ),
                temperature=0.1,
                max_tokens=AGENT_GENERATION_MAX_TOKENS,
            )
        except (DeepSeekConfigError, DeepSeekRequestError) as exc:
            steps[1].update(status="failed", message=f"DeepSeek 调用失败：{exc}")
            run = AgentGenerationRun(
                project_id=project_id,
                user_id=user_id,
                task_type=task_type,
                input_params_json=input_params,
                title=title,
                body="",
                source_note_ids_json=[nw.note.id for nw in notes],
                source_file_ids_json=[file.id for file in files],
                source_graph_relation_ids_json=relation_ids,
                provider="deepseek",
                model_name=None,
                prompt_version=AGENT_PROMPT_VERSION,
                usage_json={},
                status=AgentRunStatus.FAILED.value,
                response_ms=max(0, int((perf_counter() - started) * 1000)),
                message=str(exc),
            )
            db.add(run)
            db.flush()
            status_code = 503 if isinstance(exc, DeepSeekConfigError) else 502
            raise AgentGenerationFailure(str(exc), run, status_code) from exc
        body = result["answer"]
        model_name = result.get("model")
        usage = dict(result.get("usage") or {})
        steps[1].update(status="completed", message=f"DeepSeek 已生成草稿，模型为 {result.get('model') or '未返回'}。")
        review = self._review_answer(
            body,
            note_ids=visible_citations["N"],
            file_ids=visible_citations["F"],
            relation_ids=visible_citations["R"],
            evidence_available=evidence_available,
        )
        steps.append(
            {
                "key": "reviewer",
                "name": "结果检查智能体",
                "status": "completed" if review["passed"] else "warning",
                "message": review["message"],
            }
        )
        repair_attempted = False
        if not review["passed"]:
            repair_attempted = True
            repair_step = {
                "key": "repair",
                "name": "引用修订智能体",
                "status": "running",
                "message": "正在根据检查结果修订引用。",
            }
            steps.append(repair_step)
            try:
                repair_result = await client.generate(
                    system_prompt=system_prompt,
                    user_prompt=(
                        f"原始任务：{TASK_LABELS[task_type]}\n"
                        f"可用项目资料：\n{source_context}\n\n"
                        f"待修订草稿：\n{body}\n\n"
                        f"检查结果：{review['message']}\n"
                        "请只输出修订后的完整草稿。只能使用上下文中真实存在的 [N数字]、[F数字]、[R数字] 编号；"
                        "证据不足的结论应删除或明确写为无法确认。"
                    ),
                    temperature=0.0,
                    max_tokens=AGENT_GENERATION_MAX_TOKENS,
                )
            except (DeepSeekConfigError, DeepSeekRequestError) as exc:
                repair_step.update(status="failed", message=f"自动修订失败：{exc}")
            else:
                body = repair_result["answer"]
                model_name = repair_result.get("model") or model_name
                _merge_generation_usage(usage, repair_result.get("usage"))
                repair_step.update(status="completed", message="已完成一次有上限的引用修订。")
                review = self._review_answer(
                    body,
                    note_ids=visible_citations["N"],
                    file_ids=visible_citations["F"],
                    relation_ids=visible_citations["R"],
                    evidence_available=evidence_available,
                )
                steps.append(
                    {
                        "key": "recheck",
                        "name": "结果复核智能体",
                        "status": "completed" if review["passed"] else "warning",
                        "message": review["message"],
                    }
                )
        input_params["repair_attempted"] = repair_attempted
        input_params["review_result"] = review
        messages: list[str] = []
        if not notes and task_type != AgentTaskType.GRAPH_OVERVIEW.value:
            messages.append("No approved notes in selected range")
        if not review["passed"]:
            messages.append("Citation validation still requires manual review")
        message = "; ".join(messages) or None
        run = AgentGenerationRun(
            project_id=project_id,
            user_id=user_id,
            task_type=task_type,
            input_params_json=input_params,
            title=title,
            body=body,
            source_note_ids_json=[nw.note.id for nw in notes],
            source_file_ids_json=[file.id for file in files],
            source_graph_relation_ids_json=relation_ids,
            provider="deepseek",
            model_name=model_name,
            prompt_version=AGENT_PROMPT_VERSION,
            usage_json=usage,
            status=(AgentRunStatus.COMPLETED.value if review["passed"] else AgentRunStatus.NEEDS_REVIEW.value),
            response_ms=max(0, int((perf_counter() - started) * 1000)),
            message=message,
        )
        db.add(run)
        db.flush()
        return run

    def _review_answer(
        self,
        body: str,
        *,
        note_ids: set[int],
        file_ids: set[int],
        relation_ids: set[int],
        evidence_available: bool | None = None,
    ) -> dict:
        review = audit_citations(
            body,
            allowed={"N": note_ids, "F": file_ids, "R": relation_ids},
        )
        if evidence_available and not (note_ids or file_ids or relation_ids) and not review["invalid_citations"]:
            review.update(
                passed=False,
                has_evidence=True,
                message="回答没有引用可见证据，需要人工复核。",
            )
        return review

    def _resolve_dates(self, task_type: str, date_from: date | None, date_to: date | None) -> tuple[date | None, date | None]:
        if date_to is None and task_type == AgentTaskType.WEEKLY_REPORT.value:
            date_to = datetime.now(timezone.utc).date()
        if date_from is None and task_type == AgentTaskType.WEEKLY_REPORT.value and date_to is not None:
            date_from = date_to - timedelta(days=WEEKLY_REPORT_DEFAULT_DAYS)
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
            .limit(MAX_SOURCE_FILES)
            .all()
        )

    def _load_graph(self, db: Session, project_id: int) -> tuple[list[KnowledgeEntity], list[KnowledgeRelation]]:
        return KnowledgeGraphService().get_project_graph(db, project_id)

    def _select_relation_ids(
        self,
        entities: list[KnowledgeEntity],
        relations: list[KnowledgeRelation],
        notes: list[_NoteWithContext],
        task_type: str,
    ) -> list[int]:
        visible_limit = (
            MAX_OVERVIEW_RELATIONS
            if task_type == AgentTaskType.GRAPH_OVERVIEW.value
            else MAX_RELATIONS_DISPLAY
        )
        if task_type == AgentTaskType.GRAPH_OVERVIEW.value:
            return [relation.id for relation in relations[:visible_limit]]
        note_ids = {nw.note.id for nw in notes}
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
        return selected[:visible_limit]

    def _title(self, task_type: str, project_id: int, date_from: date | None, date_to: date | None) -> str:
        label = TASK_LABELS[task_type]
        if date_from or date_to:
            return f"{label} - 项目 {project_id} ({date_from or '开始'} ~ {date_to or '至今'})"
        return f"{label} - 项目 {project_id}"

    def _body(
        self,
        task_type: str,
        project_id: int,
        notes: list[_NoteWithContext],
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
                lines.extend([f"- [F{file.id}] {_inline_text(file.original_filename)}" for file in files])
            return "\n".join(lines)
        lines.append("### 实验记录概览")
        for nw in notes:
            lines.append(
                f"- [N{nw.note.id}] {_inline_text(nw.note.title)}"
                f"（{_inline_text(nw.note.experiment_type)}，{nw.note.experiment_date or '未填日期'}）"
            )
            for version in self._version_snapshots(nw):
                for key, value in list(version.items())[:MAX_NOTE_FIELDS_DISPLAY]:
                    text = self._short_value(value)
                    if text:
                        lines.append(f"  - {_inline_text(key)}：{text}")
        lines.append("")
        lines.append("### 主要结论")
        result_lines = self._result_lines(notes)
        lines.extend(result_lines or ["- 已完成实验记录整理，后续可结合评价数据补充效果分析。"])
        lines.append("")
        lines.append("### 知识图谱依据")
        lines.extend(self._relation_lines(entity_by_id, selected_relations[:MAX_RELATIONS_DISPLAY]) or ["- 当前范围内未检索到直接关联的图谱关系。"])
        lines.append("")
        lines.append("### 资料来源")
        lines.extend(
            [f"- [F{file.id}] {_inline_text(file.original_filename)}" for file in files]
            or ["- 当前项目暂无已审核资料库文件。"]
        )
        lines.append("")
        lines.append("### 后续建议")
        lines.append("- 对关键实验结果继续补充附件资料和结果字段，便于图谱抽取与 RAG 问答引用。")
        lines.append("- 对生成内容进行人工确认后，可作为论文实验管理流程截图和案例材料。")
        return "\n".join(lines)

    def _version_snapshots(self, nw: _NoteWithContext) -> tuple[dict, ...]:
        if nw.version is None:
            return ()
        return (nw.version.fixed_fields_json or {}, nw.version.content_json or {})

    def _result_lines(self, notes: list[_NoteWithContext]) -> list[str]:
        lines: list[str] = []
        for nw in notes:
            for version in self._version_snapshots(nw):
                for key, value in version.items():
                    if "result" in str(key).lower() or "结果" in str(key):
                        text = self._short_value(value)
                        if text:
                            lines.append(f"- [N{nw.note.id}] {_inline_text(nw.note.title)}：{text}")
        return lines

    def _graph_overview_lines(self, entity_by_id: dict[int, KnowledgeEntity], relations: list[KnowledgeRelation]) -> list[str]:
        lines = ["### 实验过程关联概览"]
        lines.extend(self._relation_lines(entity_by_id, relations[:MAX_OVERVIEW_RELATIONS]) or ["- 当前项目暂无知识图谱关系。"])
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
                f"- [R{relation.id}] "
                f"[{_inline_text(ENTITY_LABELS.get(source.entity_type, source.entity_type))}] "
                f"{_inline_text(source.label)} "
                f"--{_inline_text(RELATION_LABELS.get(relation.relation_type, relation.relation_type))}--> "
                f"[{_inline_text(ENTITY_LABELS.get(target.entity_type, target.entity_type))}] "
                f"{_inline_text(target.label)}"
            )
        return lines

    def _short_value(self, value: object) -> str:
        if isinstance(value, list):
            text = "、".join(str(item) for item in value)
        elif isinstance(value, dict):
            text = "；".join(f"{key}: {val}" for key, val in value.items())
        else:
            text = str(value)
        return _inline_text(text).strip()[:MAX_VALUE_DISPLAY_LENGTH]


def attach_current_versions(db: Session, notes: list[ExperimentNote]) -> list[_NoteWithContext]:
    """将每条笔记与其当前版本打包为不可变的 _NoteWithContext，避免在 ORM 实例上挂载瞬态属性。"""
    version_ids = [note.current_version_id for note in notes if note.current_version_id]
    versions: dict[int, NoteVersion] = {}
    if version_ids:
        versions = {
            version.id: version
            for version in db.query(NoteVersion).filter(NoteVersion.id.in_(version_ids)).all()
        }
    return [
        _NoteWithContext(note=note, version=versions.get(note.current_version_id))
        for note in notes
    ]
