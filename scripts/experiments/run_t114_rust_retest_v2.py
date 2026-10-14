#!/usr/bin/env python3
"""V2 pre-freeze four-arm context adapter around current Rust retrieval.

This is an internal prospective rerun, not an independent confirmatory study.
The production backend is unchanged. Generation happens only after a separate
finalize command has bound questions, references, contexts, code and settings.
V2 explicitly disables provider thinking and retains invalid answer responses.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import gzip
import hashlib
import itertools
import json
import os
import random
import re
import shutil
import subprocess
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
ARMS = ("document_rag", "document_plus_full_notes", "document_plus_all_triples", "document_plus_one_hop")
SYSTEM_PROMPT = (
    "你是科研记录检索助手。仅根据给出的证据回答问题，不使用外部知识补足缺失事实。"
    "准确保留样本对应关系、数值、单位与版本。每项事实用对应的[E编号]引用。"
    "证据不足时明确说明；证据冲突时指出冲突，不能自行裁定。简洁回答。"
)
USER_TEMPLATE = "问题：{question}\n\n证据：\n{context}\n\n请依据以上证据回答，并给出引用。"
SOURCE_HASHES = {
    "GSE111619_family.soft.gz": "fbfb8aa0a5b0bee99c8ec44d641eec82568a4ce24706b1d16a3010c9403c6043",
    "GSE111619_series_matrix.txt.gz": "b8086b3dad39d1120d6e03fc62ee22007692e86c7ad688e4da300c38822b8849",
    "GSE111619_HTSeq_counts.txt.gz": "662eeaa22c55beb5457b447a27be6f9c5df70f831addd3b04ed6bc718de569f5",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_hash(path: Path) -> str:
    return digest(path.read_bytes())


def save_json(path: Path, value: Any, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x" if exclusive else "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_questions(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = value.get("questions")
    if not isinstance(value, list) or not value:
        raise ValueError("questions must be a nonempty list")
    ids: set[str] = set()
    for question in value:
        if not isinstance(question, dict) or not isinstance(question.get("id"), str) or not question["id"]:
            raise ValueError("each question needs a string id")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", question["id"]):
            raise ValueError("question id must be safe ASCII letters, digits, underscore or hyphen")
        if question["id"] in ids:
            raise ValueError("duplicate question id")
        ids.add(question["id"])
        if not isinstance(question.get("question"), str) or not question["question"].strip():
            raise ValueError("question text is required")
        facts = question.get("facts")
        if not isinstance(facts, list) or not facts:
            raise ValueError("each question needs pre-established facts")
        for fact in [*facts, *question.get("forbidden_facts", [])]:
            if not isinstance(fact, dict) or not isinstance(fact.get("aliases"), list) or not fact["aliases"]:
                raise ValueError("each fact needs nonempty aliases")
            if any(not isinstance(alias, str) or not alias.strip() for alias in fact["aliases"]):
                raise ValueError("fact aliases must be nonempty strings")
    return value


def sanitize_geo(text: str) -> str:
    """Remove public contact metadata, retaining scientific metadata verbatim."""
    return "\n".join(line for line in text.splitlines() if not re.match(r"!\w+_contact_", line)) + "\n"


def prepare_corpus(data_dir: Path, destination: Path) -> dict[str, Any]:
    if destination.exists():
        raise ValueError("corpus destination exists; refuse to overwrite")
    for filename, expected in SOURCE_HASHES.items():
        if file_hash(data_dir / filename) != expected:
            raise ValueError(f"original source hash mismatch: {filename}")
        if digest(gzip.decompress((data_dir / filename).read_bytes())) != file_hash(data_dir / filename[:-3]):
            raise ValueError(f"decompressed source hash mismatch: {filename}")
    validation = verify_derived_counts(data_dir)
    destination.mkdir(parents=True)
    knowledge = destination / "knowledge_files"
    knowledge.mkdir()
    derivations = []
    for filename in ("gse111619_knowledge_document.txt", "gse111619_samples.csv", "GSE111619_family.soft", "GSE111619_series_matrix.txt"):
        original = data_dir / filename
        target = knowledge / filename
        if filename.endswith((".soft", "series_matrix.txt")):
            target.write_text(sanitize_geo(original.read_text(encoding="utf-8")), encoding="utf-8")
            rule = "remove lines matching ^!\\w+_contact_; scientific metadata retained; UTF-8 newline normalization"
        else:
            shutil.copyfile(original, target)
            rule = "byte-for-byte copy"
        derivations.append({"source": str(original.resolve()), "source_sha256": file_hash(original), "derived": str(target.relative_to(destination)), "derived_sha256": file_hash(target), "rule": rule})
    shutil.copyfile(data_dir / "gse111619_notes.json", destination / "notes.json")
    all_sources = [*SOURCE_HASHES, "GSE111619_family.soft", "GSE111619_series_matrix.txt", "GSE111619_HTSeq_counts.txt", "gse111619_notes.json", "gse111619_knowledge_document.txt", "gse111619_samples.csv"]
    report = {"created_at": utc_now(), "dataset": "NCBI GEO GSE111619", "source_files": [{"path": str((data_dir / name).resolve()), "sha256": file_hash(data_dir / name)} for name in all_sources], "derivations": derivations, "notes_sha256": file_hash(destination / "notes.json"), "count_matrix_upload": False, "notes_origin": "existing source-derived normalized records, not new laboratory observations", "derived_count_validation": validation}
    save_json(destination / "derivation.json", report, exclusive=True)
    return report


def verify_derived_counts(data_dir: Path) -> dict[str, Any]:
    with (data_dir / "GSE111619_HTSeq_counts.txt").open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader)
        totals, detected, rows = [0] * 4, [0] * 4, 0
        if len(header) != 5:
            raise ValueError("unexpected count matrix columns")
        for row in reader:
            if len(row) != 5:
                raise ValueError("malformed count matrix row")
            values = [int(value) for value in row[1:]]
            if any(value < 0 for value in values):
                raise ValueError("negative raw gene count")
            rows += 1
            for index, value in enumerate(values):
                totals[index] += value
                detected[index] += value > 0
    with (data_dir / "gse111619_samples.csv").open(encoding="utf-8", newline="") as handle:
        records = list(csv.DictReader(handle))
    notes = load_json(data_dir / "gse111619_notes.json")
    if len(records) != 4 or len(notes) != 4:
        raise ValueError("expected exactly four sample records and derived notes")
    notes_by_accession = {note["fixed_fields_json"]["source_accession"]: note for note in notes}
    for record in records:
        index = header[1:].index(record["count_column"])
        if int(record["total_gene_count"]) != totals[index] or int(record["detected_gene_rows"]) != detected[index] or int(record["zero_gene_rows"]) != rows - detected[index]:
            raise ValueError("derived sample CSV does not match original count matrix")
        note = notes_by_accession[record["geo_accession"]]
        text = json_bytes(note).decode()
        for value in (f"total_count={totals[index]}", f"detected_gene_rows={detected[index]}", f"count_matrix_gene_rows={rows}"):
            if value not in text:
                raise ValueError("derived note does not match original count matrix")
    return {"status": "PASS", "gene_rows": rows, "sample_columns": header[1:], "totals": totals, "nonzero_gene_rows": detected, "rule": "integer sum and count(value > 0), computed afresh from original matrix before any new answers"}


class ApiClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.client = httpx.Client(base_url=base_url.rstrip("/"), timeout=900, trust_env=False)
        login = self.request("POST", "/auth/login", json={"username": username, "password": password})
        self.client.headers["Authorization"] = "Bearer " + login["access_token"]

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.client.request(method, path, **kwargs)
        if not response.is_success:
            # Do not echo server bodies that may contain credentials or account details.
            raise RuntimeError(f"local API {method} {path}: HTTP {response.status_code}")
        return response.json()

    def all_items(self, path: str, **params: Any) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        while True:
            value = self.request("GET", path, params={**params, "skip": len(result), "limit": 100})
            if isinstance(value, list):
                return value
            result.extend(value["items"])
            if len(result) >= value["total"]:
                return result
            if not value["items"]:
                raise ValueError("empty page before declared total")


def import_fresh_project(api: ApiClient, corpus: Path, name: str, output: Path) -> dict[str, Any]:
    project_record = output / "prepared-project.json"
    if project_record.exists():
        saved = load_json(project_record)
        if saved["name"] != name:
            raise ValueError("preparation project name changed")
        project = api.request("GET", f"/projects/{saved['id']}")
        if project["name"] != name:
            raise ValueError("preparation project identity changed")
        if api.all_items(f"/projects/{saved['id']}/rag/query-logs"):
            raise ValueError("preparation project already has generated answers")
    else:
        if any(p["name"] == name for p in api.all_items("/projects")):
            raise ValueError("project name already exists; refuse to reuse an unbound project")
        project = api.request("POST", "/projects", json={"name": name, "description": "T114 isolated public-data prospective rule-freeze rerun; experimental context adapter", "is_sensitive": False, "approval_enabled": True})
        save_json(project_record, {"id": project["id"], "name": name, "created_at": utc_now()}, exclusive=True)
    pid = project["id"]
    existing = {n["title"]: n for n in api.all_items(f"/projects/{pid}/notes")}
    for payload in load_json(corpus / "notes.json"):
        clean = {key: payload[key] for key in ("title", "experiment_type", "experiment_date", "fixed_fields_json", "content_json") if key in payload}
        note = existing.get(clean["title"])
        if note is None:
            note = api.request("POST", f"/projects/{pid}/notes", json=clean)
        else:
            version = api.request("GET", f"/notes/{note['id']}/versions/{note['current_version_id']}")
            if any(version[key] != clean[key] for key in ("fixed_fields_json", "content_json")):
                raise ValueError("existing isolated note content differs")
        if note["status"] == "draft":
            note = api.request("POST", f"/notes/{note['id']}/submit")
        if note["status"] == "submitted":
            note = api.request("POST", f"/notes/{note['id']}/approve", json={"comment": "T114 public source import, no human-subject review"})
        if note["status"] != "approved":
            raise ValueError("imported note was not approved")
    files = {f["original_filename"]: f for f in api.all_items(f"/projects/{pid}/files")}
    api.request("POST", f"/projects/{pid}/rag/init")
    for path in sorted((corpus / "knowledge_files").iterdir()):
        if not path.is_file():
            continue
        record = files.get(path.name)
        if record is None:
            with path.open("rb") as handle:
                record = api.request("POST", f"/projects/{pid}/files", params={"file_category": "knowledge_document"}, files={"upload": (path.name, handle, "text/plain")})
        elif record["file_hash"] != file_hash(path):
            raise ValueError("existing isolated knowledge file differs")
        if record["status"] == "uploaded":
            record = api.request("POST", f"/files/{record['id']}/review", json={"action": "approve", "comment": "T114 source-derived frozen corpus"})
        if record["status"] != "approved":
            raise ValueError("knowledge file was not approved")
        if record["knowledge_sync_status"] != "synced":
            api.request("POST", f"/files/{record['id']}/rag/sync")
    api.request("POST", f"/projects/{pid}/kg/rebuild")
    return project


def document_evidence(sources: list[dict[str, Any]], budget: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    evidence = []
    used = 0
    for source in sources:
        text = source.get("content")
        if not isinstance(text, str) or not text:
            raise ValueError("retrieval source lacks full content")
        if digest(text.encode()) != source.get("content_sha256"):
            raise ValueError("retrieval source content hash mismatch")
        block = {"type": "document", "source_id": source["chunk_id"], "filename": source["filename"], "text": text, "content_sha256": source["content_sha256"]}
        # Select whole passages. No silent character truncation or candidate backfill.
        rendered_length = len(render_evidence([*evidence, block]))
        if rendered_length > budget:
            break
        evidence.append(block)
        used = rendered_length
    return evidence, {"budget_chars": budget, "used_chars": used, "retrieved_count": len(sources), "included_count": len(evidence), "omitted_count": len(sources) - len(evidence), "policy": "ordered whole passages; stop before first overflowing passage; no backfill"}


def render_evidence(evidence: list[dict[str, Any]]) -> str:
    return "\n\n".join(f"[E{i}] {item['text']}" for i, item in enumerate(evidence, 1))


def note_evidence(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"type": "full_note", "source_id": n["note_id"], "version_id": n["id"], "text": json_bytes({"title": n["title"], "fixed_fields_json": n["fixed_fields_json"], "content_json": n["content_json"]}).decode()} for n in sorted(notes, key=lambda n: n["note_id"])]


def triple_evidence(graph: dict[str, Any]) -> list[dict[str, Any]]:
    entities = {e["id"]: e for e in graph["entities"]}
    result = []
    for relation in sorted(graph["relations"], key=lambda r: r["id"]):
        head, tail = entities[relation["source_entity_id"]], entities[relation["target_entity_id"]]
        semantic = {"head": head["label"], "relation": relation["relation_type"], "tail": tail["label"], "source_note_id": relation.get("source_id")}
        result.append({"type": "serialized_triple", "source_id": relation["id"], "source_note_id": relation.get("source_id"), "text": json_bytes(semantic).decode()})
    return result


def one_hop_evidence(relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"type": "one_hop_relation", "source_id": r["relation_id"], "text": json_bytes({"head": r["source_label"], "relation": r["relation_type"], "tail": r["target_label"]}).decode()} for r in relations]


def verify_retrieval(response: dict[str, Any], expected: dict[str, str]) -> None:
    if response.get("retrieval_only") is not True or any(response.get(key) is not False for key in ("generation_invoked", "llm_query_rewrite_invoked", "citation_repair_invoked")):
        raise ValueError("Rust response does not prove retrieval-only execution")
    for key, value in expected.items():
        for field in ("actual_" + key, "used_" + key):
            if response.get(field) != value:
                raise ValueError("Rust retrieval snapshot drift")


def generation_config(base_url: str, model: str) -> dict[str, Any]:
    return {"provider": "DeepSeek", "base_url": base_url, "model": model, "temperature": 0.1,
            "max_tokens": 1000, "thinking": {"type": "disabled"}, "request_timeout_seconds": 180,
            "retry_policy": {"max_attempts": 2, "retry_statuses": [429, 500, 502, 503, 504], "backoff_seconds": 2}}


def validate_generation_config(config: dict[str, Any]) -> None:
    if config.get("thinking") != {"type": "disabled"}:
        raise ValueError("v2 requires explicit thinking.type=disabled in frozen generation config")


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    output, corpus = args.output.resolve(), args.corpus.resolve()
    if (output / "freeze.sha256").exists():
        raise ValueError("already finalized; preparation is immutable")
    questions = validate_questions(load_json(args.questions))
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.questions, output / "questions.json")
    password = os.environ.get(args.password_env)
    if not password:
        raise ValueError(f"{args.password_env} must be set; do not pass credentials in argv")
    api = ApiClient(args.api_base, args.username, password)
    try:
        metrics = api.request("GET", "/metrics")
        if metrics.get("runtime", {}).get("api_runtime") != "rust-axum":
            raise ValueError("runtime is not Rust Axum")
        project = import_fresh_project(api, corpus, args.project_name, output)
        pid = project["id"]
        status = api.request("GET", f"/projects/{pid}/rag/status")
        snapshot = status["corpus_snapshot"]
        expected = {key: snapshot[key] for key in ("corpus_snapshot_hash", "graph_snapshot_hash")}
        if any(not isinstance(v, str) or not re.fullmatch("[a-f0-9]{64}", v) for v in expected.values()):
            raise ValueError("missing Rust corpus/graph snapshot")
        graph = api.request("GET", f"/projects/{pid}/kg/graph")
        notes = []
        for note in api.all_items(f"/projects/{pid}/notes", status="approved"):
            version = api.request("GET", f"/notes/{note['id']}/versions/{note['current_version_id']}")
            notes.append({**version, "title": note["title"]})
        full_notes, all_triples = note_evidence(notes), triple_evidence(graph)
        for label, evidence in (("full notes", full_notes), ("all triples", all_triples)):
            if len(render_evidence(evidence)) > args.aux_budget:
                raise ValueError(f"BLOCKED: complete {label} exceeds frozen auxiliary budget")
        contexts = {}
        for question in questions:
            raw = {}
            for mode in ("project_rag", "kg_enhanced_rag"):
                raw[mode] = api.request("POST", f"/projects/{pid}/rag/retrieve", json={"query": question["question"], "mode": mode, **{"expected_" + key: value for key, value in expected.items()}})
                verify_retrieval(raw[mode], expected)
            if raw["project_rag"]["sources"] != raw["kg_enhanced_rag"]["sources"]:
                raise ValueError("document base differs between Rust modes")
            save_json(output / "retrieval-raw" / f"{question['id']}.json", raw)
            base, base_stats = document_evidence(raw["project_rag"]["sources"], args.base_budget)
            if raw["project_rag"]["sources"] and not base:
                raise ValueError("BLOCKED: first whole document passage exceeds base budget")
            one_hop = one_hop_evidence(raw["kg_enhanced_rag"]["graph_context"])
            if len(render_evidence(one_hop)) > args.aux_budget:
                raise ValueError("BLOCKED: complete returned one-hop context exceeds budget")
            contexts[question["id"]] = {}
            for arm, extra in zip(ARMS, ([], full_notes, all_triples, one_hop), strict=True):
                evidence = [*base, *extra]
                context = render_evidence(evidence)
                if len(context) > args.base_budget + args.aux_budget + 2:
                    raise ValueError("complete context exceeds budget due to citation headers")
                messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": USER_TEMPLATE.format(question=question["question"], context=context)}]
                contexts[question["id"]][arm] = {"messages": messages, "prompt_sha256": digest(json_bytes(messages)), "evidence": evidence, "context_chars": len(context), "base_stats": base_stats, "aux_count": len(extra), "aux_chars": len(render_evidence(extra)), "aux_omitted_count": 0, "effective_retrieval_config": raw["kg_enhanced_rag" if extra is one_hop else "project_rag"]["effective_retrieval_config"]}
        after = api.request("GET", f"/projects/{pid}/rag/status")["corpus_snapshot"]
        if any(after[key] != value for key, value in expected.items()):
            raise ValueError("snapshot drift at end of preparation")
        save_json(output / "contexts.json", contexts)
        save_json(output / "raw-graph.json", graph)
        save_json(output / "approved-note-versions.json", notes)
        cases = [{"case_id": f"{q['id']}:{arm}:r{rep}", "question_id": q["id"], "arm": arm, "repetition": rep} for q in questions for arm in ARMS for rep in range(1, args.repetitions + 1)]
        random.Random(args.seed).shuffle(cases)
        for order, case in enumerate(cases, 1):
            case["execution_order"] = order
        preparation = {"prepared_at": utc_now(), "status": "PREPARED_NOT_FINALIZED", "evidence_level": "internal prospective rerun with source-derived references", "method_label": "current-Rust retrieval + frozen experimental context adapter", "not_native_four_mode_api": True, "human_validation": False, "project_id": pid, "project_name": project["name"], "api_base": args.api_base, "runtime_metrics": metrics, "rag_status": status, "snapshots": expected, "arms": list(ARMS), "question_count": len(questions), "repetitions": args.repetitions, "case_count": len(cases), "case_plan": cases, "random_seed": args.seed, "generation": generation_config(args.model_base, args.model), "budget": {"base_chars": args.base_budget, "aux_chars": args.aux_budget, "equal_input_tokens_claimed": False, "whole_passage_policy": "ordered stop before first overflow"}, "corpus_dir": str(corpus), "source_provenance": load_json(corpus / "derivation.json")}
        save_json(output / "preparation.json", preparation)
        return {"status": preparation["status"], "project_id": pid, "question_count": len(questions), "case_count": len(cases), "graph_relations": len(all_triples), "notes": len(full_notes), "aux_full_notes_chars": len(render_evidence(full_notes)), "aux_all_triples_chars": len(render_evidence(all_triples))}
    finally:
        api.client.close()


def finalize(output: Path, protocol: Path, identity: Path | None) -> dict[str, Any]:
    if (output / "freeze.sha256").exists() or (output / "results.jsonl").exists():
        raise ValueError("finalized or generation already started; refuse overwrite")
    preparation = load_json(output / "preparation.json")
    validate_generation_config(preparation["generation"])
    questions = validate_questions(load_json(output / "questions.json"))
    if not protocol.is_file() or (identity is not None and not identity.is_file()):
        raise ValueError("protocol/runtime identity file missing")
    semantic_protocol = output / "semantic-protocol.json"
    semantic_script = Path(__file__).with_name("run_t114_semantic_judge.py")
    if not semantic_protocol.is_file() or not semantic_script.is_file():
        raise ValueError("semantic primary-outcome protocol and script must be frozen before generation")
    if len(list((output / "retrieval-raw").glob("*.json"))) != len(questions):
        raise ValueError("prepared retrieval files do not cover all questions")
    contexts = load_json(output / "contexts.json")
    if set(contexts) != {q["id"] for q in questions} or any(set(value) != set(ARMS) for value in contexts.values()):
        raise ValueError("prepared contexts do not cover question × arm product")
    for value in contexts.values():
        for context in value.values():
            if digest(json_bytes(context["messages"])) != context["prompt_sha256"]:
                raise ValueError("prepared prompt hash mismatch")
    bound_paths = [output / "preparation.json", output / "questions.json", output / "contexts.json", output / "raw-graph.json", output / "approved-note-versions.json", *sorted((output / "retrieval-raw").glob("*.json")), *sorted(Path(preparation["corpus_dir"]).rglob("*")), Path(__file__).resolve(), protocol.resolve(), semantic_protocol, semantic_script]
    bound_paths.extend(Path(item["path"]) for item in preparation["source_provenance"]["source_files"])
    for item in preparation["source_provenance"]["source_files"]:
        if file_hash(Path(item["path"])) != item["sha256"]:
            raise ValueError("original source drift since corpus derivation")
    if identity is not None:
        bound_paths.append(identity.resolve())
    status = subprocess.run(["git", "status", "--porcelain=v1"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    patch = subprocess.run(["git", "diff", "--binary", "HEAD"], cwd=ROOT, capture_output=True, check=True).stdout
    manifest = {"finalized_at": utc_now(), "status": "FROZEN_BEFORE_GENERATION", "preparation": preparation, "git_revision": revision, "dirty": bool(status), "dirty_status_sha256": digest(status.encode()), "working_patch_sha256": digest(patch), "dirty_checkout_is_disclosed": True, "independent_confirmatory_claim": False, "runtime_identity": load_json(identity) if identity else {"status": "image_and_embedding_artifact_identity_not_provided"}, "input_files": [{"path": str(path.resolve()), "sha256": file_hash(path)} for path in sorted(set(bound_paths)) if path.is_file()], "statistical_plan": {"unit": "question", "primary_metric": "separate GPT semantic required-fact coverage using frozen source_refs and entity-field binding; not computed by lexical analyze command", "auxiliary_metric": "pre-frozen lexical alias presence, exploratory proxy only", "primary_comparison": "document_plus_one_hop minus document_rag", "secondary_comparisons": ["document_plus_one_hop minus document_plus_full_notes", "document_plus_one_hop minus document_plus_all_triples"], "repetitions_aggregation": "per-question per-arm mean", "bootstrap_draws": 10000, "bootstrap_seed": preparation["random_seed"], "paired_sign_flip": "exact two-sided across question means; secondary Holm correction", "missing": "failures missing; paired metrics use shared complete question rows; report planned and effective counts"}}
    save_json(output / "freeze-manifest.json", manifest, exclusive=True)
    sha = file_hash(output / "freeze-manifest.json")
    (output / "freeze.sha256").write_text(sha + "\n", encoding="ascii")
    return {"status": manifest["status"], "freeze_sha256": sha, "case_count": preparation["case_count"]}


def verify_freeze(output: Path) -> dict[str, Any]:
    if file_hash(output / "freeze-manifest.json") != (output / "freeze.sha256").read_text().strip():
        raise ValueError("freeze manifest hash changed")
    manifest = load_json(output / "freeze-manifest.json")
    for item in manifest["input_files"]:
        if file_hash(Path(item["path"])) != item["sha256"]:
            raise ValueError(f"frozen input drift: {Path(item['path']).name}")
    return manifest


def generate_case(case: dict[str, Any], context: dict[str, Any], config: dict[str, Any], key: str) -> dict[str, Any]:
    validate_generation_config(config)
    started = time.monotonic()
    result = {**case, "started_at": utc_now(), "prompt_sha256": context["prompt_sha256"], "requested_model": config["model"], "requested_thinking": config["thinking"], "attempts": [], "status": "failed"}
    with httpx.Client(timeout=config["request_timeout_seconds"], trust_env=False) as client:
        for attempt in range(1, config["retry_policy"]["max_attempts"] + 1):
            retryable = False
            try:
                response = client.post(config["base_url"].rstrip("/") + "/chat/completions", headers={"Authorization": "Bearer " + key}, json={"model": config["model"], "messages": context["messages"], "temperature": config["temperature"], "max_tokens": config["max_tokens"], "thinking": config["thinking"]})
                result["attempts"].append({"attempt": attempt, "http_status": response.status_code, "at": utc_now()})
                retryable = response.status_code in config["retry_policy"]["retry_statuses"]
                if response.is_success:
                    payload = response.json()
                    # Persist provider evidence before validating content. Reasoning is
                    # never substituted for the answer, including on HTTP 200 failures.
                    result["raw_response"] = payload
                    if not isinstance(payload, dict):
                        raise ValueError("invalid_response_object")
                    result.update({"returned_model": payload.get("model"), "usage": payload.get("usage"), "response_id": payload.get("id")})
                    choice = payload["choices"][0]
                    result["finish_reason"] = choice.get("finish_reason")
                    message = choice["message"]
                    if not isinstance(message, dict):
                        raise ValueError("invalid_message_object")
                    result["message_keys"] = sorted(message)
                    answer = message.get("content")
                    errors = []
                    if result["finish_reason"] == "length":
                        errors.append("finish_reason_length")
                    if not isinstance(answer, str) or not answer.strip():
                        errors.append("empty_answer")
                    if errors:
                        result["response_validation_errors"] = errors
                        raise ValueError(",".join(errors))
                    result.update({"status": "completed", "answer": answer})
                    break
            except (httpx.HTTPError, ValueError, KeyError, IndexError) as error:
                result["attempts"].append({"attempt": attempt, "error_type": type(error).__name__, "at": utc_now()})
                retryable = isinstance(error, httpx.HTTPError)
            if not retryable or attempt == config["retry_policy"]["max_attempts"]:
                break
            time.sleep(config["retry_policy"]["backoff_seconds"])
    result.update({"finished_at": utc_now(), "elapsed_seconds": round(time.monotonic() - started, 3)})
    return result


def run(output: Path, key_env: str, workers: int, resume: bool = False) -> dict[str, Any]:
    manifest = verify_freeze(output)
    validate_generation_config(manifest["preparation"]["generation"])
    key = os.environ.get(key_env)
    if not key:
        raise ValueError(f"{key_env} must be set")
    result_path = output / "results.jsonl"
    existing = []
    if result_path.exists():
        if not resume:
            raise ValueError("results exist; explicit --resume required")
        existing = [json.loads(line) for line in result_path.read_text().splitlines() if line.strip()]
    completed_ids = {item["case_id"] for item in existing}
    if len(completed_ids) != len(existing):
        raise ValueError("duplicate persisted case id")
    preparation = manifest["preparation"]
    planned_ids = {case["case_id"] for case in preparation["case_plan"]}
    if not completed_ids <= planned_ids:
        raise ValueError("unplanned persisted case id")
    contexts = load_json(output / "contexts.json")
    pending = [case for case in preparation["case_plan"] if case["case_id"] not in completed_ids]
    if not (output / "run-start.json").exists():
        save_json(output / "run-start.json", {"started_at": utc_now(), "freeze_sha256": file_hash(output / "freeze-manifest.json"), "workers": workers}, exclusive=True)
    with result_path.open("a", encoding="utf-8") as handle, concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        # Submission order is frozen; concurrency makes completion order variable.
        futures = {executor.submit(generate_case, case, contexts[case["question_id"]][case["arm"]], preparation["generation"], key): case for case in pending}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            handle.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            completed_ids.add(result["case_id"])
            print(json.dumps({"completed_cases": len(completed_ids), "planned_cases": len(planned_ids), "case_id": result["case_id"], "status": result["status"]}), flush=True)
    verify_freeze(output)
    return {"persisted_cases": len(completed_ids), "planned_cases": len(planned_ids)}


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text).casefold())


def matching_alias(text: str, aliases: list[str]) -> str | None:
    text = normalize(text)
    for alias in aliases:
        value = normalize(alias)
        pattern = re.escape(value)
        if value[0].isdigit():
            pattern = r"(?<!\d)" + pattern
        if value[-1].isdigit():
            pattern += r"(?!\d)"
        if re.search(pattern, text):
            return alias
    return None


def score_answer(answer: str, question: dict[str, Any]) -> dict[str, Any]:
    facts = [{"fact_id": f.get("id", f"{question['id']}:F{i}"), "matched_alias": matching_alias(answer, f["aliases"])} for i, f in enumerate(question["facts"], 1)]
    forbidden = [{"fact_id": f.get("id", f"{question['id']}:X{i}"), "matched_alias": matching_alias(answer, f["aliases"])} for i, f in enumerate(question.get("forbidden_facts", []), 1)]
    hits = sum(f["matched_alias"] is not None for f in facts)
    return {"required_fact_coverage": hits / len(facts), "all_required_facts_present": hits == len(facts), "forbidden_fact_hit": any(f["matched_alias"] is not None for f in forbidden), "facts": facts, "forbidden_facts": forbidden, "metric_limit": "lexical presence only; no entailment, polarity, or sample-pairing guarantee"}


def paired_stats(differences: list[float], seed: int) -> dict[str, Any]:
    if not differences:
        return {"n_questions": 0, "mean_difference": None, "bootstrap_ci95": None, "sign_flip_p": None}
    n = len(differences)
    mean = sum(differences) / n
    rng = random.Random(seed)
    boot = sorted(sum(rng.choice(differences) for _ in differences) / n for _ in range(10000))
    if n > 20:
        raise ValueError("exact sign-flip enumeration limited to 20 questions")
    observed = abs(sum(differences))
    extremes = sum(abs(sum(value * sign for value, sign in zip(differences, signs, strict=True))) >= observed - 1e-12 for signs in itertools.product((-1, 1), repeat=n))
    return {"n_questions": n, "mean_difference": mean, "bootstrap_ci95": [boot[249], boot[9749]], "sign_flip_p": extremes / (2 ** n)}


def analyze(output: Path) -> dict[str, Any]:
    manifest = verify_freeze(output)
    questions = {q["id"]: q for q in validate_questions(load_json(output / "questions.json"))}
    rows = [json.loads(line) for line in (output / "results.jsonl").read_text().splitlines() if line.strip()]
    plan = {case["case_id"]: case for case in manifest["preparation"]["case_plan"]}
    if len({r["case_id"] for r in rows}) != len(rows) or any(r["case_id"] not in plan for r in rows):
        raise ValueError("duplicate or unplanned result")
    scored = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if any(row[field] != plan[row["case_id"]][field] for field in ("question_id", "arm", "repetition", "execution_order")):
            raise ValueError("result identity differs from frozen case")
        if row["status"] != "completed":
            continue
        metrics = score_answer(row["answer"], questions[row["question_id"]])
        scored.append({"case_id": row["case_id"], **metrics})
        grouped.setdefault((row["question_id"], row["arm"]), []).append(metrics)
    repetitions = manifest["preparation"]["repetitions"]
    question_rows = []
    for qid in questions:
        for arm in ARMS:
            values = grouped.get((qid, arm), [])
            question_rows.append({"question_id": qid, "arm": arm, "planned_repetitions": repetitions, "effective_repetitions": len(values), "complete_repetitions": len(values) == repetitions, "required_fact_coverage": sum(v["required_fact_coverage"] for v in values) / len(values) if values else None, "all_required_fraction": sum(v["all_required_facts_present"] for v in values) / len(values) if values else None, "forbidden_fraction": sum(v["forbidden_fact_hit"] for v in values) / len(values) if values else None})
    lookup = {(row["question_id"], row["arm"]): row for row in question_rows}
    comparisons = {}
    for other in ARMS[:-1]:
        eligible = [qid for qid in questions if lookup[qid, ARMS[-1]]["complete_repetitions"] and lookup[qid, other]["complete_repetitions"]]
        diffs = [lookup[qid, ARMS[-1]]["required_fact_coverage"] - lookup[qid, other]["required_fact_coverage"] for qid in eligible]
        comparisons[other] = {"paired_question_ids": eligible, **paired_stats(diffs, manifest["preparation"]["random_seed"])}
    secondary = [(name, comparisons[name]["sign_flip_p"]) for name in ARMS[1:3] if comparisons[name]["sign_flip_p"] is not None]
    previous = 0.0
    for index, (name, p) in enumerate(sorted(secondary, key=lambda pair: pair[1])):
        previous = max(previous, min(1.0, p * (len(secondary) - index)))
        comparisons[name]["holm_secondary_p"] = previous
    summary = {"analyzed_at": utc_now(), "analysis_kind": "auxiliary lexical presence proxy; semantic primary outcome requires separate GPT adjudication", "semantic_primary_outcome_computed": False, "evidence_level": "internal prospective rerun; source-derived references; dirty checkout disclosed", "method_label": manifest["preparation"]["method_label"], "freeze_sha256": file_hash(output / "freeze-manifest.json"), "planned_cases": len(plan), "persisted_cases": len(rows), "successful_cases": len(scored), "failed_cases": sum(r["status"] != "completed" for r in rows), "not_yet_run_cases": sorted(set(plan) - {r["case_id"] for r in rows}), "unit": "question", "arm_summary": {arm: {"planned_questions": len(questions), "effective_questions": sum(row["required_fact_coverage"] is not None for row in question_rows if row["arm"] == arm), "mean_question_coverage": sum(row["required_fact_coverage"] for row in question_rows if row["arm"] == arm and row["required_fact_coverage"] is not None) / max(1, sum(row["required_fact_coverage"] is not None for row in question_rows if row["arm"] == arm)), "successful_repetitions": sum(len(v) for (qid, a), v in grouped.items() if a == arm)} for arm in ARMS}, "question_rows": question_rows, "comparisons": comparisons, "limitations": ["Not independent human validation", "Lexical required-fact coverage does not establish semantic support or truthful sample-fact pairing", "Four arms are experimental adapters using frozen current Rust retrieval, not four production API modes", "Equal output budget; input context and token counts differ by arm", "Existing source-derived notes and some facts overlap prior question topics; no independent held-out claim"]}
    save_json(output / "fact-score-traces.json", scored, exclusive=True)
    save_json(output / "analysis.json", summary, exclusive=True)
    return {key: summary[key] for key in ("planned_cases", "persisted_cases", "successful_cases", "failed_cases", "unit", "arm_summary")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    corpus = sub.add_parser("corpus")
    corpus.add_argument("--data-dir", type=Path, default=ROOT / "data/real/GSE111619")
    corpus.add_argument("--destination", type=Path, required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--api-base", default="http://127.0.0.1:18014")
    prep.add_argument("--username", default="t114_admin")
    prep.add_argument("--password-env", default="ELN_PASSWORD")
    prep.add_argument("--project-name", default="T114 GSE111619 前置规则重测 2026-10-01")
    prep.add_argument("--questions", type=Path, required=True)
    prep.add_argument("--corpus", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    prep.add_argument("--repetitions", type=int, choices=range(1, 11), default=3)
    prep.add_argument("--seed", type=int, default=20261001114)
    prep.add_argument("--base-budget", type=int, default=4000)
    prep.add_argument("--aux-budget", type=int, default=12000)
    prep.add_argument("--model", default="deepseek-v4-flash")
    prep.add_argument("--model-base", default="https://api.deepseek.com")
    final = sub.add_parser("finalize")
    final.add_argument("--output", type=Path, required=True)
    final.add_argument("--protocol", type=Path, required=True)
    final.add_argument("--runtime-identity", type=Path)
    execution = sub.add_parser("run")
    execution.add_argument("--output", type=Path, required=True)
    execution.add_argument("--key-env", default="DEEPSEEK_API_KEY")
    execution.add_argument("--workers", type=int, choices=range(1, 9), default=4)
    execution.add_argument("--resume", action="store_true")
    execution.add_argument("--execute", action="store_true", help="Explicitly execute the frozen external DeepSeek generation batch")
    analysis = sub.add_parser("analyze")
    analysis.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "corpus":
        result = prepare_corpus(args.data_dir.resolve(), args.destination.resolve())
        result = {"dataset": result["dataset"], "source_count": len(result["source_files"]), "knowledge_document_count": len(result["derivations"]), "destination": str(args.destination)}
    elif args.command == "prepare":
        result = prepare(args)
    elif args.command == "finalize":
        result = finalize(args.output.resolve(), args.protocol, args.runtime_identity)
    elif args.command == "run":
        if not args.execute:
            raise SystemExit("run requires --execute; finalize and verify inputs first")
        result = run(args.output.resolve(), args.key_env, args.workers, args.resume)
    else:
        result = analyze(args.output.resolve())
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
