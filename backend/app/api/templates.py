from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.template import ExperimentTemplate
from app.models.user import User
from app.schemas.template import TemplateRead

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=list[TemplateRead])
def list_templates(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[ExperimentTemplate]:
    return db.query(ExperimentTemplate).filter(ExperimentTemplate.is_active.is_(True)).order_by(ExperimentTemplate.id).all()
