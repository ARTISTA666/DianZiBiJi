"""Collect runtime and experiment evidence into one hash-tracked report."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "docs" / "system-evidence"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source(path: Path) -> dict:
    resolved = path.resolve()
    try:
        display_path = resolved.relative_to(ROOT)
    except ValueError:
        display_path = resolved
    return {
        "path": str(display_path),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
    }


def env_value(key: str, fallback: str) -> str:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return fallback
    for line in env_path.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() == key:
            return value.strip() or fallback
    return fallback


def run_command(command: list[str]) -> dict:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": command,
        "exit_code": completed.returncode,
        "passed": completed.returncode == 0,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def runtime_probe_commands(postgres_user: str, postgres_db: str) -> list[list[str]]:
    schema_check = (
        "DO $$ BEGIN "
        "IF COALESCE((SELECT max(version) FROM public.rust_schema_versions), 0) < 2 "
        "THEN RAISE EXCEPTION 'Rust schema version is missing'; "
        "END IF; END $$;"
    )
    return [
        ["docker", "compose", "config", "--quiet"],
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "db",
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            postgres_user,
            "-d",
            postgres_db,
            "-tAc",
            schema_check,
        ],
        ["docker", "compose", "exec", "-T", "backend", "tesseract", "--list-langs"],
    ]


def check_url(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            body = response.read(1000).decode("utf-8", errors="replace")
            return {"url": url, "status": response.status, "passed": response.status == 200, "body": body}
    except Exception as exc:
        return {"url": url, "status": None, "passed": False, "error": str(exc)}


def read_json_url(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return {"url": url, "status": response.status, "ok": response.status == 200, "payload": payload}
    except Exception as exc:
        return {"url": url, "status": None, "ok": False, "error": str(exc)}


def metrics_url_from_backend(backend_url: str) -> str:
    return urljoin(backend_url.rstrip("/") + "/", "../metrics")


def capture_runtime(backend_url: str | None = None, frontend_url: str | None = None, metrics_url: str | None = None) -> dict:
    commands = [
        run_command(command)
        for command in runtime_probe_commands(
            env_value("POSTGRES_USER", "eln_user"),
            env_value("POSTGRES_DB", "eln"),
        )
    ]
    backend_port = env_value("BACKEND_PORT", "8000")
    frontend_port = env_value("FRONTEND_PORT", "3000")
    urls = [
        check_url(backend_url or f"http://127.0.0.1:{backend_port}/health"),
        check_url(frontend_url or f"http://127.0.0.1:{frontend_port}"),
    ]
    metrics_url = metrics_url or metrics_url_from_backend(backend_url or f"http://127.0.0.1:{backend_port}/health")
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "commands": commands,
        "urls": urls,
        "metrics": read_json_url(metrics_url),
        "ok": all(item["passed"] for item in commands + urls),
    }


def report_exit_code(report: dict) -> int:
    return 0 if bool((report.get("runtime") or {}).get("ok")) else 1


def playwright_results(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    tests = []
    for suite in payload.get("suites", []):
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                for result in test.get("results", []):
                    tests.append(
                        {
                            "title": spec["title"],
                            "status": result["status"],
                            "duration_ms": result["duration"],
                        }
                    )
    stats = payload.get("stats", {})
    return {
        "captured_at": stats.get("startTime") or datetime.now(timezone.utc).isoformat(),
        "source": source(path),
        "stats": stats,
        "tests": tests,
    }


def graph_results(path: Path) -> dict:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    verdicts = Counter(row.get("gold_verdict", "") for row in rows)
    tp, fp, fn = verdicts["TP"], verdicts["FP"], verdicts["FN"]
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "source": source(path),
        "relation_count": len(rows),
        "verdicts": dict(sorted(verdicts.items())),
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "author_signoff_count": sum(bool(row.get("author_signoff", "").strip()) for row in rows),
    }


def retrieval_results(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "source": source(path),
        "project": payload["project"],
        "question_count": payload["question_count"],
        "fact_count": payload["fact_count"],
        "corpus": payload["corpus"],
        "aggregate": payload["aggregate"],
        "ablation": payload["ablation"],
        "result_sha256": payload["result_sha256"],
        "reproducibility_verified": payload["reproducibility_verified"],
    }


def load_smoke_results(path: Path | None) -> dict:
    if path is None:
        return {"ok": False, "error": "load smoke report was not provided"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {"ok": not payload.get("errors") and payload.get("successful", 0) > 0, "source": source(path), **payload}


def restart_recovery_results(path: Path | None) -> dict:
    if path is None:
        return {"ok": False, "error": "restart recovery report was not provided"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "ok": (
            payload.get("interrupted") is True
            and payload.get("resumed_status") == "completed"
            and isinstance(payload.get("run_id"), int)
            and payload["run_id"] > 0
        ),
        "source": source(path),
        **payload,
    }


def soak_smoke_results(path: Path | None) -> dict:
    if path is None:
        return {"ok": False, "error": "soak smoke report was not provided"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    summary = payload.get("summary") or {}
    return {"ok": bool(summary.get("ok")), "source": source(path), **payload}


def npm_audit_results(path: Path | None) -> dict:
    if path is None:
        return {"ok": False, "error": "npm audit report was not provided"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    vulnerabilities = (payload.get("metadata") or {}).get("vulnerabilities") or {}
    return {
        "ok": vulnerabilities.get("total", 0) == 0,
        "source": source(path),
        "vulnerabilities": vulnerabilities,
    }


def production_config_results(path: Path | None) -> dict:
    if path is None:
        return {"ok": False, "error": "production config report was not provided"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {"source": source(path), **payload}


def secret_hygiene_results(path: Path | None) -> dict:
    if path is None:
        return {"ok": False, "error": "secret hygiene report was not provided"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {"source": source(path), **payload}


def secret_rotation_results(path: Path | None) -> dict:
    if path is None:
        return {"ok": False, "error": "secret rotation report was not provided"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {"source": source(path), **payload}


def backup_policy_results(path: Path | None) -> dict:
    if path is None:
        return {"ok": False, "error": "backup policy report was not provided"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {"source": source(path), **payload}


def backup_results(path: Path | None, *, verify_dump: bool = False) -> dict:
    if path is None:
        return {"ok": False, "error": "backup directory was not provided"}
    manifest_path = path / "manifest.txt"
    if not manifest_path.is_file():
        return {"ok": False, "path": str(path), "error": "manifest.txt is missing"}
    manifest = {}
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            manifest[key] = value
    checks = {}
    for filename, key in (("database.dump", "database_sha256"), ("storage.tar.gz", "storage_sha256")):
        artifact = path / filename
        checks[filename] = artifact.is_file() and sha256(artifact) == manifest.get(key)
    dump_readable = None
    dump_error = None
    if verify_dump and checks.get("database.dump"):
        completed = subprocess.run(
            ["docker", "compose", "exec", "-T", "db", "pg_restore", "--list"],
            cwd=ROOT,
            input=(path / "database.dump").read_bytes(),
            capture_output=True,
            check=False,
        )
        dump_readable = completed.returncode == 0
        dump_error = completed.stderr.decode("utf-8", errors="replace").strip()
    return {
        "ok": manifest.get("manifest_version") == "1" and all(checks.values()) and dump_readable is not False,
        "source": source(manifest_path),
        "path": str(path),
        "manifest": manifest,
        "checks": checks,
        "dump_readable": dump_readable,
        "dump_error": dump_error,
    }


def restore_drill_results(path: Path | None) -> dict:
    if path is None:
        return {"ok": False, "error": "restore drill report was not provided"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {"source": source(path), **payload}


def monitoring_alerts_results(path: Path | None) -> dict:
    if path is None:
        return {"ok": False, "error": "monitoring alerts report was not provided"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {"source": source(path), **payload}


def reverse_proxy_results(path: Path | None) -> dict:
    if path is None:
        return {"ok": False, "error": "reverse proxy report was not provided"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {"source": source(path), **payload}


def ocr_results(root: Path = ROOT) -> list[dict]:
    results = []
    sources = (
        (
            "smithsonian_joseph_henry",
            "development",
            root / "data" / "real" / "smithsonian_joseph_henry" / "runs",
        ),
        (
            "rukopys_university",
            "development",
            root / "data" / "real" / "rukopys_university" / "development_variants",
        ),
        (
            "rukopys_university",
            "development",
            root / "data" / "real" / "rukopys_university" / "runs",
        ),
        (
            "rukopys_university",
            "holdout",
            root / "data" / "real" / "rukopys_university" / "holdout",
        ),
        (
            "rukopys_university",
            "holdout",
            root / "data" / "real" / "rukopys_university" / "holdout" / "runs",
        ),
    )
    for dataset, split, directory in sources:
        for evaluation_path in sorted(directory.glob("*/evaluation*.json")):
            evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
            run_path = evaluation_path.parent / "run.json"
            run = json.loads(run_path.read_text(encoding="utf-8")) if run_path.is_file() else {}
            results.append(
                {
                    "dataset": dataset,
                    "split": split,
                    "name": evaluation_path.parent.name,
                    "source": source(evaluation_path),
                    "run_source": source(run_path) if run_path.is_file() else None,
                    "sample_count": evaluation["sample_count"],
                    "summary": evaluation["summary"]["raw"],
                    "engine": run.get("engine"),
                    "layout": run.get("layout"),
                    "models": run.get("models"),
                    "manifest_sha256": run.get("manifest_sha256"),
                }
            )
    return results


def markdown(report: dict) -> str:
    lines = [
        "# 系统验证证据汇总",
        "",
        f"生成时间：{report['generated_at']}",
        "",
            "## 运行与迁移",
        "",
            f"- 当前环境检查：{'通过' if report['runtime']['ok'] else '未通过'}",
            f"- 系统：{report['runtime']['platform']['system']} {report['runtime']['platform']['machine']}",
            f"- 并发读 smoke：{'通过' if report['load_smoke']['ok'] else '未通过'} "
            f"({report['load_smoke'].get('successful', 0)}/{report['load_smoke'].get('requests', 0)} requests, "
            f"p95={report['load_smoke'].get('p95_ms', 0)}ms)",
            f"- 实验强杀恢复：{'通过' if report.get('restart_recovery', {}).get('ok') else '未通过'}",
            f"- 短 soak smoke：{'通过' if report['soak_smoke']['ok'] else '未通过'} "
            f"({report['soak_smoke'].get('summary', {}).get('cycles', 0)} cycles, "
            f"p95={report['soak_smoke'].get('summary', {}).get('p95_ms', 0)}ms)",
            f"- 前端生产依赖审计：{'通过' if report['npm_audit']['ok'] else '未通过'} "
            f"(vulnerabilities={report['npm_audit'].get('vulnerabilities', {}).get('total', 0)})",
            f"- 生产配置预检：{report['production_config'].get('status', 'missing')}",
            f"- 密钥泄漏预检：{'通过' if report['secret_hygiene']['ok'] else '未通过'}",
            f"- 密钥轮换手册：{'通过' if report.get('secret_rotation', {}).get('ok') else '未通过'}",
            f"- 灾备策略手册：{'通过' if report.get('backup_policy', {}).get('ok') else '未通过'}",
            f"- 运行指标端点：{'通过' if report['runtime'].get('metrics', {}).get('ok') else '未通过'} "
            f"(requests={report['runtime'].get('metrics', {}).get('payload', {}).get('total_requests', 0)}, "
            f"p95={report['runtime'].get('metrics', {}).get('payload', {}).get('p95_duration_ms', 0)}ms)",
            f"- 监控告警探针：{'通过' if report.get('monitoring_alerts', {}).get('ok') else '未通过'}",
            f"- 反向代理/TLS 模板：{'通过' if report.get('reverse_proxy', {}).get('ok') else '未通过'}",
        "",
        "## 浏览器端到端测试",
        "",
        "| 流程 | 状态 | 耗时(ms) |",
        "| --- | --- | ---: |",
    ]
    for item in report["playwright"]["tests"]:
        lines.append(f"| {item['title']} | {item['status']} | {item['duration_ms']} |")
    lines.extend(
        [
            "",
            "> 问答使用本地固定 LLM 桩，只验证调用和业务闭环，不代表生成模型准确率。",
            "",
            "## 自动检索评价",
            "",
            "| 模式 | Recall@10 | MRR | nDCG@10 |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for item in report["retrieval"]["aggregate"]:
        lines.append(
            f"| {item['mode']} | {item['Recall@10']:.4f} | {item['MRR']:.4f} | {item['nDCG@10']:.4f} |"
        )
    lines.extend(
        [
            "",
            "> 题目和事实金标准由项目开发方整理，只能作为内部检索诊断，不能替代独立测试集。",
            "",
            "## 知识图谱抽取核验",
            "",
            f"- 关系数：{report['knowledge_graph']['relation_count']}",
            f"- TP/FP/FN：{report['knowledge_graph']['verdicts'].get('TP', 0)}/"
            f"{report['knowledge_graph']['verdicts'].get('FP', 0)}/"
            f"{report['knowledge_graph']['verdicts'].get('FN', 0)}",
            f"- F1：{report['knowledge_graph']['f1']:.4f}",
            f"- 人工签核数：{report['knowledge_graph']['author_signoff_count']}",
            "",
            "> 该核验只覆盖四条固定演示笔记，不能外推到真实跨领域笔记。",
            "",
            "## OCR 评价",
            "",
            "| 数据集 | 分组 | 运行 | 样本数 | CER | 去空白 CER | 数字 F1 |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in report["ocr"]:
        summary = item["summary"]
        lines.append(
            f"| {item['dataset']} | {item['split']} | {item['name']} | {item['sample_count']} | "
            f"{summary['micro_character_error_rate']:.4f} | "
            f"{summary['micro_compact_character_error_rate']:.4f} | "
            f"{summary['numeric_tokens']['f1']:.4f} |"
        )
    lines.extend(
        [
            "",
            "> development 结果用于选模型；只有 split 为 holdout 的固定留出集结果可作为最终测试。",
            "",
            "## 备份 smoke",
            "",
            f"- 备份包校验：{'通过' if report['backup']['ok'] else '未通过'}",
            f"- 数据库 dump 可读：{report['backup'].get('dump_readable')}",
            f"- 隔离恢复演练：{'通过' if report.get('restore_drill', {}).get('ok') else '未通过'}",
            f"- 路径：`{report['backup'].get('path', '')}`",
            "",
            "## 完整性",
            "",
            "JSON 文件保存每个来源文件的 SHA-256，可据此检查报告是否对应当前原始结果。",
            "",
        ]
    )
    return "\n".join(lines)


def export(
    output_dir: Path,
    *,
    playwright_path: Path | None = None,
    retrieval_path: Path | None = None,
    backend_url: str | None = None,
    frontend_url: str | None = None,
    metrics_url: str | None = None,
    backup_dir: Path | None = None,
    load_smoke_path: Path | None = None,
    restart_recovery_path: Path | None = None,
    soak_smoke_path: Path | None = None,
    npm_audit_path: Path | None = None,
    production_config_path: Path | None = None,
    secret_hygiene_path: Path | None = None,
    secret_rotation_path: Path | None = None,
    backup_policy_path: Path | None = None,
    restore_drill_path: Path | None = None,
    monitoring_alerts_path: Path | None = None,
    reverse_proxy_path: Path | None = None,
    verify_backup_dump: bool = False,
) -> dict:
    playwright_path = playwright_path or ROOT / "output" / "playwright" / "results.json"
    graph_path = ROOT / "docs" / "experiments" / "kg-relation-gold-audit-after-fix.csv"
    retrieval_path = retrieval_path or ROOT / "data" / "real" / "GSE111619" / "main-retrieval-evaluation" / "report.json"
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime": capture_runtime(backend_url=backend_url, frontend_url=frontend_url, metrics_url=metrics_url),
        "load_smoke": load_smoke_results(load_smoke_path),
        "restart_recovery": restart_recovery_results(restart_recovery_path),
        "soak_smoke": soak_smoke_results(soak_smoke_path),
        "npm_audit": npm_audit_results(npm_audit_path),
        "production_config": production_config_results(production_config_path),
        "secret_hygiene": secret_hygiene_results(secret_hygiene_path),
        "secret_rotation": secret_rotation_results(secret_rotation_path),
        "backup_policy": backup_policy_results(backup_policy_path),
        "monitoring_alerts": monitoring_alerts_results(monitoring_alerts_path),
        "reverse_proxy": reverse_proxy_results(reverse_proxy_path),
        "playwright": playwright_results(playwright_path),
        "knowledge_graph": graph_results(graph_path),
        "retrieval": retrieval_results(retrieval_path),
        "backup": backup_results(backup_dir, verify_dump=verify_backup_dump),
        "restore_drill": restore_drill_results(restore_drill_path),
        "ocr": ocr_results(),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "validation-results.json"
    markdown_path = output_dir / "validation-results.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(markdown(report), encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--playwright-results", type=Path, default=ROOT / "output" / "playwright" / "results.json")
    parser.add_argument("--retrieval-report", type=Path, default=ROOT / "data" / "real" / "GSE111619" / "main-retrieval-evaluation" / "report.json")
    parser.add_argument("--backend-url", default=None)
    parser.add_argument("--frontend-url", default=None)
    parser.add_argument("--metrics-url", default=None)
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--load-smoke-report", type=Path, default=None)
    parser.add_argument("--restart-recovery-report", type=Path, default=None)
    parser.add_argument("--soak-smoke-report", type=Path, default=None)
    parser.add_argument("--npm-audit-report", type=Path, default=None)
    parser.add_argument("--production-config-report", type=Path, default=None)
    parser.add_argument("--secret-hygiene-report", type=Path, default=None)
    parser.add_argument("--secret-rotation-report", type=Path, default=None)
    parser.add_argument("--backup-policy-report", type=Path, default=None)
    parser.add_argument("--restore-drill-report", type=Path, default=None)
    parser.add_argument("--monitoring-alerts-report", type=Path, default=None)
    parser.add_argument("--reverse-proxy-report", type=Path, default=None)
    parser.add_argument("--verify-backup-dump", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    result = export(
        args.output_dir,
        playwright_path=args.playwright_results,
        retrieval_path=args.retrieval_report,
        backend_url=args.backend_url,
        frontend_url=args.frontend_url,
        metrics_url=args.metrics_url,
        backup_dir=args.backup_dir,
        load_smoke_path=args.load_smoke_report,
        restart_recovery_path=args.restart_recovery_report,
        soak_smoke_path=args.soak_smoke_report,
        npm_audit_path=args.npm_audit_report,
        production_config_path=args.production_config_report,
        secret_hygiene_path=args.secret_hygiene_report,
        secret_rotation_path=args.secret_rotation_report,
        backup_policy_path=args.backup_policy_report,
        restore_drill_path=args.restore_drill_report,
        monitoring_alerts_path=args.monitoring_alerts_report,
        reverse_proxy_path=args.reverse_proxy_report,
        verify_backup_dump=args.verify_backup_dump,
    )
    print(json.dumps({"runtime_ok": result["runtime"]["ok"], "ocr_runs": len(result["ocr"])}, ensure_ascii=False))
    raise SystemExit(report_exit_code(result))
