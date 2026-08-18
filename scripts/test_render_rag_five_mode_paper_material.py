from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render_rag_five_mode_paper_material.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("render_rag_five_mode_paper_material", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_material_renders_audit_status_and_recomputed_values() -> None:
    audit_path = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"
    validation_path = ROOT / "data/real/experiment-5/internal-five-mode-validation.json"
    material = MODULE.render(
        json.loads(audit_path.read_text(encoding="utf-8")),
        json.loads(validation_path.read_text(encoding="utf-8")),
        audit_path,
        validation_path,
    )

    assert "内部开发证据，不是确认性结果" in material
    assert "90.62%" in material
    assert "非法范围标记" in material
    assert "paper_ready=false" in material
    assert "重复生成的配对 p 值" in material
    assert "Bootstrap 95% CI" in material
    assert "重复式稳定性" not in material
    assert "重复稳定性" in material
    assert "11/11" in material
    assert "CAUTION" in material
    assert "运行版本与参数快照" in material
    assert "实验设计与运行配置绑定门禁" in material
    assert "| 题集哈希与冻结题集一致 | PASS |" in material
    assert "| 随机种子与运行配置一致 | PASS |" in material
    assert "| 检索 top-k 与运行配置一致 | PASS |" in material
    assert "## 数据—问题集绑定门禁" in material
    assert "| 题目编号在冻结题集范围内 | PASS |" in material
    assert "| 逐案例 retrieval snapshot 绑定 | FAIL |" in material
    assert "门禁失败摘要" in material
    assert "## 论文门禁推导审计" in material
    assert "| `paper_gate_consistent` | `required` | PASS |" in material
    assert "top-level paper gate fields match severity-derived checks" in material
    assert "## 论文门禁固定集合覆盖" in material
    assert "| 实验设计与运行配置绑定 | 18 | 18 | — | PASS |" in material
    assert "| 证据链门禁 | 5 | 5 | — | PASS |" in material
    assert "| 数据—问题集绑定门禁 | 7 | 7 | — | PASS |" in material
    assert "| 论文门禁派生检查 | 1 | 1 | — | PASS |" in material
    assert "## 论文主张边界审计" in material
    assert "| 证据等级 | 内部开发证据 | 仅允许描述性/方法学诊断表述 | PASS |" in material
    assert "| 确认性效果结论 | paper_ready=false | 禁止升级为确认性结果 | FAIL |" in material
    assert "本批次必须同步披露的未完成归档项" in material
    assert "`app_revision_is_bound`：8. 版本归档" in material
    assert "`confirmatory_evidence_package_present`：4. 逐案例证据" in material
    assert "## 论文阻塞披露闭环" in material
    assert "| 失败摘要与映射 FAIL 名称一致 | 5 | 5 | PASS |" in material
    assert "| paper_blockers 与主张边界披露一致 | 5 个 paper_blocker | 5 个 paper_blocker | PASS |" in material
    assert "## 失败检查身份闭环" in material
    assert "| 失败检查总数 | 153 |" in material
    assert "| 失败检查总数 | 153 | 153 | — | PASS |" in material
    assert "| paper_blockers 与 paper_blocker 失败名一致 | 5 | 5 | — | PASS |" in material
    assert "Retrieval 缺口摘要结构一致" in material
    assert "| Retrieval 缺口摘要结构一致 | PASS |" in material
    assert "| 论文门禁逻辑一致 | PASS |" in material
    assert "input_freeze_manifest_verifies" in material
    assert "versioned revision" in material
    assert "rag-evidence-package-v1" in material
    assert "app_revision=unversioned" in material
    assert "random_seed" not in material
    assert "20260713" in material
    assert "输入材料指纹" in material
    assert "数据—问题集绑定门禁" in material
    assert "题目编号在冻结题集范围内" in material
    assert "CSV 题干与冻结题集逐字一致" in material
    assert "逐案例 provider/model/prompt_version 绑定" in material
    assert "逐案例 retrieval snapshot 绑定" in material
    assert "Retrieval snapshot 缺口（按方法、按字段、按行数）" in material
    assert '"corpus_snapshot_hash":36' in material
    assert '"graph_schema_version":36' in material
    assert "不适用" in material
    assert "案例键域完整" in material
    assert "题目索引" in material
    assert "| 6 | 4 | H04 |" in material
    assert material.count("`" + "sha256" + "`") == 0
    assert material.count("| `") >= 20
    assert str(ROOT) not in material
    assert "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json" in material
    assert "data/real/experiment-5/internal-five-mode-validation.json" in material
    assert len(MODULE.source_fingerprints(
        json.loads(audit_path.read_text(encoding="utf-8")),
        audit_path,
        validation_path,
        ROOT,
    )) == 11


def test_audit_and_renderer_share_retrieval_contract() -> None:
    audit_script = ROOT / "scripts" / "audit_rag_five_mode_bundle.py"
    audit_spec = importlib.util.spec_from_file_location("audit_contract_probe", audit_script)
    assert audit_spec and audit_spec.loader
    audit_module = importlib.util.module_from_spec(audit_spec)
    sys.modules[audit_spec.name] = audit_module
    audit_spec.loader.exec_module(audit_module)

    assert MODULE.RETRIEVAL_GAP_MODES == audit_module.MODES
    assert MODULE.RETRIEVAL_REQUIRED_FIELDS == audit_module.RETRIEVAL_SNAPSHOT_FIELDS


def test_material_renders_reported_citation_summary_differences() -> None:
    audit_path = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"
    validation_path = ROOT / "data/real/experiment-5/internal-five-mode-validation.json"
    material = MODULE.render(
        json.loads(audit_path.read_text(encoding="utf-8")),
        json.loads(validation_path.read_text(encoding="utf-8")),
        audit_path,
        validation_path,
    )

    assert "引用审计报告—重算差异" in material
    assert "`all_citation_indices_in_range`" in material
    assert "`false`" in material
    assert "`true`" in material
    assert "`bm25_rag / invalid_marker_rows`" in material
    assert "`4`" in material
    assert "`0`" in material
    assert "报告值与原始 CSV 重算值不一致" in material


def test_material_renders_method_level_citation_rates() -> None:
    audit_path = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"
    validation_path = ROOT / "data/real/experiment-5/internal-five-mode-validation.json"
    material = MODULE.render(
        json.loads(audit_path.read_text(encoding="utf-8")),
        json.loads(validation_path.read_text(encoding="utf-8")),
        audit_path,
        validation_path,
    )

    assert "有来源标记 n/%" in material
    assert "有任一证据标记 n/%" in material
    assert "非法标记行 n/%" in material
    assert "32/36 (88.89%)" in material
    assert "4/36 (11.11%)" in material


def test_material_renders_retrieval_snapshot_gap_rates() -> None:
    audit_path = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"
    validation_path = ROOT / "data/real/experiment-5/internal-five-mode-validation.json"
    material = MODULE.render(
        json.loads(audit_path.read_text(encoding="utf-8")),
        json.loads(validation_path.read_text(encoding="utf-8")),
        audit_path,
        validation_path,
    )

    assert "完整快照行 n/%" in material
    assert "有任一缺口行 n/%" in material
    assert "0/36 (0.00%)" in material
    assert "36/36 (100.00%)" in material
    retrieval_table = material.split("## Retrieval snapshot 缺口", 1)[1].split(
        "严格语法下", 1
    )[0]
    assert all(len(line.split("|")) == 9 for line in retrieval_table.splitlines() if line.startswith("|"))


def test_material_renders_retrieval_field_gap_rates() -> None:
    audit_path = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"
    validation_path = ROOT / "data/real/experiment-5/internal-five-mode-validation.json"
    material = MODULE.render(
        json.loads(audit_path.read_text(encoding="utf-8")),
        json.loads(validation_path.read_text(encoding="utf-8")),
        audit_path,
        validation_path,
    )

    assert "缺失字段 n/%" in material
    assert "非空漂移 n/%" in material
    assert "corpus_snapshot_hash=36/36 (100.00%)" in material
    assert "graph_schema_version=36/36 (100.00%)" in material
    assert "非空漂移计数" not in material


def test_retrieval_field_gap_summary_rejects_counts_above_any_gap_rows() -> None:
    gap = {
        "row_count": 3,
        "rows_with_any_gap": 1,
        "required_fields": [
            "corpus_snapshot_hash",
            "retrieval_top_k",
            "collection_retrieval_top_k",
            "chunk_size",
            "chunk_overlap",
        ],
        "missing_by_field": {
            "corpus_snapshot_hash": 2,
            "retrieval_top_k": 0,
            "collection_retrieval_top_k": 0,
            "chunk_size": 0,
            "chunk_overlap": 0,
        },
        "mismatch_by_field": {
            "corpus_snapshot_hash": 0,
            "retrieval_top_k": 0,
            "collection_retrieval_top_k": 0,
            "chunk_size": 0,
            "chunk_overlap": 0,
        },
    }

    with pytest.raises(ValueError, match="exceeds any-gap rows"):
        MODULE.retrieval_field_gap_summary(gap, "bm25_rag")


def test_retrieval_snapshot_gap_table_rejects_non_partitioned_rows() -> None:
    gap = {
        "row_count": 3,
        "rows_with_complete_snapshot": 2,
        "rows_with_any_gap": 2,
        "required_fields": [
            "corpus_snapshot_hash",
            "retrieval_top_k",
            "collection_retrieval_top_k",
            "chunk_size",
            "chunk_overlap",
        ],
        "missing_by_field": {"corpus_snapshot_hash": 2},
        "mismatch_by_field": {"corpus_snapshot_hash": 0},
    }

    with pytest.raises(ValueError, match="must partition row count"):
        MODULE.retrieval_field_gap_summary(gap, "bm25_rag")


def test_retrieval_field_gap_summary_rejects_unbound_field_keys() -> None:
    gap = {
        "row_count": 2,
        "rows_with_complete_snapshot": 0,
        "rows_with_any_gap": 2,
        "required_fields": [
            "corpus_snapshot_hash",
            "retrieval_top_k",
            "collection_retrieval_top_k",
            "chunk_size",
            "chunk_overlap",
        ],
        "missing_by_field": {"corpus_snapshot_hash": 2, "unexpected": 0},
        "mismatch_by_field": {"corpus_snapshot_hash": 0},
    }

    with pytest.raises(ValueError, match="canonical required fields"):
        MODULE.retrieval_field_gap_summary(gap, "bm25_rag")


def test_citation_count_rate_rejects_invalid_denominator_or_count() -> None:
    assert MODULE.citation_count_rate(4, 36) == "4/36 (11.11%)"

    for count, denominator in ((True, 36), (-1, 36), (37, 36), (1, 0)):
        with pytest.raises(ValueError, match="bounded count"):
            MODULE.citation_count_rate(count, denominator)


def test_citation_summary_mismatch_rows_fail_closed_on_malformed_binding() -> None:
    base = {
        "reported_audit_mismatch": True,
        "reported_summary_mismatches": [
            {"field": "all_citation_indices_in_range", "recomputed": False, "reported": True}
        ],
    }

    assert MODULE.citation_summary_mismatch_rows(base) == [
        {
            "label": "all_citation_indices_in_range",
            "recomputed": "false",
            "reported": "true",
        }
    ]

    malformed = dict(base)
    malformed["reported_audit_mismatch"] = False
    with pytest.raises(ValueError, match="does not match summary mismatches"):
        MODULE.citation_summary_mismatch_rows(malformed)

    duplicate = dict(base)
    duplicate["reported_summary_mismatches"] = [
        {"field": "same", "recomputed": 1, "reported": 0},
        {"field": "same", "recomputed": 2, "reported": 0},
    ]
    with pytest.raises(ValueError, match="duplicate citation summary mismatch"):
        MODULE.citation_summary_mismatch_rows(duplicate)


def test_failure_gate_rows_are_sorted_and_preserve_typed_values() -> None:
    audit = {
        "checks": [
            {
                "name": "z_blocker",
                "passed": False,
                "severity": "paper_blocker",
                "actual": {"count": 0, "ready": False},
                "expected": ["signed", "review"],
            },
            {
                "name": "a_required",
                "passed": False,
                "severity": "required",
                "actual": None,
                "expected": True,
            },
            {
                "name": "passing_check",
                "passed": True,
                "severity": "informational",
                "actual": "ignored",
                "expected": "ignored",
            },
        ]
    }

    assert MODULE.failure_gate_rows(audit) == [
        {
            "name": "a_required",
            "severity": "required",
            "actual": "null",
            "actual_summary": "null",
            "expected": "true",
            "expected_summary": "true",
        },
        {
            "name": "z_blocker",
            "severity": "paper_blocker",
            "actual": '{"count":0,"ready":false}',
            "actual_summary": "count=0; ready=false",
            "expected": '["signed","review"]',
            "expected_summary": '["signed", "review"]',
        },
    ]


def test_failure_gate_summary_is_bounded_for_nested_audit_values() -> None:
    value = {
        "recomputed": {
            "answers_with_source_marker": 90,
            "by_mode": {"bm25_rag": {"completed": 36}},
            "invalid_marker_rows": [{"row": 6}],
        },
        "reported": {"all_citation_indices_in_range": True},
    }

    summary = MODULE.compact_value(value)

    assert summary == (
        "recomputed={answers_with_source_marker=90; by_mode=object[1 keys]; "
        "invalid_marker_rows=array[1]}; reported={all_citation_indices_in_range=true}"
    )
    assert len(summary) < 180


def test_required_audit_check_status_rejects_missing_or_non_boolean() -> None:
    with pytest.raises(ValueError, match="required audit check missing or invalid"):
        MODULE.required_audit_check_status({}, "retrieval_gap_summary_valid")

    with pytest.raises(ValueError, match="required audit check missing or invalid"):
        MODULE.required_audit_check_status(
            {"retrieval_gap_summary_valid": "true"},
            "retrieval_gap_summary_valid",
        )


def test_run_binding_gate_requires_every_registered_check() -> None:
    audit_path = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"
    validation_path = ROOT / "data/real/experiment-5/internal-five-mode-validation.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["checks"] = [
        item for item in audit["checks"] if item["name"] != "random_seed_matches"
    ]

    with pytest.raises(ValueError, match="random_seed_matches"):
        MODULE.render(audit, json.loads(validation_path.read_text(encoding="utf-8")), audit_path, validation_path)


