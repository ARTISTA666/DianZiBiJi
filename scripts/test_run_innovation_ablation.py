#!/usr/bin/env python3
"""run_innovation_ablation.py 纯函数单测(离线,不依赖 docker)。"""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "ablation", Path(__file__).resolve().parent / "run_innovation_ablation.py"
)
ab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ab)


def test_rule_based_suggest_orders_by_priority_and_hits_uncovered():
    nodes = [
        {"id": 2, "entity_type": "instrument", "label": "电镜", "priority": 50, "source_kind": "plan_document"},
        {"id": 1, "entity_type": "reagent", "label": "TRIzol", "priority": 10, "source_kind": "meeting_note"},
    ]
    covered = set()
    sugg, uncovered = ab.rule_based_suggest(nodes, covered)
    assert uncovered == 2
    assert sugg[0]["related_labels"] == ["TRIzol"]  # 优先级 10 先于 50
    assert "试剂" in sugg[0]["rationale"]


def test_rule_based_suggest_skips_covered():
    nodes = [{"id": 1, "entity_type": "reagent", "label": "TRIzol", "priority": 10, "source_kind": "plan_document"}]
    sugg, uncovered = ab.rule_based_suggest(nodes, {"TRIzol"})
    assert uncovered == 0 and sugg == []


def test_eval_suggestions_counts_fabricated():
    nodes = [{"id": 1, "entity_type": "reagent", "label": "TRIzol", "priority": 10, "source_kind": "plan_document"}]
    sugg = [{"title": "x", "rationale": "y", "related_labels": ["TRIzol", "不存在的试剂"]}]
    m = ab.eval_suggestions(sugg, nodes, set())
    assert m["actionable_refs"] == 1 and m["hit_uncovered"] == 1 and m["fabricated_refs"] == 1


def test_graph_relation_score_matches_rust_semantics():
    rel = {"relation_type": "uses_reagent", "confidence": 0.7, "source_type": "note_extraction",
           "source_label": "笔记A", "target_label": "TRIzol", "source_type2": "note", "source_id": 1,
           "target_type": "reagent", "target_id": 2}
    # hint 命中 3.0 + target 词元全等 3.0 + note_extraction 0.3 = 6.3
    # (Python 复刻版 source_type 合并了 Rust 的 source_type 与实体类型两列;
    #  source_type="note_extraction" 时 Rust 的 +0.2 note 分对应实体类型列,此处不触发)
    assert ab.graph_relation_score(rel, {"trizol"}, {"uses_reagent"}) == 6.3


def test_profile_gain_discriminates_by_seen_types():
    rel = {"source_label": "n", "target_label": "m", "source_type": "note", "target_type": "instrument"}
    profiles = {1: {"quality_score": 1.0, "completion_speed": 1.0}}
    unmet = {"instrument"}
    novice = ab.profile_gain(rel, profiles, 1, set(), set(), unmet, {"reagent"})
    expert = ab.profile_gain(rel, profiles, 1, set(), set(), unmet, {"reagent", "instrument"})
    assert novice > expert  # 新手(未见过 instrument)画像增益更高


def test_kendall_tau_identical_and_reversed():
    assert ab.kendall_tau([1, 2, 3], [1, 2, 3]) == 1.0
    assert ab.kendall_tau([1, 2, 3], [3, 2, 1]) == -1.0
    assert ab.kendall_tau([1], [1]) is None
