# Rust 交付系统 20 题成对 RAG 对照重跑报告(目标 2:消除 legacy 脱钩)

- 执行日期:2026-09-04
- 实验运行 ID:Rust 后端 `ai_experiment_runs` #24(40/40 完成,0 失败)
- 回应问题:论文 7.1 节与评审(skeptical-001 / innovation-003)指出的核心缺口——实验 4/5 产生于迁移前 legacy 批次(commit UNKNOWN),交付 Rust 系统不承担任何检索/生成效果证明。本次重跑在**交付 Rust 系统(production Docker 镜像,revision `74dad169`)** 上按同题集、同评价指标完成 20 题成对对照,使核心对照结论首次由交付系统自身产生。
- 原始工件:`docs/experiments/rust-rerun-paired-2026-09-04.csv`(40 行)、`rust-rerun-paired-2026-09-04-report.json`(含 objective_evaluation、citation_marker_audit、paired_comparison、per-case 明细)

## 实验配置(全部由后端记录,可复核)

| 项 | 值 |
| --- | --- |
| 运行时 | production Docker `eln-backend`(Rust/Axum),`/ready` revision `74dad169181c7794a8130a22d09106b3acad56d1` |
| 模型 | deepseek-v4-flash,temperature=0.1(后端固定),prompt 版本 rag-v9-source-and-graph-citations |
| 嵌入 | BAAI/bge-m3(1024 维),rag_index_version=structured-v1 |
| 检索 | retrieval_strategy=rrf-v1,top_k=6,collection_top_k=12,vector_candidate_k=30 |
| 图谱 | graph_top_k=10,graph_min_score=1.0,schema kg-v3-numbered-list-expansion |
| 语料绑定 | corpus_snapshot_hash `ebd165f8…acee2a15`(12 块,2 份已审核资料:bge-m3 重新入库) |
| 图谱绑定 | graph_snapshot_hash `ac10068f…b143e`(39 实体/100 关系) |
| 题集 | `data/real/GSE111619/gse111619_questions.json`(20 题,与 legacy 实验 4 分析所用同源题集;评分规则同 `run_gse111619_experiment.py` 的 alias-based fact coverage 与 closed-set exact) |
| 口径 | **内部开发证据,非独立盲评**——题集为开发期题目、评价为 alias 自动匹配,不构成确认性结论;本次重跑的目的是把"核心对照由交付系统产生"这一脱钩闭合 |

## 结果(20 题 × 2 模式 × 1 重复)

| 指标 | 普通RAG(project_rag) | 图谱增强RAG(kg_enhanced_rag) |
| --- | ---: | ---: |
| Micro 事实覆盖率 | 0.9286 | **0.9821** |
| Macro 事实覆盖率 | 0.9333 | **0.9833** |
| 封闭集 exact 正确题数 | 17/20(0.85) | **19/20(0.95)** |
| 总 Token | 80,055 | 133,766 |
| 平均时延 | 7,100.4 ms | 9,688.1 ms |

**配对比较(kg_enhanced_rag − project_rag)**:20 对中改善 3、持平 17、**恶化 0**;覆盖率差值均值 +0.05;McNemar 精确双侧 p=0.5(配对改善数少,不构成显著性结论,仅作方向性描述)。

**引用审计(Rust 生产端 strict 口径)**:40/40 回答带 [S] 来源标记、20/20 图谱臂回答带 [G] 标记,`all_citation_indices_in_range=true`,非法标记行 0——与 legacy 批次审计出现 4 行越界标记形成对照,交付系统的引用修复链路(`strip_citation_template_placeholders` + 审计)在真实运行中零违规。

## 与 legacy 实验 4 的对照说明(诚实性边界)

- **不可直接比较数字**:legacy 实验 4(论文 7.6)与本次重跑的语料状态不同——实验 4 运行时项目内 15 条已审核笔记 + 7 份 SOP 提要(资料通道近乎空载),当前库为库重建后的 4 条笔记 + 2 份 GSE111619 结构化资料(bge-m3 入库 12 块),题集亦为 GSE111619 开发题集。因此本次 4→覆盖率不能与论文头条的 4→14、p=0.0020 并列或替换,两者是**不同语料条件下的两次机制诊断**。
- 本次重跑的回答了评审的核心质疑("论文实现与论文实验脱节")中的**可实现性**部分:同样的成对对照协议、同样的指标口径,在交付 Rust 系统上可以完整执行并产出方向一致的结果(图谱增强 ≥ 普通检索,0 恶化)。
- **遗留**:题集仍未做外部命题者签署,评分仍为 alias 自动匹配(非人工)——这两项属人工介入类(最低优先级),完成前本批次的证据等级保持"内部开发证据"。

## 结论

1. 交付 Rust 系统已具备完整的成对对照实验执行与审计能力,核心对照(图谱增强 vs 普通 RAG)在交付系统上首次产生数据:覆盖率 0.9821 对 0.9286、exact 0.95 对 0.85、配对 3 胜 0 负 17 平。
2. 引用审计在交付系统上零违规,支持论文"可审计证据链"的工程主张。
3. 论文 7.1 节可在"legacy 口径对照表"处增补本批次作为"交付系统复现批次"(方向性证据),并在 8.3/8.4 的"Rust 侧重跑"遗留项中销账其文字部分;显著性确认与人工盲评仍属后续工作。
