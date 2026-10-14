from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import httpx
import pytest


def load_module(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load_module("run_t114_rust_retest_v2.py", "t114_rust_retest_v2")
OLD_MODULE = load_module("run_t114_rust_retest.py", "t114_rust_retest_v1")
CASE = {"case_id": "Q1:document_rag:r1"}
CONTEXT = {"messages": [{"role": "user", "content": "synthetic test context"}], "prompt_sha256": "abc"}


def response_payload(content, finish_reason: str = "stop") -> dict:
    return {
        "id": "synthetic-response-1", "model": "returned-model",
        "usage": {"prompt_tokens": 42, "completion_tokens": 1000},
        "choices": [{"message": {"role": "assistant", "reasoning_content": "synthetic reasoning only", "content": content},
                     "finish_reason": finish_reason}],
    }


def test_frozen_generation_config_keeps_prior_settings_and_disables_thinking() -> None:
    config = MODULE.generation_config("https://provider.test", "deepseek-v4-flash")
    assert config == {
        "provider": "DeepSeek", "base_url": "https://provider.test", "model": "deepseek-v4-flash",
        "temperature": 0.1, "max_tokens": 1000, "thinking": {"type": "disabled"},
        "request_timeout_seconds": 180,
        "retry_policy": {"max_attempts": 2, "retry_statuses": [429, 500, 502, 503, 504], "backoff_seconds": 2},
    }


def test_request_sends_disabled_thinking_and_valid_response_matches_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    original_client = httpx.Client
    requests = []
    payload = response_payload("synthetic answer[E1]")

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(MODULE.httpx, "Client", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    config = MODULE.generation_config("https://provider.test", "deepseek-v4-flash")
    old = OLD_MODULE.generate_case(CASE, CONTEXT, config, "synthetic-key")
    new = MODULE.generate_case(CASE, CONTEXT, config, "synthetic-key")
    assert requests[1] == {**requests[0], "thinking": {"type": "disabled"}}
    for field in ("status", "answer", "requested_model", "returned_model", "usage", "finish_reason", "response_id", "raw_response"):
        assert new[field] == old[field]
    assert new["status"] == "completed"
    assert new["answer"] == "synthetic answer[E1]"
    assert new["message_keys"] == ["content", "reasoning_content", "role"]
    assert "synthetic-key" not in json.dumps(new)


@pytest.mark.parametrize(
    ("content", "finish_reason", "errors"),
    [("", "stop", ["empty_answer"]),
     ("  \n", "stop", ["empty_answer"]),
     (None, "stop", ["empty_answer"]),
     ("", "length", ["finish_reason_length", "empty_answer"]),
     ("synthetic partial answer", "length", ["finish_reason_length"])],
)
def test_empty_or_truncated_response_keeps_raw_evidence_and_fails_without_retry(
    monkeypatch: pytest.MonkeyPatch, content, finish_reason: str, errors: list[str],
) -> None:
    original_client = httpx.Client
    requests = []
    payload = response_payload(content, finish_reason)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(MODULE.httpx, "Client", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    config = MODULE.generation_config("https://provider.test", "deepseek-v4-flash")
    result = MODULE.generate_case(CASE, CONTEXT, config, "synthetic-key")
    assert len(requests) == 1
    assert requests[0]["thinking"] == {"type": "disabled"}
    assert result["status"] == "failed"
    assert "answer" not in result
    assert result["raw_response"] == payload
    assert result["usage"] == payload["usage"]
    assert result["response_id"] == payload["id"]
    assert result["returned_model"] == payload["model"]
    assert result["finish_reason"] == finish_reason
    assert result["message_keys"] == ["content", "reasoning_content", "role"]
    assert result["response_validation_errors"] == errors
    assert result["attempts"][0]["http_status"] == 200
    assert result["attempts"][1]["error_type"] == "ValueError"


def test_http_retry_remains_fixed_with_disabled_thinking(monkeypatch: pytest.MonkeyPatch) -> None:
    original_client = httpx.Client
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(503) if len(requests) == 1 else httpx.Response(200, json=response_payload("synthetic answer"))

    monkeypatch.setattr(MODULE.httpx, "Client", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr(MODULE.time, "sleep", lambda _: None)
    result = MODULE.generate_case(CASE, CONTEXT, MODULE.generation_config("https://provider.test", "deepseek-v4-flash"), "synthetic-key")
    assert result["status"] == "completed"
    assert [attempt["http_status"] for attempt in result["attempts"]] == [503, 200]
    assert all(request["thinking"] == {"type": "disabled"} for request in requests)


@pytest.mark.parametrize("thinking", [None, {"type": "enabled"}])
def test_generation_rejects_missing_or_enabled_thinking_before_any_request(thinking) -> None:
    config = MODULE.generation_config("https://provider.test", "deepseek-v4-flash")
    if thinking is None:
        del config["thinking"]
    else:
        config["thinking"] = thinking
    with pytest.raises(ValueError, match="explicit thinking.type=disabled"):
        MODULE.generate_case(CASE, CONTEXT, config, "synthetic-key")


def prepare_offline_fixture(tmp_path: Path) -> Path:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    questions = [{"id": "Q1", "question": "synthetic question", "facts": [{"aliases": ["synthetic fact"]}]}]
    MODULE.save_json(tmp_path / "questions.json", questions)
    context = {**CONTEXT, "prompt_sha256": MODULE.digest(MODULE.json_bytes(CONTEXT["messages"]))}
    MODULE.save_json(tmp_path / "contexts.json", {"Q1": {arm: context for arm in MODULE.ARMS}})
    MODULE.save_json(tmp_path / "raw-graph.json", {})
    MODULE.save_json(tmp_path / "approved-note-versions.json", [])
    MODULE.save_json(tmp_path / "retrieval-raw/Q1.json", {})
    MODULE.save_json(tmp_path / "preparation.json", {
        "generation": MODULE.generation_config("https://provider.test", "deepseek-v4-flash"),
        "corpus_dir": str(corpus), "source_provenance": {"source_files": []},
        "random_seed": 1, "case_count": 4,
    })
    protocol = tmp_path / "operational-protocol.md"
    protocol.write_text("Synthetic offline protocol fixture.\n")
    return protocol


def test_finalize_still_requires_semantic_protocol_and_binds_v2_script(tmp_path: Path) -> None:
    protocol = prepare_offline_fixture(tmp_path)
    with pytest.raises(ValueError, match="semantic primary-outcome protocol and script"):
        MODULE.finalize(tmp_path, protocol, None)
    assert not (tmp_path / "freeze.sha256").exists()
    MODULE.save_json(tmp_path / "semantic-protocol.json", {"schema_version": "synthetic-fixture"})
    MODULE.finalize(tmp_path, protocol, None)
    manifest = MODULE.verify_freeze(tmp_path)
    bound = {item["path"]: item["sha256"] for item in manifest["input_files"]}
    for path in (Path(MODULE.__file__).resolve(), Path(MODULE.__file__).with_name("run_t114_semantic_judge.py").resolve(),
                 (tmp_path / "semantic-protocol.json").resolve()):
        assert bound[str(path)] == MODULE.file_hash(path)
    assert str(Path(OLD_MODULE.__file__).resolve()) not in bound


def test_finalize_rejects_generation_config_without_explicit_disabled_thinking(tmp_path: Path) -> None:
    protocol = prepare_offline_fixture(tmp_path)
    MODULE.save_json(tmp_path / "semantic-protocol.json", {"schema_version": "synthetic-fixture"})
    preparation = MODULE.load_json(tmp_path / "preparation.json")
    del preparation["generation"]["thinking"]
    MODULE.save_json(tmp_path / "preparation.json", preparation)
    with pytest.raises(ValueError, match="explicit thinking.type=disabled"):
        MODULE.finalize(tmp_path, protocol, None)
    assert not (tmp_path / "freeze.sha256").exists()
