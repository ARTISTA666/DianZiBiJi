from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import accessible_project_ids, get_current_user, require_project_access
from app.core.database import get_db
from app.models.user import User
from app.schemas.search import SearchRequest, SearchResult, SearchStatus
from app.services.search import get_search_status, index_project, index_projects, search_documents

router = APIRouter(tags=["search"])


@router.post("/api/search/index", response_model=SearchStatus)
def reindex_search(
    project_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SearchStatus:
    """重建搜索索引（全部或按项目）"""
    if project_id is not None:
        require_project_access(project_id, db, user)
        indexed = index_project(db, project_id=project_id)
    else:
        project_ids = None if user.role == "super_admin" else accessible_project_ids(db, user)
        indexed = index_project(db) if project_ids is None else index_projects(db, project_ids)
    db.commit()
    status = get_search_status(db)
    return SearchStatus(
        total_documents=status["total_documents"],
        project_documents=len([d for d in indexed if project_id is None or d.project_id == project_id]),
    )


@router.post("/api/search", response_model=list[SearchResult])
def search(
    payload: SearchRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SearchResult]:
    """全文搜索"""
    if not payload.query.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Query cannot be empty")
    if payload.project_id is not None:
        require_project_access(payload.project_id, db, user)
        results = search_documents(db, payload.query, project_id=payload.project_id)
    else:
        results = search_documents(db, payload.query, project_ids=accessible_project_ids(db, user))
    return [SearchResult(**r) for r in results]
