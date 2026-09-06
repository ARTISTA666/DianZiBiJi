# GSE306433 — 小鼠结肠炎基质细胞 RNA-seq

## 为什么选这套数据

- 现代公开实验数据（2025 年提交、2026 年公开），与已有 GSE111619（人肺癌细胞系）不同物种、不同疾病场景。
- 设计简单清晰：6 个样本，2 组，每组 3 个生物学重复，便于出题和复核。
- 同时提供 GEO SOFT 元数据、series matrix 和每个样本的 FPKM 文件，可形成“元数据 + 表达结果”两级检索语料。

## 数据身份

- GEO accession：GSE306433
- 标题：The IL-10/IL-10Ra axis in fibroblasts limits large intestinal pathology by suppressing type I interferon signaling [RNA-Seq]
- 物种：Mus musculus
- 平台：GPL24247（Illumina NovaSeq 6000）
- 样本数：6（WT8/WT9/WT43 为 Il10ra flox/flox 对照；cKO13/cKO23/cKO25 为 Pdgfra cre; Il10ra flox/flox）
- 组织/细胞：大肠组织，FACS 分选活基质细胞（Podoplanin+ CD45- CD31- EpCAM- 7AAD-）
- 处理：1% DSS 诱导结肠炎，12 周龄小鼠
- 提交机构：Osaka University, NGS core facility
- 来源：https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE306433

## 文件清单

| 文件 | 说明 | SHA-256 |
|---|---|---|
| GSE306433_family.soft.gz | GEO 原始 SOFT 元数据 | `2ece4462902de5c0229916e4c5cfa0e9d8047bb352cf4f26b94b8dc2fd7811e8` |
| GSE306433_series_matrix.txt.gz | GEO series matrix | `502c3a4722e87d3011c1af80521077b88b085fa776b61e6b1ac7d0ef86a0d466` |
| GSE306433_RAW.tar | GEO supplementary RAW 包（含 6 个 FPKM 文件） | `5d4f46df8ffed6f32e2dfb634a75783a98a28d10921e86d7f7d629a2805d89b3` |
| GSE306433_knowledge_document.txt | 由 SOFT + FPKM 生成的系统导入用知识文档 | 见 `generated_manifest.json` |
| GSE306433_samples.csv | 结构化样本表 | 见 `generated_manifest.json` |

## 使用边界

- NCBI GEO 数据为公开数据，论文中使用需按 GEO 引用规范标注 accession、作者和来源。
- 本目录只保存元数据、表达矩阵和系统生成的知识文档，不保存原始 FASTQ。
- 该数据仅用于论文中的系统检索问答验证，不据此做任何医学结论。
