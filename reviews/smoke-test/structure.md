# Structure Review — Round 00 (Smoke Test)

Scope: §5.2.3 混合检索的 RRF 融合(L764-780),上下文 §5.2 导语(L744-763)、§5.2.4 开头(L781-800)。

## Review Summary
总体评分:5/10
风险等级:Medium
小节技术细节扎实,但结构存在三处硬伤:导语承诺的 5.2.5/5.2.6 小节不存在、节内历史考证压过当前方法且问题定义缺位、尾段执行流程越界并与 5.2.4 图 5-3 重复。

## Issues
### ISSUE-001
Severity: Major
Priority: P0
Location: 5.2 导语 L746,对照实际标题结构(5.2.4 止于 L814,5.3 起于 L845)
Category: structure/broken-outline
Problem: 5.2 导语承诺"5.2.5、5.2.6 节给出权限约束下的问答执行流程和三层来源追溯机制",但全文不存在 5.2.5/5.2.6 小节,5.2.4 之后直接进入 5.3;"三层来源追溯机制"在全文中仅此一处提及。
Evidence: L746 "5.2.5、5.2.6 节给出权限约束下的问答执行流程和三层来源追溯机制";grep 全文确认无 "#### 5.2.5"/"#### 5.2.6" 标题。
Recommendation: 按导语补齐 5.2.5/5.2.6 两个小节(问答执行流程、三层来源追溯),或将导语改写为与实际小节一致的规划;目录与正文不一致是盲审易发现的硬伤。
Confidence: High

### ISSUE-002
Severity: Major
Priority: P1
Location: 5.2.3 混合检索的 RRF 融合, L764-775
Category: structure/method-before-problem
Problem: 小节标题对应的方法是当前 RRF 融合,但正文约一半篇幅(L766-775)先给出历史 legacy 加权公式(5-2)及其 INFERRED 考证,当前方法被压到 L777;且全节未定义"为何需要分数融合、为何选 RRF 而非加权"的问题,公式先于问题定义出现。
Evidence: L766 开篇即"历史实验/legacy 原型材料曾以向量分数与词项分数的加权形式描述资料融合";L775 同一句"式(5-2)不是当前 Rust 默认实现……以各自实际工件为准"连续重复出现两次(编辑残留);5.2.2 仅铺垫了词法通道动机,未铺垫融合问题。
Recommendation: 开篇先用 1–2 句定义融合问题(两路异构分数量纲不可直接比较等),再给 RRF 方法;式(5-2)历史考证压缩为脚注或移至第 7 章实验对照处,并删除 L775 重复句。
Confidence: High

### ISSUE-003
Severity: Major
Priority: P1
Location: 5.2.3 混合检索的 RRF 融合, L779(尾段);对照 5.2.4 L783-785、图 5-3 L793-808
Category: structure/responsibility-overflow
Problem: 尾段"项目级 RAG 流程"描述完整问答执行链路(权限校验→数据集检查→混合检索→构造输入→调用 DeepSeek→保存日志),超出"RRF 融合"的单一职责,与导语承诺的 5.2.5 职责重叠,也与 5.2.4 图 5-3 的共享链路内容重复。
Evidence: L779 "项目级 RAG 流程包括:校验项目权限;检查本地数据集;执行混合检索;构造带证据编号的模型输入;调用 DeepSeek 官方接口;保存回答、来源、检索配置、Token 用量和响应耗时";图 5-3 中"项目权限校验→项目内混合检索→资料证据 top-6 [S1]…[Sn]→DeepSeek 生成→ai_query_logs 回存"为同一链路。
Recommendation: 尾段仅保留"按 RRF 得分降序选 top-k 并分配 [S1]…[Sn] 引用编号"这一与融合直接相关的收尾;执行流程整体移交 5.2.5(补齐后),避免与 5.2.4 图 5-3 重复。
Confidence: High

## 结构评分与最严重三个问题
- 评分:5/10(单小节技术描述准确,但导语-正文结构不闭合、节内主次颠倒、尾段越界三处结构缺陷叠加,盲审观感受损)
- TOP3:ISSUE-001, ISSUE-002, ISSUE-003
