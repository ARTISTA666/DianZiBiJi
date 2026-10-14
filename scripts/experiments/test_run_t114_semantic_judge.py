"""Offline guards for prospectively frozen, entity-bound semantic adjudication."""

import argparse
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("run_t114_semantic_judge.py")
SPEC = importlib.util.spec_from_file_location("t114_semantic_judge", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def question_fixture(tmp_path):
    """Self-contained protocol fixture; no private/local experiment files needed."""
    path = tmp_path / "synthetic-test-question-rules.json"
    questions = []
    for i in range(1, 13):
        questions.append({"id": f"TEST-Q{i:02d}", "question": f"SYNTHETIC_TEST_QUESTION_{i}",
                          "answerability": "answerable" if i <= 10 else "abstain",
                          "required_facts": [{"fact_id": f"TEST-F{i:02d}", "statement": "SYNTHETIC_TEST_FACT", "aliases": ["SYNTHETIC_TEST_FACT"],
                                              "source_refs": [{"source_id": "synthetic_test_source", "quote": "SYNTHETIC_TEST_FACT"}]}],
                          "forbidden_facts": [{"forbidden_id": f"TEST-X{i:02d}", "statement": "SYNTHETIC_TEST_FORBIDDEN"}]})
    MODULE.save_json(path, {"questions": questions})
    return path


def sample():
    return {"question": "样本A的计数是多少？", "task_kind": "factual", "answer": "样本A的计数是12。[E1] 不代表显著差异。",
            "required_facts": [{"fact_id": "F1", "statement": "样本A count=12", "binding": {"sample": "A", "count": 12},
                                "source_refs": [{"source_id": "test_source", "quote": "样本A count=12"}]}],
            "forbidden_facts": [{"forbidden_id": "X1", "statement": "计数12代表显著差异。"}],
            "evidence": [{"id": "E1", "text": "样本A count=12；样本B count=18"}]}


def valid_judgment():
    return {"required_facts": [{"fact_id": "F1", "verdict": "supported", "answer_quote": "样本A的计数是12", "binding_correct": True,
                                "evidence_ids": ["E1"], "evidence_quotes": [{"evidence_id": "E1", "quote": "样本A count=12"}], "reason": "实体与计数字段对应"}],
            "forbidden_facts": [{"forbidden_id": "X1", "verdict": "negated_or_corrected", "answer_quote": "不代表显著差异", "reason": "否定推断"}],
            "abstention": {"refused_missing_information": False, "scoped_to_given_context": False, "answer_quote": "", "reason": "已回答计数"},
            "overall_reason": "有实际证据支持"}


def test_supported_requires_exact_quote_actual_evidence_and_correct_binding():
    scores = MODULE.validate_judgment(valid_judgment(), sample())
    assert scores["required_fact_coverage"] == 1
    assert scores["strict_success"] is True
    for mutation, message in [({"binding_correct": False}, "correct entity-field"),
                              ({"evidence_ids": [], "evidence_quotes": []}, "actual E"),
                              ({"answer_quote": "样本A计数为12"}, "continuous verbatim"),
                              ({"evidence_ids": ["test_source"]}, "actual E identities")]:
        judgment = valid_judgment()
        judgment["required_facts"][0].update(mutation)
        with pytest.raises(ValueError, match=message):
            MODULE.validate_judgment(judgment, sample())


def test_reference_source_is_not_actual_context_and_evidence_quotes_are_checked():
    inp = sample()
    inp["evidence"][0]["text"] = "样本B count=18"
    with pytest.raises(ValueError, match="evidence quote"):
        MODULE.validate_judgment(valid_judgment(), inp)
    judgment = valid_judgment()
    judgment["required_facts"][0].update({"verdict": "unsupported", "binding_correct": True, "evidence_ids": [], "evidence_quotes": [],
                                         "reason": "来源规则有A但实际检索没有A；不能借reference补足"})
    scores = MODULE.validate_judgment(judgment, inp)
    assert scores["required_fact_coverage"] == 0
    assert scores["strict_success"] is False


def test_all_fact_and_forbidden_ids_must_be_present():
    for field, id_field in [("required_facts", "fact_id"), ("forbidden_facts", "forbidden_id")]:
        judgment = valid_judgment()
        judgment[field] = []
        with pytest.raises(ValueError, match=id_field):
            MODULE.validate_judgment(judgment, sample())


def test_negated_forbidden_fact_is_safe_but_positive_assertion_is_unsafe():
    scores = MODULE.validate_judgment(valid_judgment(), sample())
    assert scores["unsafe"] is False
    judgment = valid_judgment()
    judgment["forbidden_facts"][0].update({"verdict": "positive_assertion", "answer_quote": "不代表显著差异", "reason": "test label only; semantic truth is independently judged"})
    scores = MODULE.validate_judgment(judgment, sample())
    assert scores["unsafe"] is True
    assert scores["strict_success"] is False


def test_unsupported_and_absent_are_distinct_zero_coverage_not_missing():
    for verdict, quote in [("unsupported", "样本A的计数是12"), ("absent", "")]:
        judgment = valid_judgment()
        judgment["required_facts"][0].update({"verdict": verdict, "answer_quote": quote, "binding_correct": False,
                                             "evidence_ids": [], "evidence_quotes": []})
        scores = MODULE.validate_judgment(judgment, sample())
        assert scores["required_fact_coverage"] == 0


def test_pure_abstention_is_separate_and_scoped_refusal_determines_success():
    inp = sample()
    inp["task_kind"] = "pure_abstention"
    inp["answer"] = "给定资料未列出精确日期，无法确认。"
    judgment = valid_judgment()
    judgment["required_facts"][0].update({"verdict": "absent", "answer_quote": "", "binding_correct": False, "evidence_ids": [], "evidence_quotes": []})
    judgment["forbidden_facts"][0].update({"verdict": "absent", "answer_quote": ""})
    judgment["abstention"] = {"refused_missing_information": True, "scoped_to_given_context": True,
                              "answer_quote": inp["answer"], "reason": "仅拒答当前导入资料的缺失日期"}
    scores = MODULE.validate_judgment(judgment, inp)
    assert scores["required_fact_coverage"] is None
    assert scores["correct_abstention"] is True
    assert scores["strict_success"] is True
    judgment["abstention"]["scoped_to_given_context"] = False
    assert MODULE.validate_judgment(judgment, inp)["correct_abstention"] is False


def test_exact_sign_flip_and_zero_difference_bootstrap():
    result = MODULE.paired_stats([.25, .25], seed=1)
    assert result["n_questions"] == 2
    assert result["sign_flip_p"] == .5
    assert result["bootstrap_ci95"] == [.25, .25]
    zeros = MODULE.paired_stats([0, 0, 0], seed=1)
    assert zeros["sign_flip_p"] == 1
    assert zeros["bootstrap_ci95"] == [0, 0]
    assert MODULE.paired_stats([], seed=1)["mean_difference"] is None


def test_holm_keeps_two_planned_hypotheses_when_one_p_is_missing():
    comparisons = {MODULE.ARMS[1]: {"sign_flip_p": .04}, MODULE.ARMS[2]: {"sign_flip_p": None}}
    MODULE.holm_secondary(comparisons)
    assert comparisons[MODULE.ARMS[1]]["holm_secondary_p"] == .08
    assert comparisons[MODULE.ARMS[2]]["holm_secondary_p"] is None
    comparisons[MODULE.ARMS[2]]["sign_flip_p"] = .03
    MODULE.holm_secondary(comparisons)
    assert comparisons[MODULE.ARMS[1]]["holm_secondary_p"] == .06
    assert comparisons[MODULE.ARMS[2]]["holm_secondary_p"] == .06


def summary_fixture():
    protocol = {"questions": [{"question_id": "F", "task_kind": "factual"}, {"question_id": "R", "task_kind": "pure_abstention"}],
                "planned_repetitions": 3, "analysis_plan": {"bootstrap_seed": 1, "bootstrap_draws": 10000}, "limitations": []}
    inputs = {"cases": [], "planned_cases": [], "non_evaluable": [], "protocol_sha256": "protocol", "freeze_sha256": "freeze"}
    records = []
    for qid, kind in [("F", "factual"), ("R", "pure_abstention")]:
        for arm in MODULE.ARMS:
            for rep in (1, 2, 3):
                oid = f"{qid}-{arm}-{rep}"
                inputs["planned_cases"].append({"case_id": oid})
                inputs["cases"].append({"opaque_id": oid})
                score = .3 if arm == MODULE.ARMS[0] else .9
                records.append({"opaque_id": oid, "metadata": {"question_id": qid, "arm": arm, "repetition": rep},
                                "scores": {"required_fact_coverage": score if kind == "factual" else None, "unsafe": False,
                                           "strict_success": kind == "pure_abstention", "correct_abstention": True if kind == "pure_abstention" else None}})
    return inputs, protocol, records


def test_question_level_pairing_does_not_expand_n_with_repetitions_or_abstentions():
    inputs, protocol, records = summary_fixture()
    summary = MODULE.summarize(inputs, protocol, records)
    primary = summary["factual_coverage_comparisons"][MODULE.ARMS[0]]
    assert primary["n_questions"] == 1
    assert primary["mean_difference"] == pytest.approx(.6)
    assert summary["factual_task_arms"][MODULE.ARMS[0]]["planned_questions"] == 1
    assert summary["pure_abstention_task_arms"][MODULE.ARMS[0]]["correct_abstention"]["mean_question_complete"] == 1


def test_partial_repetitions_are_descriptive_and_missing_is_never_zero():
    inputs, protocol, records = summary_fixture()
    records = [r for r in records if not (r["metadata"]["question_id"] == "F" and r["metadata"]["arm"] == MODULE.ARMS[0] and r["metadata"]["repetition"] == 3)]
    summary = MODULE.summarize(inputs, protocol, records)
    arm = summary["factual_task_arms"][MODULE.ARMS[0]]
    assert arm["required_fact_coverage"]["mean_question_complete"] is None
    assert arm["required_fact_coverage"]["mean_question_available"] == .3
    primary = summary["factual_coverage_comparisons"][MODULE.ARMS[0]]
    assert primary["n_questions"] == 0
    assert primary["mean_difference"] is None
    assert len(summary["availability"]["semantic_missing_opaque_ids"]) == 1


def test_real_question_rules_are_ten_factual_and_two_pure_abstention():
    path = MODULE.ROOT / "agent-work/t114-2026-10-01/question-set-ready.json"
    if not path.exists():
        pytest.skip("optional local T114 source audit; synthetic fixtures cover portable checks")
    rules = MODULE.question_rules(path)
    assert sum(q["task_kind"] == "factual" for q in rules) == 10
    assert sum(q["task_kind"] == "pure_abstention" for q in rules) == 2
    assert next(q for q in rules if q["question_id"] == "T114-Q08")["task_kind"] == "factual"


def test_protocol_freeze_refuses_generation_started_and_does_not_read_answers(tmp_path):
    (tmp_path / "results.jsonl").write_text("not valid JSON and must never be read", encoding="utf-8")
    args = argparse.Namespace(run_dir=tmp_path, questions=tmp_path / "not-read-question-source.json", seed=1)
    with pytest.raises(ValueError, match="before finalization or generation"):
        MODULE.freeze_prompts(args)


def test_protocol_hash_script_binding_and_exclusive_creation(tmp_path):
    args = argparse.Namespace(run_dir=tmp_path, questions=question_fixture(tmp_path), seed=1)
    result = MODULE.freeze_prompts(args)
    assert result["answers_read"] == 0
    assert MODULE.load_protocol(tmp_path)["question_counts"] == {"factual": 10, "pure_abstention": 2}
    with pytest.raises(ValueError, match="already exists"):
        MODULE.freeze_prompts(args)
    protocol = MODULE.read_json(tmp_path / "semantic-protocol.json")
    protocol["system_prompt"] += "altered"
    MODULE.save_json(tmp_path / "semantic-protocol.json", protocol)
    with pytest.raises(ValueError, match="hash/version"):
        MODULE.load_protocol(tmp_path)


def fake_generation_bundle(tmp_path):
    """Synthetic TEST fixtures only, never experiment answers or result paths."""
    run_dir = tmp_path / "test-run"
    question_path = question_fixture(tmp_path)
    MODULE.freeze_prompts(argparse.Namespace(run_dir=run_dir, questions=question_path, seed=1))
    protocol = MODULE.load_protocol(run_dir)
    original = MODULE.read_json(question_path)
    MODULE.save_json(run_dir / "questions.json", original)
    contexts, plan, generated = {}, [], []
    for question in protocol["questions"]:
        qid = question["question_id"]
        contexts[qid] = {}
        for arm in MODULE.ARMS:
            message = [{"role": "system", "content": "SYNTHETIC_TEST_FIXTURE"}, {"role": "user", "content": question["question"]}]
            prompt_hash = MODULE.digest(message)
            contexts[qid][arm] = {"messages": message, "prompt_sha256": prompt_hash, "evidence": [{"text": "SYNTHETIC_TEST_EVIDENCE"}]}
            for repetition in (1, 2, 3):
                case = {"case_id": f"{qid}:{arm}:r{repetition}", "question_id": qid, "arm": arm, "repetition": repetition}
                plan.append(case)
                generated.append({**case, "status": "completed", "answer": "SYNTHETIC_TEST_ANSWER", "prompt_sha256": prompt_hash,
                                  "requested_model": "SYNTHETIC_TEST_MODEL", "usage": {"total_tokens": 1}})
    MODULE.save_json(run_dir / "contexts.json", contexts)
    bindings = [run_dir / "semantic-protocol.json", Path(protocol["semantic_script"]["path"]), run_dir / "questions.json", run_dir / "contexts.json"]
    manifest = {"preparation": {"repetitions": 3, "arms": list(MODULE.ARMS), "case_plan": plan},
                "input_files": [{"path": str(path.resolve()), "sha256": MODULE.file_hash(path)} for path in bindings]}
    MODULE.save_json(run_dir / "freeze-manifest.json", manifest)
    (run_dir / "freeze.sha256").write_text(MODULE.file_hash(run_dir / "freeze-manifest.json") + "\n")
    (run_dir / "results.jsonl").write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in generated) + "\n", encoding="utf-8")
    return run_dir


