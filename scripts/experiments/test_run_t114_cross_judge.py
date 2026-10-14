"""Meaningful offline checks for T114 input identity, scoring and credentials."""

import argparse
import importlib.util
import json
import urllib.error
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("run_t114_cross_judge.py")
SPEC = importlib.util.spec_from_file_location("t114_cross_judge", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def judge_config():
    return [{"id": "gpt_session", "kind": "codex_session_independent_agent", "provider": "codex", "model": None}]


def sample_input():
    return {"question": "退火温度是多少？", "answer": "退火温度为58℃。[E1]", "evidence": [{"id": "E1", "text": "退火温度58℃。"}],
            "reference_groups": [{"id": "F1", "aliases": ["58℃", "58°C"]}],
            "citations": [{"id": "C1", "evidence_id": "E1", "token": "[E1]", "start": 10, "end": 14}]}


def valid_judgment():
    return {"claims": [{"id": "K1", "text": "退火温度为58℃", "support": "supported", "evidence_ids": ["E1"], "explanation": "证据明确"}],
            "references": [{"group_id": "F1", "covered": True, "answer_quote": "58℃", "explanation": "已给出"}],
            "contexts": [{"evidence_id": "E1", "relevance": "relevant", "explanation": "直接回答"}],
            "citations": [{"citation_id": "C1", "claim_quote": "退火温度为58℃", "support": "supported", "explanation": "编号对应"}],
            "overall_notes": "无过度推断"}


def minimal_frozen():
    inp = sample_input()
    return {"schema_version": MODULE.SCHEMA, "rubric_version": MODULE.RUBRIC, "system_prompt": MODULE.SYSTEM_PROMPT,
            "system_prompt_sha256": MODULE.hashlib.sha256(MODULE.SYSTEM_PROMPT.encode()).hexdigest(), "judges": judge_config(),
            "samples": [{"sample_id": "A1", "input_sha256": MODULE.digest(inp), "input": inp,
                         "metadata": {"question_index": 1, "mode": "project_rag", "repetition": 1}}],
            "analysis_plan": {"bootstrap_seed": 1, "bootstrap_resamples": 100}, "limitations": []}


def test_anonymization_expands_ranges_and_preserves_unresolved_ids():
    assert MODULE.anonymize_answer("[G1-G3][S1][S9]", {"G1": "E2", "G2": "E3", "G3": "E4", "S1": "E1"}) == "[E2][E3][E4][E1][E_UNRESOLVED_S9]"


def test_archived_40_have_correct_source_mapping_without_old_scores():
    samples = MODULE.archived_samples(MODULE.ROOT / "docs/experiments/rag-experiment-4.csv", MODULE.ROOT / "docs/experiments/rag-experiment-4-evaluation-sheet.csv")
    assert len(samples) == 40
    assert len({s["sample_id"] for s in samples}) == 40
    for sample in samples:
        assert MODULE.digest(sample["input"]) == sample["input_sha256"]
        assert "mode" not in sample["input"]
        assert "evaluation_score" not in sample["input"]
        assert "[S1]" not in sample["input"]["answer"]
        assert "[G1]" not in sample["input"]["answer"]
        assert len(sample["input"]["evidence"]) == len(sample["evidence_provenance"])


def test_supported_quote_and_evidence_are_validated():
    result = MODULE.validate_judgment(valid_judgment(), sample_input())
    assert set(result["metrics"].values()) == {1.0}
    value = valid_judgment()
    value["claims"][0]["text"] = "模型编造的引文"
    with pytest.raises(ValueError, match="quote"):
        MODULE.validate_judgment(value, sample_input())
    value = valid_judgment()
    value["claims"][0]["evidence_ids"] = ["E9"]
    with pytest.raises(ValueError, match="evidence ids"):
        MODULE.validate_judgment(value, sample_input())


def test_missing_coverage_item_and_false_citation_support_fail():
    value = valid_judgment()
    value["references"] = []
    with pytest.raises(ValueError, match="identities"):
        MODULE.validate_judgment(value, sample_input())
    inp = sample_input()
    inp["citations"][0]["evidence_id"] = "E_UNRESOLVED_S9"
    with pytest.raises(ValueError, match="nonexistent citation"):
        MODULE.validate_judgment(valid_judgment(), inp)


def test_empty_denominators_are_missing_not_zero():
    inp = sample_input()
    inp["citations"] = []
    value = valid_judgment()
    value["claims"] = []
    value["citations"] = []
    scores = MODULE.validate_judgment(value, inp)
    assert scores["metrics"]["claim_support_rate"] is None
    assert scores["metrics"]["citation_support_rate"] is None


def test_official_credentials_cannot_be_sent_to_gateway():
    judge = {"id": "api", "kind": "chat_completions", "provider": "openai", "model": "gpt-example", "base_url": "https://example.com/v1", "key_env": "OPENAI_API_KEY"}
    with pytest.raises(ValueError, match="official endpoint"):
        MODULE.validate_judges([judge])
    judge["provider"] = "compatible"
    with pytest.raises(ValueError, match="dedicated credential"):
        MODULE.validate_judges([judge])
    judge["key_env"] = "TEST_GATEWAY_API_KEY"
    MODULE.validate_judges([judge])


def test_redirect_is_refused():
    request = MODULE.urllib.request.Request("https://api.deepseek.com/chat/completions")
    with pytest.raises(urllib.error.HTTPError):
        MODULE.NoRedirect().redirect_request(request, None, 302, "Found", {}, "https://foreign.invalid")


def test_secrets_or_path_escape_are_not_allowed_in_frozen_configuration():
    config = judge_config()
    config[0]["api_key"] = "must-not-be-frozen"
    with pytest.raises(ValueError, match="do not include credentials"):
        MODULE.validate_judges(config)
    config = judge_config()
    config[0]["id"] = "../../outside"
    with pytest.raises(ValueError, match="unsafe id"):
        MODULE.validate_judges(config)


def test_manifest_tampering_is_rejected(tmp_path):
    frozen = minimal_frozen()
    frozen["manifest_sha256"] = MODULE.digest(frozen)
    path = tmp_path / "freeze.json"
    MODULE.write_json(path, frozen)
    assert MODULE.load_frozen(path)["manifest_sha256"] == frozen["manifest_sha256"]
    frozen["samples"][0]["input"]["answer"] = "改写后答案"
    MODULE.write_json(path, frozen)
    with pytest.raises(ValueError, match="integrity"):
        MODULE.load_frozen(path)


def test_import_rejects_wrong_sample_hash_and_duplicate_result(tmp_path):
    frozen = minimal_frozen()
    frozen["manifest_sha256"] = MODULE.digest(frozen)
    freeze = tmp_path / "freeze.json"
    MODULE.write_json(freeze, frozen)
    document = {"source": "codex_session_independent_agent", "judge_id": "gpt_session", "model": None, "agent_id": "/root/gpt_independent_1",
                "manifest_sha256": frozen["manifest_sha256"], "judgments": [{"sample_id": "A1", "input_sha256": "wrong", "judgment": valid_judgment()}]}
    source = tmp_path / "judgment.json"
    MODULE.write_json(source, document)
    args = argparse.Namespace(freeze=freeze, judge="gpt_session", import_judgments=source, output=tmp_path / "run")
    with pytest.raises(ValueError, match="identity/hash"):
        MODULE.import_judgments(args)
    document["judgments"][0]["input_sha256"] = frozen["samples"][0]["input_sha256"]
    MODULE.write_json(source, document)
    MODULE.import_judgments(args)
    with pytest.raises(ValueError, match="already exists"):
        MODULE.import_judgments(args)


def test_pairing_is_by_question_and_missing_does_not_become_zero():
    frozen = minimal_frozen()
    frozen["manifest_sha256"] = MODULE.digest(frozen)
    frozen["samples"] += [{**frozen["samples"][0], "sample_id": "A2", "metadata": {"question_index": 1, "mode": "kg_enhanced_rag"}}]
    records = []
    for mode, rep, value in [("project_rag", 1, .2), ("project_rag", 2, .4), ("kg_enhanced_rag", 1, .8)]:
        records.append({"judge_id": "gpt_session", "sample_id": f"{mode}{rep}", "status": "valid", "metadata": {"mode": mode, "question_index": 1},
                        "metrics": {m: value if m != "citation_support_rate" else None for m in MODULE.METRICS}})
    summary = MODULE.summarize(frozen, {"records": records})
    contrast = summary["within_judge_paired_contrasts"]["gpt_session"]
    assert contrast["claim_support_rate"]["paired_question_n"] == 1
    assert contrast["claim_support_rate"]["mean_difference"] == pytest.approx(.5)
    assert contrast["citation_support_rate"]["paired_question_n"] == 0
    assert contrast["citation_support_rate"]["mean_difference"] is None


def test_jsonl_offline_import_has_same_provenance_contract(tmp_path):
    frozen = minimal_frozen()
    frozen["manifest_sha256"] = MODULE.digest(frozen)
    freeze = tmp_path / "freeze.json"
    MODULE.write_json(freeze, frozen)
    metadata = {"type": "metadata", "source": "codex_session_independent_agent", "judge_id": "gpt_session", "model": None,
                "agent_id": "/root/gpt_independent_1", "manifest_sha256": frozen["manifest_sha256"]}
    row = {"sample_id": "A1", "input_sha256": frozen["samples"][0]["input_sha256"], "judgment": valid_judgment()}
    source = tmp_path / "judge.jsonl"
    source.write_text(json.dumps(metadata) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    MODULE.import_judgments(argparse.Namespace(freeze=freeze, judge="gpt_session", import_judgments=source, output=tmp_path / "run"))
    payload = json.loads((tmp_path / "run/results.json").read_text())
    assert payload["records"][0]["agent_id"] == metadata["agent_id"]
    assert payload["records"][0]["model"] is None


def test_checkpoint_persistence_reloads_latest_records_before_appending(tmp_path):
    frozen = minimal_frozen()
    frozen["manifest_sha256"] = MODULE.digest(frozen)
    frozen["samples"].append({**frozen["samples"][0], "sample_id": "A2", "metadata": {"question_index": 1, "mode": "kg_enhanced_rag"}})
    output = tmp_path / "run"
    first = {"judge_id": "gpt_session", "sample_id": "A1", "status": "failed", "metadata": frozen["samples"][0]["metadata"], "metrics": dict.fromkeys(MODULE.METRICS)}
    second = {**first, "sample_id": "A2", "metadata": frozen["samples"][1]["metadata"]}
    MODULE.persist_records(frozen, output, [first])
    MODULE.persist_records(frozen, output, [second])
    payload = json.loads((output / "results.json").read_text())
    assert [r["sample_id"] for r in payload["records"]] == ["A1", "A2"]
    summary = json.loads((output / "summary.json").read_text())
    assert summary["availability"]["gpt_session"]["failed_samples"] == 2
    assert summary["within_judge_paired_contrasts"]["gpt_session"]["claim_support_rate"]["paired_question_n"] == 0


def test_prepare_is_reproducible_random_order_and_refuses_overwrite(tmp_path):
    judges = tmp_path / "judges.json"
    MODULE.write_json(judges, judge_config())
    args = argparse.Namespace(judges=judges, samples=MODULE.ROOT / "docs/experiments/rag-experiment-4.csv",
                              references=MODULE.ROOT / "docs/experiments/rag-experiment-4-evaluation-sheet.csv",
                              output=tmp_path / "freeze", seed=114, group_size=10, max_attempts=2, timeout=240)
    MODULE.prepare(args)
    frozen = MODULE.load_frozen(args.output / "frozen-input.json")
    all_packets = [json.loads(p.read_text()) for p in sorted(args.output.glob("gpt-group-*.json"))]
    assert len(all_packets) == 4
    assert all(len(p["samples"]) == 10 for p in all_packets)
    assert [s["sample_id"] for p in all_packets for s in p["samples"]] == frozen["sample_order"]
    assert all(set(s) == {"sample_id", "input_sha256", "input"} for p in all_packets for s in p["samples"])
    with pytest.raises(ValueError, match="already exists"):
        MODULE.prepare(args)
