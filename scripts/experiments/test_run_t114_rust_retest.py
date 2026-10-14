from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("t114_rust_retest", Path(__file__).with_name("run_t114_rust_retest.py"))
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def source(text: str, identifier: int) -> dict:
    return {"content": text, "content_sha256": MODULE.digest(text.encode()), "chunk_id": identifier, "filename": "source.txt"}


def test_corpus_preserves_source_hashes_and_removes_contact_metadata(tmp_path: Path) -> None:
    destination = tmp_path / "corpus"
    report = MODULE.prepare_corpus(ROOT / "data/real/GSE111619", destination)
    soft = (destination / "knowledge_files/GSE111619_family.soft").read_text()
    assert "_contact_" not in soft
    assert "!Sample_geo_accession = GSM3035185" in soft
    assert len(report["source_files"]) == 9
    assert len(report["derivations"]) == 4
    assert MODULE.file_hash(destination / "notes.json") == MODULE.file_hash(ROOT / "data/real/GSE111619/gse111619_notes.json")
    assert report["count_matrix_upload"] is False
    with pytest.raises(ValueError, match="refuse to overwrite"):
        MODULE.prepare_corpus(ROOT / "data/real/GSE111619", destination)


def test_document_budget_never_partially_truncates_or_backfills() -> None:
    evidence, stats = MODULE.document_evidence([source("a" * 10, 1), source("b" * 30, 2), source("c", 3)], 25)
    assert [item["source_id"] for item in evidence] == [1]
    assert evidence[0]["text"] == "a" * 10
    assert stats["omitted_count"] == 2
    invalid = source("correct", 1)
    invalid["content_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash mismatch"):
        MODULE.document_evidence([invalid], 100)


def test_retrieval_requires_all_negative_llm_flags_and_atomic_hash_binding() -> None:
    expected = {"corpus_snapshot_hash": "a" * 64, "graph_snapshot_hash": "b" * 64}
    response = {"retrieval_only": True, "generation_invoked": False, "llm_query_rewrite_invoked": False, "citation_repair_invoked": False}
    for key, value in expected.items():
        response["actual_" + key] = value
        response["used_" + key] = value
    MODULE.verify_retrieval(response, expected)
    response["used_graph_snapshot_hash"] = "c" * 64
    with pytest.raises(ValueError, match="snapshot drift"):
        MODULE.verify_retrieval(response, expected)
    response["used_graph_snapshot_hash"] = expected["graph_snapshot_hash"]
    del response["citation_repair_invoked"]
    with pytest.raises(ValueError, match="retrieval-only"):
        MODULE.verify_retrieval(response, expected)


def test_pagination_import_adapter_gets_all_rust_items() -> None:
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        skip = int(request.url.params["skip"])
        requested.append(skip)
        items = [{"id": i} for i in range(skip, min(skip + 100, 201))]
        return httpx.Response(200, json={"items": items, "total": 201})

    api = object.__new__(MODULE.ApiClient)
    api.client = httpx.Client(base_url="http://local.test", transport=httpx.MockTransport(handler))
    assert len(api.all_items("/projects")) == 201
    assert requested == [0, 100, 200]
    api.client.close()


def test_finalized_inputs_fail_closed_on_drift(tmp_path: Path) -> None:
    frozen_input = tmp_path / "questions.json"
    frozen_input.write_text("[]")
    MODULE.save_json(tmp_path / "freeze-manifest.json", {"input_files": [{"path": str(frozen_input), "sha256": MODULE.file_hash(frozen_input)}]})
    (tmp_path / "freeze.sha256").write_text(MODULE.file_hash(tmp_path / "freeze-manifest.json"))
    MODULE.verify_freeze(tmp_path)
    frozen_input.write_text("[1]")
    with pytest.raises(ValueError, match="frozen input drift"):
        MODULE.verify_freeze(tmp_path)


def test_numeric_aliases_do_not_match_longer_numbers() -> None:
    assert MODULE.matching_alias("检测17926个", ["17926"]) == "17926"
    assert MODULE.matching_alias("检测117926个", ["17926"]) is None
    assert MODULE.matching_alias("检测179260个", ["17926"]) is None


def test_generation_records_fixed_retry_and_actual_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    original_client = httpx.Client
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"id": "response-1", "model": "returned-model", "usage": {"prompt_tokens": 42, "completion_tokens": 5}, "choices": [{"message": {"content": "结论[E1]"}, "finish_reason": "stop"}]})

    monkeypatch.setattr(MODULE.httpx, "Client", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr(MODULE.time, "sleep", lambda _: None)
    config = {"model": "requested-model", "base_url": "https://provider.test", "temperature": 0.1, "max_tokens": 1000, "request_timeout_seconds": 10, "retry_policy": {"max_attempts": 2, "retry_statuses": [503], "backoff_seconds": 2}}
    result = MODULE.generate_case({"case_id": "Q1:arm:r1"}, {"messages": [], "prompt_sha256": "abc"}, config, "never-persist-this-key")
    assert result["status"] == "completed"
    assert len(result["attempts"]) == 2
    assert result["usage"]["prompt_tokens"] == 42
    assert result["requested_model"] == "requested-model"
    assert result["returned_model"] == "returned-model"
    assert all(request["temperature"] == 0.1 and request["max_tokens"] == 1000 for request in requests)
    assert "never-persist-this-key" not in json.dumps(result)


def test_analysis_uses_question_means_and_excludes_incomplete_pairs(tmp_path: Path) -> None:
    questions = [{"id": qid, "question": "question", "facts": [{"id": "F1", "aliases": ["correct"]}], "forbidden_facts": []} for qid in ("Q1", "Q2")]
    MODULE.save_json(tmp_path / "questions.json", questions)
    cases = [{"case_id": f"{qid}:{arm}:r{rep}", "question_id": qid, "arm": arm, "repetition": rep, "execution_order": index} for index, (qid, arm, rep) in enumerate([(qid, arm, rep) for qid in ("Q1", "Q2") for arm in MODULE.ARMS for rep in (1, 2, 3)], 1)]
    manifest = {"input_files": [{"path": str(tmp_path / "questions.json"), "sha256": MODULE.file_hash(tmp_path / "questions.json")}], "preparation": {"case_plan": cases, "repetitions": 3, "random_seed": 1, "method_label": "adapter"}}
    MODULE.save_json(tmp_path / "freeze-manifest.json", manifest)
    (tmp_path / "freeze.sha256").write_text(MODULE.file_hash(tmp_path / "freeze-manifest.json"))
    rows = []
    for case in cases:
        failed = case["question_id"] == "Q2" and case["arm"] == "document_plus_one_hop" and case["repetition"] == 2
        rows.append({**case, "status": "failed" if failed else "completed", "answer": "correct" if case["arm"] == "document_plus_one_hop" else "missing"})
    (tmp_path / "results.jsonl").write_text("\n".join(json.dumps(row) for row in rows))
    result = MODULE.analyze(tmp_path)
    assert result["planned_cases"] == 24
    assert result["failed_cases"] == 1
    report = MODULE.load_json(tmp_path / "analysis.json")
    assert report["comparisons"]["document_rag"]["n_questions"] == 1
    assert report["comparisons"]["document_rag"]["paired_question_ids"] == ["Q1"]
    assert report["comparisons"]["document_rag"]["mean_difference"] == 1.0
    assert report["unit"] == "question"
