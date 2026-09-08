from datetime import datetime

from pydantic import BaseModel, Field


class KnowledgeEntityRead(BaseModel):
    id: int
    project_id: int
    entity_type: str
    label: str
    normalized_label: str
    natural_key: str
    source_type: str | None
    source_id: int | None
    properties: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeRelationRead(BaseModel):
    id: int
    project_id: int
    source_entity_id: int
    target_entity_id: int
    relation_type: str
    source_type: str | None
    source_id: int | None
    confidence: float
    properties: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeGraphRead(BaseModel):
    project_id: int
    entities: list[KnowledgeEntityRead]
    relations: list[KnowledgeRelationRead]


class KnowledgeExtractionRunRead(BaseModel):
    id: int
    project_id: int
    note_id: int
    triggered_by: int
    status: str
    extracted_entities: int
    extracted_relations: int
    message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeExtractionRequest(BaseModel):
    rebuild: bool = Field(default=True)
