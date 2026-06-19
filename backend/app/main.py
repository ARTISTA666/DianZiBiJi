from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api import agents, audit, auth, dashboard, files, groups, knowledge_graph, notes, notifications, ocr, projects, rag, reports, search, templates, users
from app.core.database import Base, SessionLocal, engine
from app.models import *  # noqa: F403
from app.services.seed import ensure_seed_data

app = FastAPI(title="智能电子实验笔记系统 API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    ensure_database_extensions()
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema()
    db = SessionLocal()
    try:
        ensure_seed_data(db)
    finally:
        db.close()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def ensure_runtime_schema() -> None:
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    if "files" not in table_names:
        return
    file_columns = {column["name"] for column in inspector.get_columns("files")}
    statements = []
    if "knowledge_sync_status" not in file_columns:
        statements.append(
            "ALTER TABLE files ADD COLUMN knowledge_sync_status VARCHAR(40) "
            "NOT NULL DEFAULT 'not_applicable'"
        )
    if "knowledge_synced_at" not in file_columns:
        statements.append("ALTER TABLE files ADD COLUMN knowledge_synced_at TIMESTAMP WITH TIME ZONE")
    if "knowledge_sync_message" not in file_columns:
        statements.append("ALTER TABLE files ADD COLUMN knowledge_sync_message TEXT")
    if "project_rag_datasets" in table_names:
        columns = {column["name"] for column in inspector.get_columns("project_rag_datasets")}
        if "provider" not in columns:
            statements.append("ALTER TABLE project_rag_datasets ADD COLUMN provider VARCHAR(40) NOT NULL DEFAULT 'local_deepseek'")
        if "embedding_model" not in columns:
            statements.append(
                "ALTER TABLE project_rag_datasets ADD COLUMN embedding_model VARCHAR(160) "
                "NOT NULL DEFAULT 'BAAI/bge-small-zh-v1.5'"
            )
        if "generation_model" not in columns:
            statements.append(
                "ALTER TABLE project_rag_datasets ADD COLUMN generation_model VARCHAR(120) "
                "NOT NULL DEFAULT 'deepseek-v4-flash'"
            )
    if "rag_file_syncs" in table_names:
        columns = {column["name"] for column in inspector.get_columns("rag_file_syncs")}
        if "chunk_count" not in columns:
            statements.append("ALTER TABLE rag_file_syncs ADD COLUMN chunk_count INTEGER NOT NULL DEFAULT 0")
        if "content_hash" not in columns:
            statements.append("ALTER TABLE rag_file_syncs ADD COLUMN content_hash VARCHAR(64)")
    if "ai_query_logs" in table_names:
        columns = {column["name"] for column in inspector.get_columns("ai_query_logs")}
        additions = {
            "provider": "VARCHAR(40) NOT NULL DEFAULT 'deepseek'",
            "model_name": "VARCHAR(120)",
            "prompt_version": "VARCHAR(40) NOT NULL DEFAULT 'rag-v1'",
            "retrieval_config_json": "JSON NOT NULL DEFAULT '{}'",
            "usage_json": "JSON NOT NULL DEFAULT '{}'",
            "fallback_reason": "TEXT",
            "experiment_run_id": "INTEGER",
            "experiment_case_index": "INTEGER",
        }
        statements.extend(
            f"ALTER TABLE ai_query_logs ADD COLUMN {name} {definition}"
            for name, definition in additions.items()
            if name not in columns
        )
    if "agent_generation_runs" in table_names:
        columns = {column["name"] for column in inspector.get_columns("agent_generation_runs")}
        additions = {
            "provider": "VARCHAR(40) NOT NULL DEFAULT 'deepseek'",
            "model_name": "VARCHAR(120)",
            "prompt_version": "VARCHAR(40) NOT NULL DEFAULT 'agent-v1'",
            "usage_json": "JSON NOT NULL DEFAULT '{}'",
        }
        statements.extend(
            f"ALTER TABLE agent_generation_runs ADD COLUMN {name} {definition}"
            for name, definition in additions.items()
            if name not in columns
        )
    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def ensure_database_extensions() -> None:
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(groups.router)
app.include_router(projects.router)
app.include_router(templates.router)
app.include_router(notes.router)
app.include_router(files.router)
app.include_router(knowledge_graph.router)
app.include_router(rag.router)
app.include_router(agents.router)
app.include_router(search.router)
app.include_router(ocr.router)
app.include_router(reports.router)
app.include_router(dashboard.router)
app.include_router(notifications.router)
app.include_router(audit.router)
