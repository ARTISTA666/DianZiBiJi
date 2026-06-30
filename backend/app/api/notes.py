from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import can_review_project, can_write_project, get_current_user, require_note_access, require_project_access
from app.core.database import get_db
from app.models.note import ExperimentNote, NoteApproval, NoteStatus, NoteVersion
from app.models.user import User
from app.schemas.note import ApprovalRequest, NoteApprovalRead, NoteCreate, NoteRead, NoteUpdate, NoteVersionRead
from app.services.audit import write_audit
from app.services.knowledge_graph import KnowledgeGraphService

router = APIRouter(tags=["notes"])


@router.get("/projects/{project_id}/notes", response_model=list[NoteRead])
def list_notes(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[ExperimentNote]:
    require_project_access(project_id, db, user)
    return db.query(ExperimentNote).filter(ExperimentNote.project_id == project_id).order_by(ExperimentNote.updated_at.desc()).all()


@router.post("/projects/{project_id}/notes", response_model=NoteRead)
def create_note(
    project_id: int,
    payload: NoteCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExperimentNote:
    require_project_access(project_id, db, user)
    if not can_write_project(db, user, project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Write permission required")
    note = ExperimentNote(
        project_id=project_id,
        template_id=payload.template_id,
        title=payload.title,
        experiment_type=payload.experiment_type,
        experiment_date=payload.experiment_date,
        owner_user_id=user.id,
        status=NoteStatus.DRAFT,
    )
    db.add(note)
    db.flush()
    version = NoteVersion(
        note_id=note.id,
        version_number=1,
        fixed_fields_json=payload.fixed_fields_json,
        content_json=payload.content_json,
        created_by=user.id,
        change_summary="Initial draft",
    )
    db.add(version)
    db.flush()
    note.current_version_id = version.id
    write_audit(db, actor=user, action="create_note", project_id=project_id, target_type="note", target_id=note.id)
    db.commit()
    db.refresh(note)
    return note


@router.get("/notes/{note_id}", response_model=NoteRead)
def get_note(note_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ExperimentNote:
    return require_note_access(note_id, db, user)


@router.patch("/notes/{note_id}", response_model=NoteRead)
def update_note(
    note_id: int,
    payload: NoteUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExperimentNote:
    note = require_note_access(note_id, db, user)
    if not can_write_project(db, user, note.project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Write permission required")
    if note.status not in {NoteStatus.DRAFT, NoteStatus.RETURNED}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only draft or returned notes can be edited")

    latest_version_number = (
        db.query(func.max(NoteVersion.version_number)).filter(NoteVersion.note_id == note.id).scalar()
    ) or 0
    current_version = db.get(NoteVersion, note.current_version_id) if note.current_version_id else None
    fixed_fields = payload.fixed_fields_json if payload.fixed_fields_json is not None else (current_version.fixed_fields_json if current_version else {})
    content = payload.content_json if payload.content_json is not None else (current_version.content_json if current_version else {})

    if payload.title is not None:
        note.title = payload.title
    if payload.experiment_type is not None:
        note.experiment_type = payload.experiment_type
    if payload.experiment_date is not None:
        note.experiment_date = payload.experiment_date

    version = NoteVersion(
        note_id=note.id,
        version_number=latest_version_number + 1,
        fixed_fields_json=fixed_fields,
        content_json=content,
        created_by=user.id,
        change_summary=payload.change_summary or "Updated draft",
    )
    db.add(version)
    db.flush()
    note.current_version_id = version.id
    write_audit(db, actor=user, action="update_note", project_id=note.project_id, target_type="note", target_id=note.id)
    db.commit()
    db.refresh(note)
    return note


@router.post("/notes/{note_id}/submit", response_model=NoteRead)
def submit_note(note_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ExperimentNote:
    note = db.get(ExperimentNote, note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    project = require_project_access(note.project_id, db, user)
    if note.owner_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only note owner can submit the draft")
    if note.status not in {NoteStatus.DRAFT, NoteStatus.RETURNED}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Note cannot be submitted")
    if project.approval_enabled:
        note.status = NoteStatus.SUBMITTED
    else:
        version = db.get(NoteVersion, note.current_version_id)
        if version:
            version.is_locked = True
        note.status = NoteStatus.APPROVED
        kg_run = KnowledgeGraphService().extract_note(db, note, triggered_by=user.id, rebuild=True)
        write_audit(
            db,
            actor=user,
            action="auto_extract_note_kg",
            project_id=note.project_id,
            target_type="note",
            target_id=note.id,
            detail={"entities": kg_run.extracted_entities, "relations": kg_run.extracted_relations, "trigger": "submit_without_approval"},
        )
    write_audit(
        db,
        actor=user,
        action="submit_note",
        project_id=note.project_id,
        target_type="note",
        target_id=note.id,
        detail={"approval_enabled": project.approval_enabled},
    )
    db.commit()
    db.refresh(note)
    return note


@router.get("/notes/{note_id}/versions", response_model=list[NoteVersionRead])
def list_note_versions(note_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[NoteVersion]:
    require_note_access(note_id, db, user)
    return db.query(NoteVersion).filter(NoteVersion.note_id == note_id).order_by(NoteVersion.version_number.desc()).all()


@router.get("/notes/{note_id}/versions/{version_id}", response_model=NoteVersionRead)
def get_note_version(
    note_id: int,
    version_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NoteVersion:
    require_note_access(note_id, db, user)
    version = db.get(NoteVersion, version_id)
    if version is None or version.note_id != note_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note version not found")
    return version


@router.post("/notes/{note_id}/archive", response_model=NoteRead)
def archive_note(note_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ExperimentNote:
    note = require_note_access(note_id, db, user)
    if not can_write_project(db, user, note.project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Write permission required")
    if note.status not in {NoteStatus.APPROVED, NoteStatus.RETURNED, NoteStatus.DRAFT}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Note cannot be archived")
    note.status = NoteStatus.ARCHIVED
    write_audit(db, actor=user, action="archive_note", project_id=note.project_id, target_type="note", target_id=note.id)
    db.commit()
    db.refresh(note)
    return note


@router.post("/notes/{note_id}/void", response_model=NoteRead)
def void_note(
    note_id: int,
    payload: ApprovalRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExperimentNote:
    note = require_note_access(note_id, db, user)
    if not can_review_project(db, user, note.project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Review permission required")
    if note.status == NoteStatus.VOIDED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Note already voided")
    note.status = NoteStatus.VOIDED
    db.add(
        NoteApproval(
            note_id=note.id,
            version_id=note.current_version_id,
            reviewer_user_id=user.id,
            action="voided",
            comment=payload.comment,
        )
    )
    write_audit(db, actor=user, action="void_note", project_id=note.project_id, target_type="note", target_id=note.id)
    db.commit()
    db.refresh(note)
    return note


@router.get("/approvals/pending", response_model=list[NoteRead])
def list_pending_approvals(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[ExperimentNote]:
    notes = db.query(ExperimentNote).filter(ExperimentNote.status == NoteStatus.SUBMITTED).order_by(ExperimentNote.updated_at.desc()).all()
    return [note for note in notes if can_review_project(db, user, note.project_id)]


@router.post("/notes/{note_id}/approve", response_model=NoteRead)
def approve_note(
    note_id: int,
    payload: ApprovalRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExperimentNote:
    note = require_note_access(note_id, db, user)
    if not can_review_project(db, user, note.project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Review permission required")
    if note.status != NoteStatus.SUBMITTED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only submitted notes can be approved")
    version = db.get(NoteVersion, note.current_version_id)
    if version:
        version.is_locked = True
    note.status = NoteStatus.APPROVED
    approval = NoteApproval(
        note_id=note.id,
        version_id=note.current_version_id,
        reviewer_user_id=user.id,
        action="approved",
        comment=payload.comment,
    )
    db.add(approval)
    kg_run = KnowledgeGraphService().extract_note(db, note, triggered_by=user.id, rebuild=True)
    write_audit(db, actor=user, action="approve_note", project_id=note.project_id, target_type="note", target_id=note.id)
    write_audit(
        db,
        actor=user,
        action="auto_extract_note_kg",
        project_id=note.project_id,
        target_type="note",
        target_id=note.id,
        detail={"entities": kg_run.extracted_entities, "relations": kg_run.extracted_relations, "trigger": "approve_note"},
    )
    db.commit()
    db.refresh(note)
    return note


@router.post("/notes/{note_id}/return", response_model=NoteRead)
def return_note(
    note_id: int,
    payload: ApprovalRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExperimentNote:
    note = require_note_access(note_id, db, user)
    if not can_review_project(db, user, note.project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Review permission required")
    if note.status != NoteStatus.SUBMITTED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only submitted notes can be returned")
    note.status = NoteStatus.RETURNED
    approval = NoteApproval(
        note_id=note.id,
        version_id=note.current_version_id,
        reviewer_user_id=user.id,
        action="returned",
        comment=payload.comment,
    )
    db.add(approval)
    write_audit(db, actor=user, action="return_note", project_id=note.project_id, target_type="note", target_id=note.id)
    db.commit()
    db.refresh(note)
    return note


@router.get("/notes/{note_id}/approvals", response_model=list[NoteApprovalRead])
def list_note_approvals(note_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[NoteApproval]:
    require_note_access(note_id, db, user)
    return db.query(NoteApproval).filter(NoteApproval.note_id == note_id).order_by(NoteApproval.created_at.desc()).all()
