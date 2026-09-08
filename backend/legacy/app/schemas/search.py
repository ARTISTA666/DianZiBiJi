from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
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