def test_data_binding_gate_requires_every_registered_check() -> None:
    audit_path = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"
    validation_path = ROOT / "data/real/experiment-5/internal-five-mode-validation.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["checks"] = [
        item for item in audit["checks"] if item["name"] != "csv_methods_bound"
    ]

    with pytest.raises(ValueError, match="csv_methods_bound"):
        MODULE.render(audit, json.loads(validation_path.read_text(encoding="utf-8")), audit_path, validation_path)


def test_paper_gate_requires_boolean_ready_and_structured_blockers() -> None:
    audit_path = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"
    validation_path = ROOT / "data/real/experiment-5/internal-five-mode-validation.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))

    non_boolean = json.loads(audit_path.read_text(encoding="utf-8"))
    non_boolean["paper_ready"] = "false"
    with pytest.raises(ValueError, match="paper_ready must be boolean"):
        MODULE.render(non_boolean, validation, audit_path, validation_path)

    missing_blockers = json.loads(audit_path.read_text(encoding="utf-8"))
    missing_blockers.pop("paper_blockers")
    with pytest.raises(ValueError, match="paper_blockers must be an array"):
        MODULE.render(missing_blockers, validation, audit_path, validation_path)


def test_paper_gate_rejects_inconsistent_derived_fields() -> None:
    audit_path = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"
    validation_path = ROOT / "data/real/experiment-5/internal-five-mode-validation.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["paper_blockers"] = []

    with pytest.raises(ValueError, match="paper gate consistency mismatch"):
        MODULE.render(
            audit,
            json.loads(validation_path.read_text(encoding="utf-8")),
            audit_path,
            validation_path,
        )


