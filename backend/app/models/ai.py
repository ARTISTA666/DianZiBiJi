from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RagMode(StrEnum):
    AUTO = "auto"
    PURE_LLM = "pure_llm"
    BM25_RAG = "bm25_rag"
    PROJECT_RAG = "project_rag"
    STRUCTURED_QUERY = "structured_query"
    KG_ENHANCED_RAG = "kg_enhanced_rag"


class AgentTaskType(StrEnum):
    EXPERIMENT_SUMMARY = "experiment_summary"
    WEEKLY_REPORT = "weekly_report"
    STAGE_REPORT = "stage_report"
    GRAPH_OVERVIEW = "graph_overview"


class AgentRunStatus(StrEnum):
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class ReviewProtocol(StrEnum):
    METHOD_MASKED = "method_masked"
    UNBLINDED = "unblinded"


class AIExperimentRun(Base):
    __tablename__ = "ai_experiment_runs"
    __table_args__ = (
        Index(
            "uq_ai_experiment_runs_one_active_per_project",
            "project_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
            sqlite_where=text("status IN ('queued', 'running')"),
        ),
        Index("ix_ai_experiment_runs_lease", "status", "lease_expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(40), default="running", index=True)
    questions_json: Mapped[list] = mapped_column(JSON, default=list)
    modes_json: Mapped[list] = mapped_column(JSON, default=list)
    config_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    total_cases: Mapped[int] = mapped_column(default=0)
    completed_cases: Mapped[int] = mapped_column(default=0)
    failed_cases: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AIQueryLog(Base):
    __tablename__ = "ai_query_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    rag_mode: Mapped[str] = mapped_column(String(40), default=RagMode.PROJECT_RAG.value, index=True)
    graph_hit_count: Mapped[int] = mapped_column(default=0)
    source_count: Mapped[int] = mapped_column(default=0)
    response_ms: Mapped[int] = mapped_column(default=0)
    conversation_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    graph_context_json: Mapped[list] = mapped_column(JSON, default=list)
    sources_json: Mapped[list] = mapped_column(JSON, default=list)
    provider: Mapped[str] = mapped_column(String(40), default="deepseek", index=True)
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    prompt_version: Mapped[str] = mapped_column(String(40), default="rag-v1")
    retrieval_config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    usage_json: Mapped[dict] = mapped_column(JSON, default=dict)
    fallback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    experiment_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_experiment_runs.id"), nullable=True, index=True
    )
    experiment_case_index: Mapped[int | None] = mapped_column(nullable=True)
    experiment_repetition_index: Mapped[int | None] = mapped_column(nullable=True)
    experiment_execution_order: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AIQueryEvaluation(Base):
    __tablename__ = "ai_query_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "query_log_id",
            "evaluator_user_id",
            name="uq_ai_query_evaluation_log_evaluator",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    query_log_id: Mapped[int] = mapped_column(ForeignKey("ai_query_logs.id"), index=True)
    evaluator_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    score: Mapped[int] = mapped_column(default=3)
    is_accurate: Mapped[bool] = mapped_column(default=True)
    is_traceable: Mapped[bool] = mapped_column(default=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_protocol: Mapped[str] = mapped_column(
        String(40),
        default=ReviewProtocol.UNBLINDED.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AgentGenerationRun(Base):
    __tablename__ = "agent_generation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    task_type: Mapped[str] = mapped_column(String(60), index=True)
    input_params_json: Mapped[dict] = mapped_column(JSON, default=dict)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    source_note_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    source_file_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    source_graph_relation_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    provider: Mapped[str] = mapped_column(String(40), default="deepseek", index=True)
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(40), default="agent-v1")
    usage_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(40), default=AgentRunStatus.COMPLETED.value, index=True)
    response_ms: Mapped[int] = mapped_column(default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
