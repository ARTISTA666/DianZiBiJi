#!/usr/bin/env python3
"""Validate a five-mode repeated experiment at the question-cluster level."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from freeze_preregistration import verify_manifest


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "data" / "real" / "experiment-5" / "internal-five-mode-experiment-report.json"
DEFAULT_CSV = ROOT / "data" / "real" / "experiment-5" / "internal-five-mode-experiment.csv"
DEFAULT_FREEZE = ROOT / "docs" / "experiments" / "rag-experiment-5-internal-freeze-manifest-v2.json"
DEFAULT_JSON = ROOT / "data" / "real" / "experiment-5" / "internal-five-mode-validation.json"
DEFAULT_MARKDOWN = ROOT / "docs" / "experiments" / "rag-experiment-5-internal-automatic-validation.md"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = round((len(ordered) - 1) * quantile)
    return ordered[index]


def bootstrap_mean_ci(
    values: list[float],
    *,
    seed: int = 20260713,
    samples: int = 10000,
) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    randomizer = random.Random(seed)
    means = [
        statistics.fmean(randomizer.choice(values) for _ in values)
        for _ in range(samples)
    ]
    return percentile(means, 0.025), percentile(means, 0.975)


def build_validation(
    report: dict[str, Any],
    csv_path: Path,
    freeze_path: Path,
    report_path: Path = DEFAULT_REPORT,
) -> dict[str, Any]:
    with csv_path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    modes = tuple(report["methods"])
    repetitions = int(report["repetitions"])
    question_ids = tuple(report["selected_case_ids"])
    expected_rows = len(modes) * repetitions * len(question_ids)
    keys = [
        (int(row["question_index"]), int(row["repetition_index"]), row["mode"])
        for row in rows
    ]
    row_checks = {
        "expected_rows": expected_rows,
        "actual_rows": len(rows),
        "unique_case_keys": len(set(keys)),
        "completed_rows": sum(row["status"] == "completed" for row in rows),
        "failed_rows": sum(row["status"] != "completed" for row in rows),
        "mode_counts": dict(sorted(Counter(row["mode"] for row in rows).items())),
        "repetition_counts": dict(sorted(Counter(row["repetition_index"] for row in rows).items())),
    }
    row_checks["ok"] = (
        len(rows) == expected_rows
        and len(set(keys)) == expected_rows
        and row_checks["failed_rows"] == 0
    )

    details = report["objective_evaluation"]["case_results"]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for detail in details:
        grouped[(detail["mode"], detail["case_id"])].append(detail)

    question_means: dict[str, dict[str, float]] = defaultdict(dict)
    repeat_stability: dict[str, dict[str, float]] = {}
    for mode in modes:
        stable = 0
        within_question_sd = []
        for case_id in question_ids:
            values = [item["fact_coverage"] for item in grouped[(mode, case_id)]]
            if len(values) != repetitions:
                raise ValueError(f"{mode}/{case_id} has {len(values)} repetitions")
            question_means[mode][case_id] = statistics.fmean(values)
            stable += len(set(values)) == 1
            within_question_sd.append(statistics.pstdev(values))
        repeat_stability[mode] = {
            "stable_question_count": stable,
            "question_count": len(question_ids),
            "stable_question_rate": round(stable / len(question_ids), 4),
            "mean_within_question_sd": round(statistics.fmean(within_question_sd), 4),
        }

    comparisons = {}
    baseline = question_means["project_rag"]
    for index, mode in enumerate(modes):
        if mode == "project_rag":
            continue
        deltas = [question_means[mode][case_id] - baseline[case_id] for case_id in question_ids]
        lower, upper = bootstrap_mean_ci(deltas, seed=20260713 + index)
        comparisons[mode] = {
            "unit_of_analysis": "question-level mean across repetitions",
            "question_count": len(deltas),
            "mean_fact_coverage_delta": round(statistics.fmean(deltas), 4),
            "median_fact_coverage_delta": round(statistics.median(deltas), 4),
            "bootstrap_95_ci": [round(lower, 4), round(upper, 4)],
            "improved_questions": sum(value > 0 for value in deltas),
            "tied_questions": sum(value == 0 for value in deltas),
            "worse_questions": sum(value < 0 for value in deltas),
            "multiple_comparison_adjusted": False,
        }

    freeze = verify_manifest(freeze_path, ROOT)
    fallacy_scan = [
        {"fallacy": "Simpson's Paradox", "severity": "NOTE", "detail": "Category cells contain only 1-3 questions; subgroup reversal is not estimated reliably."},
        {"fallacy": "Ecological Fallacy", "severity": "NOTE", "detail": "Inference remains at question level; no individual-level claim is made."},
        {"fallacy": "Berkson's Paradox", "severity": "CAUTION", "detail": "The benchmark is a selected single GEO project rather than a representative project sample."},
        {"fallacy": "Collider Bias", "severity": "NOTE", "detail": "No covariate adjustment or conditioning model is used."},
        {"fallacy": "Base Rate Neglect", "severity": "NOTE", "detail": "Fact coverage is not a diagnostic probability and is reported with its denominator."},
        {"fallacy": "Regression to the Mean", "severity": "NOTE", "detail": "There is no pre-post extreme-group selection."},
        {"fallacy": "Survivorship Bias", "severity": "NOTE", "detail": "All planned cases completed; no failed case was removed."},
        {"fallacy": "Look-Elsewhere Effect", "severity": "CAUTION", "detail": "Four comparisons and several metrics are reported without multiplicity correction."},
        {"fallacy": "Garden of Forking Paths", "severity": "CAUTION", "detail": "Inputs were frozen before generation, but clustered bootstrap validation was added post-run to correct pseudoreplication."},
        {"fallacy": "Correlation != Causation", "severity": "CAUTION", "detail": "Differences on this benchmark do not establish general method superiority across projects."},
        {"fallacy": "Reverse Causality", "severity": "NOTE", "detail": "No directional causal relationship is estimated."},
    ]
    return {
        "material_passport": {
            "origin_skill": "experiment-agent",
            "origin_mode": "validate",
            "origin_date": datetime.now(timezone.utc).isoformat(),
            "verification_status": "ANALYZED",
            "version_label": "validation_v1",
        },
        "overall_confidence": "CAUTION",
        "scope": "post-run automatic methodological validation of an internal developer-authored benchmark",
        "source": {
            "report_path": str(report.get("question_set", "")),
            "csv_sha256": sha256_file(csv_path),
            "report_sha256": sha256_file(report_path),
            "freeze_manifest": str(freeze_path.relative_to(ROOT)),
            "freeze_ok_after_run": freeze["ok"],
        },
        "row_integrity": row_checks,
        "mode_summary": report["objective_evaluation"]["mode_summary"],
        "repeat_stability": repeat_stability,
        "question_clustered_comparisons_vs_project_rag": comparisons,
        "warnings": [
            "Frozen repeat-level sign and McNemar p-values treat repeated generations as independent and must not be used as confirmatory inference.",
            "Bootstrap intervals are post-run methodological validation and are not multiplicity-adjusted.",
            "Alias-based fact coverage is not factual accuracy, association correctness or citation validity.",
            "The single developer-authored project does not establish external validity.",
        ],
        "fallacy_scan": {
            "coverage": "11/11",
            "items": fallacy_scan,
        },
        "reproducibility": {
            "method": "N/A — external API responses are stochastic; three frozen repetitions are reported instead",
            "verdict": "N/A",
        },
    }


def markdown(validation: dict[str, Any]) -> str:
    lines = [
        "## Material Passport",
        "",
        "- Origin Skill: experiment-agent",
        "- Origin Mode: validate",
        f"- Origin Date: {validation['material_passport']['origin_date']}",
        "- Verification Status: ANALYZED",
        "- Version Label: validation_v1",
        "",
        "# 实验 5 内部五方法自动验证",
        "",
        f"- 总体置信度：{validation['overall_confidence']}",
        f"- 行完整性：{'通过' if validation['row_integrity']['ok'] else '失败'}",
        f"- 冻结包运行后校验：{'通过' if validation['source']['freeze_ok_after_run'] else '失败'}",
        "",
        "## 问题聚类配对比较",
        "",
        "| 方法（相对混合 RAG） | 平均覆盖差 | 95% bootstrap CI | 改善/持平/下降问题数 |",
        "| --- | ---: | --- | ---: |",
    ]
    for mode, item in validation["question_clustered_comparisons_vs_project_rag"].items():
        lines.append(
            f"| {mode} | {item['mean_fact_coverage_delta']:+.4f} | "
            f"[{item['bootstrap_95_ci'][0]:+.4f}, {item['bootstrap_95_ci'][1]:+.4f}] | "
            f"{item['improved_questions']}/{item['tied_questions']}/{item['worse_questions']} |"
        )
    lines.extend(
        [
            "",
            "## 重复稳定性",
            "",
            "| 方法 | 三次覆盖完全一致的问题 | 比例 | 问题内平均标准差 |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for mode, item in validation["repeat_stability"].items():
        lines.append(
            f"| {mode} | {item['stable_question_count']}/{item['question_count']} | "
            f"{item['stable_question_rate']:.4f} | {item['mean_within_question_sd']:.4f} |"
        )
    lines.extend(["", "## 警告", ""])
    lines.extend(f"- {warning}" for warning in validation["warnings"])
    lines.extend(
        [
            "",
            "## 统计谬误扫描",
            "",
            f"覆盖：{validation['fallacy_scan']['coverage']}",
            "",
            "| 类型 | 严重度 | 说明 |",
            "| --- | --- | --- |",
        ]
    )
    lines.extend(
        f"| {item['fallacy']} | {item['severity']} | {item['detail']} |"
        for item in validation["fallacy_scan"]["items"]
    )
    lines.extend(
        [
            "",
            "## 复现性",
            "",
            "外部 API 响应具有随机性，不做逐字重跑判定；本轮报告同一冻结协议下的三次重复。",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--freeze", type=Path, default=DEFAULT_FREEZE)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    validation = build_validation(report, args.csv, args.freeze, args.report)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown.write_text(markdown(validation), encoding="utf-8")
    print(json.dumps({"row_integrity": validation["row_integrity"]["ok"], "freeze_ok": validation["source"]["freeze_ok_after_run"]}))
    return 0 if validation["row_integrity"]["ok"] and validation["source"]["freeze_ok_after_run"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