def test_paper_blockers_map_one_to_one_to_archive_requirements() -> None:
    audit_path = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    rows = MODULE.paper_blocker_archive_rows(audit)

    assert [row["name"] for row in rows] == [
        "report_scope_is_internal_only",
        "app_revision_is_bound",
        "external_freeze_inputs_present",
        "multi_project_question_set_ready",
        "independent_human_review_present",
        "confirmatory_evidence_package_present",
    ]
    assert [row["archive_item"] for row in rows] == [
        "范围声明（不属于八项最低清单）",
        "8. 版本归档",
        "1. 数据绑定",
        "2. 问题集绑定",
        "6. 人工评价",
        "4. 逐案例证据",
    ]
    assert [row["status"] for row in rows] == ["PASS", "FAIL", "FAIL", "FAIL", "FAIL", "FAIL"]


def test_paper_blocker_archive_mapping_rejects_unregistered_blocker() -> None:
    audit_path = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["checks"].append(
        {
            "name": "unregistered_paper_blocker",
            "passed": False,
            "severity": "paper_blocker",
            "actual": None,
            "expected": "registered mapping",
        }
    )

    with pytest.raises(ValueError, match="paper blocker archive mapping mismatch"):
        MODULE.paper_blocker_archive_rows(audit)


def test_paper_blocker_archive_mapping_rejects_tampered_audit_mapping() -> None:
    audit_path = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["paper_blocker_archive_mapping"][1]["archive_item"] = "1. 数据绑定"

    with pytest.raises(ValueError, match="paper blocker archive mapping missing or mismatched"):
        MODULE.paper_blocker_archive_rows(audit)


