#!/usr/bin/env python3
"""Run a small real-model regression without storing prompts or answers."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.deepseek import DeepSeekClient  # noqa: E402


CASES = (
    {
        "name": "exact_instruction",
        "system": "Follow the user's output instruction exactly.",
        "user": "Reply with exactly MODEL_OK and no other text.",
        "required": ("MODEL_OK",),
    },
    {
        "name": "no_evidence_refusal",
        "system": "只能依据给定证据回答；证据为空或不足时必须明确写出“无法确认”。",
        "user": "证据：（空）\n问题：样本 A 使用了什么试剂？",
        "required": ("无法确认",),
    },
    {
        "name": "single_source_citation",
        "system": "只能依据证据回答，事实后必须原样标注证据编号，不得编造编号。",
        "user": "证据：[S1] 样本 A 使用 PBS 洗涤。\n问题：样本 A 使用了什么试剂？",
        "required": ("PBS", "[S1]"),
    },
)


def evaluate_answer(case: dict, answer: str, result: dict, elapsed_ms: int) -> dict:
    required = list(case["required"])
    return {
        "name": case["name"],
        "passed": all(marker in answer for marker in required),
        "required_markers": required,
        "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
        "answer_chars": len(answer),
        "model": result.get("model"),
        "request_id_present": bool(result.get("request_id")),
        "usage": result.get("usage") or {},
        "elapsed_ms": elapsed_ms,
    }


async def run() -> dict:
    client = DeepSeekClient()
    reports = []
    for case in CASES:
        started = perf_counter()
        result = await client.generate(
            system_prompt=case["system"],
            user_prompt=case["user"],
            temperature=0,
            max_tokens=120,
        )
        reports.append(evaluate_answer(case, result["answer"], result, round((perf_counter() - started) * 1000)))
    return {"passed": all(item["passed"] for item in reports), "cases": reports}


def main() -> int:
    report = asyncio.run(run())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
