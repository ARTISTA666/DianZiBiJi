"""Generate the score-(5-3) coefficient-ablation stability chart used by the thesis.

图 7-3:式(5-3) 系数消融的排序稳定性。数据源为
docs/experiments/kg-score53-coefficient-ablation-2026-09-04.json(2026-09-04 批次)。
风格与 scripts/generate_kg_sensitivity_chart.py(图 7-2)保持一致。
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "docs" / "experiments" / "kg-score53-coefficient-ablation-2026-09-04.json"
CHART_PATH = ROOT / "docs" / "user-guide-assets" / "11-score53-coefficient-ablation.png"


def _cjk_font() -> FontProperties | None:
    for candidate in (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
    ):
        if Path(candidate).exists():
            return FontProperties(fname=candidate)
    return None


def main() -> None:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    summary = data["summary"]
    # 档位顺序:基线在最左,变体按一致性降序展示
    order = ["role=2.0", "role=1.0", "role=0.0", "exact=2.0", "partial=2.0", "hint=1.0", "bonuses=0"]
    labels = [
        "角色命中\n4.0→2.0",
        "角色命中\n4.0→1.0",
        "角色命中\n4.0→0",
        "词元全等\n3.0→2.0",
        "部分匹配\n1.0→2.0",
        "关系提示\n3.0→1.0",
        "来源加成\n归零",
    ]
    tau = [summary[key]["kendall_tau_consistency"] for key in order]
    overlap = [summary[key]["mean_top10_set_overlap"] for key in order]

    font = _cjk_font()
    positions = range(len(order))
    figure, axis_left = plt.subplots(figsize=(7.4, 4.4))
    axis_right = axis_left.twinx()
    bars = axis_left.bar(
        [p - 0.18 for p in positions],
        tau,
        width=0.36,
        color="#4C78A8",
        label="排序一致率 (Kendall)",
    )
    axis_right.bar(
        [p + 0.18 for p in positions],
        overlap,
        width=0.36,
        color="#F58518",
        label="top-10 集合重合率",
    )
    axis_left.set_ylim(0.9, 1.005)
    axis_right.set_ylim(0.0, 1.05)
    axis_left.set_xticks(list(positions))
    if font is not None:
        axis_left.set_xticklabels(labels, fontproperties=font, fontsize=8.5)
        axis_left.set_ylabel("排序一致率", fontproperties=font, color="#4C78A8")
        axis_right.set_ylabel("top-10 集合重合率", fontproperties=font, color="#F58518")
    else:
        axis_left.set_xticklabels(labels, fontsize=8.5)
        axis_left.set_ylabel("Kendall consistency", color="#4C78A8")
        axis_right.set_ylabel("top-10 set overlap", color="#F58518")
    for tick, color in ((axis_left, "#4C78A8"), (axis_right, "#F58518")):
        tick.tick_params(axis="y", colors=color)
    axis_left.grid(linestyle="--", alpha=0.3)
    for p, value in zip(positions, tau, strict=True):
        axis_left.annotate(
            f"{value:.4f}" if value < 1.0 else "1.0",
            (p - 0.18, value),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            fontsize=8,
            color="#4C78A8",
        )
    axis_right.annotate(
        "全部档位 0.91",
        (len(order) - 1.35, 0.91),
        xytext=(0, 6),
        textcoords="offset points",
        ha="center",
        fontsize=8.5,
        color="#F58518",
    )
    axis_left.axhline(1.0, color="#4C78A8", linewidth=0.8, linestyle=":", alpha=0.6)
    legend_lines = [
        plt.Line2D([0], [0], color="#4C78A8", lw=6, label="排序一致率"),
        plt.Line2D([0], [0], color="#F58518", lw=6, label="top-10 集合重合率"),
    ]
    if font is not None:
        for handle in legend_lines:
            handle.set_fontproperties(font)
    if font is not None:
        legend = axis_left.legend(handles=legend_lines, loc="lower left", prop=font, fontsize=9)
    else:
        legend = axis_left.legend(handles=legend_lines, loc="lower left", fontsize=9)
    axis_left.set_title("")

    CHART_PATH.parent.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(CHART_PATH, dpi=180)
    print(f"written: {CHART_PATH}")


if __name__ == "__main__":
    main()