def test_paper_claim_boundary_rejects_confirmatory_ready_state() -> None:
    audit_path = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    archive_rows = MODULE.paper_blocker_archive_rows(audit)
    audit["paper_ready"] = True

    with pytest.raises(ValueError, match="paper claim boundary requires paper_ready=false"):
        MODULE.paper_claim_boundary_audit(audit, "PASS", archive_rows)


def test_paper_disclosure_consistency_rejects_tampered_claim_disclosure() -> None:
    audit_path = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    failed_gate_rows = MODULE.failure_gate_rows(audit)
    archive_rows = MODULE.paper_blocker_archive_rows(audit)
    claim_rows = MODULE.paper_claim_boundary_audit(audit, "FAIL", archive_rows)
    claim_rows[2]["observed"] = "4 个 paper_blocker"

    with pytest.raises(ValueError, match="paper disclosure boundary mismatch"):
        MODULE.paper_disclosure_consistency_audit(
            audit, failed_gate_rows, archive_rows, claim_rows
        )


def test_paper_material_rejects_missing_registered_check_from_coverage() -> None:
    audit_path = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"
    validation_path = ROOT / "data/real/experiment-5/internal-five-mode-validation.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["checks"] = [item for item in audit["checks"] if item["name"] != "paper_gate_consistent"]

    with pytest.raises(ValueError, match="paper material check coverage missing"):
        MODULE.render(
            audit,
            json.loads(validation_path.read_text(encoding="utf-8")),
            audit_path,
            validation_path,
        )


