# GSE291942 — 拟南芥 PRMT5 高温胁迫 RNA-seq

## 为什么选这套数据

- 现代公开植物实验数据（2025 年提交、2026 年公开），与已有 GSE111619（人肺癌细胞）和 GSE306433（小鼠结肠炎）形成“人—动物—植物”三类现代语料。
- 设计为 2 基因型 × 3 条件 × 3 重复 = 18 个样本，结构规整、事实丰富。
- 提供 GEO SOFT 元数据和全基因 TPM 矩阵，便于构建“元数据 + 表达矩阵摘要”两级检索语料。

## 数据身份

- GEO accession：GSE291942
- 标题：Transcriptome analysis of PRMT5 in Arabidopsis thaliana group to regulate high temperature stress response
- 物种：Arabidopsis thaliana
- 平台：GPL26208（Illumina NovaSeq 6000）
- 样本数：18
  - 基因型：WT、PRMT5 T-insert
  - 条件：22℃ 对照；37℃ 处理 3 天；37℃ 处理 3 天后恢复 24 小时
  - 重复：每条件 3 个生物学重复
- 组织：幼苗（seedling）
- 提交机构：Yunnan University
- 来源：https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE291942

## 文件清单

| 文件 | 说明 | SHA-256 |
|---|---|---|
| GSE291942_family.soft.gz | GEO 原始 SOFT 元数据 | `b6a18f584443c7a0fb7a7cd761fe476d255372272e279c4a2fa5f73a3d8387a5` |
| GSE291942_series_matrix.txt.gz | GEO series matrix | `42e00555cb7455906ea7ee0939ebffaa783c98625a82763375cb8902ebf638d9` |
| GSE291942_gene.tpm.matrix.annot.txt.gz | 全基因 TPM 矩阵 | `e9cfb45cc604cbdd74f4e07b4c24e889b66b81617cee493f53814ac840e760a6` |
| GSE291942_knowledge_document.txt | 由 SOFT + TPM 生成的系统导入用知识文档 | 见 `generated_manifest.json` |
| GSE291942_samples.csv | 结构化样本表 | 见 `generated_manifest.json` |
| GSE291942_expression_summary.txt | TPM 矩阵摘要（条件、基因数、高表达基因） | 见 `generated_manifest.json` |

## 使用边界

- NCBI GEO 数据为公开数据，论文中使用需按 GEO 引用规范标注 accession、作者和来源。
- 本目录只保存元数据、TPM 矩阵和系统生成的知识文档，不保存原始 FASTQ。
- 该数据仅用于论文中的系统检索问答验证，不据此做任何植物学或农学结论。
