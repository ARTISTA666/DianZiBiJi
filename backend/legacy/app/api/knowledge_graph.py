from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import can_write_project, get_current_user, require_note_access, require_project_access
from app.core.database import get_db
from app.models.note import ExperimentNote, NoteStatus
from app.models.user import User
from app.schemas.knowledge_graph import (
    KnowledgeExtractionRequest,
    KnowledgeExtractionRunRead,
    KnowledgeGraphRead,
)
from app.services.audit import write_audit
from app.services.knowledge_graph import KnowledgeGraphService

router = APIRouter(tags=["knowledge-graph"])


@router.post("/notes/{note_id}/kg/extract", response_model=KnowledgeExtractionRunRead)
def extract_note_knowledge_graph(
    note_id: int,
    payload: KnowledgeExtractionRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeExtractionRunRead:
    note = require_note_access(note_id, db, user)
    if not can_write_project(db, user, note.project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Write permission required")
    if note.status != NoteStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only approved notes can be extracted")
    request = payload or KnowledgeExtractionRequest()
    run = KnowledgeGraphService().extract_note(db, note, triggered_by=user.id, rebuild=request.rebuild)
    write_audit(db, actor=user, action="extract_note_kg", project_id=note.project_id, target_type="note", target_id=note.id)
    db.commit()
    db.refresh(run)
    return run


@router.post("/projects/{project_id}/kg/rebuild", response_model=list[KnowledgeExtractionRunRead])
def rebuild_project_knowledge_graph(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[KnowledgeExtractionRunRead]:
    require_project_access(project_id, db, user)
    if not can_write_project(db, user, project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Write permission required")
    service = KnowledgeGraphService()
    runs = []
    notes = (
        db.query(ExperimentNote)
        .filter(ExperimentNote.project_id == project_id, ExperimentNote.status == NoteStatus.APPROVED)
        .order_by(ExperimentNote.id)
        .all()
    )
    for note in notes:
        runs.append(service.extract_note(db, note, triggered_by=user.id, rebuild=True))
    write_audit(db, actor=user, action="rebuild_project_kg", project_id=project_id, target_type="project", target_id=project_id)
    db.commit()
    for run in runs:
        db.refresh(run)
    return runs


@router.get("/projects/{project_id}/kg/graph", response_model=KnowledgeGraphRead)
def get_project_knowledge_graph(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeGraphRead:
    require_project_access(project_id, db, user)
    entities, relations = KnowledgeGraphService().get_project_graph(db, project_id)
    return KnowledgeGraphRead(project_id=project_id, entities=entities, relations=relations)


@router.get("/notes/{note_id}/kg/graph", response_model=KnowledgeGraphRead)
def get_note_knowledge_graph(
    note_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeGraphRead:
    note = require_note_access(note_id, db, user)
    entities, relations = KnowledgeGraphService().get_note_graph(db, note)
    return KnowledgeGraphRead(project_id=note.project_id, entities=entities, relations=relations)
