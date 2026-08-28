# RAGAS 自动评测报告（去人工化评价标准）

- 执行日期：2026-08-26（UTC 时间戳：2026-08-26T11:36:22.959348+00:00）
- ragas 版本：`0.4.3`
- judge 模型：`deepseek-v4-flash`（temperature=0.1，经 DeepSeek OpenAI 兼容接口接入 langchain-openai ChatOpenAI）
- 指标：faithfulness（无参考）、context_precision（带参考）、context_recall（带参考）；统一由 judge 模型按 RAGAS 提示词打分
- 总耗时：2362s（各臂 wall time 之和；执行分臂进行并逐臂写检查点），样本数：148（含失败单元格 260 个，涉及 105 个样本，均如实记录）

## 明确跳过项

| 项目 | 原因 |
| --- | --- |
| 指标 `response_relevancy` | 需要嵌入模型，本轮明确跳过 |
| 实验五臂 `pure_llm` | 无检索上下文，不适用 RAG 检索/忠实度指标 |
| 实验五臂 `structured_query` | 结构化查询路径，非 RAG 生成管线，不适用本轮指标 |

## 评测口径说明

- **retrieved_contexts 的构成**：`kg_enhanced_rag` 臂的回答以 [G#] 标记引用图谱三元组，其主张来自图谱检索通道而非资料 chunk。为避免把 KG 臂正常引用的图谱证据误判为无证据支撑，retrieved_contexts 取`sources_json` 的 snippet 列表与 `graph_context_json` 序列化三元组（"KG三元组：源实体 -[关系]-> 目标实体"）之和；project_rag/bm25_rag 臂无图谱上下文，仅有 snippet。该口径与本仓库既有"合并证据覆盖"分析一致。
- **参考答案**：实验 4 由 `rag-experiment-4-evaluation-sheet.csv` 的 `gold_rule_groups` 别名组拼接为"答案要点：组1：…/…；组2：…"文本；实验 5 由 `gse111619_kg_holdout_questions.json` 各题金标准事实 label 拼接。
- **失败处理**：judge 单元格在 RunConfig(max_retries=2) 重试后仍失败则记 NaN，报告中记 null 并不计入均值，逐样本明细如实保留失败原因。

## 分臂聚合

| 批次/臂 | 状态 | 有效样本 | faithfulness 均值 | context_precision 均值 | context_recall 均值 | 任一指标失败样本数 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| exp4/Plain RAG | 完整 | 20 | 0.6060 (20) | 0.2667 (20) | 0.0500 (20) | 0 |
| exp4/KG-Enhanced RAG | 完整 | 20 | 0.5332 (20) | 0.2360 (20) | 0.5150 (20) | 0 |
| exp5/project_rag | 未评测（judge 全部失败） | 36 | — (0) | — (0) | — (0) | 36 |
| exp5/kg_enhanced_rag | 部分完成 | 36 | 0.8160 (29) | 0.7841 (4) | 1.0000 (31) | 33 |
| exp5/bm25_rag | 未评测（judge 全部失败） | 36 | — (0) | — (0) | — (0) | 36 |

注：括号内为该指标的有效样本数（judge 在重试后仍失败的单元格不计入均值，逐样本明细见同名 JSON）。均值缺失（—）表示该单元格未获得有效 judge 分数，**不得解读为低分**。

## 评测中断与有效性警告

以下臂存在 judge 调用大面积失败，对应均值不完整或不可用：

- `exp5/bm25_rag`：三指标全部 36 个样本均无有效分数，该臂应视为**未评测**（常见原因为 judge 服务异常或账户余额不足）。
- `exp5/kg_enhanced_rag`：部分指标部分样本失败（faithfulness 29/36，context_precision 4/36，context_recall 31/36），均值仅基于有效子集，解释时需谨慎。
- `exp5/project_rag`：三指标全部 36 个样本均无有效分数，该臂应视为**未评测**（常见原因为 judge 服务异常或账户余额不足）。
- 执行说明：2026-08-26T11:55Z 起出现成批 HTTP 402 Insufficient Balance（DeepSeek 账户余额耗尽；本次运行日志记录约 234 次 APIStatusError 拒绝）。exp4 两臂在余额耗尽前完成且无失败单元格；exp5/kg_enhanced_rag 自该臂中途开始失败（faithfulness 29/36、context_precision 4/36、context_recall 31/36 有效）；exp5/project_rag 与 exp5/bm25_rag 全部单元格失败，应视为未评测。按任务纪律遇 402 即如实报告并停止，未充值重试。另：本日首次全量运行在本环境后台进程被终止时未写出任何分数，其 judge 调用消耗已发生。均值缺失（—）不得解读为低分。

## 与既有规则化判定的定性对照

以下对照为定性说明，不构成统计检验。

- **实验 4**：既有规则化判定（`rag-experiment-4-objective-analysis.md`）显示KG-Enhanced RAG 规则化任务完成率 70.0%，Plain RAG 仅 20.0%，且差异主要由检索证据是否覆盖答案要点解释（合并证据覆盖 66.7% vs 16.7%）。本轮 RAGAS context_recall（Plain RAG 0.0500 vs KG-Enhanced 0.5150）与该结论方向一致：图谱增强臂的参考要点更多出现在检索上下文中。faithfulness 两臂均较高（0.6060 vs 0.5332），说明两臂回答总体忠于各自检索证据，规则化完成率的差距不能归因于幻觉程度差异，而应归因于证据可得性——这与既有分析“主要差异可由检索证据覆盖解释”的结论互相印证。
- **实验 5**：既有内部描述性结果（alias-based fact coverage，`rag-experiment-5-internal-descriptive-results-v1.md`，micro 口径）为 kg_enhanced_rag 90.62% > bm25_rag 42.71% > project_rag 30.21%；closed-set exact 为 83.33% / 22.22% / 8.33%。本轮 RAGAS 的 context_recall（project_rag —、kg_enhanced_rag 1.0000、bm25_rag —，judge 视角）与该机械匹配排序可对照阅读：若 judge 视角的 context_recall 排序与 alias 匹配排序一致，说明两种独立方法对"检索证据是否覆盖金标准要点"给出同向证据；若不一致，则需回查是别名匹配过严/过宽还是 judge 判定偏差。三臂 faithfulness（project_rag —、kg_enhanced_rag 0.8160、bm25_rag —）补充回答-证据一致性维度，这是既有规则化判定未覆盖的指标。
- **方法学定位**：RAGAS 三项指标均为“去人工化”的 LLM-as-judge 评价，judge 为单一模型（deepseek-v4-flash，temperature=0.1），存在 judge 偏差风险，结果应视为与规则化判定、人工盲评互补的证据线，而非替代。response_relevancy 因需要嵌入模型本轮未测，回答相关性维度暂缺。
