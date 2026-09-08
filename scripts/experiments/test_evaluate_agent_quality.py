from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "experiments" / "evaluate_agent_quality.py"
SPEC = importlib.util.spec_from_file_location("evaluate_agent_quality", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_complete_grounded_answer_scores_full_credit() -> None:
    case = {
        "id": "case",
        "task_type": "experiment_summary",
        "criteria": [
            {
                "id": "fact",
                "required_all": ["58℃", "最清晰"],
                "anchor_any": ["58℃"],
                "allowed_citations": ["[N1]"],
            }
        ],
        "forbidden_claims": ["62℃ 最佳"],
    }

    report = MODULE.score_case(case, "58℃ 条带最清晰 [N1]")

    assert report["fact_consistency"] == 1
    assert report["citation_precision"] == 1
    assert report["citation_recall"] == 1
    assert report["boundary_passed"] is True
    assert "answer" not in report


def test_unknown_and_dangling_citations_reduce_precision() -> None:
    case = {
        "id": "case",
        "task_type": "experiment_summary",
        "criteria": [
            {
                "id": "fact",
                "required_all": ["58℃"],
                "anchor_any": ["58℃"],
                "allowed_citations": ["[N1]"],
            }
        ],
    }

    report = MODULE.score_case(case, "58℃ 最佳 [N1]\n\n其他内容 [N999]")

    assert report["citation_precision"] == 0.5
    assert report["citation_recall"] == 1


def test_fact_without_colocated_citation_has_zero_recall() -> None:
    case = {
        "id": "case",
        "task_type": "anomaly_detection",
        "criteria": [
            {
                "id": "fact",
                "required_all": ["31.7", "偏离"],
                "anchor_any": ["31.7"],
                "allowed_citations": ["[N4]"],
            }
        ],
    }

    report = MODULE.score_case(case, "31.7 明显偏离。\n\n来源列表：[N4]")

    assert report["fact_consistency"] == 1
    assert report["citation_recall"] == 0
    assert report["citation_precision"] == 0


def test_stage_boundary_accepts_direct_negative_control_citation() -> None:
    case = {
        "id": "stage",
        "task_type": "stage_report",
        "criteria": [
            {
                "id": "boundary",
                "required_all": ["独立重复", "阴性对照"],
                "anchor_any": ["锁定", "结论", "阴性对照"],
                "allowed_citations": ["[F201]", "[N103]"],
            }
        ],
    }

    report = MODULE.score_case(case, "阴性对照未见扩增 [N103]；方案边界需独立重复后锁定 [F201]")

    assert report["citation_precision"] == 1
    assert report["citation_recall"] == 1
    assert report["unsupported_citations"] == []


def test_frozen_gold_has_five_unique_task_types() -> None:
    gold = json.loads((ROOT / "tools/evaluation-lab/agent-quality/gold-v1.json").read_text(encoding="utf-8"))

    assert len(gold["cases"]) == 5
    assert {case["task_type"] for case in gold["cases"]} == {
        "experiment_summary",
        "weekly_report",
        "stage_report",
        "literature_review",
        "anomaly_detection",
    }
    assert len(MODULE.canonical_sha256(gold)) == 64
