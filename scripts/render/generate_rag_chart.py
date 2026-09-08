"""Generate a RAG comparison chart from a real experiment CSV export."""

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes"}


def load_metrics(path: Path) -> dict[str, dict[str, float]]:
    groups: dict[str, list[dict[str, str]]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("status") != "completed" or not row.get("evaluation_score"):
                continue
            groups.setdefault(row["mode"], []).append(row)
    if not groups:
        raise SystemExit("No evaluated completed rows found in the experiment CSV")

    metrics: dict[str, dict[str, float]] = {}
    for mode, rows in groups.items():
        count = len(rows)
        metrics[mode] = {
            "count": count,
            "accuracy": sum(parse_bool(row["is_accurate"]) for row in rows) / count,
            "traceability": sum(parse_bool(row["is_traceable"]) for row in rows) / count,
            "score": sum(float(row["evaluation_score"]) for row in rows) / count,
        }
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", type=Path, help="CSV exported by the RAG experiment endpoint")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/user-guide-assets/09-rag-comparison-chart.png"),
    )
    args = parser.parse_args()
    metrics = load_metrics(args.csv_path)
    modes = [mode for mode in ("project_rag", "kg_enhanced_rag") if mode in metrics]
    labels = {
        "project_rag": "Plain RAG",
        "kg_enhanced_rag": "KG-Enhanced RAG",
    }
    categories = ["Accuracy", "Traceability", "Avg score / 5"]
    x = np.arange(len(categories))
    width = 0.7 / max(1, len(modes))

    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    for index, mode in enumerate(modes):
        values = [
            metrics[mode]["accuracy"],
            metrics[mode]["traceability"],
            metrics[mode]["score"] / 5,
        ]
        offset = (index - (len(modes) - 1) / 2) * width
        bars = ax.bar(x + offset, values, width, label=f"{labels[mode]} (n={int(metrics[mode]['count'])})")
        for bar, value in zip(bars, values, strict=True):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                value + 0.02,
                f"{value:.1%}",
                ha="center",
                va="bottom",
                fontsize=9,
            )

    ax.set_ylabel("Normalized score")
    ax.set_title("Plain RAG vs KG-Enhanced RAG")
    ax.set_xticks(x)
    ax.set_xticklabels(categories)
    ax.set_ylim(0, 1.12)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.legend()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(args.output, dpi=200, bbox_inches="tight")
    print(f"Chart saved: {args.output}")


if __name__ == "__main__":
    main()
