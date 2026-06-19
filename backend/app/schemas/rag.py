from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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


class RagFileSyncRead(BaseModel):
    id: int
    file_id: int
    project_id: int
    dify_dataset_id: str
    dify_document_id: str | None
    sync_status: str
    sync_message: str | None
    synced_at: datetime | None
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
    query: str
    mode: Literal["auto", "project_rag", "kg_enhanced_rag"] = "auto"


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


class RagQueryResponse(BaseModel):
    answer: str
    conversation_id: str | None = None
    sources: list[RagSourceRead] = Field(default_factory=list)
    graph_context: list[RagGraphContextRead] = Field(default_factory=list)
    rag_mode: str = "project_rag"
    query_log_id: int | None = None
    response_ms: int | None = None
    provider: str = "deepseek"
    model_name: str | None = None
    fallback_reason: str | None = None
