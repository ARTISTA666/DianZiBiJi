from datetime import date, datetime

from pydantic import BaseModel, Field


class AIQueryEvaluationRequest(BaseModel):
    score: int = Field(ge=1, le=5)
    is_accurate: bool = True
    is_traceable: bool = True
    comment: str | None = None


class AIQueryEvaluationRead(BaseModel):
    id: int
    query_log_id: int
    evaluator_user_id: int
    score: int
    is_accurate: bool
    is_traceable: bool
    comment: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AIQueryLogRead(BaseModel):
    id: int
    project_id: int
    user_id: int
    question: str
    answer: str | None
    rag_mode: str
    graph_hit_count: int
    source_count: int
    response_ms: int
    conversation_id: str | None
    graph_context_json: list = Field(default_factory=list)
    sources_json: list = Field(default_factory=list)
    error_message: str | None
    created_at: datetime
    evaluation: AIQueryEvaluationRead | None = None

    model_config = {"from_attributes": True}


class AIQueryModeStats(BaseModel):
    rag_mode: str
    total_queries: int = 0
    evaluated_queries: int = 0
    avg_score: float | None = None
    accurate_rate: float | None = None
    traceable_rate: float | None = None
    avg_graph_hit_count: float = 0
    avg_source_count: float = 0
    avg_response_ms: float = 0


class AIQueryAnalyticsRead(BaseModel):
    project_id: int
    total_queries: int = 0
    evaluated_queries: int = 0
    evaluation_rate: float = 0
    project_rag_queries: int = 0
    kg_enhanced_queries: int = 0
    failed_queries: int = 0
    avg_response_ms: float = 0
    avg_score: float | None = None
    accurate_rate: float | None = None
    traceable_rate: float | None = None
    avg_graph_hit_count: float = 0
    avg_source_count: float = 0
    mode_stats: list[AIQueryModeStats] = Field(default_factory=list)


class AgentGenerateRequest(BaseModel):
    project_id: int
    task_type: str = "experiment_summary"
    date_from: date | None = None
    date_to: date | None = None


class AgentGenerationRunRead(BaseModel):
    id: int
    project_id: int
    user_id: int
    task_type: str
    input_params_json: dict = Field(default_factory=dict)
    title: str
    body: str
    source_note_ids_json: list[int] = Field(default_factory=list)
    source_file_ids_json: list[int] = Field(default_factory=list)
    source_graph_relation_ids_json: list[int] = Field(default_factory=list)
    status: str
    response_ms: int
    message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