def test_paper_material_rejects_missing_failure_identity_summary() -> None:
    audit_path = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"
    validation_path = ROOT / "data/real/experiment-5/internal-five-mode-validation.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit.pop("failure_summary")

    with pytest.raises(ValueError, match="failure identity audit requires failure_summary"):
        MODULE.render(
            audit,
            json.loads(validation_path.read_text(encoding="utf-8")),
            audit_path,
            validation_path,
        )


def test_failure_gate_rows_reject_malformed_or_duplicate_checks() -> None:
    with pytest.raises(ValueError, match="audit checks must be an array"):
        MODULE.failure_gate_rows({})

    with pytest.raises(ValueError, match="audit checks must be an array"):
        MODULE.failure_gate_rows({"checks": {}})

    with pytest.raises(ValueError, match="audit checks must not be empty"):
        MODULE.failure_gate_rows({"checks": []})

    with pytest.raises(ValueError, match="failed audit checks must be objects"):
        MODULE.failure_gate_rows({"checks": ["not-an-object"]})

    with pytest.raises(ValueError, match="duplicate audit check name"):
        MODULE.failure_gate_rows(
            {
                "checks": [
                    {"name": "same", "passed": False, "severity": "required"},
                    {"name": "same", "passed": False, "severity": "paper_blocker"},
                ]
            }
        )

    with pytest.raises(ValueError, match="audit check passed must be boolean"):
        MODULE.failure_gate_rows(
            {"checks": [{"name": "typed_passed", "passed": "false", "severity": "required"}]}
        )

    with pytest.raises(ValueError, match="audit check must have a non-empty severity"):
        MODULE.failure_gate_rows({"checks": [{"name": "missing_severity", "passed": False}]})


