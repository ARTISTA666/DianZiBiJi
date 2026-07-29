"""Export live database, API, module, and project evidence for the thesis."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.main import app
from app.models.file import StoredFile
from app.models.knowledge_graph import KnowledgeEntity, KnowledgeRelation
from app.models.note import ExperimentNote, NoteStatus, NoteVersion
from app.models.project import Project


DEFAULT_PROJECT = "GSE111619 KG-RAG 原始语料盲测项目"
HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def collect_openapi_rows(schema: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    for path, operations in sorted(schema.get("paths", {}).items()):
        for method in HTTP_METHODS:
            operation = operations.get(method)
            if not operation:
                continue
            rows.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "tags": ", ".join(operation.get("tags") or []),
                    "summary": operation.get("summary") or "",
                    "operation_id": operation.get("operationId") or "",
                }
            )
    return rows


def collect_database_schema() -> list[dict[str, Any]]:
    inspector = inspect(engine)
    quote = engine.dialect.identifier_preparer.quote
    tables = []
    with engine.connect() as connection:
        for table_name in sorted(inspector.get_table_names()):
            row_count = connection.scalar(text(f"SELECT COUNT(*) FROM {quote(table_name)}"))
            tables.append(
                {
                    "name": table_name,
                    "row_count": int(row_count or 0),
                    "primary_key": inspector.get_pk_constraint(table_name),
                    "columns": [
                        {
                            "name": item["name"],
                            "type": str(item["type"]),
                            "nullable": bool(item["nullable"]),
                            "default": str(item.get("default") or ""),
                        }
                        for item in inspector.get_columns(table_name)
                    ],
                    "foreign_keys": inspector.get_foreign_keys(table_name),
                    "unique_constraints": inspector.get_unique_constraints(table_name),
                    "indexes": inspector.get_indexes(table_name),
                }
            )
    return tables


def database_markdown(tables: list[dict[str, Any]]) -> str:
    lines = [
        "# 数据库实表结构",
        "",
        "> 本文件由运行中的数据库反射生成，不是按模型文件手工填写。",
        "",
    ]
    for table in tables:
        lines.extend(
            [
                f"## {table['name']}",
                "",
                f"当前记录数：{table['row_count']}",
                "",
                "| 字段 | 类型 | 可空 | 默认值 |",
                "| --- | --- | --- | --- |",
            ]
        )
        for column in table["columns"]:
            default = str(column["default"]).replace("|", "\\|")
            lines.append(
                f"| {column['name']} | {column['type']} | "
                f"{'是' if column['nullable'] else '否'} | {default} |"
            )
        foreign_keys = [
            f"{','.join(item.get('constrained_columns') or [])} -> "
            f"{item.get('referred_table')}({','.join(item.get('referred_columns') or [])})"
            for item in table["foreign_keys"]
        ]
        indexes = [item.get("name") or "未命名索引" for item in table["indexes"]]
        lines.extend(
            [
                "",
                f"- 主键：{', '.join(table['primary_key'].get('constrained_columns') or []) or '无'}",
                f"- 外键：{'; '.join(foreign_keys) or '无'}",
                f"- 索引：{', '.join(indexes) or '无'}",
                "",
            ]
        )
    return "\n".join(lines)


def project_sample(project_name: str) -> dict[str, Any]:
    with SessionLocal() as db:
        project = db.query(Project).filter(Project.name == project_name).one_or_none()
        if project is None:
            raise ValueError(f"Project not found: {project_name}")
        note = (
            db.query(ExperimentNote)
            .filter(
                ExperimentNote.project_id == project.id,
                ExperimentNote.status == NoteStatus.APPROVED,
            )
            .order_by(ExperimentNote.id)
            .first()
        )
        if note is None:
            note = (
                db.query(ExperimentNote)
                .filter(ExperimentNote.project_id == project.id)
                .order_by(ExperimentNote.id)
                .first()
            )
        version = db.get(NoteVersion, note.current_version_id) if note and note.current_version_id else None
        files = (
            db.query(StoredFile)
            .filter(StoredFile.project_id == project.id)
            .order_by(StoredFile.id)
            .all()
        )
        entities = {
            item.id: item
            for item in db.query(KnowledgeEntity)
            .filter(KnowledgeEntity.project_id == project.id)
            .all()
        }
        relations = (
            db.query(KnowledgeRelation)
            .filter(KnowledgeRelation.project_id == project.id)
            .order_by(KnowledgeRelation.id)
            .limit(50)
            .all()
        )
        return {
            "project": {"id": project.id, "name": project.name, "description": project.description},
            "note": None
            if note is None
            else {
                "id": note.id,
                "title": note.title,
                "experiment_type": note.experiment_type,
                "experiment_date": note.experiment_date,
                "status": str(note.status.value if hasattr(note.status, "value") else note.status),
                "fixed_fields_json": version.fixed_fields_json if version else {},
                "content_json": version.content_json if version else {},
            },
            "files": [
                {
                    "id": item.id,
                    "filename": item.original_filename,
                    "mime_type": item.mime_type,
                    "size": item.file_size,
                    "sha256": item.file_hash,
                    "status": str(item.status.value if hasattr(item.status, "value") else item.status),
                    "knowledge_sync_status": item.knowledge_sync_status,
                }
                for item in files
            ],
            "graph_relations": [
                {
                    "id": item.id,
                    "source": entities[item.source_entity_id].label,
                    "source_type": entities[item.source_entity_id].entity_type,
                    "relation": item.relation_type,
                    "target": entities[item.target_entity_id].label,
                    "target_type": entities[item.target_entity_id].entity_type,
                    "confidence": item.confidence,
                    "source_record_type": item.source_type,
                    "source_record_id": item.source_id,
                }
                for item in relations
            ],
        }


def mermaid_label(value: object) -> str:
    return str(value or "").replace('"', "'").replace("\n", " ")[:80]


def graph_markdown(sample: dict[str, Any]) -> str:
    lines = [
        "# 知识图谱实表样例",
        "",
        f"项目：{sample['project']['name']}",
        "",
        "```mermaid",
        "flowchart LR",
    ]
    nodes: dict[tuple[str, str], str] = {}
    for relation in sample["graph_relations"]:
        for prefix in ("source", "target"):
            key = (relation[f"{prefix}_type"], relation[prefix])
            nodes.setdefault(key, f"N{len(nodes) + 1}")
    for (entity_type, label), node_id in nodes.items():
        lines.append(f'  {node_id}["{mermaid_label(entity_type)}: {mermaid_label(label)}"]')
    for relation in sample["graph_relations"]:
        source = nodes[(relation["source_type"], relation["source"])]
        target = nodes[(relation["target_type"], relation["target"])]
        lines.append(f'  {source} -->|"{mermaid_label(relation["relation"])}"| {target}')
    lines.extend(["```", ""])
    return "\n".join(lines)


def architecture_markdown() -> str:
    return """# 系统架构与业务流程

