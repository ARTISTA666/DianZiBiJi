# -*- coding: utf-8 -*-
"""论文 md 零损失审计:两个版本间守卫 token 类必须全等(T-049 口径工具化)。

守卫七类(任一不等即 exit 1):
- number     数字 token(其他类已认领的区域不再重复计)
- citation   引文标记 [13-15]/[118](纯数字区间/列表方括号)
- formula    $...$ / $$...$$ 公式体(去首尾空白)
- table_row  表行整行(| 开头)
- tikz       含 \begin{tikzpicture} 的 fence 整块行
- fence      其余 fence 整块行
- backtick   行内反引号代码 span

信息统计(不做守卫):全稿中文正文 ；：、 计数,供标点改写轮参考。

用法:
    python scripts/audit/thesis_zero_loss_audit.py --baseline OLD.md --current NEW.md [--json OUT]

退出码:0=守卫类全等;1=存在差异;2=用法/读文件错误。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

FENCE_RE = re.compile(r"^```(\w*)\s*$")
CITATION_RE = re.compile(r"\[(\d+(?:\s*[-–,，]\s*\d+)*)\]")
DISPLAY_MATH_RE = re.compile(r"\$\$(.+?)\$\$", re.S)
INLINE_MATH_RE = re.compile(r"(?<!\\)\$([^$\n]+?)\$(?!\$)")
BACKTICK_RE = re.compile(r"`([^`\n]+)`")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
PUNCT_CHARS = "；：、"

GUARD_CLASSES = ("number", "citation", "formula", "table_row", "tikz", "fence", "backtick")


def split_fences(text: str) -> list[tuple[str, str]]:
    """把 md 切成 ("fence", 块内容) / ("text", 段内容) 序列,fence 外零改动。"""
    parts: list[tuple[str, str]] = []
    cur: list[str] = []
    in_fence = False
    fence_lang = ""
    fence_body: list[str] = []
    for ln in text.split("\n"):
        m = FENCE_RE.match(ln.strip())
        if not in_fence and m:
            parts.append(("text", "\n".join(cur)))
            cur = []
            in_fence = True
            fence_lang = m.group(1)
            fence_body = []
        elif in_fence and ln.strip().startswith("```"):
            parts.append(("fence", fence_lang + "\n" + "\n".join(fence_body)))
            in_fence = False
        elif in_fence:
            fence_body.append(ln)
        else:
            cur.append(ln)
    if in_fence:
        parts.append(("fence", fence_lang + "\n" + "\n".join(fence_body)))
    parts.append(("text", "\n".join(cur)))
    return parts


def extract_classes(text: str) -> dict[str, Counter]:
    """按守卫类提取 token 多重集。fence 优先于正文,表行优先于行内提取。"""
    classes: dict[str, Counter] = {name: Counter() for name in GUARD_CLASSES}
    classes["_punct"] = Counter()
    for kind, body in split_fences(text):
        if kind == "fence":
            cls = "tikz" if r"\begin{tikzpicture}" in body else "fence"
            lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
            classes[cls].update(lines)
            continue
        punct_counter: Counter = Counter()
        for ln in body.split("\n"):
            if ln.lstrip().startswith("|"):
                row = ln.strip()
                if row:
                    classes["table_row"].update([row])
                continue
            punct_counter.update(ch for ch in ln if ch in PUNCT_CHARS)
            rest = ln
            rest = BACKTICK_RE.sub(lambda m: _emit(classes, "backtick", m.group(1)), rest)
            rest = DISPLAY_MATH_RE.sub(lambda m: _emit(classes, "formula", m.group(1)), rest)
            rest = INLINE_MATH_RE.sub(lambda m: _emit(classes, "formula", m.group(1)), rest)
            rest = CITATION_RE.sub(lambda m: _emit(classes, "citation", m.group(1)), rest)
            classes["number"].update(NUMBER_RE.findall(rest))
        classes.setdefault("_punct", Counter()).update(punct_counter)
    return classes


def _emit(classes: dict[str, Counter], cls: str, token: str) -> str:
    classes[cls].update([token.strip()])
    return ""


def diff_counter(base: Counter, cur: Counter) -> tuple[Counter, Counter]:
    return base - cur, cur - base


def audit(baseline_text: str, current_text: str) -> dict:
    base = extract_classes(baseline_text)
    cur = extract_classes(current_text)
    classes_report = {}
    all_equal = True
    for cls in GUARD_CLASSES:
        missing, added = diff_counter(base[cls], cur[cls])
        equal = not missing and not added
        all_equal = all_equal and equal
        classes_report[cls] = {
            "baseline": sum(base[cls].values()),
            "current": sum(cur[cls].values()),
            "equal": equal,
            "missing": dict(missing),
            "added": dict(added),
        }
    punct = {
        ch: {"baseline": base["_punct"].get(ch, 0), "current": cur["_punct"].get(ch, 0)}
        for ch in PUNCT_CHARS
    }
    return {"pass": all_equal, "classes": classes_report, "punctuation_info": punct}


def format_report(report: dict, max_examples: int = 20) -> str:
    lines = []
    for cls, data in report["classes"].items():
        mark = "OK  " if data["equal"] else "DIFF"
        lines.append(f"[{mark}] {cls:<10} baseline={data['baseline']:<6} current={data['current']:<6}")
        for label, items in (("missing", data["missing"]), ("added", data["added"])):
            for i, (token, cnt) in enumerate(items.items()):
                if i >= max_examples:
                    lines.append(f"       {label}: …(其余 {len(items) - max_examples} 项略)")
                    break
                lines.append(f"       {label}: {token!r} x{cnt}")
    lines.append("标点统计(信息,非守卫):")
    for ch, d in report["punctuation_info"].items():
        lines.append(f"  {ch}  {d['baseline']} -> {d['current']}")
    lines.append("VERDICT: " + ("PASS 守卫类全等" if report["pass"] else "FAIL 守卫类存在差异,禁止提交"))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="论文 md 零损失审计(守卫类 token 全等校验)")
    ap.add_argument("--baseline", required=True, help="基线 md(改动前快照)")
    ap.add_argument("--current", required=True, help="当前 md(改动后)")
    ap.add_argument("--json", dest="json_out", help="可选,结果 JSON 输出路径")
    ap.add_argument("--max-examples", type=int, default=20)
    args = ap.parse_args(argv)

    try:
        baseline_text = Path(args.baseline).read_text(encoding="utf-8")
        current_text = Path(args.current).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"读文件失败: {exc}", file=sys.stderr)
        return 2
    if baseline_text == current_text:
        print("两文件内容完全相同,无需审计。VERDICT: PASS")
        return 0

    report = audit(baseline_text, current_text)
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(format_report(report, args.max_examples))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
