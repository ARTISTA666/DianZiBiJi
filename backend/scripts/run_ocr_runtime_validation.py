"""Run a live OCR review and indexing-gate validation against the local API."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


PROJECT_NAME = "运行验收：图片 OCR 校对闭环"
UPLOAD_NAME = "ocr-runtime-validation.png"
CORRECTED_TEXT = """指标 普通 RAG 图谱增强 RAG 变化
微平均事实覆盖率 28.12% 78.12% +50.00 个百分点
宏平均事实覆盖率 26.11% 76.11% +50.00 个百分点"""


def require_ok(response: httpx.Response, action: str) -> dict:
    if response.is_error:
        raise RuntimeError(f"{action} failed: HTTP {response.status_code} {response.text}")
    return response.json()


def run_validation(
    base_url: str,
    username: str,
    password: str,
    source_file_id: int,
) -> dict:
    from app.core.database import SessionLocal
    from app.models.file import StoredFile
    from app.models.rag import RagDocumentChunk

    with SessionLocal() as db:
        source = db.get(StoredFile, source_file_id)
        if source is None:
            raise RuntimeError(f"Source file #{source_file_id} does not exist")
        source_path = Path(source.storage_path)
        if not source_path.is_file():
            raise RuntimeError(f"Source image is missing: {source_path}")
        source_info = {
            "file_id": source.id,
            "original_filename": source.original_filename,
            "file_hash": source.file_hash,
            "storage_path": str(source_path),
        }

    with httpx.Client(base_url=base_url, timeout=300.0) as client:
        login = require_ok(
            client.post("/auth/login", json={"username": username, "password": password}),
            "login",
        )
        client.headers["Authorization"] = f"Bearer {login['access_token']}"
        me = require_ok(client.get("/auth/me"), "load current user")

        projects = require_ok(client.get("/projects"), "list projects")
        project = next((item for item in projects if item["name"] == PROJECT_NAME), None)
        if project is None:
            project = require_ok(
                client.post(
                    "/projects",
                    json={
                        "name": PROJECT_NAME,
                        "description": (
                            "仅用于验证图片 OCR 提取、人工校对、确认签名、审计记录和确认后入库。"
                            "图片内容不是正式实验结果。"
                        ),
                        "owner_user_id": me["id"],
                        "is_sensitive": False,
                        "approval_enabled": True,
                    },
                ),
                "create validation project",
            )
        project_id = int(project["id"])

        with source_path.open("rb") as image:
            upload = require_ok(
                client.post(
                    f"/projects/{project_id}/files",
                    params={"file_category": "knowledge_document"},
                    files={"upload": (UPLOAD_NAME, image, "image/png")},
                ),
                "upload validation image",
            )
        file_id = int(upload["id"])
        approved = require_ok(client.post(f"/documents/{file_id}/approve"), "approve validation image")
        require_ok(client.post(f"/projects/{project_id}/rag/init"), "initialize project RAG")

        before_sync = client.post(f"/files/{file_id}/rag/sync")
        before_detail = before_sync.json().get("detail") if before_sync.headers.get("content-type", "").startswith("application/json") else before_sync.text
        if before_sync.status_code != 502 or "reviewed and confirmed" not in str(before_detail):
            raise RuntimeError(
                "Unconfirmed image was not blocked from indexing: "
                f"HTTP {before_sync.status_code} {before_sync.text}"
            )

        extracted = require_ok(
            client.post("/api/ocr/extract", json={"file_id": file_id}),
            "extract image text",
        )
        if extracted["review_status"] != "pending_review" or not extracted["raw_text"].strip():
            raise RuntimeError("OCR extraction did not produce a pending non-empty result")
        confirmed = require_ok(
            client.post(
                f"/api/ocr/results/{extracted['ocr_result_id']}/confirm",
                json={"corrected_text": CORRECTED_TEXT},
            ),
            "confirm corrected OCR text",
        )
        if confirmed["review_status"] != "confirmed":
            raise RuntimeError("OCR result was not confirmed")
        latest = require_ok(client.get(f"/api/ocr/files/{file_id}/latest"), "load latest OCR result")
        if latest["extracted_text"] != CORRECTED_TEXT:
            raise RuntimeError("Latest OCR text does not match the confirmed correction")

        after_sync_response = client.post(f"/files/{file_id}/rag/sync")
        after_sync = require_ok(after_sync_response, "index confirmed image")
        files = require_ok(client.get(f"/projects/{project_id}/files"), "load validation file")
        stored_file = next(item for item in files["items"] if int(item["id"]) == file_id)
        audit_logs = require_ok(
            client.get("/audit-logs", params={"project_id": project_id}),
            "load validation audit logs",
        )

    with SessionLocal() as db:
        chunks = (
            db.query(RagDocumentChunk)
            .filter(RagDocumentChunk.file_id == file_id)
            .order_by(RagDocumentChunk.id)
            .all()
        )
        indexed_chunks = [
            {
                "chunk_id": chunk.id,
                "content": chunk.content,
                "content_hash": chunk.content_hash,
            }
            for chunk in chunks
        ]
    if not indexed_chunks or "\n".join(item["content"] for item in indexed_chunks) != CORRECTED_TEXT:
        raise RuntimeError("Indexed chunks do not contain the confirmed OCR text")

    relevant_actions = {
        "upload_file",
        "review_document",
        "init_local_rag",
        "index_rag_document_failed",
        "extract_file_text",
        "confirm_file_ocr",
        "index_rag_document",
    }
    action_counts = {
        action: sum(item["action"] == action for item in audit_logs["items"])
        for action in sorted(relevant_actions)
    }
    missing_actions = [action for action, count in action_counts.items() if count == 0]
    if missing_actions:
        raise RuntimeError("Missing audit actions: " + ", ".join(missing_actions))

    return {
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "functional OCR review and indexing gate; not OCR accuracy",
        "source": source_info,
        "project_id": project_id,
        "file_id": file_id,
        "file_status_after_validation": stored_file["status"],
        "knowledge_sync_status_after_validation": stored_file["knowledge_sync_status"],
        "before_confirmation": {
            "sync_http_status": before_sync.status_code,
            "sync_detail": before_detail,
        },
        "ocr": {
            "ocr_result_id": extracted["ocr_result_id"],
            "extraction_method": extracted["extraction_method"],
            "raw_character_count": len(extracted["raw_text"]),
            "raw_text": extracted["raw_text"],
            "confirmed_character_count": len(confirmed["extracted_text"]),
            "confirmed_text": confirmed["extracted_text"],
            "review_status": confirmed["review_status"],
            "reviewed_by": confirmed["reviewed_by"],
            "reviewed_at": confirmed["reviewed_at"],
        },
        "after_confirmation": {
            "sync_http_status": after_sync_response.status_code,
            "rag_status": after_sync,
            "indexed_chunks": indexed_chunks,
        },
        "audit_action_counts": action_counts,
        "passed": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin123")
    parser.add_argument("--source-file-id", type=int, default=18)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/storage/validation/ocr-runtime-e2e-2026-07-12.json"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_validation(args.base_url, args.username, args.password, args.source_file_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
