from datetime import datetime

from pydantic import BaseModel, Field

from app.models.ai import RagMode

MAX_RAG_QUERY_CHARS = 4_000


class RagDatasetRead(BaseModel):
    id: int
    project_id: int
    dify_dataset_id: str
    dify_dataset_name: str
    provider: str
    embedding_model: str
    generation_model: str
    status: str
    created_by: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RagStatusRead(BaseModel):
    initialized: bool
    dataset: RagDatasetRead | None
    pending_sync_count: int
    failed_sync_count: int
    synced_count: int


class RagQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=MAX_RAG_QUERY_CHARS)
    mode: RagMode = RagMode.AUTO


class RagSourceRead(BaseModel):
    chunk_id: int | None = None
    file_id: int | None = None
    filename: str | None = None
    dify_document_id: str | None = None
    snippet: str | None = None
    vector_score: float | None = None
    lexical_score: float | None = None
    retrieval_score: float | None = None


class RagGraphContextRead(BaseModel):
    relation_id: int
    relation_type: str
    relation_label: str
    source_entity_id: int
    source_label: str
    source_entity_type: str
    source_entity_type_label: str
    target_entity_id: int
    target_label: str
    target_entity_type: str
    target_entity_type_label: str
    confidence: float
    retrieval_score: float = 0
    relation_roles: list[str] = Field(default_factory=list)


class RagCitationAuditRead(BaseModel):
    passed: bool
    citation_count: int
    invalid_citations: list[str] = Field(default_factory=list)
    has_evidence: bool
    message: str
    repair_attempted: bool = False


class RagQueryResponse(BaseModel):
    answer: str
    conversation_id: str | None = None
    sources: list[RagSourceRead] = Field(default_factory=list)
    graph_context: list[RagGraphContextRead] = Field(default_factory=list)
    rag_mode: RagMode = RagMode.PROJECT_RAG
    query_log_id: int | None = None
    response_ms: int | None = None
    provider: str = "deepseek"
    model_name: str | None = None
    fallback_reason: str | None = None
    citation_audit: RagCitationAuditRead | None = None
