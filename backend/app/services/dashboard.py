from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.file import StoredFile
from app.models.note import ExperimentNote, NoteStatus
from app.models.project import Project
from app.models.user import User


class DashboardService:
    def summary(self, db: Session, project_ids: list[int] | None = None, include_users: bool = True) -> dict:
        project_query = db.query(Project)
        note_query = db.query(ExperimentNote)
        file_query = db.query(StoredFile)
        pending_query = db.query(ExperimentNote).filter(ExperimentNote.status == NoteStatus.SUBMITTED)
        if project_ids is not None:
            if not project_ids:
                return {
                    "projects": 0,
                    "experiments": 0,
                    "attachments": 0,
                    "audit_events": 0,
                    "users": 0,
                    "pending_approvals": 0,
                }
            project_query = project_query.filter(Project.id.in_(project_ids))
            note_query = note_query.filter(ExperimentNote.project_id.in_(project_ids))
            file_query = file_query.filter(StoredFile.project_id.in_(project_ids))
            pending_query = pending_query.filter(ExperimentNote.project_id.in_(project_ids))

        project_count = project_query.count()
        note_count = note_query.count()
        file_count = file_query.count()
        user_count = db.query(func.count(User.id)).scalar() or 0 if include_users else 0
        pending = pending_query.count()
        return {
            "projects": project_count,
            "experiments": note_count,
            "attachments": file_count,
            "audit_events": 0,  # 可选：从 audit_logs 表统计
            "users": user_count,
            "pending_approvals": pending,
        }