def test_citation_failure_rows_are_sorted_and_bound_to_unique_identity() -> None:
    citation = {
        "invalid_marker_rows": [
            {
                "row": 50,
                "question_index": 4,
                "question_id": "H04",
                "mode": "bm25_rag",
                "repetition_index": 3,
                "query_log_id": 172,
                "markers": ["[S1-S12]"],
                "source_count": 12,
                "graph_hit_count": 0,
            },
            {
                "row": 6,
                "question_index": 4,
                "question_id": "H04",
                "mode": "bm25_rag",
                "repetition_index": 1,
                "query_log_id": 128,
                "markers": ["[S1-S12]"],
                "source_count": 12,
                "graph_hit_count": 0,
            },
        ]
    }

    rows = MODULE.citation_failure_rows(citation)

    assert [row["row"] for row in rows] == [6, 50]
    assert rows[0]["question_index"] == 4
    assert rows[0]["query_log_id"] == 128


def test_citation_failure_rows_reject_missing_identity_and_duplicates() -> None:
    with pytest.raises(ValueError, match="citation invalid_marker_rows must be an array"):
        MODULE.citation_failure_rows({})

    with pytest.raises(ValueError, match="citation failure row must have a positive row"):
        MODULE.citation_failure_rows({"invalid_marker_rows": [{"row": 0}]})

    base = {
        "row": 6,
        "question_index": 4,
        "question_id": "H04",
        "mode": "bm25_rag",
        "repetition_index": 1,
        "query_log_id": 128,
        "markers": ["[S1-S12]"],
        "source_count": 12,
        "graph_hit_count": 0,
    }
    duplicate = dict(base)
    duplicate["row"] = 7
    with pytest.raises(ValueError, match="duplicate citation failure query_log_id"):
        MODULE.citation_failure_rows({"invalid_marker_rows": [base, duplicate]})


def test_citation_failures_are_recomputed_from_raw_csv() -> None:
    audit_path = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"
    csv_path = ROOT / "data/real/experiment-5/internal-five-mode-experiment.csv"
    questions_path = ROOT / "data/real/GSE111619/gse111619_kg_holdout_questions.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    assert MODULE.recompute_citation_failure_rows(csv_path, questions_path) == MODULE.citation_failure_rows(
        audit["citation_audit"]
    )


def test_material_rejects_stale_citation_failure_rows() -> None:
    audit_path = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"
    validation_path = ROOT / "data/real/experiment-5/internal-five-mode-validation.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["citation_audit"]["invalid_marker_rows"][0]["query_log_id"] = 999999

    with pytest.raises(ValueError, match="raw CSV citation failure recomputation"):
        MODULE.render(audit, json.loads(validation_path.read_text(encoding="utf-8")), audit_path, validation_path)


def test_recompute_citation_failures_rejects_count_drift(tmp_path: Path) -> None:
    csv_path = tmp_path / "experiment.csv"
    csv_path.write_text(
        "question_index,repetition_index,query_log_id,mode,question,answer,source_count,graph_hit_count,sources_json,graph_context_json\n"
        '1,1,1,bm25_rag,"冻结题干","[S1-S2]",0,0,"[{\\"id\\": 1}]",[]\n',
        encoding="utf-8",
    )
    questions_path = tmp_path / "questions.json"
    questions_path.write_text('[{"id":"H01","question":"冻结题干"}]', encoding="utf-8")

    with pytest.raises(ValueError, match="citation failure row source_count does not match CSV evidence array"):
        MODULE.recompute_citation_failure_rows(csv_path, questions_path)