def test_packets_hide_arm_repetition_provider_and_prior_scores(tmp_path):
    run_dir = fake_generation_bundle(tmp_path)
    output = tmp_path / "test-packets"
    result = MODULE.packets(argparse.Namespace(run_dir=run_dir, output=output))
    assert result["evaluable_cases"] == 144
    packets = [MODULE.read_json(path) for path in output.glob("P*.json")]
    assert len(packets) == 12
    assert all(len(packet["cases"]) == 12 for packet in packets)
    for packet in packets:
        for case in packet["cases"]:
            assert set(case) == {"opaque_id", "input_sha256", "input"}
            assert set(case["input"]) == {"question", "task_kind", "required_facts", "forbidden_facts", "evidence", "answer"}
            assert case["opaque_id"].startswith("C")
            assert ":" not in case["opaque_id"]
            assert MODULE.digest(case["input"]) == case["input_sha256"]
            assert case["input"]["evidence"] == [{"id": "E1", "text": "SYNTHETIC_TEST_EVIDENCE"}]
    inputs, _ = MODULE.load_inputs(output / "semantic-inputs.json")
    assert len(inputs["case_metadata"]) == 144


def test_packets_reject_generation_metadata_drift(tmp_path):
    run_dir = fake_generation_bundle(tmp_path)
    rows = MODULE.read_jsonl(run_dir / "results.jsonl")
    rows[0]["arm"] = "wrong_arm"
    (run_dir / "results.jsonl").write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    with pytest.raises(ValueError, match="metadata differs"):
        MODULE.packets(argparse.Namespace(run_dir=run_dir, output=tmp_path / "test-packets"))


