#!/usr/bin/env python3
"""Render a citable descriptive appendix from a checked RAG evidence package."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "rag-evidence-package-v1"
STATISTICS_SCHEMA_VERSION = "rag-evidence-statistics-v1"


def _load_checker() -> Any:
    path = ROOT / "scripts/check_rag_experiment_evidence.py"
    spec = importlib.util.spec_from_file_location("rag_evidence_checker_for_renderer", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load evidence checker: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = _load_checker()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object expected: {path}")
    return value


def repository_relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise ValueError(f"evidence material must be inside repository root: {path}") from error


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def input_fingerprints(package_path: Path, root: Path = ROOT) -> list[dict[str, str]]:
    """Return portable fingerprints for the package and its generation contract."""

    root = root.resolve()
    inputs = (
        ("evidence_package", package_path),
        ("evidence_checker", root / "scripts/check_rag_experiment_evidence.py"),
        ("paper_material_renderer", root / "scripts/render_rag_evidence_paper_material.py"),
        ("evidence_protocol", root / "docs/experiments/rag-evidence-package-protocol-v1.md"),
        ("paper_evidence_index", root / "docs/experiments/rag-paper-evidence-index-v1.md"),
    )
    fingerprints: list[dict[str, str]] = []
    for name, path in inputs:
        resolved = path.resolve()
        if not resolved.is_file():
            raise ValueError(f"required fingerprint input is missing: {path}")
        fingerprints.append(
            {
                "name": name,
                "path": repository_relative_path(resolved, root),
                "sha256": sha256_file(resolved),
            }
        )
    return fingerprints


def _count_lines(values: dict[str, int]) -> str:
    return ", ".join(f"`{key}`={value}" for key, value in values.items()) or "无"


def _metric_value(metric: dict[str, Any], key: str) -> str:
    value = metric.get(key)
    return "—" if value is None else str(value)


def _parameter_snapshot_lines(bindings: dict[str, Any]) -> str:
    snapshots = bindings.get("parameter_snapshots", [])
    if not snapshots:
        return "- 已落库案例参数快照：无（本包没有带 `query_log_id` 的案例）。"
    return "\n".join(
        "- 参数快照：`" + json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "`"
        for snapshot in snapshots
    )


def _markdown_cell(value: Any, empty: str = "—") -> str:
    if value is None or value == "":
        return empty
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def failure_case_rows(package: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every failed case in stable execution order for paper review."""

    cases = package.get("cases")
    if not isinstance(cases, list):
        return []
    rows = [
        {
            "execution_order": case.get("execution_order"),
            "question_index": case.get("question_index"),
            "mode": case.get("mode"),
            "repetition_index": case.get("repetition_index"),
            "query_log_id": case.get("query_log_id"),
            "failure_scope": case.get("failure_scope"),
            "failure_code": case.get("failure_code"),
            "source_count": case.get("source_count"),
            "graph_hit_count": case.get("graph_hit_count"),
            "error": case.get("error"),
        }
        for case in cases
        if isinstance(case, dict) and case.get("status") == "failed"
    ]
    return sorted(
        rows,
        key=lambda row: (
            row["execution_order"] if isinstance(row["execution_order"], int) else 2**63 - 1,
            str(row["mode"] or ""),
            row["question_index"] if isinstance(row["question_index"], int) else 2**63 - 1,
        ),
    )