```mermaid
flowchart LR
  U["用户浏览器"] --> F["Next.js 前端"]
  F --> A["FastAPI 后端"]
  A --> P["PostgreSQL + pgvector"]
  A --> O["OpenCV + Tesseract OCR"]
  A --> E["FastEmbed 向量模型"]
  A --> D["DeepSeek 兼容接口"]
  A --> S["项目文件存储"]
```

```mermaid
flowchart TD
  N1["成员新建实验笔记"] --> N2["提交审批"]
  N2 --> N3["审核人通过或退回"]
  N3 -->|通过| N4["抽取实体和关系"]
  F1["上传实验资料"] --> F2["资料审核"]
  F2 -->|图片| F3["OCR 提取"]
  F3 --> F4["人工校对并签名"]
  F2 -->|文本| F5["文本分块"]
  F4 --> F5
  F5 --> F6["向量入库"]
  N4 --> Q["图谱增强检索"]
  F6 --> R["BM25/向量混合检索"]
  Q --> G["生成回答并保存证据"]
  R --> G
  G --> H["独立评价人盲评"]
```
"""


def export(project_name: str, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    openapi = app.openapi()
    api_rows = collect_openapi_rows(openapi)
    database = collect_database_schema()
    sample = project_sample(project_name)

    write_json(output_dir / "openapi.json", openapi)
    write_csv(
        output_dir / "api-list.csv",
        api_rows,
        ["method", "path", "tags", "summary", "operation_id"],
    )
    write_json(output_dir / "database-schema.json", database)
    (output_dir / "database-schema.md").write_text(database_markdown(database), encoding="utf-8")
    write_json(output_dir / "project-input-output-sample.json", sample)
    (output_dir / "knowledge-graph-sample.md").write_text(graph_markdown(sample), encoding="utf-8")
    (output_dir / "architecture-and-flow.md").write_text(architecture_markdown(), encoding="utf-8")

    generated = sorted(
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.name != "manifest.json"
    )
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "app_revision": get_settings().app_revision,
        "database_dialect": engine.dialect.name,
        "project": sample["project"],
        "counts": {
            "database_tables": len(database),
            "api_operations": len(api_rows),
            "sample_files": len(sample["files"]),
            "sample_graph_relations": len(sample["graph_relations"]),
        },
        "files": [
            {"name": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in generated
        ],
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--output-dir", type=Path, default=Path("/storage/system-evidence"))
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    print(json.dumps(export(args.project, args.output_dir), ensure_ascii=False, indent=2))