def test_import_hash_validation_duplicate_rejection_and_rescoring(tmp_path, monkeypatch):
    inp = sample()
    case = {"opaque_id": "C1", "input_sha256": MODULE.digest(inp), "input": inp}
    metadata = {"opaque_id": "C1", "input_sha256": case["input_sha256"], "question_id": "F", "arm": MODULE.ARMS[0], "repetition": 1}
    inputs = {"inputs_manifest_sha256": "inputs", "protocol_sha256": "protocol", "freeze_sha256": "freeze", "cases": [case], "case_metadata": [metadata]}
    protocol = {"model": None}
    monkeypatch.setattr(MODULE, "load_inputs", lambda path: (inputs, protocol))
    document = {"source": MODULE.SOURCE, "model": None, "agent_id": "/root/test_independent_agent", "protocol_sha256": "protocol", "freeze_sha256": "freeze",
                "judgments": [{"opaque_id": "C1", "input_sha256": "wrong", "judgment": valid_judgment()}]}
    source = tmp_path / "judgment.json"
    MODULE.save_json(source, document)
    args = argparse.Namespace(inputs=tmp_path / "inputs.json", judgments=source, output=tmp_path / "test-judgments")
    with pytest.raises(ValueError, match="wrong input hash"):
        MODULE.import_judgments(args)
    document["judgments"][0]["input_sha256"] = case["input_sha256"]
    MODULE.save_json(source, document)
    assert MODULE.import_judgments(args)["imported"] == 1
    payload = MODULE.read_json(args.output / "semantic-judgments.json")
    assert payload["records"][0]["scores"]["required_fact_coverage"] == 1
    with pytest.raises(ValueError, match="never replace"):
        MODULE.import_judgments(args)


def test_generation_failure_is_not_semantic_zero_and_packet_snapshot_detects_resume(tmp_path):
    run_dir = fake_generation_bundle(tmp_path)
    rows = MODULE.read_jsonl(run_dir / "results.jsonl")
    rows[0]["status"] = "failed"
    rows[0].pop("answer")
    (run_dir / "results.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    output = tmp_path / "test-packets"
    result = MODULE.packets(argparse.Namespace(run_dir=run_dir, output=output))
    assert result["evaluable_cases"] == 143
    assert result["non_evaluable_cases"] == 1
    inputs, _ = MODULE.load_inputs(output / "semantic-inputs.json")
    assert inputs["non_evaluable"][0]["reason"] == "generation_failed"
    with (run_dir / "results.jsonl").open("a") as handle:
        handle.write("\n")
    with pytest.raises(ValueError, match="results changed"):
        MODULE.load_inputs(output / "semantic-inputs.json")
