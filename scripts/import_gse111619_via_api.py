#!/usr/bin/env python3
"""Import the verified GSE111619 package through the public ELN API."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import mimetypes
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "data" / "real" / "GSE111619"
DEFAULT_REPORT = DEFAULT_DATA_DIR / "system_import_report.json"
PROJECT_NAME = "GSE111619 真实数据验证项目"
BENCHMARK_PROJECT_NAME = "GSE111619 KG-RAG 原始语料盲测项目"
BENCHMARK_REPORT = DEFAULT_DATA_DIR / "kg_benchmark_import_report.json"
EXPECTED_ACCESSIONS = {"GSM3035185", "GSM3035186", "GSM3035187", "GSM3035188"}
EXPECTED_COMPRESSED_HASHES = {
    "GSE111619_family.soft.gz": "fbfb8aa0a5b0bee99c8ec44d641eec82568a4ce24706b1d16a3010c9403c6043",
    "GSE111619_series_matrix.txt.gz": "b8086b3dad39d1120d6e03fc62ee22007692e86c7ad688e4da300c38822b8849",
    "GSE111619_HTSeq_counts.txt.gz": "662eeaa22c55beb5457b447a27be6f9c5df70f831addd3b04ed6bc718de569f5",
}
RAW_FILES = (
    "GSE111619_family.soft.gz",
    "GSE111619_series_matrix.txt.gz",
    "GSE111619_HTSeq_counts.txt.gz",
    "gse111619_notes.json",
)
KNOWLEDGE_FILES = (
    "gse111619_samples.csv",
    "gse111619_knowledge_document.txt",
)
BENCHMARK_KNOWLEDGE_FILES = (
    "GSE111619_family.soft",
    "GSE111619_series_matrix.txt",
    "GSE111619_HTSeq_counts.txt",
    "gse111619_samples.csv",
)
VERIFY_QUESTION = "GSE111619 包含哪些样本，哪些样本属于 p63 敲低组？"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_import_plan(data_dir: Path, benchmark: bool = False) -> dict[str, Any]:
    required = [
        data_dir / "gse111619_notes.json",
        *(data_dir / name for name in RAW_FILES),
        *(data_dir / name for name in (BENCHMARK_KNOWLEDGE_FILES if benchmark else KNOWLEDGE_FILES)),
    ]
    missing = sorted({str(path) for path in required if not path.is_file()})
    if missing:
        raise ValueError("Missing import files: " + ", ".join(missing))

    for name, expected in EXPECTED_COMPRESSED_HASHES.items():
        actual = sha256_file(data_dir / name)
        if actual != expected:
            raise ValueError(f"SHA-256 mismatch for {name}: expected {expected}, got {actual}")

    notes = json.loads((data_dir / "gse111619_notes.json").read_text(encoding="utf-8"))
    if not isinstance(notes, list) or len(notes) != 4:
        raise ValueError("gse111619_notes.json must contain exactly four notes")
    accessions = {
        note.get("fixed_fields_json", {}).get("source_accession")
        for note in notes
    }
    if accessions != EXPECTED_ACCESSIONS:
        raise ValueError(f"Unexpected sample accessions: {sorted(str(item) for item in accessions)}")

    payload_keys = {
        "title",
        "experiment_type",
        "experiment_date",
        "fixed_fields_json",
        "content_json",
    }
    note_payloads = [{key: note[key] for key in payload_keys if key in note} for note in notes]
    if benchmark:
        with (data_dir / "gse111619_samples.csv").open(encoding="utf-8", newline="") as handle:
            rows = {row["geo_accession"]: row for row in csv.DictReader(handle)}
        for payload in note_payloads:
            fields = payload["fixed_fields_json"]
            row = rows[fields["source_accession"]]
            fields.update(
                {
                    "count_column": row["count_column"],
                    "condition": row["condition"],
                    "replicate_label": f"biological replicate {row['replicate']}",
                    "sra_accession": row["sra"],
                    "biosample_accession": row["biosample"].rsplit("/", 1)[-1],
                    "alignment_method": "TopHat2 v2.0.13",
                    "processing_software": [
                        "bcl2fastq v1.8.4",
                        "FASTQC v0.11.2",
                        "TopHat2 v2.0.13",
                        "SAMtools v0.1.19",
                        "Picard v1.129",
                        "RSeQC v2.6",
                        "HTSeq v0.6.1",
                    ],
                }
            )
    files = [
        {
            "path": data_dir / name,
            "category": "note_attachment",
            "sha256": sha256_file(data_dir / name),
        }
        for name in RAW_FILES
    ]
    knowledge_files = BENCHMARK_KNOWLEDGE_FILES if benchmark else KNOWLEDGE_FILES
    files.extend(
        {
            "path": data_dir / name,
            "category": "knowledge_document",
            "sha256": sha256_file(data_dir / name),
        }
        for name in knowledge_files
    )
    return {"notes": note_payloads, "files": files}


def find_existing_file(records: list[dict[str, Any]], item: dict[str, Any]) -> dict[str, Any] | None:
    same_name = [record for record in records if record["original_filename"] == item["path"].name]
    for record in same_name:
        if record["file_hash"] == item["sha256"]:
            return record
    if same_name:
        raise ValueError(f"System already contains {item['path'].name} with different content")
    return None


def summarize_extraction(record: dict[str, Any], extraction: dict[str, Any]) -> dict[str, Any]:
    text = extraction["extracted_text"]
    return {
        "file_id": record["id"],
        "filename": record["original_filename"],
        "extraction_method": extraction["extraction_method"],
        "character_count": extraction["character_count"],
        "truncated": extraction["truncated"],
        "first_line": text.splitlines()[0] if text else "",
        "extracted_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


class ApiClient:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=900,
            follow_redirects=True,
            trust_env=False,
        )
        login = self.post("/auth/login", json={"username": username, "password": password})
        self.client.headers["Authorization"] = f"Bearer {login['access_token']}"

    def close(self) -> None:
        self.client.close()

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.client.request(method, path, **kwargs)
        if not response.is_success:
            try:
                detail = response.json()
            except ValueError:
                detail = response.text[:500]
            raise RuntimeError(f"{method} {path} failed ({response.status_code}): {detail}")
        return response.json()

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Any:
        return self.request("PATCH", path, **kwargs)

    def upload(self, project_id: int, item: dict[str, Any]) -> dict[str, Any]:
        path = item["path"]
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with path.open("rb") as source:
            return self.post(
                f"/projects/{project_id}/files",
                params={"file_category": item["category"]},
                files={"upload": (path.name, source, mime_type)},
            )


def ensure_project(api: ApiClient, project_name: str = PROJECT_NAME) -> dict[str, Any]:
    existing = next((project for project in api.get("/projects") if project["name"] == project_name), None)
    if existing is None:
        return api.post(
            "/projects",
            json={
                "name": project_name,
                "description": (
                    "NCBI GEO GSE111619 公开 RNA-seq 数据验证项目；"
                    + (
                        "仅以原始 GEO 文档作为向量语料，用冻结题集验证知识图谱关系补证。"
                        if project_name == BENCHMARK_PROJECT_NAME
                        else "保留原始来源文件、结构化样本笔记、知识图谱与 RAG 处理记录。"
                    )
                ),
                "is_sensitive": False,
                "approval_enabled": True,
            },
        )
    if not existing["approval_enabled"]:
        existing = api.patch(f"/projects/{existing['id']}", json={"approval_enabled": True})
    return existing


def ensure_notes(api: ApiClient, project_id: int, payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing = {note["title"]: note for note in api.get(f"/projects/{project_id}/notes")}
    imported: list[dict[str, Any]] = []
    for payload in payloads:
        note = existing.get(payload["title"])
        if note is None:
            note = api.post(f"/projects/{project_id}/notes", json=payload)
        else:
            version = api.get(f"/notes/{note['id']}/versions/{note['current_version_id']}")
            content_matches = (
                version["fixed_fields_json"] == payload.get("fixed_fields_json", {})
                and version["content_json"] == payload.get("content_json", {})
            )
            if not content_matches and note["status"] == "approved":
                raise ValueError(f"Approved note has different content: {note['title']}")
            if not content_matches:
                note = api.patch(
                    f"/notes/{note['id']}",
                    json={**payload, "change_summary": "Refresh verified GSE111619 import"},
                )

        if note["status"] in {"draft", "returned"}:
            note = api.post(f"/notes/{note['id']}/submit")
        if note["status"] == "submitted":
            note = api.post(
                f"/notes/{note['id']}/approve",
                json={"comment": "Verified public-data import from NCBI GEO GSE111619"},
            )
        if note["status"] != "approved":
            raise ValueError(f"Note did not reach approved state: {note['title']} ({note['status']})")
        imported.append(note)
    return imported


def ensure_files(
    api: ApiClient,
    project_id: int,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records = api.get(f"/projects/{project_id}/files")
    imported: list[dict[str, Any]] = []
    for item in items:
        record = find_existing_file(records, item)
        if record is None:
            record = api.upload(project_id, item)
            records.append(record)
        if item["category"] == "knowledge_document":
            if record["status"] == "uploaded":
                record = api.post(
                    f"/files/{record['id']}/review",
                    json={"action": "approve", "comment": "Verified GSE111619 source document"},
                )
            if record["status"] != "approved":
                raise ValueError(f"Knowledge document is not approved: {record['original_filename']}")
        imported.append(record)

    api.post(f"/projects/{project_id}/rag/init")
    synchronized: list[dict[str, Any]] = []
    for record in imported:
        if record["file_category"] == "knowledge_document" and record["knowledge_sync_status"] != "synced":
            api.post(f"/files/{record['id']}/rag/sync")
            record = api.get(f"/files/{record['id']}")
        synchronized.append(record)
    return synchronized


def run_import(
    api: ApiClient,
    plan: dict[str, Any],
    verify_query: bool,
    project_name: str = PROJECT_NAME,
) -> dict[str, Any]:
    project = ensure_project(api, project_name)
    notes = ensure_notes(api, project["id"], plan["notes"])
    files = ensure_files(api, project["id"], plan["files"])
    source_extraction = [
        summarize_extraction(
            record,
            api.post("/api/ocr/extract", json={"file_id": record["id"]}),
        )
        for record in files
    ]
    api.post(f"/projects/{project['id']}/kg/rebuild")
    graph = api.get(f"/projects/{project['id']}/kg/graph")
    rag_status = api.get(f"/projects/{project['id']}/rag/status")
    query = None
    if verify_query:
        query = api.post(
            f"/projects/{project['id']}/rag/query",
            json={"query": VERIFY_QUESTION, "mode": "kg_enhanced_rag"},
        )
    return {
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "dataset": "NCBI GEO GSE111619",
        "project": project,
        "notes": [
            {"id": note["id"], "title": note["title"], "status": note["status"]}
            for note in notes
        ],
        "files": [
            {
                "id": record["id"],
                "filename": record["original_filename"],
                "category": record["file_category"],
                "sha256": record["file_hash"],
                "status": record["status"],
                "knowledge_sync_status": record["knowledge_sync_status"],
                "knowledge_sync_message": record["knowledge_sync_message"],
            }
            for record in files
        ],
        "source_extraction": source_extraction,
        "knowledge_graph": {
            "entity_count": len(graph["entities"]),
            "relation_count": len(graph["relations"]),
        },
        "rag_status": rag_status,
        "verification_query": query,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://127.0.0.1:8001")
    parser.add_argument("--username", default=os.environ.get("ELN_USERNAME", "admin"))
    parser.add_argument("--password", default=os.environ.get("ELN_PASSWORD"))
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--verify-query", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--benchmark", action="store_true", help="Create the raw-corpus KG-RAG holdout project")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_name = BENCHMARK_PROJECT_NAME if args.benchmark else PROJECT_NAME
    if args.benchmark and args.report == DEFAULT_REPORT:
        args.report = BENCHMARK_REPORT
    plan = load_import_plan(args.data_dir.resolve(), benchmark=args.benchmark)
    if args.dry_run:
        print(json.dumps({
            "project": project_name,
            "note_count": len(plan["notes"]),
            "files": [
                {
                    "filename": item["path"].name,
                    "category": item["category"],
                    "sha256": item["sha256"],
                }
                for item in plan["files"]
            ],
        }, ensure_ascii=False, indent=2))
        return
    if not args.password:
        raise SystemExit("Set ELN_PASSWORD or pass --password")

    api = ApiClient(args.api_base, args.username, args.password)
    try:
        report = run_import(api, plan, args.verify_query, project_name=project_name)
    finally:
        api.close()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Imported project #{report['project']['id']}: {report['project']['name']}")
    print(f"Approved notes: {len(report['notes'])}")
    print(
        "Graph: "
        f"{report['knowledge_graph']['entity_count']} entities / "
        f"{report['knowledge_graph']['relation_count']} relations"
    )
    print(f"Report: {args.report}")


if __name__ == "__main__":
    main()
