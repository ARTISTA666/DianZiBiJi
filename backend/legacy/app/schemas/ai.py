from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.schemas.rag import MAX_RAG_QUERY_CHARS


class AIQueryEvaluationRequest(BaseModel):
    score: int = Field(ge=1, le=5)
    is_accurate: bool
    is_traceable: bool
    comment: str | None = None


class AIQueryEvaluationRead(BaseModel):
    id: int
    query_log_id: int
    evaluator_user_id: int
    score: int
    is_accurate: bool
    is_traceable: bool
    comment: str | None
    review_protocol: str = "unblinded"
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BlindReviewEvaluationRead(BaseModel):
    score: int
    is_accurate: bool
    is_traceable: bool
    comment: str | None
    updated_at: datetime


class BlindReviewEvidenceRead(BaseModel):
    evidence_id: str
    content: str


class BlindReviewItemRead(BaseModel):
    blind_id: str
    question: str
    answer: str | None
    evidence: list[BlindReviewEvidenceRead] = Field(default_factory=list)
    evaluation: BlindReviewEvaluationRead | None = None


class BlindReviewBatchRead(BaseModel):
    batch_id: str
    total_items: int = 0
    completed_items: int = 0


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
    provider: str = "deepseek"
    model_name: str | None = None
    prompt_version: str = "rag-v1"
    retrieval_config_json: dict = Field(default_factory=dict)
    usage_json: dict = Field(default_factory=dict)
    fallback_reason: str | None = None
    error_message: str | None
    experiment_run_id: int | None = None
    experiment_case_index: int | None = None
    experiment_repetition_index: int | None = None
    experiment_execution_order: int | None = None
    created_at: datetime
    evaluation: AIQueryEvaluationRead | None = None
    evaluations: list[AIQueryEvaluationRead] = Field(default_factory=list)

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


class AIQueryAgreementMetric(BaseModel):
    paired_ratings: int = 0
    agreement_rate: float | None = None
    cohens_kappa: float | None = None


class AIQueryAnalyticsRead(BaseModel):
    project_id: int
    total_queries: int = 0
    evaluated_queries: int = 0
    evaluation_count: int = 0
    evaluator_count: int = 0
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
    accuracy_agreement: AIQueryAgreementMetric = Field(default_factory=AIQueryAgreementMetric)
    traceability_agreement: AIQueryAgreementMetric = Field(default_factory=AIQueryAgreementMetric)


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
    provider: str = "deepseek"
    model_name: str | None = None
    prompt_version: str = "agent-v1"
    usage_json: dict = Field(default_factory=dict)
    status: str
    response_ms: int
    message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AIExperimentRunRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    questions: list[Annotated[str, Field(max_length=MAX_RAG_QUERY_CHARS)]] = Field(min_length=1, max_length=50)
    modes: list[str] = Field(
        default_factory=lambda: ["project_rag", "kg_enhanced_rag"],
        min_length=1,
        max_length=5,
    )
    repetitions: int = Field(default=1, ge=1, le=10)
    randomize_order: bool = True
    random_seed: int | None = Field(default=None, ge=0, le=2_147_483_647)


class AIExperimentRunRead(BaseModel):
    id: int
    project_id: int
    created_by: int
    name: str
    status: str
    questions_json: list[str] = Field(default_factory=list)
    modes_json: list[str] = Field(default_factory=list)
    config_snapshot_json: dict = Field(default_factory=dict)
    summary_json: dict = Field(default_factory=dict)
    total_cases: int
    completed_cases: int
    failed_cases: int
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}
