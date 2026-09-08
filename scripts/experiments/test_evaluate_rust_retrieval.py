from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "experiments"))
SCRIPT = ROOT / "scripts" / "experiments" / "evaluate_rust_retrieval.py"
SPEC = importlib.util.spec_from_file_location("evaluate_rust_retrieval", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_response_evidence_preserves_document_then_graph_order() -> None:
    ranking, evidence = MODULE.response_evidence(
        {
            "sources": [{"chunk_id": 11, "filename": "protocol.txt", "snippet": "Taq"}],
            "graph_context": [
                {
                    "relation_id": 9,
                    "source_label": "Taq",
                    "relation_label": "用于",
                    "target_label": "PCR",
                }
            ],
        },
        "graph_enhanced_rag",
    )

    assert ranking == ["legacy:graph_enhanced_rag:source:11", "legacy:graph_enhanced_rag:graph:9"]
    assert evidence[ranking[0]].text == "Taq"
    assert evidence[ranking[1]].evidence_type == "graph_relation"


def test_response_evidence_ignores_malformed_items() -> None:
    ranking, evidence = MODULE.response_evidence({"sources": [None], "graph_context": [None]}, "bm25")

    assert ranking == []
    assert evidence == {}


def snapshot() -> dict[str, object]:
    return {
        "dataset_id": 19,
        "corpus_snapshot_hash": "a" * 64,
        "corpus_chunk_count": 7,
        "rag_index_version": "structured-v1",
        "embedding_model": "rust-hash-512-v1",
        "graph_snapshot_hash": "b" * 64,
        "graph_entity_count": 2,
        "graph_relation_count": 1,
    }


def runtime() -> dict[str, object]:
    return {
        "api_runtime": "rust-axum",
        "embedding_backend": "hash",
        "embedding_model": "rust-hash-512-v1",
        "embedding_dimension": 512,
    }


def retrieval_config() -> dict[str, object]:
    return {
        "embedding_backend": "hash",
        "embedding_model": "rust-hash-512-v1",
        "embedding_dimension": 512,
        "rag_index_version": "structured-v1",
    }


def status() -> dict[str, object]:
    return {
        "dataset": {"id": 19, "embedding_model": "rust-hash-512-v1"},
        "corpus_snapshot": snapshot(),
    }


def test_validate_corpus_identity_returns_api_asserted_values() -> None:
    identity = MODULE.validate_corpus_identity(
        status(), runtime(), retrieval_config(), "a" * 64, 7
    )

    assert identity == {
        "dataset_id": 19,
        "corpus_snapshot_hash": "a" * 64,
        "corpus_chunk_count": 7,
        "rag_index_version": "structured-v1",
        "embedding_model": "rust-hash-512-v1",
        "graph_snapshot_hash": "b" * 64,
        "graph_entity_count": 2,
        "graph_relation_count": 1,
    }


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("corpus_snapshot_hash", "b" * 64, "corpus snapshot hash"),
        ("corpus_chunk_count", 8, "corpus chunk count"),
        ("embedding_model", "other-model", "embedding model"),
        ("rag_index_version", "other-index", "RAG index version"),
    ],
)
def test_validate_corpus_identity_rejects_identity_drift(
    field: str, value: object, message: str
) -> None:
    changed = status()
    changed["corpus_snapshot"] = {**snapshot(), field: value}

    expected_message = "embedding identity" if field == "embedding_model" else message
    with pytest.raises(ValueError, match=expected_message):
        MODULE.validate_corpus_identity(
            changed, runtime(), retrieval_config(), "a" * 64, 7
        )


def test_validate_corpus_identity_rejects_missing_identity_field() -> None:
    changed = status()
    changed["corpus_snapshot"] = {
        key: value for key, value in snapshot().items() if key != "corpus_chunk_count"
    }

    with pytest.raises(ValueError, match="corpus_chunk_count"):
        MODULE.validate_corpus_identity(
            changed, runtime(), retrieval_config(), "a" * 64, 7
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [("corpus_snapshot_hash", "not-a-sha256"), ("corpus_chunk_count", 0)],
)
def test_validate_corpus_identity_rejects_malformed_api_values(
    field: str, value: object
) -> None:
    changed = status()
    changed["corpus_snapshot"] = {**snapshot(), field: value}

    with pytest.raises(ValueError, match="invalid corpus"):
        MODULE.validate_corpus_identity(
            changed, runtime(), retrieval_config(), "a" * 64, 7
        )


