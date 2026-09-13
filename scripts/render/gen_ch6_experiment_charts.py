#!/usr/bin/env python3
"""第六章表转图轮(T-039):表6-7→图6-1、表6-8→图6-2、表6-10→图6-6、表6-11→图6-8。
风格对齐 T-033 的 12/13 号图:matplotlib 默认蓝橙、英文图内标签、柱顶数值、虚线网格。
数据逐值取自原表,零改动;原表中的全部数值均保留在图内或正文。"""
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

def label_bars(bars, fmt="{:.0f}", dy=3):
    for r in bars:
        ax_ = r.axes
        ax_.annotate(fmt.format(r.get_height()),
                     (r.get_x() + r.get_width()/2, r.get_height()),
                     textcoords="offset points", xytext=(0, dy),
                     ha="center", va="bottom", fontsize=9)

# ---------- 图 6-1(原表 6-7):三项目语料规模统计 ----------
projects = ["Project 1\n(demo)", "Project 2\n(cancer biomarkers)", "Project 3\n(drug target)"]
notes = [15, 10, 10]
ents = [177, 93, 87]
rels = [237, 104, 104]

fig, ax = plt.subplots(figsize=(7.6, 4.0))
x = np.arange(len(projects))
w = 0.26
b1 = ax.bar(x - w, notes, w, color=BLUE, label="Approved notes")
b2 = ax.bar(x, ents, w, color=ORANGE, label="Entities")
b3 = ax.bar(x + w, rels, w, color=GREEN, label="Relations")
for bars in (b1, b2, b3):
    label_bars(bars)
ax.set_xticks(x); ax.set_xticklabels(projects, fontsize=9.5)
ax.set_ylabel("Count", fontsize=11)
ax.set_ylim(0, 265)
ax.tick_params(axis="y", labelsize=9.5)
style_ax(ax)
ax.legend(loc="upper right", fontsize=10, framealpha=0.9)
fig.tight_layout()
fig.savefig(f"{OUT}/20-corpus-structure.png", dpi=170)
plt.close(fig)

# ---------- 图 6-2(原表 6-8):关系核验原始与修复后批次 ----------
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.6, 3.8))
metrics_c = ["Actual\nrelations", "TP", "FP", "FN"]
orig_c = [53, 52, 1, 0]
fix_c = [52, 52, 0, 0]
x = np.arange(len(metrics_c))
w = 0.36
b1 = ax1.bar(x - w/2, orig_c, w, color=BLUE, label="Original batch")
b2 = ax1.bar(x + w/2, fix_c, w, color=ORANGE, label="After fix")
for bars in (b1, b2):
    label_bars(bars)
ax1.set_xticks(x); ax1.set_xticklabels(metrics_c, fontsize=9.5)
ax1.set_ylabel("Count", fontsize=11)
ax1.set_ylim(0, 62)
ax1.set_title("Relation counts", fontsize=10.5, pad=14)
style_ax(ax1)
ax1.legend(loc="upper right", fontsize=9, framealpha=0.9)

metrics_r = ["Precision", "Recall", "F1"]
orig_r = [98.11, 100.00, 99.05]
fix_r = [100.00, 100.00, 100.00]
x = np.arange(len(metrics_r))
b3 = ax2.bar(x - w/2, orig_r, w, color=BLUE, label="Original batch")
b4 = ax2.bar(x + w/2, fix_r, w, color=ORANGE, label="After fix")
for bars in (b3, b4):
    label_bars(bars, fmt="{:.2f}%", dy=3)
ax2.set_xticks(x); ax2.set_xticklabels(metrics_r, fontsize=9.5)
ax2.set_ylabel("Rate (%)", fontsize=11)
ax2.set_ylim(95, 101.6)
ax2.set_yticks([95, 96, 97, 98, 99, 100])
ax2.set_title("Rates against the 52-relation gold standard", fontsize=10.5, pad=26)
style_ax(ax2)
ax2.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=2, fontsize=9, frameon=False)
fig.tight_layout()
fig.savefig(f"{OUT}/21-gold-audit-batches.png", dpi=170)
plt.close(fig)

# ---------- 图 6-6(原表 6-10):四臂扩展消融 ----------
arms = ["Bare LLM\n(no retrieval)", "Plain RAG", "KG-Enhanced\nRAG", "Direct SQL"]
full20 = [10.0, 20.0, 70.0, 55.0]
subset14 = [7.1, 0.0, 57.1, 78.6]

fig, ax = plt.subplots(figsize=(7.6, 4.2))
x = np.arange(len(arms))
w = 0.36
b1 = ax.bar(x - w/2, full20, w, color=BLUE, label="All 20 questions")
b2 = ax.bar(x + w/2, subset14, w, color=ORANGE, label="SQL-answerable 14-question subset")
for bars in (b1, b2):
    label_bars(bars, fmt="{:.1f}%")
ax.set_xticks(x); ax.set_xticklabels(arms, fontsize=9.5)
ax.set_ylabel("Task completion rate (%)", fontsize=11)
ax.set_ylim(0, 92)
ax.tick_params(axis="y", labelsize=9.5)
style_ax(ax)
ax.legend(loc="upper left", fontsize=9.5, framealpha=0.9)
fig.tight_layout()
fig.savefig(f"{OUT}/22-four-arm-ablation.png", dpi=170)
plt.close(fig)

# ---------- 图 6-8(原表 6-11):四类固定任务的证据来源结构 ----------
tasks = ["Summary\n2191 tok / 9844 ms", "Weekly report\n2071 tok / 8791 ms",
         "Stage report\n4187 tok / 14033 ms", "KG overview\n1391 tok / 4924 ms"]
s_notes = [3, 3, 15, 15]
s_files = [7, 7, 7, 7]
s_rels = [38, 38, 40, 40]

fig, ax = plt.subplots(figsize=(7.6, 4.2))
x = np.arange(len(tasks))
w = 0.26
b1 = ax.bar(x - w, s_notes, w, color=BLUE, label="Source notes")
b2 = ax.bar(x, s_files, w, color=ORANGE, label="Source files")
b3 = ax.bar(x + w, s_rels, w, color=GREEN, label="Graph relations")
for bars in (b1, b2, b3):
    label_bars(bars)
ax.set_xticks(x); ax.set_xticklabels(tasks, fontsize=9)
ax.set_ylabel("Source count", fontsize=11)
ax.set_ylim(0, 47)
ax.tick_params(axis="y", labelsize=9.5)
style_ax(ax)
ax.legend(loc="upper left", fontsize=9.5, framealpha=0.9)
fig.tight_layout()
fig.savefig(f"{OUT}/23-generation-sources.png", dpi=170)
plt.close(fig)

print("4 charts written to", OUT)
