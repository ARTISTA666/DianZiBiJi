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
    if "files" not in inspector.get_table_names():
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
    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


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
