from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_project_access
from app.core.database import get_db
from app.models.file import StoredFile
from app.models.user import User
from app.schemas.ocr import OcrJobRequest, OcrJobResult
from app.services.ocr import OcrService

router = APIRouter(tags=["ocr"])


@router.post("/api/ocr/extract", response_model=OcrJobResult)
def extract_ocr(
    payload: OcrJobRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OcrJobResult:
    """从已上传的文件中提取文字"""
    record = db.get(StoredFile, payload.file_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    require_project_access(record.project_id, db, user)

    try:
        result = OcrService().extract(db, payload.file_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return OcrJobResult(**result)
