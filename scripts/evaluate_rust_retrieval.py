#!/usr/bin/env python3
"""Evaluate retrieval through the deployed Rust API, not a Python substitute."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from evaluate_retrieval import (
    Evidence,
    calculate_metrics,
    evidence_ranking_to_fact_run,
    fact_ids,
    load_questions,
    sha256_file,
    sha256_json,
)
from freeze_rag_evidence import build_bindings


API_MODES = {
    "bm25": "bm25_rag",
    "hybrid_rag": "project_rag",
    "graph_enhanced_rag": "kg_enhanced_rag",
}


def request_json(client: httpx.Client, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    response = client.request(method, path, **kwargs)
    try:
        payload = response.json()
    except ValueError as error:
        raise RuntimeError(f"Rust API returned non-JSON {response.status_code} for {path}") from error
    if response.is_error:
        detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
        raise RuntimeError(f"Rust API {method} {path} failed with {response.status_code}: {detail}")
    if not isinstance(payload, dict):
        raise RuntimeError(f"Rust API returned a non-object for {path}")
    return payload


def response_evidence(payload: dict[str, Any], mode: str) -> tuple[list[str], dict[str, Evidence]]:
    ranking: list[str] = []
    evidence_by_id: dict[str, Evidence] = {}
    for index, source in enumerate(payload.get("sources", []), start=1):
        if not isinstance(source, dict):
            continue
        evidence_id = f"{mode}:source:{source.get('chunk_id') or source.get('file_id') or index}"
        evidence_by_id[evidence_id] = Evidence(
            evidence_id=evidence_id,
            evidence_type="document_chunk",
            text=str(source.get("snippet") or ""),
            source=str(source.get("filename") or source.get("file_id") or "unknown"),
        )
        ranking.append(evidence_id)
    if mode == "graph_enhanced_rag":
        for index, relation in enumerate(payload.get("graph_context", []), start=1):
            if not isinstance(relation, dict):
                continue
            evidence_id = f"{mode}:graph:{relation.get('relation_id') or index}"
            text = " → ".join(
                str(relation.get(key) or "")
                for key in ("source_label", "relation_label", "target_label")
            )
            evidence_by_id[evidence_id] = Evidence(
                evidence_id=evidence_id,
                evidence_type="graph_relation",
                text=text,
                source=f"relation:{relation.get('relation_id') or index}",
            )
            ranking.append(evidence_id)
    return ranking, evidence_by_id


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    questions = load_questions(args.questions)
    retrieval_config = json.loads(args.retrieval_config.read_text(encoding="utf-8"))
    if not isinstance(retrieval_config, dict):
        raise ValueError("--retrieval-config must contain a JSON object")
    for key in ("embedding_backend", "embedding_model", "embedding_dimension"):
        if key not in retrieval_config:
            raise ValueError(f"--retrieval-config must include {key}")

    headers = {"Authorization": f"Bearer {args.token}"}
    base_url = args.base_url.rstrip("/")
    with httpx.Client(base_url=base_url, headers=headers, timeout=args.timeout) as client:
        metrics = request_json(client, "GET", "/metrics")
        runtime = metrics.get("runtime")
        if not isinstance(runtime, dict):
            raise ValueError("deployed Rust API did not expose runtime embedding metadata")
        if runtime.get("api_runtime") != "rust-axum":
            raise ValueError("deployed API is not identified as rust-axum")
        for key in ("embedding_backend", "embedding_model", "embedding_dimension"):
            if runtime.get(key) != retrieval_config.get(key):
                raise ValueError(
                    f"runtime {key} does not match retrieval configuration: "
                    f"{runtime.get(key)!r} != {retrieval_config.get(key)!r}"
                )
        status = request_json(client, "GET", f"/projects/{args.project_id}/rag/status")
        dataset = status.get("dataset") or {}
        if dataset.get("embedding_model") != runtime.get("embedding_model"):
            raise ValueError("deployed Rust dataset does not match the runtime embedding model")
        runs: dict[str, dict[str, dict[str, float]]] = {mode: {} for mode in API_MODES}
        trace_rows: list[dict[str, Any]] = []
        for question in questions:
            for mode, api_mode in API_MODES.items():
                payload = request_json(
                    client,
                    "POST",
                    f"/projects/{args.project_id}/rag/query",
                    json={"query": question["question"], "mode": api_mode},
                )
                ranking, evidence_by_id = response_evidence(payload, mode)
                runs[mode][question["id"]], trace = evidence_ranking_to_fact_run(
                    mode, question, ranking, evidence_by_id
                )
                trace_rows.extend(trace)

    qrels = {question["id"]: {fact_id: 1 for fact_id in fact_ids(question)} for question in questions}
    aggregate, per_query = calculate_metrics(qrels, runs)
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api_runtime": "rust-axum",
        "runtime": runtime,
        "base_url": base_url,
        "project_id": args.project_id,
        "questions_file": str(args.questions),
        "questions_sha256": sha256_file(args.questions),
        "question_count": len(questions),
        "fact_count": sum(len(question["facts"]) for question in questions),
        "corpus": {
            "sha256": args.corpus_sha256,
            "chunk_count": args.corpus_chunk_count,
        },
        "configuration": retrieval_config,
        "aggregate": aggregate,
        "ablation": [],
        "evidence_trace": trace_rows,
        "reproducibility_verified": False,
    }
    report["result_sha256"] = sha256_json(
        {
            "questions_sha256": report["questions_sha256"],
            "corpus": report["corpus"],
            "configuration": retrieval_config,
            "aggregate": aggregate,
            "per_query": per_query,
            "evidence_trace": trace_rows,
        }
    )
    if args.expected_result_sha256:
        if args.expected_result_sha256 != report["result_sha256"]:
            raise ValueError(
                f"result hash mismatch: expected {args.expected_result_sha256}, got {report['result_sha256']}"
            )
        report["reproducibility_verified"] = True
        report["evidence_bindings"] = build_bindings(
            report,
            image_digest=args.image_digest,
            git_revision=args.git_revision,
            embedding_model_sha256=args.embedding_model_sha256,
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"result_sha256": report["result_sha256"], "reproducibility_verified": report["reproducibility_verified"]}))
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--retrieval-config", type=Path, required=True)
    parser.add_argument("--corpus-sha256", required=True)
    parser.add_argument("--corpus-chunk-count", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-result-sha256", default="")
    parser.add_argument("--image-digest", default="")
    parser.add_argument("--git-revision", default="")
    parser.add_argument("--embedding-model-sha256", default="")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    if args.expected_result_sha256 and not all(
        (args.image_digest, args.git_revision, args.embedding_model_sha256)
    ):
        parser.error("binding metadata is required when --expected-result-sha256 is supplied")
    if args.corpus_chunk_count < 1:
        parser.error("--corpus-chunk-count must be positive")
    return args


if __name__ == "__main__":
    evaluate(parse_args())