@pytest.mark.parametrize("mutation", ["missing_used", "used_differs_actual", "used_differs_expected"])
def test_retrieval_snapshot_gate_requires_expected_actual_and_used(mutation: str) -> None:
    expected = {"corpus_snapshot_hash": "a" * 64, "graph_snapshot_hash": "b" * 64}
    payload = {
        "actual_corpus_snapshot_hash": "a" * 64,
        "used_corpus_snapshot_hash": "a" * 64,
        "actual_graph_snapshot_hash": "b" * 64,
        "used_graph_snapshot_hash": "b" * 64,
    }
    if mutation == "missing_used":
        payload.pop("used_corpus_snapshot_hash")
    elif mutation == "used_differs_actual":
        payload["used_corpus_snapshot_hash"] = "c" * 64
    else:
        payload["actual_corpus_snapshot_hash"] = "c" * 64
        payload["used_corpus_snapshot_hash"] = "a" * 64
    with pytest.raises(ValueError):
        MODULE.validate_retrieval_snapshot(payload, expected)


class FakeResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    @property
    def is_error(self) -> bool:
        return self.status_code >= 400

    def json(self) -> dict[str, object]:
        return self._payload


class FakeClient:
    def __init__(self, status_payload: dict[str, object]) -> None:
        self.status_payload = status_payload
        self.post_count = 0
        self.post_paths: list[str] = []
        self.post_payloads: list[dict[str, object]] = []

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def request(self, method: str, path: str, **kwargs: object) -> FakeResponse:
        if method == "GET" and path == "/metrics":
            return FakeResponse({"runtime": runtime()})
        if method == "GET" and path == "/projects/19/rag/status":
            return FakeResponse(self.status_payload)
        if method == "POST":
            self.post_count += 1
            self.post_paths.append(path)
            payload = kwargs["json"]
            assert isinstance(payload, dict)
            self.post_payloads.append(payload)
            return FakeResponse(
                {
                    "retrieval_only": True,
                    "generation_invoked": False,
                    "llm_query_rewrite_invoked": False,
                    "citation_repair_invoked": False,
                    "corpus_snapshot_hash": payload["expected_corpus_snapshot_hash"],
                    "actual_corpus_snapshot_hash": payload["expected_corpus_snapshot_hash"],
                    "used_corpus_snapshot_hash": payload["expected_corpus_snapshot_hash"],
                    "graph_snapshot_hash": payload["expected_graph_snapshot_hash"],
                    "actual_graph_snapshot_hash": payload["expected_graph_snapshot_hash"],
                    "used_graph_snapshot_hash": payload["expected_graph_snapshot_hash"],
                    "corpus_chunk_count": 7,
                    "graph_entity_count": 2,
                    "graph_relation_count": 1,
                    "sources": [],
                    "graph_context": [],
                    "effective_retrieval_config": {
                        "normalized_query": "what?",
                        "bm25_expanded_query": "What?",
                        "bm25_expanded_terms": [],
                    },
                }
            )
        raise AssertionError(f"unexpected request: {method} {path}")


