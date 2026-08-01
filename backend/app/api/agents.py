import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import can_write_project, get_current_user, require_project_access
from app.core.database import get_db
from app.models.ai import AgentGenerationRun
from app.models.user import User
from app.schemas.ai import AgentGenerateRequest, AgentGenerationRunRead
from app.services.agent import AgentGenerationFailure, AgentGenerationService
from app.services.audit import write_audit

router = APIRouter(tags=["agents"])

logger = logging.getLogger(__name__)


@router.post("/api/agents/generate", response_model=AgentGenerationRunRead)
async def generate_agent_output(
    payload: AgentGenerateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentGenerationRunRead:
    require_project_access(payload.project_id, db, user)
    if not can_write_project(db, user, payload.project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Write permission required")
    try:
        run = await AgentGenerationService().generate(
            db,
            project_id=payload.project_id,
            user_id=user.id,
            task_type=payload.task_type,
            date_from=payload.date_from,
            date_to=payload.date_to,
        )
    except ValueError as exc:
        logger.warning("Agent generation validation error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="请求参数有误，请检查输入后重试",
        ) from exc
    except AgentGenerationFailure as exc:
        logger.error("Agent generation failed (task_type=%s): %s", exc.run.task_type, exc)
        write_audit(
            db,
            actor=user,
            action="generate_agent_output_failed",
            project_id=payload.project_id,
            target_type="agent_generation_run",
            target_id=exc.run.id,
            detail={"task_type": exc.run.task_type, "error": str(exc)},
        )
        db.commit()
        raise HTTPException(
            status_code=exc.status_code,
            detail="内容生成失败，请稍后重试",
        ) from exc
    write_audit(
        db,
        actor=user,
        action="generate_agent_output",
        project_id=payload.project_id,
        target_type="agent_generation_run",
        target_id=run.id,
        detail={"task_type": run.task_type, "source_note_count": len(run.source_note_ids_json or [])},
    )
    db.commit()
    db.refresh(run)
    return run


@router.get("/projects/{project_id}/agents/runs", response_model=list[AgentGenerationRunRead])
def list_agent_runs(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AgentGenerationRunRead]:
    require_project_access(project_id, db, user)
    return (
        db.query(AgentGenerationRun)
        .filter(AgentGenerationRun.project_id == project_id)
        .order_by(AgentGenerationRun.created_at.desc(), AgentGenerationRun.id.desc())
        .limit(50)
        .all()
    )