def render(
    package: dict[str, Any],
    check_result: dict[str, Any],
    package_path: Path,
    root: Path = ROOT,
) -> str:
    if package.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported evidence package schema: {package.get('schema_version')!r}")
    if check_result.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("checker result schema does not match evidence package")
    if check_result.get("passed") is not True or check_result.get("failures"):
        raise ValueError("a passed checker result is required before rendering paper material")

    expected_statistics = CHECKER.derive_statistics(package)
    statistics = check_result.get("statistics")
    if statistics != expected_statistics:
        raise ValueError("statistics do not match checker-derived evidence-package statistics")
    if statistics.get("schema_version") != STATISTICS_SCHEMA_VERSION:
        raise ValueError("unsupported derived statistics schema")

    experiment = package.get("experiment")
    if not isinstance(experiment, dict):
        raise ValueError("evidence package experiment must be an object")
    package_reference = repository_relative_path(package_path, root)
    status_counts = statistics["status_counts"]
    failure_counts = statistics["failure_counts"]
    evidence = statistics["evidence"]
    citation = statistics["citation_audit"]
    bindings = statistics["runtime_bindings"]
    fingerprints = input_fingerprints(package_path, root)
    fingerprint_lines = "\n".join(
        f"| {item['name']} | `{item['path']}` | `{item['sha256']}` |" for item in fingerprints
    )
    failure_rows = failure_case_rows(package)
    failure_lines = "\n".join(
        "| {order} | {question} | `{mode}` | {repetition} | {query_log_id} | `{scope}` | "
        "`{code}` | S={sources}/G={graph} | {error} |".format(
            order=_markdown_cell(row["execution_order"]),
            question=_markdown_cell(row["question_index"]),
            mode=_markdown_cell(row["mode"]),
            repetition=_markdown_cell(row["repetition_index"]),
            query_log_id=_markdown_cell(row["query_log_id"]),
            scope=_markdown_cell(row["failure_scope"]),
            code=_markdown_cell(row["failure_code"]),
            sources=_markdown_cell(row["source_count"]),
            graph=_markdown_cell(row["graph_hit_count"]),
            error=_markdown_cell(row["error"]),
        )
        for row in failure_rows
    ) or "| — | — | — | — | — | — | — | — | 无失败案例 |"

    mode_lines: list[str] = []
    for mode, summary in statistics["modes"].items():
        latency = summary["latency_ms"]
        mode_lines.append(
            f"| `{mode}` | {summary['total_cases']} | {summary['completed_cases']} | "
            f"{summary['failed_cases']} | {_metric_value(latency, 'median')} | "
            f"{_metric_value(latency, 'p95')} | {_metric_value(latency, 'max')} |"
        )

    return f"""# RAG 证据包描述性统计材料 v1

## 使用边界

状态：**已通过 `rag-evidence-package-v1` 归档检查**；`paper_ready=false`。本材料只从逐案例证据、答案文本和遥测派生描述性统计，供论文方法、复现附录和失败案例部分引用；它不证明人工准确率、引用正确性、显著性检验或方法优越性，不把自动引用标记当作引用正确性，也不把完成率当作回答准确率。

证据包：`{package_reference}`；统计 schema：`{STATISTICS_SCHEMA_VERSION}`。检查器必须先通过，且本渲染器会再次从同一 `cases[]` 重算统计并拒绝漂移。

## 输入材料指纹

下列文件共同定义本附录的证据版本。SHA-256 只用于绑定引用的具体字节，不代表外部冻结、人工金标准或代码 revision；生成前应由 `scripts/check_paper_material_freshness.py` 重新核对。

| 材料 | 路径 | SHA-256 |
| --- | --- | --- |
{fingerprint_lines}

## 实验绑定

- 实验 ID：`{experiment.get('id')}`；归档状态：`{experiment.get('status')}`。
- 题目数：`{len(experiment.get('questions', []))}`；方法：`{', '.join(experiment.get('modes', []))}`；重复次数：`{experiment.get('repetitions')}`。
- 随机化：`{experiment.get('randomize_order')}`；随机种子：`{experiment.get('random_seed')}`；执行计划哈希：`{experiment.get('execution_plan_hash')}`。
- 嵌入模型：`{experiment.get('embedding_model')}`；生成模型：`{experiment.get('generation_model')}`；索引版本：`{experiment.get('rag_index_version')}`。
- 题集哈希：`{experiment.get('questions_sha256')}`；语料快照哈希：`{experiment.get('corpus_snapshot_hash')}`。
- 逐案例嵌入模型：`{', '.join(bindings['embedding_models']) or '无'}`；逐案例索引版本：`{', '.join(bindings['index_versions']) or '无'}`；检索策略：`{', '.join(bindings['retrieval_strategies']) or '无'}`。
{_parameter_snapshot_lines(bindings)}

## 分母与证据容器

- 观察到的案例数：`{statistics['observed_case_count']}`；状态分层：{_count_lines(status_counts)}。
- 失败代码分层：{_count_lines(failure_counts)}。
- 来源证据对象：`{evidence['source_items']}`；图谱证据对象：`{evidence['graph_items']}`。
- 含来源证据案例：`{evidence['source_evidence_cases']}`；含图谱证据案例：`{evidence['graph_evidence_cases']}`。

## 失败案例逐项清单

以下清单按 `execution_order` 保留所有 `status=failed` 案例，不因没有 `query_log_id` 而删除；`S/G` 是导出证据数组的对象数量，只用于复核证据容器，不代表相关性或正确性。

| 执行序号 | 题目序号 | 方法 | 重复 | query_log_id | failure_scope | failure_code | 来源/图谱证据 | 原始错误 |
| ---: | ---: | --- | ---: | ---: | --- | --- | --- | --- |
{failure_lines}

## 按方法的描述性时延

时延只对 `completed` 案例按方法汇总，单位为毫秒；空值表示该层没有已完成案例，不应解释为零时延。

| 方法 | 案例数 | 完成 | 失败 | 中位数 ms | P95 ms | 最大值 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(mode_lines)}

## 引用审计重算

- 带答案且证据容器可解析的审计案例：`{citation['audited_cases']}`。
- 独立重算通过：`{citation['passed_cases']}`；未通过：`{citation['failed_cases']}`。
- 引用标记总数：`{citation['citation_count']}`；非法标记总数：`{citation['invalid_marker_count']}`。

以上计数不读取归档对象中可手工修改的 `citation_audit.citation_count` 或 `passed`；检查器从答案文本和证据数组重算。它只能证明归档内部一致性、标记语法和证据数组边界，不能证明来源支持命题、答案事实正确或人工评价有效。

## 可复现入口

在同一仓库根目录执行检查器并将结果传给本渲染器；任一输入漂移均应失败关闭：

```text
backend/.venv/bin/python scripts/check_rag_experiment_evidence.py --package {package_reference} --output check.json
backend/.venv/bin/python scripts/render_rag_evidence_paper_material.py --package {package_reference} --check-result check.json --output rag-evidence-paper-material.md
```

正式效果结论仍需外部冻结题集、金标准、独立双人盲评、应用 revision 和确认性运行包。本材料不替代这些证据，也不把描述性分层升级为统计显著性检验。
"""


def run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--check-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    root = args.root.resolve()
    package_path = args.package.resolve()
    check_path = args.check_result.resolve()
    output_path = args.output.resolve()
    package = load_json(package_path)
    check_result = load_json(check_path)
    material = render(package, check_result, package_path, root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(material, encoding="utf-8")
    print(json.dumps({"passed": True, "output": repository_relative_path(output_path, root)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(run_cli())