def test_evaluate_rejects_status_before_query_post(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    questions = tmp_path / "questions.json"
    questions.write_text(
        '[{"id":"Q1","question":"What?","facts":[{"label":"fact","aliases":["fact"]}]}]',
        encoding="utf-8",
    )
    config = tmp_path / "config.json"
    config.write_text(json.dumps(retrieval_config()), encoding="utf-8")
    output = tmp_path / "report.json"
    client = FakeClient({"dataset": status()["dataset"], "corpus_snapshot": {**snapshot(), "corpus_chunk_count": 8}})
    monkeypatch.setattr(MODULE.httpx, "Client", lambda **kwargs: client)
    args = MODULE.argparse.Namespace(
        base_url="http://backend",
        token="token",
        project_id=19,
        questions=questions,
        retrieval_config=config,
        corpus_sha256="a" * 64,
        corpus_chunk_count=7,
        output=output,
        expected_result_sha256="",
        timeout=1.0,
    )

    with pytest.raises(ValueError, match="corpus chunk count"):
        MODULE.evaluate(args)

    assert client.post_count == 0


def test_evaluate_report_uses_api_asserted_corpus_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    questions = tmp_path / "questions.json"
    questions.write_text(
        '[{"id":"Q1","question":"What?","facts":[{"label":"fact","aliases":["fact"]}]}]',
        encoding="utf-8",
    )
    config = tmp_path / "config.json"
    config.write_text(json.dumps(retrieval_config()), encoding="utf-8")
    output = tmp_path / "report.json"
    client = FakeClient(status())
    monkeypatch.setattr(MODULE.httpx, "Client", lambda **kwargs: client)
    args = MODULE.argparse.Namespace(
        base_url="http://backend",
        token="token",
        project_id=19,
        questions=questions,
        retrieval_config=config,
        corpus_sha256="a" * 64,
        corpus_chunk_count=7,
        output=output,
        expected_result_sha256="",
        timeout=1.0,
    )

    report = MODULE.evaluate(args)

    assert client.post_count == 3
    assert report["corpus"] == {
        "dataset_id": 19,
        "corpus_snapshot_hash": "a" * 64,
        "corpus_chunk_count": 7,
        "rag_index_version": "structured-v1",
        "embedding_model": "rust-hash-512-v1",
        "graph_snapshot_hash": "b" * 64,
        "graph_entity_count": 2,
        "graph_relation_count": 1,
    }
    assert client.post_paths == ["/projects/19/rag/retrieve"] * 3
    assert all("expected_graph_snapshot_hash" in payload for payload in client.post_payloads)


def test_result_hash_is_recomputed_from_persisted_canonical_material(tmp_path: Path) -> None:
    material_path = tmp_path / "canonical-result-material.json"
    material_path.write_text(json.dumps({"a": 1, "n": None}) + "\n", encoding="utf-8")
    result = MODULE.compute_result_sha256(material_path)
    assert result == MODULE.verify_result_material_hash(material_path, result)
    material_path.write_text(json.dumps({"a": 2, "n": None}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="tampered"):
        MODULE.verify_result_material_hash(material_path, result)


def test_canonicalization_is_custom_nfc_sorted_and_finite() -> None:
    assert MODULE.canonical_json_bytes({"b": "e\u0301", "a": None, "n": 1.0}) == b'{"a":null,"b":"\xc3\xa9","n":1.0}'
    with pytest.raises(ValueError, match="non-finite"):
        MODULE.canonical_json_bytes({"n": float("nan")})
    with pytest.raises(ValueError, match="ASCII"):
        MODULE.canonical_json_bytes({"非ASCII": "value"})


def test_persisted_projection_rejects_content_or_graph_identity_tampering() -> None:
    question = {"id": "Q1", "question": "?", "facts": [{"label": "A", "aliases": ["Fact A"]}]}
    payload = {
        "retrieval_only": True,
        "generation_invoked": False,
        "llm_query_rewrite_invoked": False,
        "citation_repair_invoked": False,
        "sources": [{
            "filename": "a.md", "chunk_index": 0, "content": "Fact A",
            "content_sha256": MODULE.hashlib.sha256(b"Fact A").hexdigest(), "file_hash": "f" * 64,
        }],
        "graph_context": [],
        "effective_retrieval_config": {"normalized_query": "?", "bm25_expanded_query": "?", "bm25_expanded_terms": []},
    }
    projection = MODULE.build_evidence_snapshot(payload, "bm25", question)["canonical_projection"]
    tampered = json.loads(json.dumps(projection))
    tampered["ordered_evidence"][0]["text"] = "Fact B"
    with pytest.raises(ValueError, match="content hash"):
        MODULE._validate_persisted_projection(tampered, question)

    graph_payload = {
        "retrieval_only": True,
        "generation_invoked": False,
        "llm_query_rewrite_invoked": False,
        "citation_repair_invoked": False,
        "sources": [],
        "graph_context": [{
            "source_entity_type": "protein",
            "source_natural_key": "protein:taq",
            "source_normalized_label": "taq",
            "source_label": "Taq",
            "relation_type": "used_for",
            "relation_label": "用于",
            "target_entity_type": "process",
            "target_natural_key": "process:pcr",
            "target_normalized_label": "pcr",
            "target_label": "PCR",
            "relation_roles": ["enzyme"],
            "confidence": 0.9,
            "relation_properties": {"kind": "knowledge"},
        }],
        "effective_retrieval_config": {
            "normalized_query": "?",
            "bm25_expanded_query": "?",
            "bm25_expanded_terms": [],
        },
    }
    graph_projection = MODULE.build_evidence_snapshot(
        graph_payload, "graph_enhanced_rag", question
    )["canonical_projection"]
    graph_tampered = json.loads(json.dumps(graph_projection))
    graph_tampered["ordered_evidence"][0]["relation_properties"]["kind"] = "tampered"
    with pytest.raises(ValueError, match="graph stable ID"):
        MODULE._validate_persisted_projection(graph_tampered, question)


def test_unmatched_gold_fact_has_one_null_trace_row() -> None:
    projection = {
        "mode": "bm25", "question_id": "Q1",
        "ordered_evidence": [{
            "evidence_presentation_rank": 1, "evidence_id": "document:stable",
            "match_trace": [],
        }],
    }
    _, trace = MODULE._fact_ranks(
        projection,
        {"id": "Q1", "question": "?", "facts": [{"label": "A", "aliases": ["Fact A"]}]},
    )
    assert trace == [{"fact_id": "Q1:F01", "matched_alias": None, "min_evidence_presentation_rank": None, "stable_evidence_id": None}]


def test_g5b_rejects_missing_duplicate_or_failed_question_method_cases() -> None:
    questions = [{"id": "Q1", "question": "?", "facts": [{"label": "A", "aliases": ["A"]}]}]
    projection = lambda mode: {"canonical_projection": {"question_id": "Q1", "mode": mode}}
    passing = [
        {
            "run": "run",
            "question_id": "Q1",
            "mode": mode,
            "expected": {},
            "actual": {},
            "used": {},
            "equality": {"expected_actual": True, "expected_used": True, "actual_used": True},
            "counts": {},
            "utc": "2026-08-13T00:00:00+00:00",
            "verdict": "pass",
        }
        for mode in MODULE.API_MODES
    ]
    MODULE.validate_complete_batch(questions, [projection(mode) for mode in MODULE.API_MODES], passing)
    with pytest.raises(ValueError, match="exactly one"):
        MODULE.validate_complete_batch(questions, [projection("bm25")], passing)
    with pytest.raises(ValueError, match="exactly one"):
        MODULE.validate_complete_batch(questions, [projection(mode) for mode in MODULE.API_MODES], passing[:-1] + [passing[-1] | {"verdict": "fail"}])
    with pytest.raises(ValueError, match="exactly one"):
        MODULE.validate_complete_batch(questions, [projection(mode) for mode in MODULE.API_MODES], passing + [passing[0]])
    with pytest.raises(ValueError, match="schema"):
        MODULE.validate_complete_batch(
            questions,
            [projection(mode) for mode in MODULE.API_MODES],
            [passing[0] | {"equality": {}}] + passing[1:],
        )
    with pytest.raises(ValueError, match="exactly one"):
        MODULE.validate_complete_batch(questions, [projection(mode) for mode in MODULE.API_MODES] + [projection("bm25")], passing)
    with pytest.raises(ValueError, match="exactly one"):
        unknown = [*passing[:-1], {**passing[-1], "question_id": "UNKNOWN"}]
        MODULE.validate_complete_batch(questions, [projection(mode) for mode in MODULE.API_MODES], unknown)


def test_question_freeze_is_immutable_when_source_changes(tmp_path: Path) -> None:
    source = tmp_path / "questions.json"
    frozen = tmp_path / "questions-frozen.json"
    source.write_text('[{"id":"Q1","question":"old","facts":[{"label":"old","aliases":["old"]}]}]', encoding="utf-8")
    questions, digest = MODULE.load_and_freeze_questions(source, frozen)
    source.write_text('[{"id":"Q1","question":"changed","facts":[]}]', encoding="utf-8")
    assert questions == [{"id": "Q1", "question": "old", "facts": [{"label": "old", "aliases": ["old"]}]}]
    assert MODULE.hashlib.sha256(frozen.read_bytes()).hexdigest() == digest
    assert MODULE.load_questions(frozen) == questions


def test_raw_canonical_divergence_is_rejected() -> None:
    question = {"id": "Q1", "question": "?", "facts": [{"label": "A", "aliases": ["Fact A"]}]}
    payload = {
        "retrieval_only": True, "generation_invoked": False,
        "llm_query_rewrite_invoked": False, "citation_repair_invoked": False,
        "sources": [], "graph_context": [],
        "effective_retrieval_config": {"normalized_query": "?", "bm25_expanded_query": "?", "bm25_expanded_terms": []},
    }
    snapshot = MODULE.build_evidence_snapshot(payload, "bm25", question)
    snapshot["canonical_projection"]["question"] = "changed"
    with pytest.raises(ValueError, match="raw response and canonical projection"):
        MODULE._validate_persisted_snapshot(snapshot, question)


def test_second_deployment_flag_requires_exact_expected_hash() -> None:
    result = "a" * 64
    assert not MODULE.same_deployment_repeatability_verified("", result)
    assert not MODULE.same_deployment_repeatability_verified("b" * 64, result)
    assert MODULE.same_deployment_repeatability_verified(result, result)


def test_fact_metrics_inherit_one_original_rank_for_multiple_facts() -> None:
    projection = {
        "mode": "bm25",
        "question_id": "Q1",
        "ordered_evidence": [
            {
                "evidence_presentation_rank": 1,
                "evidence_id": "document:stable",
                "evidence_type": "document_chunk",
                "text": "Fact A and Fact B",
                "source": "a.md",
                "match_trace": [
                    {"fact_id": "Q1:F01", "alias": "Fact A", "evidence_presentation_rank": 1, "evidence_id": "document:stable"},
                    {"fact_id": "Q1:F02", "alias": "Fact B", "evidence_presentation_rank": 1, "evidence_id": "document:stable"},
                ],
            }
        ],
    }
    aggregate, rows = MODULE.calculate_fact_metrics(
        [{"canonical_projection": projection}],
        [{"id": "Q1", "question": "?", "facts": [{"label": "A", "aliases": ["Fact A"]}, {"label": "B", "aliases": ["Fact B"]}]}],
    )
    assert rows[0]["fact_match_trace"][0]["min_evidence_presentation_rank"] == 1
    assert rows[0]["GoldFactAliasHitCoverage@returned_set"] == 1.0
    assert rows[0]["first_alias_hit_rr"] == 1.0
    assert rows[0]["rank_discounted_fact_alias_coverage"] == 1.0
    assert aggregate[0]["GoldFactAliasHitCoverage@1"] == 1.0


def test_retrieval_request_requires_atomic_dual_snapshot() -> None:
    request = MODULE.build_retrieval_request(
        "What?",
        "bm25_rag",
        {"corpus_snapshot_hash": "a" * 64, "graph_snapshot_hash": "b" * 64},
    )
    assert request == {
        "query": "What?",
        "mode": "bm25_rag",
        "expected_corpus_snapshot_hash": "a" * 64,
        "expected_graph_snapshot_hash": "b" * 64,
    }


def test_canonical_projection_preserves_raw_response_and_match_trace() -> None:
    payload = {
        "retrieval_only": True,
        "generation_invoked": False,
        "llm_query_rewrite_invoked": False,
        "citation_repair_invoked": False,
        "sources": [
            {
                "filename": "a.md",
                "chunk_index": 0,
                "content": "Fact A",
                "content_sha256": MODULE.hashlib.sha256("Fact A".encode()).hexdigest(),
                "file_hash": "f" * 64,
            }
        ],
        "graph_context": [],
        "effective_retrieval_config": {
            "mode": "bm25_rag",
            "normalized_query": "?",
            "bm25_expanded_query": "?",
            "bm25_expanded_terms": [],
        },
    }
    snapshot = MODULE.build_evidence_snapshot(payload, "bm25", {"id": "Q1", "question": "?", "facts": [{"label": "A", "aliases": ["Fact A"]}]})
    assert snapshot["raw_response"] == payload
    assert snapshot["ordered_evidence"][0]["match_trace"][0]["fact_id"] == "Q1:F01"
