"""Generate the graph-threshold sensitivity chart used by the thesis."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = ROOT / "docs" / "experiments" / "kg-threshold-sensitivity.md"
CHART_PATH = ROOT / "docs" / "user-guide-assets" / "10-kg-threshold-sensitivity.png"

CONTAINER_CODE = r"""
import json
from statistics import mean
from app.core.database import SessionLocal
from app.models.ai import AIExperimentRun
from app.services.knowledge_graph import KnowledgeGraphService

svc = KnowledgeGraphService()
db = SessionLocal()
run = db.get(AIExperimentRun, 4)
entities, relations = svc.get_project_graph(db, run.project_id)
entity_by_id = {entity.id: entity for entity in entities}
thresholds = [0.5, 1.0, 2.0, 3.0, 4.0]
result = {}
for threshold in thresholds:
    counts = []
    for question in run.questions_json:
        tokens = svc._query_tokens(question)
        hints = svc._relation_hints(question, tokens)
        scored = []
        for relation in relations:
            source = entity_by_id[relation.source_entity_id]
            target = entity_by_id[relation.target_entity_id]
            score = svc._score_relation(source, target, relation, tokens, hints)
            scored.append((score, relation.confidence, relation.id))
        scored.sort(reverse=True)
        selected = [item for item in scored if item[0] >= threshold][:10]
        counts.append(len(selected))
    result[str(threshold)] = {
        "coverage": sum(count > 0 for count in counts) / len(counts),
        "avg_hits": mean(counts),
        "full_top10": sum(count == 10 for count in counts),
        "zero_hit": sum(count == 0 for count in counts),
    }

confidence_result = {}
for confidence in [0.5, 0.7, 0.9, 1.0]:
    selections = []
    for question in run.questions_json:
        tokens = svc._query_tokens(question)
        hints = svc._relation_hints(question, tokens)
        scored = []
        for relation in relations:
            source = entity_by_id[relation.source_entity_id]
            target = entity_by_id[relation.target_entity_id]
            score = svc._score_relation(source, target, relation, tokens, hints)
            if score < 1.0:
                continue
            tie_confidence = confidence if relation.source_type == "note_extraction" else 1.0
            scored.append((score, tie_confidence, relation.id))
        scored.sort(reverse=True)
        selections.append([item[2] for item in scored[:10]])
    confidence_result[str(confidence)] = selections
baseline = confidence_result["0.7"]
confidence_summary = {
    key: sum(selection == baseline[index] for index, selection in enumerate(selections))
    for key, selections in confidence_result.items()
}
print(json.dumps({"thresholds": result, "confidence_same_cases": confidence_summary}))
db.close()
"""


def load_sensitivity() -> dict:
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "backend", "python", "-"],
        cwd=ROOT,
        input=CONTAINER_CODE,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def main() -> None:
    data = load_sensitivity()
    thresholds = [0.5, 1.0, 2.0, 3.0, 4.0]
    rows = [data["thresholds"][str(value)] for value in thresholds]

    figure, axis_left = plt.subplots(figsize=(7.4, 4.4))
    axis_right = axis_left.twinx()
    axis_left.plot(
        thresholds,
        [row["coverage"] * 100 for row in rows],
        marker="o",
        color="#4C78A8",
        label="Graph coverage",
    )
    axis_right.plot(
        thresholds,
        [row["avg_hits"] for row in rows],
        marker="s",
        color="#F58518",
        label="Mean graph hits",
    )
    axis_left.set_xlabel("Minimum graph score")
    axis_left.set_ylabel("Coverage (%)", color="#4C78A8")
    axis_right.set_ylabel("Mean hits", color="#F58518")
    axis_left.set_ylim(0, 105)
    axis_right.set_ylim(0, 11)
    axis_left.set_yticks([0, 20, 40, 60, 80, 100])
    axis_right.set_yticks([0, 2, 4, 6, 8, 10])
    axis_left.tick_params(axis="y", colors="#4C78A8")
    axis_right.tick_params(axis="y", colors="#F58518")
    axis_left.spines["left"].set_color("#4C78A8")
    axis_right.spines["right"].set_color("#F58518")
    axis_left.grid(linestyle="--", alpha=0.3)
    for threshold, row in zip(thresholds, rows, strict=True):
        axis_left.annotate(
            f"{row['coverage']:.0%}",
            (threshold, row["coverage"] * 100),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            color="#4C78A8",
            fontsize=8,
        )
        axis_right.annotate(
            f"{row['avg_hits']:.2f}",
            (threshold, row["avg_hits"]),
            xytext=(0, -14),
            textcoords="offset points",
            ha="center",
            color="#F58518",
            fontsize=8,
        )
    lines = axis_left.get_lines() + axis_right.get_lines()
    axis_left.legend(lines, [line.get_label() for line in lines], loc="lower left")
    figure.tight_layout()
    CHART_PATH.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(CHART_PATH, dpi=200, bbox_inches="tight")

    lines_out = [
        "# 图谱检索参数敏感性分析",
        "",
        "| 最低得分阈值 | 图谱覆盖率 | 平均命中数 | 命中10条的问题数 | 零命中问题数 |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for threshold, row in zip(thresholds, rows, strict=True):
        lines_out.append(
            f"| {threshold:.1f} | {row['coverage']:.1%} | {row['avg_hits']:.2f} | "
            f"{row['full_top10']} | {row['zero_hit']} |"
        )
    lines_out.extend(
        [
            "",
            "抽取关系置信度敏感性:",
            "",
            "| 抽取关系置信度 | 与0.7基线完全相同的问题数(共20题) |",
            "| ---: | ---: |",
        ]
    )
    for confidence, same_count in data["confidence_same_cases"].items():
        lines_out.append(f"| {float(confidence):.1f} | {same_count} |")
    lines_out.extend(
        [
            "",
            "结果说明: 当前实现中的置信度不参与相关性得分求和,只在得分相同时作为次级排序键。"
            "在0.5至1.0范围内调整抽取关系置信度,20题的前10条上下文均未变化。"
            "真正影响覆盖率的是最低得分阈值: 阈值由1.0提高到3.0后覆盖率由95%降至85%,"
            "提高到4.0后降至60%。因此论文将置信度重新界定为来源强度元数据,不再把它解释为经验概率或性能参数。",
            "",
        ]
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines_out), encoding="utf-8")
    print(f"Report saved: {REPORT_PATH}")
    print(f"Chart saved: {CHART_PATH}")


if __name__ == "__main__":
    main()
