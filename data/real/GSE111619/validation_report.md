# GSE111619 离线预检报告

> 本文件只记录独立 SQLite 与测试向量后端的离线服务层预检，不是正式部署系统的运行结果。论文中的系统实现与问答实验应引用 `system_import_report.json`、`gse111619_paired_experiment.csv` 和 `gse111619_paired_experiment_report.json`。

- Verification Status: **ANALYZED**
- Reproducibility fingerprint: `54e4e477ddb927e252f5988ce1b4ec73ee68f05f04947b13795408074c26ccf2`
- 数据性质：NCBI GEO 公开 RNA-seq 实验元数据和基因级 HTSeq 计数矩阵。
- 使用边界：该数据用于验证实验记录结构化、知识图谱构建和检索证据覆盖，不代表本地实验室数据，也不替代原始 FASTQ 分析。

## 数据完整性

- GEO 系列：GSE111619，样本数 4。
- 计数矩阵：25,369 个基因条目，['NonTargeting_rep1', 'NonTargeting_rep2', 'p63KD_rep1', 'p63KD_rep2']。
- 压缩文件哈希：3/3 通过。
- gzip 完整性、字段数、整数类型、非负计数和样本映射检查均通过。
- 元数据存在一处来源内部不一致：系列总体设计写 HiSeq 2000，平台及逐样本字段写 Illumina HiSeq 2500；系统记录采用更具体的逐样本字段，并在报告中保留该警示。

## 离线服务层预检结果

- 导入实验笔记 4 条，笔记版本 4 条。
- 知识图谱包含 39 个实体、100 条关系；重复重建后数量不变。
- 实体类型计数：{"biological_source": 2, "condition": 6, "experiment_type": 1, "identifier": 5, "instrument": 2, "note": 4, "project": 1, "reagent": 3, "result": 9, "sample": 4, "software": 1, "user": 1}。
- 关系类型计数：{"created_by": 4, "has_biological_source": 8, "has_condition": 20, "has_experiment_type": 4, "has_identifier": 8, "has_note": 4, "produces_result": 24, "uses_instrument": 8, "uses_reagent": 12, "uses_sample": 4, "uses_software": 4}。
- 检索向量后端：deterministic_offline_hash_512（512 维），生成 954 个文档块。
- 4 个固定问题的普通 RAG 宏平均事实召回率为 1.0000，图谱增强后为 1.0000。

## 检索对比

| 用例 | 普通 RAG 命中/总事实 | 图谱增强命中/总事实 | 召回率增量 | 图谱关系数 |
|---|---:|---:|---:|---:|
| Q1 | 6/6 | 6/6 | 0.0000 | 12 |
| Q2 | 3/3 | 3/3 | 0.0000 | 30 |
| Q3 | 3/3 | 3/3 | 0.0000 | 8 |
| Q4 | 4/4 | 4/4 | 0.0000 | 28 |
| Q5 | 1/1 | 1/1 | 0.0000 | 24 |
| Q6 | 3/3 | 3/3 | 0.0000 | 24 |

## 描述性统计限制

- 每组仅有 2 个生物学重复，不据此进行推断统计或系统效果显著性检验。
- 本报告计算的 log1p Pearson 相关系数仅用于数据一致性描述，不等同于生物学重复质量的完整判定。
- 未运行 DESeq2，也未报告 p 值、置信区间或差异表达基因；论文不得把本验证改写为差异表达结论。
- 检索对比评价的是固定事实是否进入证据上下文，不是大语言模型答案质量，也没有独立人工盲评。
- 若向量后端为 deterministic_offline_hash_512，本结果只验证本地检索管线与图谱补证逻辑，不能写成 BAAI/bge-small-zh-v1.5 的语义检索效果。
- 11 类统计谬误已全部检查；详细状态见 JSON 报告。

## 可复现文件

- `GSE111619_family.soft(.gz)`：系列、平台和样本元数据。
- `GSE111619_HTSeq_counts.txt(.gz)`：基因级计数矩阵。
- `gse111619_samples.csv`：样本字段及描述性计数。
- `gse111619_notes.json`：导入系统的 4 条结构化实验笔记。
- `gse111619_validation.sqlite3`：独立 SQLite 离线预检数据库，不代表部署系统数据库。
- `gse111619_retrieval_comparison.csv`：逐问题事实召回对比。
- `validation_report.json`：机器可读验证报告。