def test_recompute_citation_failures_rejects_question_text_drift(tmp_path: Path) -> None:
    csv_path = tmp_path / "experiment.csv"
    csv_path.write_text(
        "question_index,repetition_index,query_log_id,mode,question,answer,source_count,graph_hit_count,sources_json,graph_context_json\n"
        '1,1,1,bm25_rag,"篡改后的题干","[S1-S2]",0,0,"[]","[]"\n',
        encoding="utf-8",
    )
    questions_path = tmp_path / "questions.json"
    questions_path.write_text(
        json.dumps([{"id": "H01", "question": "冻结题干"}], ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="citation failure row question text does not match question set",
    ):
        MODULE.recompute_citation_failure_rows(csv_path, questions_path)


def test_checked_in_material_matches_current_renderer_output() -> None:
    audit_path = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"
    validation_path = ROOT / "data/real/experiment-5/internal-five-mode-validation.json"
    material_path = ROOT / "docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md"

    rendered = MODULE.render(
        json.loads(audit_path.read_text(encoding="utf-8")),
        json.loads(validation_path.read_text(encoding="utf-8")),
        audit_path,
        validation_path,
    )

    assert rendered == material_path.read_text(encoding="utf-8")


def test_material_rejects_incomplete_audit() -> None:
    audit = {"schema_version": "rag-internal-five-mode-bundle-audit-v1", "recomputed_mode_summary": []}
    try:
        MODULE.render(audit, {}, Path("audit.json"), Path("validation.json"))
    except (KeyError, ValueError):
        pass
    else:
        raise AssertionError("incomplete audit must be rejected")


def test_material_rejects_incomplete_validation() -> None:
    audit_path = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"
    validation_path = ROOT / "data/real/experiment-5/internal-five-mode-validation.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    validation["warnings"] = []
    try:
        MODULE.render(
            json.loads(audit_path.read_text(encoding="utf-8")),
            validation,
            audit_path,
            validation_path,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("validation without warnings must be rejected")


def test_material_rejects_missing_fingerprint_input() -> None:
    audit_path = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"
    validation_path = ROOT / "data/real/experiment-5/internal-five-mode-validation.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["inputs"]["report"] = "missing-report.json"
    try:
        MODULE.render(
            audit,
            json.loads(validation_path.read_text(encoding="utf-8")),
            audit_path,
            validation_path,
        )
    except ValueError as error:
        assert "required evidence input is missing" in str(error)
    else:
        raise AssertionError("missing evidence input must be rejected")


def test_material_rejects_evidence_input_outside_repository_root(tmp_path: Path) -> None:
    audit_path = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"
    validation_path = ROOT / "data/real/experiment-5/internal-five-mode-validation.json"
    outside_report = tmp_path / "outside-report.json"
    outside_report.write_text("{}", encoding="utf-8")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["inputs"]["report"] = str(outside_report)

    with pytest.raises(ValueError, match="inside repository root"):
        MODULE.render(
            audit,
            json.loads(validation_path.read_text(encoding="utf-8")),
            audit_path,
            validation_path,
        )


def test_material_rejects_missing_protocol_field() -> None:
    audit_path = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"
    validation_path = ROOT / "data/real/experiment-5/internal-five-mode-validation.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    report_path = ROOT / "data/real/experiment-5/internal-five-mode-experiment-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["experiment_run"]["config_snapshot_json"]["corpus_snapshot_hash"] = ""
    temporary_report = validation_path.parent / "_temporary_missing_protocol_report.json"
    temporary_report.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    audit["inputs"]["report"] = str(temporary_report.relative_to(ROOT))
    try:
        MODULE.render(
            audit,
            json.loads(validation_path.read_text(encoding="utf-8")),
            audit_path,
            validation_path,
        )
    except ValueError as error:
        assert "required protocol fields are missing" in str(error)
    else:
        raise AssertionError("missing protocol field must be rejected")
    finally:
        temporary_report.unlink()
