import json

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.note import ExperimentNote, NoteStatus, NoteVersion
from app.models.search_document import SearchDocument


def _build_search_text(note: ExperimentNote, version: NoteVersion | None) -> str:
    parts = [note.title, note.experiment_type]
    if version:
        fixed = version.fixed_fields_json or {}
        content = version.content_json or {}
        for v in fixed.values():
            if isinstance(v, str):
                parts.append(v)
            elif isinstance(v, (list, dict)):
                parts.append(json.dumps(v, ensure_ascii=False))
        content_str = json.dumps(content, ensure_ascii=False)
        parts.append(content_str)
    return "\n".join(parts)


def _build_source_ids(note: ExperimentNote) -> list[str]:
    return [str(note.id)]


def index_note(db: Session, note_id: int) -> SearchDocument:
    """创建或更新单个笔记的搜索文档"""
    note = db.get(ExperimentNote, note_id)
    if note is None:
        raise LookupError(f"Note {note_id} not found")
    if note.status != NoteStatus.APPROVED:
        raise ValueError("Only approved notes can be indexed")
    version = db.get(NoteVersion, note.current_version_id) if note.current_version_id else None
    search_text = _build_search_text(note, version)
    source_ids = _build_source_ids(note)

    doc = db.query(SearchDocument).filter(SearchDocument.note_id == note_id).first()
    if doc is None:
        doc = SearchDocument(
            note_id=note_id,
            project_id=note.project_id,
            title=note.title,
            search_text=search_text,
            source_ids=",".join(source_ids),
        )
        db.add(doc)
    else:
        doc.title = note.title
        doc.search_text = search_text
        doc.source_ids = ",".join(source_ids)
    db.flush()
    return doc


def index_project(db: Session, project_id: int | None = None) -> list[SearchDocument]:
    """为整个项目或全部笔记重建搜索索引"""
    query = db.query(ExperimentNote)
    if project_id is not None:
        query = query.filter(ExperimentNote.project_id == project_id)
        db.query(SearchDocument).filter(SearchDocument.project_id == project_id).delete(synchronize_session=False)
    else:
        db.query(SearchDocument).delete(synchronize_session=False)
    query = query.filter(ExperimentNote.status == NoteStatus.APPROVED)
    notes = query.all()
    indexed: list[SearchDocument] = []
    for note in notes:
        doc = index_note(db, note.id)
        indexed.append(doc)
    return indexed


def index_projects(db: Session, project_ids: list[int]) -> list[SearchDocument]:
    indexed: list[SearchDocument] = []
    if not project_ids:
        return indexed
    db.query(SearchDocument).filter(SearchDocument.project_id.in_(project_ids)).delete(synchronize_session=False)
    notes = (
        db.query(ExperimentNote)
        .filter(ExperimentNote.project_id.in_(project_ids), ExperimentNote.status == NoteStatus.APPROVED)
        .all()
    )
    for note in notes:
        indexed.append(index_note(db, note.id))
    return indexed


def search_documents(
    db: Session,
    query: str,
    project_id: int | None = None,
    project_ids: list[int] | None = None,
    limit: int = 50,
) -> list[dict]:
    """关键词搜索（简单子串匹配，跨 project_id 过滤）"""
    terms = [t.strip().lower() for t in query.split() if t.strip()]
    if not terms:
        return []

    q = (
        db.query(SearchDocument)
        .join(ExperimentNote, ExperimentNote.id == SearchDocument.note_id)
        .filter(ExperimentNote.status == NoteStatus.APPROVED)
    )
    if project_id is not None:
        q = q.filter(SearchDocument.project_id == project_id)
    elif project_ids is not None:
        if not project_ids:
            return []
        q = q.filter(SearchDocument.project_id.in_(project_ids))

    all_docs = q.all()
    results: list[dict] = []
    for doc in all_docs:
        haystack = doc.search_text.lower()
        if all(term in haystack for term in terms):
            snippet = _snippet(doc.search_text, terms)
            results.append({
                "document_id": doc.id,
                "note_id": doc.note_id,
                "project_id": doc.project_id,
                "title": doc.title,
                "snippet": snippet,
                "source_ids": doc.source_ids.split(",") if doc.source_ids else [],
            })
    return results[:limit]


def remove_note(db: Session, note_id: int) -> None:
    db.query(SearchDocument).filter(SearchDocument.note_id == note_id).delete(synchronize_session=False)


def _snippet(text: str, terms: list[str], context: int = 40) -> str:
    if not text:
        return ""
    lower_text = text.lower()
    start = 0
    for term in terms:
        idx = lower_text.find(term)
        if idx >= 0:
            start = max(0, idx - context)
            break
    return text[start : start + 160]


def get_search_status(db: Session) -> dict:
    total = db.query(func.count(SearchDocument.id)).scalar() or 0
    return {"total_documents": total}
