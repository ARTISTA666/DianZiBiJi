import json
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.note import ExperimentNote, NoteStatus, NoteVersion


class ReportDraftService:
    """从已审核的实验笔记生成日报/周报草稿"""

    def create_draft(
        self,
        db: Session,
        project_id: int,
        report_type: str = "daily",
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict:
        now = datetime.now(timezone.utc)
        if date_to is None:
            date_to = now.date()
        if date_from is None:
            if report_type == "weekly":
                date_from = date_to - timedelta(days=7)
            else:
                date_from = date_to

        notes = (
            db.query(ExperimentNote)
            .filter(
                ExperimentNote.project_id == project_id,
                ExperimentNote.status == NoteStatus.APPROVED,
            )
            .all()
        )

        # 按实验日期过滤
        filtered: list[ExperimentNote] = []
        for note in notes:
            nd = note.experiment_date
            if nd and date_from <= nd <= date_to:
                filtered.append(note)

        if not filtered:
            return {
                "title": f"项目 {project_id} 实验报告 ({date_from} ~ {date_to})",
                "body": "该时间段内无已审核的实验记录。",
                "source_note_ids": [],
            }

        lines: list[str] = []
        source_ids: list[int] = []
        for note in filtered:
            source_ids.append(note.id)
            version = db.get(NoteVersion, note.current_version_id) if note.current_version_id else None
            fixed = version.fixed_fields_json if version else {}
            lines.append(f"## {note.title}")
            lines.append(f"- 实验类型：{note.experiment_type}")
            lines.append(f"- 实验日期：{note.experiment_date}")
            if fixed:
                for key, val in fixed.items():
                    if isinstance(val, str) and val.strip():
                        lines.append(f"- {key}：{val[:200]}")
            lines.append("")

        title = f"{'日报' if report_type == 'daily' else '周报'}草稿 — 项目 {project_id} ({date_from} ~ {date_to})"
        body = "\n".join(lines)

        return {
            "title": title,
            "body": body,
            "source_note_ids": source_ids,
        }
