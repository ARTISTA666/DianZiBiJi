#!/usr/bin/env python3
"""Generate import-ready knowledge documents for the two new GEO datasets.

Inputs (downloaded from NCBI GEO FTP, see per-dataset README.md after generation):
- data/real/GSE306433_colitis/GSE306433_family.soft.gz
- data/real/GSE306433_colitis/raw/*_FPKM.txt.gz
- data/real/GSE291942_arabidopsis_heat/GSE291942_family.soft.gz
- data/real/GSE291942_arabidopsis_heat/GSE291942_gene.tpm.matrix.annot.txt.gz

Outputs are deterministic text/CSV files used later for question freezing and RAG import.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

GSE306433_DIR = ROOT / "data" / "real" / "GSE306433_colitis"
GSE291942_DIR = ROOT / "data" / "real" / "GSE291942_arabidopsis_heat"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_soft(path: Path) -> dict:
    """Return series-level and sample-level records from a GEO family SOFT file."""
    series: dict[str, list[str]] = {}
    samples: list[dict[str, list[str]]] = []
    current_sample: dict[str, list[str]] | None = None
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("!Series_"):
                key, _, value = line[len("!Series_"):].partition(" = ")
                series.setdefault(key, []).append(value)
            elif line.startswith("^SAMPLE"):
                current_sample = {"_geo": line.split(" = ", 1)[-1]}
                samples.append(current_sample)
            elif line.startswith("!Sample_") and current_sample is not None:
                key, _, value = line[len("!Sample_"):].partition(" = ")
                current_sample.setdefault(key, []).append(value)
    return {"series": series, "samples": samples}


def one(values: list[str], default: str = "") -> str:
    return values[0] if values else default


def all_values(record: dict[str, list[str]], key: str) -> list[str]:
    return record.get(key, [])


def gse306433_fpkm_stats(sample: str) -> dict:
    matches = list((GSE306433_DIR / "raw").glob(f"{sample}_*_FPKM.txt.gz"))
    if len(matches) != 1:
        raise FileNotFoundError(f"expected one FPKM file for {sample}, got {len(matches)}")
    path = matches[0]
    values: list[tuple[str, float]] = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        header = fh.readline()
        colname = header.rstrip("\n").split("\t")[-1]
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            try:
                value = float(parts[1])
            except ValueError:
                continue
            values.append((parts[0], value))
    nonzero = [item for item in values if item[1] > 0.0]
    top = sorted(values, key=lambda item: item[1], reverse=True)[:5]
    return {
        "colname": colname,
        "gene_count": len(values),
        "nonzero_gene_rows": len(nonzero),
        "max_gene": top[0][0],
        "max_fpkm": top[0][1],
        "top5": ", ".join(f"{gene}:{value:.2f}" for gene, value in top),
    }


def build_gse306433() -> None:
    parsed = parse_soft(GSE306433_DIR / "GSE306433_family.soft.gz")
    series = parsed["series"]
    samples = parsed["samples"]
    out_dir = GSE306433_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("GEO series GSE306433 structured validation document")
    lines.append(f"研究标题：{one(series.get('title', []))}")
    lines.append(f"研究摘要：{one(series.get('summary', []))}")
    lines.append(f"总体设计：{one(series.get('overall_design', []))}")
    lines.append("数据边界：本语料为 NCBI GEO 公开的 RNA-seq 元数据与 FPKM 表达矩阵，不是本地实验室原始笔记，也不是原始 FASTQ 读段。")
    lines.append("来源：https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE306433")
    lines.append(f"平台：{one(series.get('platform_id', []))}（Illumina NovaSeq 6000，Mus musculus）")
    lines.append(f"联系机构：{one(series.get('contact_institute', []))}，{one(series.get('contact_country', []))}")
    lines.append(f"关联项目：{one(series.get('relation', []))}")
    lines.append("")

    sample_rows: list[dict[str, str]] = []
    for record in samples:
        geo = record["_geo"]
        title = one(record.get("title", []))
        chars = all_values(record, "characteristics_ch1")
        tissue = next((v.split(": ", 1)[1] for v in chars if v.startswith("tissue: ")), "")
        cell_type = next((v.split(": ", 1)[1] for v in chars if v.startswith("cell type: ")), "")
        genotype = next((v.split(": ", 1)[1] for v in chars if v.startswith("genotype: ")), "")
        biosample = next((v for v in all_values(record, "relation") if "biosample" in v), "")
        sra = next((v for v in all_values(record, "relation") if "sra" in v), "")
        stats = gse306433_fpkm_stats(geo)
        group = "control" if genotype == "Il10ra flox/flox" else "fibroblast_Il10ra_cKO"
        lines.append(f"{geo} RNA-seq record")
        lines.append(f"数据来源：NCBI GEO GSE306433，样本登录号 {geo}。")
        lines.append(f"样本信息为 {title} [{tissue} | {cell_type} | genotype={genotype}]。")
        lines.append("处理：1% DSS 诱导结肠炎；12 周龄小鼠；取大肠组织，FACS 分选活基质细胞（Podoplanin+ CD45- CD31- EpCAM- 7AAD-）。")
        lines.append("RNA 提取使用 miRNeasy Micro Kit（Qiagen）；cDNA 制备使用 SMART-Seq HT Kit（Takara Bio）；文库构建使用 NexteraXT DNA Library Preparation Kit（Illumina）。")
        lines.append("测序：Illumina NovaSeq 6000，101-base single-end；比对到 mm10 参考基因组；比对工具为 TopHat v2.1.1 + Bowtie2 v2.2.8 + SAMtools v0.1.18。")
        lines.append("表达定量：Cuffdiff 2.2.1 计算 FPKM（参数 -max-bundle-frags 50000000）；base calling 使用 Illumina RTA v3.4.4。")
        lines.append(
            f"FPKM 统计为 {geo}: gene_count={stats['gene_count']}, "
            f"nonzero_gene_rows={stats['nonzero_gene_rows']}, "
            f"max_fpkm_gene={stats['max_gene']}, max_fpkm={stats['max_fpkm']:.2f}；"
            f"top5={stats['top5']}。"
        )
        lines.append(f"结构化样本字段：{geo} [{title} | group={group} | tissue={tissue} | cell_type={cell_type} | genotype={genotype}]。")
        lines.append("")
        sample_rows.append({
            "geo_accession": geo,
            "title": title,
            "group": group,
            "tissue": tissue,
            "cell_type": cell_type,
            "genotype": genotype,
            "molecule": one(record.get("molecule_ch1", [])),
            "instrument": one(record.get("instrument_model", [])),
            "library_strategy": one(record.get("library_strategy", [])),
            "biosample": biosample,
            "sra": sra,
            "gene_count": str(stats["gene_count"]),
            "nonzero_gene_rows": str(stats["nonzero_gene_rows"]),
            "max_fpkm_gene": stats["max_gene"],
            "max_fpkm": f"{stats['max_fpkm']:.2f}",
            "top5_genes": stats["top5"],
        })

    (out_dir / "GSE306433_knowledge_document.txt").write_text("\n".join(lines), encoding="utf-8")
    csv_path = out_dir / "GSE306433_samples.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        fieldnames = list(sample_rows[0].keys())
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sample_rows)

    manifest = [
        {"path": f"{p.relative_to(ROOT)}", "sha256": sha256(p)}
        for p in sorted(out_dir.iterdir())
        if p.is_file() and p.name not in {"GSE306433_family.soft.gz", "GSE306433_series_matrix.txt.gz", "GSE306433_RAW.tar", "filelist.txt", "generated_manifest.json"}
    ]
    (out_dir / "generated_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("built", out_dir)
    print("samples", len(sample_rows))


def gse291942_tpm_stats() -> dict:
    path = GSE291942_DIR / "GSE291942_gene.tpm.matrix.annot.txt.gz"
    sample_cols: list[str] = []
    gene_count = 0
    sums: dict[str, float] = {}
    maxima: dict[str, tuple[str, float]] = {}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        header = fh.readline().rstrip("\n").split("\t")
        sample_cols = header[4:22]  # 18 per-sample columns
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 22:
                continue
            gene_count += 1
            for idx, col in enumerate(sample_cols):
                try:
                    value = float(parts[4 + idx])
                except ValueError:
                    continue
                sums[col] = sums.get(col, 0.0) + value
                if col not in maxima or value > maxima[col][1]:
                    maxima[col] = (parts[0], value)
    condition_map = {
        "PR_CO": ("PRMT5 T-insert, 22℃", [f"PR_CO_{i}" for i in (1, 2, 3)]),
        "PR_R24": ("PRMT5 T-insert, 37℃ 3d 后恢复 24h", [f"PR_R24_{i}" for i in (1, 2, 3)]),
        "PR_RH": ("PRMT5 T-insert, 37℃ 3d", [f"PR_RH_{i}" for i in (1, 2, 3)]),
        "WT_CO": ("WT, 22℃", [f"WT_CO_{i}" for i in (1, 2, 3)]),
        "WT_R24": ("WT, 37℃ 3d 后恢复 24h", [f"WT_R24_{i}" for i in (1, 2, 3)]),
        "WT_RH": ("WT, 37℃ 3d", [f"WT_RH_{i}" for i in (1, 2, 3)]),
    }
    conditions = {}
    for key, (label, cols) in condition_map.items():
        total = sum(sums.get(c, 0.0) for c in cols)
        conditions[key] = {"label": label, "cols": cols, "mean_total_tpm": total / len(cols)}
    best_by_gene: dict[str, float] = {}
    for gene, value in maxima.values():
        best_by_gene[gene] = max(best_by_gene.get(gene, 0.0), value)
    overall_top = sorted(best_by_gene.items(), key=lambda item: item[1], reverse=True)[:10]
    return {
        "gene_count": gene_count,
        "sample_cols": sample_cols,
        "conditions": conditions,
        "overall_top": overall_top,
        "per_sample_maxima": maxima,
    }


def build_gse291942() -> None:
    parsed = parse_soft(GSE291942_DIR / "GSE291942_family.soft.gz")
    series = parsed["series"]
    samples = parsed["samples"]
    stats = gse291942_tpm_stats()
    out_dir = GSE291942_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("GEO series GSE291942 structured validation document")
    lines.append(f"研究标题：{one(series.get('title', []))}")
    lines.append(f"研究摘要：{one(series.get('summary', []))}")
    lines.append(f"总体设计：{one(series.get('overall_design', []))}")
    lines.append("数据边界：本语料为 NCBI GEO 公开的 RNA-seq 元数据与 TPM 表达矩阵，不是本地实验室原始笔记，也不是原始 FASTQ 读段。")
    lines.append("来源：https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE291942")
    lines.append(f"平台：{one(series.get('platform_id', []))}（Illumina NovaSeq 6000，Arabidopsis thaliana）")
    lines.append(f"联系机构：{one(series.get('contact_institute', []))}，{one(series.get('contact_country', []))}")
    lines.append("培养条件：植物培养于含 1.2% (w/v) 蔗糖的半浓度 MS 培养基（half-strength MS medium with 1.2% (w/v) sucrose）。")
    lines.append("建库方法：Illumina TruSeq RNA sample prep Kit；mRNA 经 Oligo dT 富集并片段化。")
    lines.append("")
    lines.append("实验设计：拟南芥幼苗，比较 WT 与 PRMT5 T-insert 突变体在三个条件下的转录组：")
    lines.append("- 22℃ 对照（CO），每组 3 个生物学重复；")
    lines.append("- 37℃ 处理 3 天（RH），每组 3 个生物学重复；")
    lines.append("- 37℃ 处理 3 天后再恢复 24 小时（R24），每组 3 个生物学重复；")
    lines.append(f"共 2 种基因型 × 3 种条件 × 3 个重复 = 18 个样本；TPM 矩阵包含 {stats['gene_count']} 个基因。")
    lines.append("数据处理：RSEM 定量，参考基因组/注释为 TAIR10.1；测序平台为 Illumina NovaSeq 6000。")
    lines.append("")
    lines.append("各条件平均总 TPM（按 3 个重复计算）：")
    for key, info in stats["conditions"].items():
        lines.append(f"- {key}（{info['label']}）: mean_total_tpm={info['mean_total_tpm']:.1f}")
    lines.append("全矩阵最高表达的前 10 个基因（按单样本最高 TPM）：")
    for gene, value in stats["overall_top"]:
        lines.append(f"- {gene}: max_tpm={value:.2f}")
    lines.append("")

    sample_rows: list[dict[str, str]] = []
    for record in samples:
        geo = record["_geo"]
        title = one(record.get("title", []))
        chars = all_values(record, "characteristics_ch1")
        tissue = next((v.split(": ", 1)[1] for v in chars if v.startswith("tissue: ")), "")
        genotype = next((v.split(": ", 1)[1] for v in chars if v.startswith("genotype: ")), "")
        treatment = next((v.split(": ", 1)[1] for v in chars if v.startswith("treatment: ")), "")
        # Infer replicate from title suffix rep1/rep2/rep3.
        replicate = "1" if title.endswith("rep1") else "2" if title.endswith("rep2") else "3"
        genotype_prefix = "WT" if genotype == "WT" else "PR"
        if "recovery" in treatment:
            condition_suffix = "R24"
        elif "37℃ 3d" in treatment:
            condition_suffix = "RH"
        else:
            condition_suffix = "CO"
        matrix_column = f"{genotype_prefix}_{condition_suffix}_{replicate}"
        lines.append(f"{geo} RNA-seq record")
        lines.append(f"数据来源：NCBI GEO GSE291942，样本登录号 {geo}。")
        lines.append(f"样本信息为 {title} [{tissue} | genotype={genotype} | treatment={treatment} | replicate={replicate}]。")
        lines.append(f"TPM 矩阵列为 {matrix_column}。")
        lines.append("测序：Illumina NovaSeq 6000，RNA-Seq；表达定量使用 RSEM，参考基因组/注释为 TAIR10.1。")
        lines.append(f"结构化样本字段：{geo} [{title} | tissue={tissue} | genotype={genotype} | treatment={treatment} | replicate={replicate} | matrix_column={matrix_column}]。")
        lines.append("")
        sample_rows.append({
            "geo_accession": geo,
            "title": title,
            "tissue": tissue,
            "genotype": genotype,
            "treatment": treatment,
            "replicate": replicate,
            "matrix_column": matrix_column,
            "molecule": one(record.get("molecule_ch1", [])),
            "instrument": one(record.get("instrument_model", [])),
            "library_strategy": one(record.get("library_strategy", [])),
            "data_processing": "；".join(all_values(record, "data_processing")),
        })

    (out_dir / "GSE291942_knowledge_document.txt").write_text("\n".join(lines), encoding="utf-8")
    csv_path = out_dir / "GSE291942_samples.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        fieldnames = list(sample_rows[0].keys())
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sample_rows)
    design_index = next(i for i, line in enumerate(lines) if line.startswith("实验设计：拟南芥幼苗"))
    (out_dir / "GSE291942_expression_summary.txt").write_text("\n".join(lines[design_index:]), encoding="utf-8")

    manifest = [
        {"path": f"{p.relative_to(ROOT)}", "sha256": sha256(p)}
        for p in sorted(out_dir.iterdir())
        if p.is_file() and p.name not in {"GSE291942_family.soft.gz", "GSE291942_series_matrix.txt.gz", "GSE291942_gene.tpm.matrix.annot.txt.gz", "generated_manifest.json"}
    ]
    (out_dir / "generated_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("built", out_dir)
    print("samples", len(sample_rows), "genes", stats["gene_count"])


if __name__ == "__main__":
    build_gse306433()
    build_gse291942()
