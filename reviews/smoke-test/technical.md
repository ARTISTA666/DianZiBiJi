# Technical Review — Smoke Test(范围:§5.2.3 混合检索的 RRF 融合)

评审对象:`docs/毕业论文重构稿.md` §5.2.3(L764-780);上下文核对:§5.2.1-5.2.2(L748-763)、§5.2.4 开头(L781-800)。
核实基线:生产 Rust 后端 `backend/src/`(backend/src/rag/retrieval.rs、bm25.rs、config.rs、api/rag/mod.rs)。

## Review Summary
总体评分:7.5/10
风险等级:Medium

本节主体描述与实现高度一致,无"听起来高级但未实现"的 overclaim。以下声明已逐项用代码核实为正确:

- 默认策略 `rag_retrieval_strategy=rrf-v1`(backend/src/config.rs:146);RRF 累加 `weight/(60+rank)`(rank 从 1 计)、rank constant 60.0、按最大值归一化到 [0,1](backend/src/rag/retrieval.rs:334,337-342,210-214)。
- 普通查询两路权重 1.0/1.0(retrieval.rs:313-319);偏精确词项查询 0.25/0.75(retrieval.rs:211;触发词表与 §5.2.2 L762 描述一致,retrieval.rs:350-388)。
- `legacy-weighted`(0.7/0.3)作为兼容路径与 rrf-v1 分开登记(retrieval.rs:248;config.rs:210;api/rag/mod.rs:2195-2196)。
- 最低相关性阈值默认 0.15(config.rs:150)、同一文件最多 3 个数据块(retrieval.rs:398-403)、[S1]…[Sn] 按检索结果顺序编号(backend/src/rag/mod.rs:78-85)。
- L779 问答流程全部属实:权限校验(api/rag/mod.rs:775)→ 数据集检查(mod.rs:785-791)→ 混合检索(mod.rs:804)→ 构造带 [S] 编号输入(rag/mod.rs:72-85)→ 调用 DeepSeek 官方接口(config.rs:119,123,132,默认 https://api.deepseek.com)→ 保存回答/来源/检索配置/Token 用量/耗时(mod.rs:1109-1110,2076,2101-2107);失败走 `log_query_failure` 保存失败日志并返回明确错误,无模拟答案替代(mod.rs:807-821,1213-1248)。
- 式(5-2) 历史融合行为 0.8/0.2 反算声明属实:`docs/experiments/rag-experiment-4.csv` 样本行 retrieval_score = 0.8×vector_score + 0.2×lexical_score 精确成立(如 0.803779/0.5/0.743023;0.522388/0.0/0.41791)。
- §5.2.4 开头与实现的衔接一致:两种模式共享同一 `retrieve()` 资料通道(api/rag/mod.rs:800-865),图谱上下文另行注入,术语无混淆。

未发现 RAG 与图谱查询、Agent 与固定工作流、向量库与倒排索引等概念混淆。

超出本节范围、留给正式评审轮的两点观察(不计入 issue):① L775 "式(5-2)不是当前 Rust 默认实现……"一句连续重复出现两次,属编辑残留;② "默认 top-k=6"未提及集合型查询分支(`多少/最高/最低`等触发词恰好与 §5.2.2 偏精确触发词重叠,该分支证据上限为 12,retrieval.rs:288-296、config.rs:143-144)与低召回改写路径(api/rag/mod.rs:844-861),§5.2.4 图 5-3 的 "top-6" 同样继承此简化。

## Issues

### ISSUE-001
Severity: Major
Priority: P1
Location: §5.2.3 混合检索的 RRF 融合,L777
Category: technical/fact-error
Problem: 论文把丢弃判据描述为"融合得分低于阈值 **且** 双路均未达标"的联合条件,但实现中 RRF 路径的过滤只看两路原始分,融合得分不参与判据;融合得分高但双路原始分均低于 0.15 的块在代码中会被丢弃,按论文的"且"条件却应保留。
Evidence: 论文原句:"融合得分低于最低相关性阈值(默认 0.15)且双路均未达标的块被丢弃"。代码 `passes_relevance_floor`(backend/src/rag/retrieval.rs:420-432):非 bm25_only 路径仅判断 `vector_score >= minimum || lexical_score >= minimum`,完全不比较融合得分;单测进一步证实 `passes_relevance_floor(1.0, 0.05, 0.0, false, 0.15)` → false(融合得分 1.0 仍被拒,retrieval.rs:612-617)。阈值默认 0.15 见 backend/src/config.rs:150。
Recommendation: 改为"当两路原始得分均低于最低相关性阈值(默认 0.15)时候选块被丢弃;该判据只比较两路原始分,不比较融合得分(RRF 得分基于排名,不反映单路分数绝对水平)"。
Confidence: High

### ISSUE-002
Severity: Major
Priority: P1
Location: §5.2.2 词法检索与 BM25 倒排索引,L758(公式 L760;属本轮允许读取的上下文区,因评审焦点包含 BM25 一路描述与实现的一致性)
Category: technical/fact-error
Problem: 论文文字标注 BM25 参数 "k1=2.2",但紧随其后的公式及代码实现按标准 BM25 记号对应的有效参数是 k1=1.2——分子中的 2.2 是 k1+1。按 "k1=2.2" 用标准公式复现会得到不同的打分,论文自相矛盾。
Evidence: 论文原句:"BM25 实现取参数 k1=2.2、b=0.75",公式 "score = idf × (tf × 2.2) / (tf + 1.2 × (1 − 0.75 + 0.75 × |d|/avgdl))"。代码 backend/src/rag/bm25.rs:180-184:`denominator = tf + 1.2 * (1.0 - 0.75 + 0.75 * normalized_length)`,`score + idf * (tf * 2.2) / denominator`。标准记号 score = idf·tf·(k1+1)/(tf + k1·(1−b+b·|d|/avgdl)) 下分母系数即 k1,故实现为 k1=1.2、b=0.75;论文公式与代码完全一致,错在参数标注。
Recommendation: 将 L758 参数标注改为 "k1=1.2、b=0.75"(分子系数 2.2 = k1+1),或加一句说明本实现记号与标准记号的对应关系。
Confidence: High

### ISSUE-003
Severity: Minor
Priority: P2
Location: §5.2.3 混合检索的 RRF 融合,L777
Category: technical/impl-mismatch
Problem: 论文将三项融合微调奖励全部归入"偏精确词项查询"分支,但实现中只有"词元交集奖励"仅对偏精确查询生效;"完整查询串命中正文 +0.15"与"命中文件名 +0.10"对所有 rrf-v1 查询(含普通 1.0/1.0 权重查询)一律附加。
Evidence: 论文原句:"偏精确词项查询采用 0.25/0.75,并在融合时附加微调项:查询与候选的词元交集奖励(每命中一词 +0.02,上限 +0.12)、完整查询串命中正文内容 +0.15、命中文件名 +0.10。"代码 backend/src/rag/retrieval.rs:227-246:交集奖励 `score += (overlap * 0.02).min(0.12)` 位于 `if lexical_first` 分支内(L233-239);而 `+0.15`(L240-242)与 `+0.10`(L243-245)在该分支之外,凡 `use_rrf` 即执行。各项数值本身与代码一致。
Recommendation: 拆句表述:词元交集奖励仅用于偏精确词项查询;正文/文件名整串命中奖励对全部 rrf-v1 融合生效。
Confidence: High

## 需要人工/外部资料核验的清单
1. L775 "config snapshot 未显式冻结该权重,精确代码 revision 也未知,因此该行为标为 `INFERRED`" —— 涉及历史仓库状态与当时的 config snapshot 工件,当前工作区无法核实;需查历史 git revision / 实验归档配置。注意:0.8/0.2 的反算本身已由 `docs/experiments/rag-experiment-4.csv` 在本仓库内核实成立,无需人工核验。
