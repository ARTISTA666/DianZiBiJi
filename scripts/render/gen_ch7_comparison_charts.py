#!/usr/bin/env python3
"""第七章图表转换轮(T-033):表7-10→图7-1、表7-13→图7-4
风格对齐现有 09/10/11 三张图:matplotlib 默认蓝橙、英文图内标签、柱顶数值、虚线网格。
数据逐值取自原表,零改动。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BLUE, ORANGE = "#1f77b4", "#ff7f0e"
GREEN, RED = "#2ca02c", "#d62728"
OUT = "/tmp/crlt/projects/thesis-ahnu-master/assets/screenshots"

def style_ax(ax):
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

# ---------- 图 7-1:表 7-10 分题型任务完成率 ----------
types = ["Factual\n(from documents)", "Entity-relation", "Process tracing", "Open-ended\nsummary"]
plain = [80.0, 0.0, 0.0, 0.0]
kg = [100.0, 100.0, 60.0, 20.0]

fig, ax = plt.subplots(figsize=(7.6, 4.4))
x = np.arange(len(types))
w = 0.36
b1 = ax.bar(x - w/2, plain, w, color=BLUE, label="Plain RAG")
b2 = ax.bar(x + w/2, kg, w, color=ORANGE, label="KG-Enhanced RAG")
for bars in (b1, b2):
    for r in bars:
        ax.annotate(f"{r.get_height():.0f}%",
                    (r.get_x() + r.get_width()/2, r.get_height()),
                    textcoords="offset points", xytext=(0, 3),
                    ha="center", va="bottom", fontsize=10)
ax.set_xticks(x); ax.set_xticklabels(types, fontsize=9.5)
ax.set_ylabel("Task completion rate (%)", fontsize=11)
ax.set_ylim(0, 112)
ax.set_yticks([0, 20, 40, 60, 80, 100])
ax.tick_params(axis="y", labelsize=9.5)
style_ax(ax)
ax.legend(loc="upper right", fontsize=10, framealpha=0.9)
fig.tight_layout()
fig.savefig(f"{OUT}/12-question-type-completion.png", dpi=170)
plt.close(fig)

# ---------- 图 7-4:表 7-13 五方法描述性结果 ----------
methods = ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"]
# 指标顺序:Micro 覆盖 / Exact / Precision / F1(单位 %)
micro = [0.0, 42.7, 30.2, 90.6, 90.6]
exact = [0.0, 22.2, 8.3, 66.7, 83.3]
prec  = [0.0, 83.7, 90.6, 76.3, 100.0]
f1    = [0.0, 56.6, 45.3, 82.9, 95.1]
series = [
    ("Micro coverage", micro, BLUE),
    ("Exact match", exact, ORANGE),
    ("Precision", prec, GREEN),
    ("F1", f1, RED),
]

fig, ax = plt.subplots(figsize=(7.6, 4.4))
x = np.arange(len(methods))
w = 0.19
for i, (name, vals, color) in enumerate(series):
    bars = ax.bar(x + (i - 1.5) * w, vals, w, color=color, label=name)
    for r in bars:
        ax.annotate(f"{r.get_height():.1f}",
                    (r.get_x() + r.get_width()/2, r.get_height()),
                    textcoords="offset points", xytext=(0, 2),
                    ha="center", va="bottom", fontsize=9, rotation=90)
ax.set_xticks(x)
ax.set_xticklabels(methods, fontsize=9.5)
ax.set_ylabel("Score (%)", fontsize=11)
ax.set_ylim(0, 118)
ax.set_yticks([0, 20, 40, 60, 80, 100])
ax.tick_params(axis="y", labelsize=9.5)
style_ax(ax)
ax.legend(loc="upper left", fontsize=9, ncols=4, framealpha=0.9,
          bbox_to_anchor=(0.005, 1.0), columnspacing=0.9, handletextpad=0.4)
fig.tight_layout()
fig.savefig(f"{OUT}/13-five-method-comparison.png", dpi=170)
plt.close(fig)

print("charts written")
