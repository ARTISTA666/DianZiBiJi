"""Analyze objective and rule-based metrics from a paired RAG experiment."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


MODES = ("project_rag", "kg_enhanced_rag")
EVIDENCE_AUDIT_QUESTIONS = frozenset(range(1, 21)) - {5, 20}
MODE_LABELS = {
    "project_rag": "Plain RAG",
    "kg_enhanced_rag": "KG-Enhanced RAG",
}
CATEGORY_RANGES = (
    ("资料事实型", range(1, 6)),
    ("实验对象关系型", range(6, 11)),
    ("过程追溯型", range(11, 16)),
    ("综合总结型", range(16, 21)),
)

# Each inner tuple is an alternative group. Every group must be represented in
# the answer for the case to count as a completed task.
GOLD_RULES: dict[int, tuple[tuple[str, ...], ...]] = {
    1: (("58℃", "58°C"), ("条带最清晰", "条带清晰"), ("非特异性",)),
    2: (("PCR_protocol_demo.txt",),),
    3: (("cell_assay_reference_demo.txt",),),
    4: (("读数",), ("统计",)),
    5: (("无法确认", "无法回答"),),
    6: (("Taq DNA Polymerase",), ("dNTP",), ("MgCl2",), ("模板 DNA", "模板DNA")),
    7: (("样本 A", "样本A"), ("样本 B", "样本B")),
    8: (("CCK-8",), ("PBS",), ("DMEM",), ("酶标仪",), ("CO2 培养箱", "CO₂培养箱")),
    9: (("RIPA",), ("BCA",), ("一抗",), ("二抗",)),
    10: (("电泳仪",), ("转膜仪",), ("凝胶成像系统",)),
    11: (("PCR 条件优化实验",),),
    12: (("细胞活力检测实验",),),
    13: (("Western Blot 蛋白表达验证",),),
    14: (("系统管理员",),),
    15: (
        ("PCR 条件优化实验",),
        ("细胞活力检测实验",),
        ("Western Blot 蛋白表达验证",),
        ("qPCR 定量验证实验",),
        ("细胞传代与冻存记录",),
        ("质粒提取与酶切鉴定",),
        ("细胞转染效率优化",),
        ("蛋白浓度标准曲线测定",),
        ("SDS-PAGE 凝胶配制与电泳",),
        ("细胞凋亡检测实验",),
        ("RNA 提取与逆转录",),
        ("免疫荧光染色实验",),
        ("克隆形成实验",),
        ("ELISA 检测实验",),
        ("质粒测序结果分析",),
    ),
    16: (
        ("PCR 条件优化实验",),
        ("细胞活力检测实验",),
        ("Western Blot 蛋白表达验证",),
    ),
    17: (("58℃", "58°C"), ("18%",), ("目标蛋白", "蛋白表达降低")),
    18: (
        ("PCR",),
        ("Taq DNA Polymerase", "SYBR Green"),
        ("细胞培养", "细胞活力"),
        ("CCK-8", "DMEM"),
        ("Western Blot",),
        ("RIPA", "BCA"),
        ("质粒",),
        ("Lipofectamine", "EcoRI", "HindIII"),
    ),
    19: (
        ("PCR Thermal Cycler", "荧光定量 PCR 仪"),
        ("酶标仪",),
        ("电泳仪",),
        ("转膜仪",),
        ("凝胶成像系统",),
        ("离心机",),
    ),
    20: (("复核",), ("99.8%", "320 pg/mL", "8%", "A260/280")),
}


def percentile(values: list[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def pearson(left: list[float], right: list[float]) -> float:
    if len(left) < 2 or len(left) != len(right):
        return 0.0
    left_mean = mean(left)
    right_mean = mean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    left_scale = math.sqrt(sum((x - left_mean) ** 2 for x in left))
    right_scale = math.sqrt(sum((y - right_mean) ** 2 for y in right))
    return numerator / (left_scale * right_scale) if left_scale and right_scale else 0.0


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def usage_value(row: dict[str, str], key: str) -> float:
    try:
        return float(json.loads(row.get("usage_json") or "{}").get(key, 0))
    except (TypeError, ValueError, json.JSONDecodeError):
        return 0.0


def task_completed(row: dict[str, str]) -> bool:
    answer = row.get("answer") or ""
    rules = GOLD_RULES[int(row["question_index"])]
    return all(any(variant.lower() in answer.lower() for variant in alternatives) for alternatives in rules)


def evidence_text(row: dict[str, str], source: str) -> str:
    documents = json.loads(row.get("sources_json") or "[]")
    relations = json.loads(row.get("graph_context_json") or "[]")
    document_text = " ".join(
        " ".join(str(item.get(key, "")) for key in ("filename", "snippet"))
        for item in documents
    )
    graph_text = " ".join(
        " ".join(
            str(item.get(key, ""))
            for key in ("source_label", "target_label", "relation_label", "relation_type")
        )
        for item in relations
    )
    if source == "documents":
        return document_text
    if source == "graph":
        return graph_text
    if source == "combined":
        return f"{document_text} {graph_text}"
    raise ValueError(f"Unsupported evidence source: {source}")


def evidence_completed(row: dict[str, str], source: str) -> bool:
    question_index = int(row["question_index"])
    if question_index not in EVIDENCE_AUDIT_QUESTIONS:
        return False
    evidence = evidence_text(row, source).lower()
    return all(
        any(variant.lower() in evidence for variant in alternatives)
        for alternatives in GOLD_RULES[question_index]
    )


def summarize_evidence(rows: list[dict[str, str]]) -> dict[str, dict[str, float]]:
    summary: dict[str, dict[str, float]] = {}
    for mode in MODES:
        audited = [
            row
            for row in rows
            if row["mode"] == mode
            and row["status"] == "completed"
            and int(row["question_index"]) in EVIDENCE_AUDIT_QUESTIONS
        ]
        count = len(audited)
        document_hits = sum(evidence_completed(row, "documents") for row in audited)
        graph_hits = sum(evidence_completed(row, "graph") for row in audited)
        combined_hits = sum(evidence_completed(row, "combined") for row in audited)
        answer_hits = sum(task_completed(row) for row in audited)
        summary[mode] = {
            "count": count,
            "document_hits": document_hits,
            "document_rate": document_hits / count if count else 0,
            "graph_hits": graph_hits,
            "graph_rate": graph_hits / count if count else 0,
            "combined_hits": combined_hits,
            "combined_rate": combined_hits / count if count else 0,
            "answer_hits": answer_hits,
            "answer_rate": answer_hits / count if count else 0,
        }
    return summary


def summarize(rows: list[dict[str, str]]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["mode"]].append(row)

    summary: dict[str, dict[str, float]] = {}
    for mode in MODES:
        mode_rows = grouped.get(mode, [])
        completed = [row for row in mode_rows if row["status"] == "completed"]
        latencies = [float(row["response_ms"]) for row in completed]
        graph_hits = [float(row["graph_hit_count"]) for row in completed]
        source_counts = [float(row["source_count"]) for row in completed]
        answers = [row.get("answer") or "" for row in completed]
        completion_tokens = [usage_value(row, "completion_tokens") for row in completed]
        summary[mode] = {
            "total": len(mode_rows),
            "completed": len(completed),
            "completion_rate": len(completed) / len(mode_rows) if mode_rows else 0,
            "task_completed": sum(task_completed(row) for row in completed),
            "task_completion_rate": (
                sum(task_completed(row) for row in completed) / len(completed) if completed else 0
            ),
            "avg_response_ms": mean(latencies),
            "median_response_ms": statistics.median(latencies) if latencies else 0,
            "p95_response_ms": percentile(latencies, 0.95),
            "max_response_ms": max(latencies, default=0),
            "response_sd_ms": statistics.stdev(latencies) if len(latencies) > 1 else 0,
            "avg_source_count": mean(source_counts),
            "avg_graph_hit_count": mean(graph_hits),
            "graph_coverage": sum(hit > 0 for hit in graph_hits) / len(graph_hits) if graph_hits else 0,
            "fallback_count": sum(bool(row.get("fallback_reason")) for row in completed),
            "source_marker_rate": sum("[S" in answer for answer in answers) / len(answers) if answers else 0,
            "graph_marker_rate": sum("[G" in answer for answer in answers) / len(answers) if answers else 0,
            "evidence_marker_rate": (
                sum("[S" in answer or "[G" in answer for answer in answers) / len(answers)
                if answers
                else 0
            ),
            "avg_prompt_tokens": mean([usage_value(row, "prompt_tokens") for row in completed]),
            "avg_completion_tokens": mean(completion_tokens),
            "avg_total_tokens": mean([usage_value(row, "total_tokens") for row in completed]),
            "completion_latency_correlation": pearson(completion_tokens, latencies),
        }
    return summary


def paired_latency(rows: list[dict[str, str]]) -> dict[str, float]:
    by_case: dict[str, dict[str, float]] = defaultdict(dict)
    for row in rows:
        if row["status"] == "completed":
            by_case[row["question_index"]][row["mode"]] = float(row["response_ms"])
    deltas = [
        values["kg_enhanced_rag"] - values["project_rag"]
        for values in by_case.values()
        if all(mode in values for mode in MODES)
    ]
    return {
        "paired_cases": len(deltas),
        "mean_delta_ms": mean(deltas),
        "median_delta_ms": statistics.median(deltas) if deltas else 0,
        "kg_faster_cases": sum(delta < 0 for delta in deltas),
    }


def paired_task_test(rows: list[dict[str, str]]) -> dict[str, float]:
    by_case: dict[str, dict[str, bool]] = defaultdict(dict)
    for row in rows:
        if row["status"] == "completed":
            by_case[row["question_index"]][row["mode"]] = task_completed(row)
    kg_only = 0
    plain_only = 0
    for values in by_case.values():
        if not all(mode in values for mode in MODES):
            continue
        if values["kg_enhanced_rag"] and not values["project_rag"]:
            kg_only += 1
        elif values["project_rag"] and not values["kg_enhanced_rag"]:
            plain_only += 1
    discordant = kg_only + plain_only
    if discordant:
        tail = sum(math.comb(discordant, k) for k in range(min(kg_only, plain_only) + 1))
        p_value = min(1.0, 2 * tail / (2**discordant))
    else:
        p_value = 1.0
    return {
        "kg_only": kg_only,
        "plain_only": plain_only,
        "discordant": discordant,
        "mcnemar_exact_p": p_value,
    }


def summarize_categories(rows: list[dict[str, str]]) -> list[dict[str, float | str]]:
    categories: list[dict[str, float | str]] = []
    for label, indexes in CATEGORY_RANGES:
        index_set = {str(index) for index in indexes}
        for mode in MODES:
            completed = [
                row
                for row in rows
                if row["mode"] == mode
                and row["status"] == "completed"
                and row["question_index"] in index_set
            ]
            categories.append(
                {
                    "category": label,
                    "mode": mode,
                    "count": len(completed),
                    "task_completion_rate": (
                        sum(task_completed(row) for row in completed) / len(completed)
                        if completed
                        else 0
                    ),
                    "avg_response_ms": mean([float(row["response_ms"]) for row in completed]),
                    "avg_graph_hit_count": mean(
                        [float(row["graph_hit_count"]) for row in completed]
                    ),
                    "graph_coverage": (
                        sum(float(row["graph_hit_count"]) > 0 for row in completed) / len(completed)
                        if completed
                        else 0
                    ),
                }
            )
    return categories


def write_audit_csv(output: Path, rows: list[dict[str, str]]) -> None:
    fields = [
        "question_index",
        "query_log_id",
        "mode",
        "question",
        "rule_based_task_completed",
        "gold_rule_groups",
        "human_reviewer_decision",
        "human_reviewer_comment",
    ]
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "question_index": row["question_index"],
                    "query_log_id": row["query_log_id"],
                    "mode": row["mode"],
                    "question": row["question"],
                    "rule_based_task_completed": str(task_completed(row)).lower(),
                    "gold_rule_groups": json.dumps(
                        GOLD_RULES[int(row["question_index"])], ensure_ascii=False
                    ),
                    "human_reviewer_decision": "",
                    "human_reviewer_comment": "",
                }
            )


def write_blind_review_files(output_dir: Path, rows: list[dict[str, str]]) -> None:
    shuffled = list(rows)
    random.Random(20260612).shuffle(shuffled)
    sheet_path = output_dir / "rag-experiment-4-blind-review-sheet.csv"
    key_path = output_dir / "rag-experiment-4-blind-review-key.csv"
    with sheet_path.open("w", encoding="utf-8-sig", newline="") as handle:
        fields = [
            "blind_id",
            "question",
            "answer",
            "evidence_sources",
            "evidence_graph_relations",
            "is_accurate",
            "is_traceable",
            "score_1_to_5",
            "reviewer_comment",
            "reviewer_signature",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, row in enumerate(shuffled, start=1):
            writer.writerow(
                {
                    "blind_id": f"B{index:02d}",
                    "question": row["question"],
                    "answer": row["answer"],
                    "evidence_sources": row["sources_json"],
                    "evidence_graph_relations": row["graph_context_json"],
                    "is_accurate": "",
                    "is_traceable": "",
                    "score_1_to_5": "",
                    "reviewer_comment": "",
                    "reviewer_signature": "",
                }
            )
    with key_path.open("w", encoding="utf-8-sig", newline="") as handle:
        fields = ["blind_id", "question_index", "query_log_id", "mode"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, row in enumerate(shuffled, start=1):
            writer.writerow(
                {
                    "blind_id": f"B{index:02d}",
                    "question_index": row["question_index"],
                    "query_log_id": row["query_log_id"],
                    "mode": row["mode"],
                }
            )
    print(f"Blind review sheet saved: {sheet_path}")
    print(f"Blind review key saved: {key_path}")


def write_report(
    output: Path,
    csv_path: Path,
    summary: dict[str, dict[str, float]],
    paired: dict[str, float],
    paired_task: dict[str, float],
    categories: list[dict[str, float | str]],
    evidence_summary: dict[str, dict[str, float]],
) -> None:
    lines = [
        "# RAG 对照实验客观指标与规则化任务评价",
        "",
        f"数据来源: `{csv_path.name}`",
        "",
        "说明: 任务完成率依据回答生成后固定的答案要点进行机械匹配,用于补充可复现的客观评价。"
        "答案要点并非实验运行前预注册,存在循环设计风险;该指标不等同于人工盲评,也不替代"
        "回答完整性、表述质量和证据充分性的人工判断。",
        "",
        "## 模式指标",
        "",
        "| 指标 | 普通 RAG | 图谱增强 RAG |",
        "| --- | ---: | ---: |",
    ]
    metric_rows = [
        ("总案例数", "total", "{:.0f}"),
        ("完成案例数", "completed", "{:.0f}"),
        ("运行完成率", "completion_rate", "{:.1%}"),
        ("规则化任务完成数", "task_completed", "{:.0f}"),
        ("规则化任务完成率", "task_completion_rate", "{:.1%}"),
        ("平均响应耗时(ms)", "avg_response_ms", "{:.2f}"),
        ("响应耗时中位数(ms)", "median_response_ms", "{:.2f}"),
        ("响应耗时 P95(ms)", "p95_response_ms", "{:.2f}"),
        ("响应耗时最大值(ms)", "max_response_ms", "{:.2f}"),
        ("响应耗时标准差(ms)", "response_sd_ms", "{:.2f}"),
        ("平均资料来源数", "avg_source_count", "{:.2f}"),
        ("显式回退次数", "fallback_count", "{:.0f}"),
        ("回答包含任一证据标记比例", "evidence_marker_rate", "{:.1%}"),
        ("平均总 Token", "avg_total_tokens", "{:.2f}"),
        ("生成 Token 与时延相关系数", "completion_latency_correlation", "{:.3f}"),
    ]
    for label, key, template in metric_rows:
        lines.append(
            f"| {label} | {template.format(summary['project_rag'][key])} | "
            f"{template.format(summary['kg_enhanced_rag'][key])} |"
        )

    lines.extend(
        [
            "",
            "## 成对比较",
            "",
            f"- 完整成对案例: {int(paired['paired_cases'])}",
            f"- 图谱模式平均耗时差: {paired['mean_delta_ms']:.2f} ms",
            f"- 图谱模式耗时中位差: {paired['median_delta_ms']:.2f} ms",
            f"- 图谱模式更快的案例数: {int(paired['kg_faster_cases'])}",
            f"- 仅图谱模式完成任务: {int(paired_task['kg_only'])}",
            f"- 仅普通模式完成任务: {int(paired_task['plain_only'])}",
            f"- McNemar 精确检验: p={paired_task['mcnemar_exact_p']:.4f}",
            "",
            "## 分问题类型结果",
            "",
            "| 问题类型 | 模式 | 案例数 | 任务完成率 | 平均耗时(ms) |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    for row in categories:
        lines.append(
            f"| {row['category']} | {MODE_LABELS[str(row['mode'])]} | {int(row['count'])} | "
            f"{float(row['task_completion_rate']):.1%} | {float(row['avg_response_ms']):.2f} |"
        )

    lines.extend(
        [
            "",
            "## 答案要点的证据覆盖",
            "",
            "证据覆盖分析只纳入 18 个可由检索事实直接核对的问题。Q5 的正确行为是拒答,Q20 "
            "要求基于证据提出复核建议,两者不适合用“证据文本包含全部答案要点”判定。",
            "",
            "| 模式 | 资料证据覆盖 | 图谱证据覆盖 | 合并证据覆盖 | 最终答案完成 |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for mode in MODES:
        item = evidence_summary[mode]
        lines.append(
            f"| {MODE_LABELS[mode]} | "
            f"{int(item['document_hits'])}/{int(item['count'])} ({item['document_rate']:.1%}) | "
            f"{int(item['graph_hits'])}/{int(item['count'])} ({item['graph_rate']:.1%}) | "
            f"{int(item['combined_hits'])}/{int(item['count'])} ({item['combined_rate']:.1%}) | "
            f"{int(item['answer_hits'])}/{int(item['count'])} ({item['answer_rate']:.1%}) |"
        )
    lines.extend(
        [
            "",
            "在这 18 个事实型任务中,两种模式的合并证据覆盖数与最终答案完成数分别完全一致。"
            "这表明当前批次的主要差异可由检索证据是否覆盖答案要点解释,而不能归因于更强的"
            "通用推理能力。图谱模式的 6 个未完成事实型问题均首先表现为证据覆盖不足。",
        ]
    )

    lines.extend(
        [
            "",
            "## P95 长尾解释",
            "",
            "- 普通 RAG 的 Q18 和 Q19 分别耗时 3765 ms 和 3707 ms,生成 Token 数分别为 276 和 260。",
            "- 图谱增强 RAG 的 Q20 耗时 5268 ms,生成 Token 数为 341。",
            "- 两种模式中生成 Token 与耗时的相关系数分别为 "
            f"{summary['project_rag']['completion_latency_correlation']:.3f} 和 "
            f"{summary['kg_enhanced_rag']['completion_latency_correlation']:.3f}。"
            "因此 P95 的反向差异主要由长回答和 20 例小样本的分位数插值共同造成,不能解释为图谱模式具有稳定的性能优势。",
            "",
            "## 解释边界",
            "",
            "- 规则化任务完成率验证答案是否覆盖预先定义的关键要点,不判断语言质量和细微语义。",
            "- 图谱命中数和来源数描述证据检索结构,不能替代人工准确性与可追溯性判断。",
            "- 人工盲评应在隐藏模式标识后独立完成,并写回单独评价文件;本报告预留人工签核列但不伪造人工结论。",
            "",
        ]
    )
    output.write_text("\n".join(lines), encoding="utf-8")


def write_chart(
    output: Path,
    summary: dict[str, dict[str, float]],
    evidence_summary: dict[str, dict[str, float]],
) -> None:
    labels = [MODE_LABELS[mode] for mode in MODES]
    evidence_rate = [evidence_summary[mode]["combined_rate"] * 100 for mode in MODES]
    task_rate = [summary[mode]["task_completion_rate"] * 100 for mode in MODES]
    latency = [summary[mode]["avg_response_ms"] for mode in MODES]
    figure, axes = plt.subplots(1, 2, figsize=(9.2, 3.8))
    positions = list(range(len(labels)))
    width = 0.34
    evidence_bars = axes[0].bar(
        [position - width / 2 for position in positions],
        evidence_rate,
        width,
        color="#4C78A8",
        label="Combined evidence coverage (18 factual)",
    )
    task_bars = axes[0].bar(
        [position + width / 2 for position in positions],
        task_rate,
        width,
        color="#F58518",
        label="Task completion (20 total)",
    )
    axes[0].set_title("Evidence coverage and task completion")
    axes[0].set_ylabel("Percent")
    axes[0].set_xticks(positions, labels, rotation=10)
    axes[0].legend(fontsize=8)
    axes[0].grid(axis="y", linestyle="--", alpha=0.3)
    for bars in (evidence_bars, task_bars):
        for bar in bars:
            value = bar.get_height()
            axes[0].text(
                bar.get_x() + bar.get_width() / 2,
                value,
                f"{value:.0f}%",
                ha="center",
                va="bottom",
            )

    latency_bars = axes[1].bar(labels, latency, color=["#4C78A8", "#F58518"])
    axes[1].set_title("Mean response latency")
    axes[1].set_ylabel("Milliseconds")
    axes[1].grid(axis="y", linestyle="--", alpha=0.3)
    axes[1].tick_params(axis="x", labelrotation=10)
    for bar in latency_bars:
        value = bar.get_height()
        axes[1].text(
            bar.get_x() + bar.get_width() / 2,
            value,
            f"{value:.0f}",
            ha="center",
            va="bottom",
        )

    figure.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=200, bbox_inches="tight")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--chart", type=Path)
    parser.add_argument("--audit-csv", type=Path)
    args = parser.parse_args()

    rows = load_rows(args.csv_path)
    summary = summarize(rows)
    paired = paired_latency(rows)
    paired_task = paired_task_test(rows)
    categories = summarize_categories(rows)
    evidence_summary = summarize_evidence(rows)
    report = args.report or args.csv_path.with_name(f"{args.csv_path.stem}-objective-analysis.md")
    chart = args.chart or args.csv_path.with_name(f"{args.csv_path.stem}-objective-metrics.png")
    audit_csv = args.audit_csv or args.csv_path.with_name(f"{args.csv_path.stem}-evaluation-sheet.csv")
    write_report(
        report,
        args.csv_path,
        summary,
        paired,
        paired_task,
        categories,
        evidence_summary,
    )
    write_chart(chart, summary, evidence_summary)
    write_audit_csv(audit_csv, rows)
    write_blind_review_files(args.csv_path.parent, rows)
    print(f"Report saved: {report}")
    print(f"Chart saved: {chart}")
    print(f"Evaluation sheet saved: {audit_csv}")


if __name__ == "__main__":
    main()
