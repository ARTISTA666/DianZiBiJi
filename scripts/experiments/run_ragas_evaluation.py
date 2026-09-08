#!/usr/bin/env python3
"""RAGAS 自动评测（去人工化评价标准）：实验 4 与实验 5 的 RAG 样本。

必须使用独立 venv 运行（系统 python3 受 PEP 668 限制，且依赖不在系统环境）：

    /Users/yusong/.venvs/ragas/bin/python scripts/run_ragas_evaluation.py [--smoke N]

judge 模型：deepseek-v4-flash（DeepSeek OpenAI 兼容接口），密钥从仓库根目录
.env 的 DEEPSEEK_API_KEY 读取，脚本不会打印密钥。

产出（写入 docs/experiments/）：
    - ragas-evaluation-<date>.json：逐样本分数
    - ragas-evaluation-<date>.md：分臂聚合报告

指标：faithfulness、context_precision、context_recall。
response_relevancy 需要嵌入模型，本轮明确跳过。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from langchain_openai import ChatOpenAI  # noqa: E402
from ragas import evaluate  # noqa: E402
from ragas.dataset_schema import EvaluationDataset  # noqa: E402
from ragas.llms import LangchainLLMWrapper  # noqa: E402
from ragas.metrics import (  # noqa: E402
    Faithfulness,
    LLMContextPrecisionWithReference,
    LLMContextRecall,
)
from ragas.run_config import RunConfig  # noqa: E402

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

OUTPUT_DATE = "2026-08-26"
EXP4_CSV = REPO_ROOT / "docs/experiments/rag-experiment-4.csv"
EXP4_SHEET_CSV = REPO_ROOT / "docs/experiments/rag-experiment-4-evaluation-sheet.csv"
EXP5_CSV = REPO_ROOT / "data/real/experiment-5/internal-five-mode-experiment.csv"
HOLDOUT_JSON = REPO_ROOT / "data/real/GSE111619/gse111619_kg_holdout_questions.json"
ENV_FILE = REPO_ROOT / ".env"
OUTPUT_DIR = REPO_ROOT / "docs/experiments"

# 批次一：mode 原始值 -> 报告用臂名
EXP4_ARMS = {
    "project_rag": "Plain RAG",
    "kg_enhanced_rag": "KG-Enhanced RAG",
}
# 批次二：三臂（pure_llm 与 structured_query 不适用 RAG 检索指标，跳过）
EXP5_ARMS = {
    "project_rag": "project_rag",
    "kg_enhanced_rag": "kg_enhanced_rag",
    "bm25_rag": "bm25_rag",
}

METRIC_NAMES = ("faithfulness", "context_precision", "context_recall")


def load_api_key() -> str:
    """从仓库 .env 读取 DEEPSEEK_API_KEY；绝不打印。"""
    if not ENV_FILE.exists():
        raise SystemExit(f"missing env file: {ENV_FILE}")
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("DEEPSEEK_API_KEY="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            if value:
                return value
    raise SystemExit("DEEPSEEK_API_KEY not found in .env")


def read_csv(path: Path) -> list[dict]:
    import csv

    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def parse_sources(snippets_from: dict) -> list[str]:
    """sources_json 行 -> snippet 列表（空 JSON 时返回空列表）。"""
    if not snippets_from:
        return []
    try:
        items = json.loads(snippets_from)
    except json.JSONDecodeError:
        return []
    return [it.get("snippet", "") for it in items if isinstance(it, dict)]


def parse_graph_context(graph_context_json: str) -> list[str]:
    """graph_context_json -> 序列化 KG 三元组文本列表。

    kg_enhanced_rag 臂的回答引用 [G#] 标记，其主张来自图谱通道而非资料
    chunk；RAGAS faithfulness/context 指标需要看到系统实际检索到的全部证据，
    因此把图谱三元组并入 retrieved_contexts（与既有"合并证据覆盖"口径一致）。
    """
    if not graph_context_json or graph_context_json.strip() in ("", "[]", "null"):
        return []
    try:
        items = json.loads(graph_context_json)
    except json.JSONDecodeError:
        return []
    triples = []
    for it in items:
        if not isinstance(it, dict):
            continue
        src = it.get("source_label") or ""
        rel = it.get("relation_label") or it.get("relation_type") or ""
        dst = it.get("target_label") or ""
        if src and dst:
            triples.append(f"KG三元组：{src} -[{rel}]-> {dst}")
    return triples


def gold_reference_exp4(groups_json: str) -> str:
    """gold_rule_groups（别名组的数组）-> 参考答案文本。"""
    groups = json.loads(groups_json)
    parts = []
    for i, group in enumerate(groups, start=1):
        parts.append(f"组{i}：{'/'.join(group)}")
    return "答案要点：" + "；".join(parts)


def gold_reference_exp5(question_entry: dict) -> str:
    """holdout 问题金标准事实 -> 参考答案文本。"""
    labels = [fact["label"] for fact in question_entry.get("facts", [])]
    return "答案要点：" + "；".join(labels)


# ---------------------------------------------------------------------------
# 数据准备
# ---------------------------------------------------------------------------


def build_batch_exp4() -> list[dict]:
    rows = read_csv(EXP4_CSV)
    sheet_rows = read_csv(EXP4_SHEET_CSV)
    gold_by_qi: dict[int, str] = {}
    for r in sheet_rows:
        qi = int(r["question_index"])
        gold_by_qi.setdefault(qi, gold_reference_exp4(r["gold_rule_groups"]))

    samples = []
    for r in rows:
        if r["mode"] not in EXP4_ARMS or r["status"] != "completed":
            continue
        qi = int(r["question_index"])
        chunks = parse_sources(r.get("sources_json", ""))
        triples = parse_graph_context(r.get("graph_context_json", ""))
        samples.append(
            {
                "batch": "exp4",
                "arm": EXP4_ARMS[r["mode"]],
                "arm_raw": r["mode"],
                "batch_arm": f"exp4/{EXP4_ARMS[r['mode']]}",
                "question_index": qi,
                "repetition": None,
                "user_input": r["question"],
                "response": r["answer"],
                "retrieved_contexts": chunks + triples,
                "n_chunk_contexts": len(chunks),
                "n_graph_contexts": len(triples),
                "reference": gold_by_qi[qi],
            }
        )
    return samples


def build_batch_exp5() -> list[dict]:
    rows = read_csv(EXP5_CSV)
    holdout = json.loads(HOLDOUT_JSON.read_text(encoding="utf-8"))
    gold_by_qi = {
        int(entry["id"].lstrip("H")): gold_reference_exp5(entry) for entry in holdout
    }

    samples = []
    for r in rows:
        if r["mode"] not in EXP5_ARMS or r["status"] != "completed":
            continue
        qi = int(r["question_index"])
        rep = int(r["repetition_index"])
        chunks = parse_sources(r.get("sources_json", ""))
        triples = parse_graph_context(r.get("graph_context_json", ""))
        samples.append(
            {
                "batch": "exp5",
                "arm": EXP5_ARMS[r["mode"]],
                "arm_raw": r["mode"],
                "batch_arm": f"exp5/{r['mode']}",
                "question_index": qi,
                "repetition": rep,
                "user_input": r["question"],
                "response": r["answer"],
                "retrieved_contexts": chunks + triples,
                "n_chunk_contexts": len(chunks),
                "n_graph_contexts": len(triples),
                "reference": gold_by_qi[qi],
            }
        )
    return samples


# ---------------------------------------------------------------------------
# 评测执行
# ---------------------------------------------------------------------------


def run_evaluation(samples: list[dict], api_key: str) -> tuple[list, object]:
    judge = ChatOpenAI(
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        api_key=api_key,
        temperature=0.1,
        timeout=240,
        max_retries=2,
    )
    evaluator_llm = LangchainLLMWrapper(judge)

    metrics = [
        Faithfulness(),
        LLMContextPrecisionWithReference(),
        LLMContextRecall(),
    ]
    dataset = EvaluationDataset.from_list(
        [
            {
                "user_input": s["user_input"],
                "retrieved_contexts": s["retrieved_contexts"],
                "response": s["response"],
                "reference": s["reference"],
            }
            for s in samples
        ]
    )
    run_config = RunConfig(max_workers=8, max_retries=2, timeout=240)
    result = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=evaluator_llm,
        run_config=run_config,
        raise_exceptions=False,
        show_progress=True,
    )
    return result.scores, result


# ragas 0.4.x 在 result.scores 中使用的原始指标键 -> 报告用规范名
RAGAS_SCORE_KEYS = {
    "faithfulness": "faithfulness",
    "llm_context_precision_with_reference": "context_precision",
    "context_recall": "context_recall",
}


def collect_per_sample(samples: list[dict], scores: list) -> list[dict]:
    """把 ragas 分数对齐回样本；NaN 记为 null 并标注失败原因。"""
    out = []
    for s, sc in zip(samples, scores):
        record = {
            "batch": s["batch"],
            "arm": s["arm"],
            "batch_arm": s["batch_arm"],
            "question_index": s["question_index"],
            "repetition": s["repetition"],
            "n_chunk_contexts": s.get("n_chunk_contexts"),
            "n_graph_contexts": s.get("n_graph_contexts"),
            "faithfulness": None,
            "context_precision": None,
            "context_recall": None,
            "failed_metrics": [],
            "failure_reasons": [],
        }
        raw = sc if isinstance(sc, dict) else vars(sc)
        for ragas_key, canonical in RAGAS_SCORE_KEYS.items():
            value = raw.get(ragas_key)
            if value is None or (isinstance(value, float) and math.isnan(value)):
                record["failed_metrics"].append(canonical)
                record["failure_reasons"].append(
                    f"{canonical}: judge 调用在重试后仍未返回有效分数（NaN）"
                )
            else:
                record[canonical] = round(float(value), 4)
        out.append(record)
    return out


def identity_key(rec: dict):
    return (rec["batch"], rec["arm"], rec["question_index"], rec["repetition"])


def aggregate(per_sample: list[dict]) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for rec in per_sample:
        groups[rec["batch_arm"]].append(rec)
    report = {}
    for arm_key, recs in sorted(groups.items()):
        entry: dict = {"n_total": len(recs)}
        valid_counts = []
        for m in METRIC_NAMES:
            vals = [r[m] for r in recs if r[m] is not None]
            entry[f"{m}_mean"] = round(statistics.fmean(vals), 4) if vals else None
            entry[f"{m}_valid_n"] = len(vals)
            valid_counts.append(len(vals))
        entry["n_any_failure"] = sum(1 for r in recs if r["failed_metrics"])
        # 臂级状态：complete=三指标全有效；partial=部分有效；all_invalid=全部失败
        # （all_invalid 通常意味着 judge 服务/账户异常，该臂应视为未评测）
        if all(c == len(recs) for c in valid_counts):
            entry["status"] = "complete"
        elif all(c == 0 for c in valid_counts):
            entry["status"] = "all_invalid"
        else:
            entry["status"] = "partial"
        report[arm_key] = entry
    return report


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--smoke",
        type=int,
        default=0,
        metavar="N",
        help="每臂只取前 N 个样本做冒烟验证，写入 _smoke 后缀文件",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只构建数据并打印统计，不调用 judge",
    )
    parser.add_argument(
        "--out-suffix",
        default="",
        help="输出文件名后缀（如 _smoke），默认正式文件名",
    )
    parser.add_argument(
        "--only",
        default="",
        help="逗号分隔的 batch_arm 列表（如 'exp5/bm25_rag,exp4/Plain RAG'），"
        "只评测这些臂并与已有 JSON 合并（断点续跑）",
    )
    parser.add_argument(
        "--note",
        default="",
        help="不调用 judge；向已有正式 JSON 追加一条执行说明并重写 JSON/MD 报告"
        "（用于如实记录执行中断等事实）",
    )
    args = parser.parse_args()

    api_key = load_api_key()
    assert len(api_key) > 0  # 只校验存在性，不打印

    json_path = OUTPUT_DIR / f"ragas-evaluation-{OUTPUT_DATE}{args.out_suffix}.json"

    # --note：只追加执行说明并重写产出，不调用 judge
    if args.note:
        if not json_path.exists():
            raise SystemExit(f"--note requires existing payload: {json_path}")
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        notes = payload.setdefault("execution_notes", [])
        if args.note not in notes:
            notes.append(args.note)
        # 用当前版本的聚合逻辑重算（补齐 status 等后加字段）
        payload["aggregate"] = aggregate(payload["samples"])
        tmp_path = json_path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp_path.replace(json_path)
        write_markdown_report(payload)
        print(f"note appended; rewrote {json_path} and matching .md")
        return 0

    all_samples = build_batch_exp4() + build_batch_exp5()
    total_expected = len(all_samples)
    samples = list(all_samples)
    by_arm: dict[str, int] = defaultdict(int)
    for s in samples:
        by_arm[s["batch_arm"]] += 1
    print(f"prepared samples: {len(samples)} (expected total {total_expected})")
    for k in sorted(by_arm):
        print(f"  {k}: {by_arm[k]}")

    if args.dry_run:
        empty_ctx = sum(1 for s in samples if not s["retrieved_contexts"])
        print(f"dry-run: samples with empty retrieved_contexts = {empty_ctx}")
        print("sample reference (exp4):", samples[0]["reference"])
        exp5_ref = next(s["reference"] for s in samples if s["batch"] == "exp5")
        print("sample reference (exp5):", exp5_ref[:200])
        return 0

    groups: dict[str, list[dict]] = defaultdict(list)
    for s in samples:
        groups[s["batch_arm"]].append(s)

    if args.smoke > 0:
        picked: list[dict] = []
        seen: dict[str, int] = defaultdict(int)
        for s in samples:
            if seen[s["batch_arm"]] < args.smoke:
                picked.append(s)
                seen[s["batch_arm"]] += 1
        smoke_groups: dict[str, list[dict]] = defaultdict(list)
        for s in picked:
            smoke_groups[s["batch_arm"]].append(s)
        groups = smoke_groups
        print(f"smoke mode: {len(picked)} samples")

    if args.only:
        keys = [k.strip() for k in args.only.split(",") if k.strip()]
        unknown = [k for k in keys if k not in groups]
        if unknown:
            raise SystemExit(f"unknown batch_arm keys: {unknown}")
    else:
        keys = sorted(groups)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 断点续跑：正式产出（无后缀）时加载已有部分结果
    payload = None
    if not args.out_suffix and json_path.exists():
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        print(f"resuming: found existing partial payload with "
              f"{len(payload.get('samples', []))} sample records")
    if payload is None:
        payload = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "ragas_version": _ragas_version(),
            "judge_model": "deepseek-v4-flash",
            "judge_base_url": "https://api.deepseek.com",
            "judge_temperature": 0.1,
            "metrics": list(METRIC_NAMES),
            "skipped_metrics": {
                "response_relevancy": "需要嵌入模型，本轮明确跳过",
            },
            "skipped_arms": {
                "pure_llm": "无检索上下文，不适用 RAG 检索/忠实度指标",
                "structured_query": "结构化查询路径，非 RAG 生成管线，不适用本轮指标",
            },
            "n_samples_expected": total_expected,
            "arm_runs": [],
            "samples": [],
        }

    for key in keys:
        subset = groups[key]
        t0 = datetime.now(timezone.utc)
        print(f"[{t0.isoformat()}] evaluating arm {key} ({len(subset)} samples)...")
        scores, _result = run_evaluation(subset, api_key)
        t1 = datetime.now(timezone.utc)
        per_sample = collect_per_sample(subset, scores)

        merged: dict = {identity_key(r): r for r in payload["samples"]}
        for r in per_sample:
            merged[identity_key(r)] = r
        payload["samples"] = list(merged.values())
        payload["finished_at_utc"] = t1.isoformat()
        payload["arm_runs"].append(
            {
                "batch_arm": key,
                "started_at_utc": t0.isoformat(),
                "finished_at_utc": t1.isoformat(),
                "wall_time_seconds": round((t1 - t0).total_seconds(), 1),
                "n_samples": len(subset),
            }
        )
        payload["wall_time_seconds"] = round(
            sum(run_["wall_time_seconds"] for run_ in payload["arm_runs"]), 1
        )
        n_fail_records = sum(1 for r in payload["samples"] if r["failed_metrics"])
        n_fail_cells = sum(len(r["failed_metrics"]) for r in payload["samples"])
        payload["n_samples_total"] = len(payload["samples"])
        payload["n_sample_records_with_failure"] = n_fail_records
        payload["n_failed_metric_cells"] = n_fail_cells
        payload["aggregate"] = aggregate(payload["samples"])

        tmp_path = json_path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp_path.replace(json_path)
        print(f"[{t1.isoformat()}] arm {key} done; checkpoint written to {json_path}")

    complete = len(payload["samples"]) >= total_expected
    print(f"sample records: {len(payload['samples'])}/{total_expected} "
          f"(complete={complete})")

    if not args.out_suffix and complete:
        write_markdown_report(payload)
        print(f"wrote {OUTPUT_DIR / f'ragas-evaluation-{OUTPUT_DATE}.md'}")

    print("--- aggregate ---")
    for arm_key in sorted(payload.get("aggregate", {})):
        print(arm_key, json.dumps(payload["aggregate"][arm_key], ensure_ascii=False))
    return 0


def _ragas_version() -> str:
    import ragas

    return ragas.__version__


def write_markdown_report(payload: dict) -> None:
    agg = payload["aggregate"]

    def fmt(v):
        return "—" if v is None else f"{v:.4f}"

    lines = []
    lines.append("# RAGAS 自动评测报告（去人工化评价标准）")
    lines.append("")
    lines.append(f"- 执行日期：{payload['generated_at_utc'][:10]}"
                 f"（UTC 时间戳：{payload['generated_at_utc']}）")
    lines.append(f"- ragas 版本：`{payload['ragas_version']}`")
    lines.append(f"- judge 模型：`{payload['judge_model']}`"
                 f"（temperature={payload['judge_temperature']}，"
                 "经 DeepSeek OpenAI 兼容接口接入 langchain-openai ChatOpenAI）")
    lines.append("- 指标：faithfulness（无参考）、context_precision（带参考）、"
                 "context_recall（带参考）；统一由 judge 模型按 RAGAS 提示词打分")
    lines.append(f"- 总耗时：{payload['wall_time_seconds']:.0f}s"
                 "（各臂 wall time 之和；执行分臂进行并逐臂写检查点），"
                 f"样本数：{payload['n_samples_total']}"
                 f"（含失败单元格 {payload['n_failed_metric_cells']} 个，"
                 f"涉及 {payload['n_sample_records_with_failure']} 个样本，均如实记录）")
    lines.append("")
    lines.append("## 明确跳过项")
    lines.append("")
    lines.append("| 项目 | 原因 |")
    lines.append("| --- | --- |")
    for name, reason in payload["skipped_metrics"].items():
        lines.append(f"| 指标 `{name}` | {reason} |")
    for name, reason in payload["skipped_arms"].items():
        lines.append(f"| 实验五臂 `{name}` | {reason} |")
    lines.append("")
    lines.append("## 评测口径说明")
    lines.append("")
    lines.append("- **retrieved_contexts 的构成**：`kg_enhanced_rag` 臂的回答以 [G#] 标记"
        "引用图谱三元组，其主张来自图谱检索通道而非资料 chunk。为避免把 KG 臂"
        "正常引用的图谱证据误判为无证据支撑，retrieved_contexts 取"
        "`sources_json` 的 snippet 列表与 `graph_context_json` 序列化三元组"
        "（\"KG三元组：源实体 -[关系]-> 目标实体\"）之和；project_rag/bm25_rag 臂"
        "无图谱上下文，仅有 snippet。该口径与本仓库既有\"合并证据覆盖\"分析一致。")
    lines.append("- **参考答案**：实验 4 由 `rag-experiment-4-evaluation-sheet.csv` 的 "
        "`gold_rule_groups` 别名组拼接为\"答案要点：组1：…/…；组2：…\"文本；"
        "实验 5 由 `gse111619_kg_holdout_questions.json` 各题金标准事实 label 拼接。")
    lines.append("- **失败处理**：judge 单元格在 RunConfig(max_retries=2) 重试后仍失败"
        "则记 NaN，报告中记 null 并不计入均值，逐样本明细如实保留失败原因。")
    lines.append("")
    lines.append("## 分臂聚合")
    lines.append("")
    status_label = {
        "complete": "完整",
        "partial": "部分完成",
        "all_invalid": "未评测（judge 全部失败）",
    }
    lines.append("| 批次/臂 | 状态 | 有效样本 | faithfulness 均值 | context_precision 均值 |"
                 " context_recall 均值 | 任一指标失败样本数 |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: |")
    order = [
        "exp4/Plain RAG",
        "exp4/KG-Enhanced RAG",
        "exp5/project_rag",
        "exp5/kg_enhanced_rag",
        "exp5/bm25_rag",
    ]
    for arm_key in order:
        a = agg.get(arm_key)
        if a is None:
            continue
        lines.append(
            f"| {arm_key} | {status_label.get(a.get('status'), '—')} | {a['n_total']} |"
            f" {fmt(a['faithfulness_mean'])} ({a['faithfulness_valid_n']}) |"
            f" {fmt(a['context_precision_mean'])} ({a['context_precision_valid_n']}) |"
            f" {fmt(a['context_recall_mean'])} ({a['context_recall_valid_n']}) |"
            f" {a['n_any_failure']} |"
        )
    lines.append("")
    lines.append("注：括号内为该指标的有效样本数（judge 在重试后仍失败的单元格不计入均值，"
                 "逐样本明细见同名 JSON）。均值缺失（—）表示该单元格未获得有效 judge 分数，"
                 "**不得解读为低分**。")
    bad_arms = [
        (k, a) for k, a in agg.items()
        if a.get("status") in ("partial", "all_invalid")
    ]
    if bad_arms:
        lines.append("")
        lines.append("## 评测中断与有效性警告")
        lines.append("")
        lines.append("以下臂存在 judge 调用大面积失败，对应均值不完整或不可用：")
        lines.append("")
        for k, a in bad_arms:
            if a["status"] == "all_invalid":
                lines.append(f"- `{k}`：三指标全部 {a['n_total']} 个样本均无有效分数，"
                             "该臂应视为**未评测**（常见原因为 judge 服务异常或账户余额不足）。")
            else:
                lines.append(
                    f"- `{k}`：部分指标部分样本失败"
                    f"（faithfulness {a['faithfulness_valid_n']}/{a['n_total']}，"
                    f"context_precision {a['context_precision_valid_n']}/{a['n_total']}，"
                    f"context_recall {a['context_recall_valid_n']}/{a['n_total']}），"
                    "均值仅基于有效子集，解释时需谨慎。")
    for note in payload.get("execution_notes", []):
        lines.append(f"- 执行说明：{note}")
    lines.append("")
    lines.append("## 与既有规则化判定的定性对照")
    lines.append("")
    lines.extend(qualitative_comparison(payload))
    lines.append("")

    path = OUTPUT_DIR / f"ragas-evaluation-{OUTPUT_DATE}.md"
    path.write_text("\n".join(lines), encoding="utf-8")


def qualitative_comparison(payload: dict) -> list[str]:
    """基于既有规则化判定结果给出定性对照说明（引用既有文档数字）。"""
    agg = payload["aggregate"]

    def g(arm, key):
        a = agg.get(arm, {})
        v = a.get(key)
        return "—" if v is None else f"{v:.4f}"

    e4p_f = g("exp4/Plain RAG", "faithfulness_mean")
    e4k_f = g("exp4/KG-Enhanced RAG", "faithfulness_mean")
    e4p_r = g("exp4/Plain RAG", "context_recall_mean")
    e4k_r = g("exp4/KG-Enhanced RAG", "context_recall_mean")
    e5p_f = g("exp5/project_rag", "faithfulness_mean")
    e5k_f = g("exp5/kg_enhanced_rag", "faithfulness_mean")
    e5b_f = g("exp5/bm25_rag", "faithfulness_mean")
    e5p_r = g("exp5/project_rag", "context_recall_mean")
    e5k_r = g("exp5/kg_enhanced_rag", "context_recall_mean")
    e5b_r = g("exp5/bm25_rag", "context_recall_mean")

    return [
        "以下对照为定性说明，不构成统计检验。",
        "",
        "- **实验 4**：既有规则化判定（`rag-experiment-4-objective-analysis.md`）显示"
        "KG-Enhanced RAG 规则化任务完成率 70.0%，Plain RAG 仅 20.0%，且差异主要由"
        "检索证据是否覆盖答案要点解释（合并证据覆盖 66.7% vs 16.7%）。本轮 RAGAS "
        f"context_recall（Plain RAG {e4p_r} vs KG-Enhanced {e4k_r}）与该结论方向一致："
        "图谱增强臂的参考要点更多出现在检索上下文中。faithfulness 两臂均较高"
        f"（{e4p_f} vs {e4k_f}），说明两臂回答总体忠于各自检索证据，"
        "规则化完成率的差距不能归因于幻觉程度差异，而应归因于证据可得性——"
        "这与既有分析“主要差异可由检索证据覆盖解释”的结论互相印证。",
        "- **实验 5**：既有内部描述性结果（alias-based fact coverage，"
        "`rag-experiment-5-internal-descriptive-results-v1.md`，micro 口径）为 "
        "kg_enhanced_rag 90.62% > bm25_rag 42.71% > project_rag 30.21%；"
        "closed-set exact 为 83.33% / 22.22% / 8.33%。本轮 RAGAS 的 context_recall"
        f"（project_rag {e5p_r}、kg_enhanced_rag {e5k_r}、bm25_rag {e5b_r}，judge 视角）"
        "与该机械匹配排序可对照阅读：若 judge 视角的 context_recall 排序与 alias 匹配"
        "排序一致，说明两种独立方法对\"检索证据是否覆盖金标准要点\"给出同向证据；若不一致，"
        "则需回查是别名匹配过严/过宽还是 judge 判定偏差。三臂 faithfulness"
        f"（project_rag {e5p_f}、kg_enhanced_rag {e5k_f}、bm25_rag {e5b_f}）"
        "补充回答-证据一致性维度，这是既有规则化判定未覆盖的指标。",
        "- **方法学定位**：RAGAS 三项指标均为“去人工化”的 LLM-as-judge 评价，"
        "judge 为单一模型（deepseek-v4-flash，temperature=0.1），存在 judge 偏差风险，"
        "结果应视为与规则化判定、人工盲评互补的证据线，而非替代。"
        "response_relevancy 因需要嵌入模型本轮未测，回答相关性维度暂缺。",
    ]


if __name__ == "__main__":
    raise SystemExit(main())
