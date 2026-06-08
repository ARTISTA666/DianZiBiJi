from pydantic import BaseModel


class SearchRequest(BaseModel):
    query: str
    project_id: int | None = None


class SearchResult(BaseModel):
    document_id: int
    note_id: int
    project_id: int
    title: str
    snippet: str
    source_ids: list[str] = []


class SearchStatus(BaseModel):
    total_documents: int
    project_documents: int = 0
