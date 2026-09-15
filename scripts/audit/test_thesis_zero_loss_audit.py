from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "audit" / "thesis_zero_loss_audit.py"
SPEC = importlib.util.spec_from_file_location("thesis_zero_loss_audit", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


BASE_MD = """# 面向科研实验记录的系统

审核门禁把 D1 的三项相符从 15 个蓝图计划知识点提升到 4/20、14/20[13-15],置信度 0.7。

| 编号 | 金标准判定 | 置信度 |
| --- | --- | --- |
| K-01 | 相符 | 1.0 |

运行参数 `bm25_k1=2.2`,公式 $F1=100\\%$,复现批次见[118]。

```latex
\\begin{tikzpicture}
\\node[a] (x) at (0,0) {KD=8.3nM};
\\end{tikzpicture}
```

```text
plain fence line
```
"""


def test_identical_pass():
    report = MODULE.audit(BASE_MD, BASE_MD)
    assert report["pass"] is True


def test_prose_rewrite_keeps_numbers_pass():
    rewritten = BASE_MD.replace("审核门禁把 D1 的三项相符从", "审核门禁使 D1 的三项相符自")
    report = MODULE.audit(BASE_MD, rewritten)
    assert report["pass"] is True


def test_missing_number_flagged():
    current = BASE_MD.replace("4/20、14/20", "4/20")
    report = MODULE.audit(BASE_MD, current)
    assert report["pass"] is False
    assert report["classes"]["number"]["missing"] == {"14": 1, "20": 1}


def test_added_number_flagged():
    current = BASE_MD.replace("置信度 0.7。", "置信度 0.75。")
    report = MODULE.audit(BASE_MD, current)
    assert report["classes"]["number"]["added"] == {"0.75": 1}


def test_citation_change_flagged():
    current = BASE_MD.replace("[13-15]", "[13]")
    report = MODULE.audit(BASE_MD, current)
    assert report["pass"] is False
    assert report["classes"]["citation"]["missing"] == {"13-15": 1}
    assert report["classes"]["citation"]["added"] == {"13": 1}
    # 引文里的数字不应再泄漏进 number 类
    assert "13" not in report["classes"]["number"]["missing"]


def test_markdown_link_not_citation():
    text = "见 [项目主页](https://example.com) 与 [118]。"
    classes = MODULE.extract_classes(text)
    assert classes["citation"] == {"118": 1}


def test_table_row_change_flagged():
    current = BASE_MD.replace("| K-01 | 相符 | 1.0 |", "| K-01 | 相符 | 0.9 |")
    report = MODULE.audit(BASE_MD, current)
    assert report["pass"] is False
    assert report["classes"]["table_row"]["missing"] == {"| K-01 | 相符 | 1.0 |": 1}
    assert report["classes"]["table_row"]["added"] == {"| K-01 | 相符 | 0.9 |": 1}


def test_tikz_change_flagged_but_other_fence_separate():
    current = BASE_MD.replace("KD=8.3nM", "KD=8.4nM")
    report = MODULE.audit(BASE_MD, current)
    assert report["pass"] is False
    assert report["classes"]["tikz"]["added"] and not report["classes"]["tikz"]["equal"]
    assert report["classes"]["fence"]["equal"]


def test_formula_and_backtick_flagged():
    cur_f = BASE_MD.replace("$F1=100\\%$", "$F1=99\\%$")
    report = MODULE.audit(BASE_MD, cur_f)
    assert report["classes"]["formula"]["missing"] == {"F1=100\\%": 1}

    cur_b = BASE_MD.replace("`bm25_k1=2.2`", "`bm25_k1=1.2`")
    report = MODULE.audit(BASE_MD, cur_b)
    assert report["classes"]["backtick"]["missing"] == {"bm25_k1=2.2": 1}


def test_punctuation_info_not_guard():
    current = BASE_MD.replace(
        "审核门禁把 D1 的三项相符从 15 个蓝图计划知识点提升到",
        "审核门禁：D1 的三项相符自 15 个蓝图计划知识点")
    report = MODULE.audit(BASE_MD, current)
    assert report["pass"] is True
    assert report["punctuation_info"]["："]["current"] == 1
    assert report["punctuation_info"]["："]["baseline"] == 0


def test_main_exit_codes(tmp_path):
    base = tmp_path / "base.md"
    cur_ok = tmp_path / "cur_ok.md"
    cur_bad = tmp_path / "cur_bad.md"
    base.write_text(BASE_MD, encoding="utf-8")
    cur_ok.write_text(BASE_MD, encoding="utf-8")
    cur_bad.write_text(BASE_MD.replace("[118]", "[117]"), encoding="utf-8")
    assert MODULE.main(["--baseline", str(base), "--current", str(cur_ok)]) == 0
    assert MODULE.main(["--baseline", str(base), "--current", str(cur_bad)]) == 1
    assert MODULE.main(["--baseline", str(base), "--current", str(tmp_path / "no.md")]) == 2
