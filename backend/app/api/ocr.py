from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import can_review_project, get_current_user, require_project_access
from app.core.config import get_settings
from app.core.database import get_db
from app.models.file import StoredFile
from app.models.ocr import FileOcrResult, OcrReviewStatus
from app.models.user import User
from app.schemas.ocr import OcrCorrectionRequest, OcrJobRequest, OcrJobResult
from app.services.audit import write_audit
from app.services.ocr import OcrService, UnsupportedFileTypeError

router = APIRouter(tags=["ocr"])

logger = logging.getLogger(__name__)


def _ocr_result_read(result: FileOcrResult) -> OcrJobResult:
    return OcrJobResult(
        ocr_result_id=result.id,
        file_id=result.file_id,
        extracted_text=result.corrected_text,
        raw_text=result.raw_text,
        source_ids=[str(result.file_id)],
        character_count=len(result.corrected_text),
        truncated=result.truncated,
        extraction_method=result.extraction_method,
        review_status=result.review_status,
        created_by=result.created_by,
        reviewed_by=result.reviewed_by,
        created_at=result.created_at,
        reviewed_at=result.reviewed_at,
    )


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
        logger.warning("OCR source file not found (file_id=%s): %s", payload.file_id, exc)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="源文件不存在，请确认后重试") from exc
    except LookupError as exc:
        logger.warning("OCR resource not found (file_id=%s): %s", payload.file_id, exc)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="相关资源未找到") from exc
    except UnsupportedFileTypeError as exc:
        logger.warning("Unsupported file type for OCR (file_id=%s): %s", payload.file_id, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="不支持的文件格式，请上传 PDF、图片或文本文件",
        ) from exc

    ocr_result = FileOcrResult(
        file_id=record.id,
        project_id=record.project_id,
        created_by=user.id,
        file_hash=record.file_hash,
        raw_text=result["extracted_text"],
        corrected_text=result["extracted_text"],
        extraction_method=result["extraction_method"],
        character_count=result["character_count"],
        truncated=result["truncated"],
        review_status=OcrReviewStatus.PENDING_REVIEW.value,
    )
    db.add(ocr_result)
    db.flush()
    write_audit(
        db,
        actor=user,
        action="extract_file_text",
        project_id=record.project_id,
        target_type="file",
        target_id=record.id,
        detail={
            "extraction_method": result["extraction_method"],
            "character_count": result["character_count"],
            "truncated": result["truncated"],
            "ocr_result_id": ocr_result.id,
            "review_status": ocr_result.review_status,
        },
    )
    db.commit()
    db.refresh(ocr_result)
    return _ocr_result_read(ocr_result)


@router.get("/api/ocr/files/{file_id}/latest", response_model=OcrJobResult)
def get_latest_ocr_result(
    file_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OcrJobResult:
    record = db.get(StoredFile, file_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    require_project_access(record.project_id, db, user)
    result = (
        db.query(FileOcrResult)
        .filter(FileOcrResult.file_id == file_id)
        .order_by(FileOcrResult.id.desc())
        .first()
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No text extraction result found")
    return _ocr_result_read(result)


@router.post("/api/ocr/results/{result_id}/confirm", response_model=OcrJobResult)
def confirm_ocr_result(
    result_id: int,
    payload: OcrCorrectionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OcrJobResult:
    result = db.get(FileOcrResult, result_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Text extraction result not found")
    record = db.get(StoredFile, result.file_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    require_project_access(result.project_id, db, user)
    if not can_review_project(db, user, result.project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="File review permission required")
    latest = (
        db.query(FileOcrResult)
        .filter(FileOcrResult.file_id == result.file_id)
        .order_by(FileOcrResult.id.desc())
        .first()
    )
    if latest is None or latest.id != result.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A newer extraction result exists")
    if result.review_status == OcrReviewStatus.CONFIRMED.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Text extraction result is already confirmed")
    if result.file_hash != record.file_hash:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The source file has changed")
    corrected_text = payload.corrected_text.strip()
    if len(corrected_text) > get_settings().document_text_max_chars:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Corrected text is too long")
    result.corrected_text = corrected_text
    result.character_count = len(corrected_text)
    result.review_status = OcrReviewStatus.CONFIRMED.value
    result.reviewed_by = user.id
    result.reviewed_at = datetime.now(timezone.utc)
    write_audit(
        db,
        actor=user,
        action="confirm_file_ocr",
        project_id=result.project_id,
        target_type="file_ocr_result",
        target_id=result.id,
        detail={
            "file_id": result.file_id,
            "raw_character_count": len(result.raw_text),
            "corrected_character_count": len(corrected_text),
        },
    )
    db.commit()
    db.refresh(result)
    return _ocr_result_read(result)
