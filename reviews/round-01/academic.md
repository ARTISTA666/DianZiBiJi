# Academic Review — Round 01

## Review Summary
总体评分:6/10
风险等级:High
主张-证据纪律在同类工程论文中属上乘(INFERRED/CONFIRMED 口径标注、边界声明、工件均可回查),但三处 P0 级缺口直接动摇盲审立足点:核心创新点二的技术内核式(5-3)全文无定义,头部定量结论(4→14、p=0.0020)建立在事后答案规则之上却配了推断统计,7.9 用自标 paper_ready=false 的内部批次宣布"归因链条由此闭合";另有点三创新中创新点三的验证声明超出实际测试证据、生成与评判同源等评价独立性问题。

## Issues
### ISSUE-001
Severity: Critical
Priority: P0
Location: 1.5 核心创新点二(L118)、5.2 导语(L746)与 5.2.4(L781-843)、7.9(L1456)、8.4(L1496)
Category: academic/claim-without-method-definition
Problem: 核心创新点二"可审计证据链上的融合检索与受约束生成"把"按式(5-3) 注入一跳关系证据"列为其技术内核,7.9 与 8.4 还在讨论该式的系数消融(角色命中项 4.0/2.0/1.0),但全文没有任何一处给出式(5-3)的定义,已编号公式仅 4-1、5-1、5-2、7-1~7-5。
Evidence: L118"并按式(5-3) 注入一跳关系证据";L1456"式(5-3)的评分系数(含权重最大的角色命中项 4.0 分)尚未消融";grep 全文 "tag{5-" 仅命中 5-2,5.2.4 节内无公式。
Recommendation: 在 5.2.4 补出式(5-3)完整定义(评分项、各权重、top-k 与阈值),否则创新点二的主张无法被评审复核,8.4 的系数消融计划也失去对象。
Confidence: High

### ISSUE-002
Severity: Major
Priority: P0
Location: 7.6.1 答案规则(L1303)、7.6.2 表 7-8 与 McNemar(L1307-1323)、摘要(L9)
Category: academic/post-hoc-evaluation-with-inferential-statistics
Problem: RQ2 的头部定量结论(完成 4 vs 14)依据回答生成之后才建立的答案要点规则,论文自认"规则制定者可能已经接触回答内容,存在循环设计和评价偏差风险";在此前提下报告 McNemar 精确检验 p=0.0020 属推断统计误用——事后构建的判定规则不满足显著性检验的前提,p 值制造了证据不支撑的确证感。
Evidence: L1303"正式问答运行于 2026 年 6 月 12 日 00:12 完成,答案规则文件于同日 19:31 后生成";L1323"McNemar 精确检验 p=0.0020"。缺的证据:运行前冻结的答案规则或已签核的独立盲评(两者论文均承认未完成)。
Recommendation: 正文将 p=0.0020 降级为附录中的描述性不一致计数并注明其统计前提不成立,主文只报告覆盖数与逐题对照;显著性结论留给预注册复现实验。
Confidence: High

### ISSUE-003
Severity: Major
Priority: P0
Location: 7.6.6(L1399-1417)、7.9(L1456)、8.1(L1474)、8.4(L1496)
Category: academic/conclusion-on-unconfirmed-evidence
Problem: 实验 5 批次自标 paper_ready=false 且存在审计未通过项(证据标记越界、检索绑定字段缺失),正文亦声明"不构成确认性结论",但 7.9 用它宣布"归因链条由此闭合",8.1/8.4 复用其数字(exact 83.3%、F1 95.1%、27 胜 0 负)支撑贡献与展望;同时"预注册协议(v2 及其五项目修订)"经五次修订后是否仍满足预注册语义未作说明,"预注册"标签可能使读者高估证据等级。
Evidence: L1401"paper_ready=false……因此以下数字仅用于方法学诊断,不构成确认性结论"vs L1456"归因链条由此闭合";L1399"预注册协议(v2 及其五项目修订)"。缺的证据:该批次的签核化(paper_ready 化)记录与协议修订冻结说明。
Recommendation: 7.9 改为"内部描述性证据初步印证归因方向",8.1/8.4 引用处显式携带 paper_ready=false 限定,并补充协议五次修订的时间线与冻结说明。
Confidence: High

### ISSUE-004
Severity: Major
Priority: P1
Location: 1.5 核心创新点三(L120)对照 7.2 表 7-2(L1191-1197)与 7.7(L1432)
Category: academic/verification-claim-exceeds-evidence
Problem: 创新点三的实质机制是"12 个受控工具的五项安全属性分级、高风险动作人工确认队列与幂等键防重放",但所列验证(生成-来源对账、只读成员拦截)均不覆盖这些机制;第七章无任何确认队列拦截、幂等重放返回缓存或风险分级判定的测试条目,7.7 亦自述"只验证四类任务能生成并保存证据"。
Evidence: L120"验证:四类任务的生成-来源对账、只读成员拦截测试(7.7 节)";L1432"该实验只验证四类任务能生成并保存证据";表 7-2 安全边界行仅覆盖搜索/通知/仪表盘隔离。缺的证据:agent_pending_actions 拦截与 tool_execution_keys 防重放的专项测试结果。
Recommendation: 补充确认队列与幂等重放的自动化测试并写入 7.2,或将创新点三的验证表述收窄到已有证据实际覆盖的范围。
Confidence: High

### ISSUE-005
Severity: Major
Priority: P1
Location: 1.5 三项创新点的验证表述(L116-120)、8.2(L1480-1484)对照 7.1(L1173-1185)
Category: academic/claim-evidence-runtime-mismatch
Problem: 三项创新均描述当前 Rust 系统,但其核心质量证据(20 题对照、四臂消融、RAGAS)产生于迁移前的 legacy FastAPI 批次;摘要与 7.1 已明确该边界,而 1.5 与 8.2 的验证表述未携带任何运行时限定,读者会把"4→14、覆盖 3→12"直接读作所交付系统的实验结果。
Evidence: L118"验证:20 题成对实验完成任务 4→14、证据覆盖 3→12……"(无 legacy 限定);摘要 L9"报告的对照实验在迁移前的 legacy FastAPI 原型批次上完成"。缺的证据:当前 Rust 系统上复现核心对照实验的结果。
Recommendation: 在 1.5 与 8.2 各验证句末统一补"(legacy 批次,见 7.1)"类限定;中期能在 Rust 系统上重跑一次同口径对照以消除该错位。
Confidence: High

### ISSUE-006
Severity: Major
Priority: P1
Location: 7.3 评价协议(L1236)、7.6.6 RAGAS 段(L1417)、7.7 盲评现状(L1434)
Category: academic/evaluator-independence
Problem: 回答生成与 LLM 评判同为 deepseek-v4-flash,存在同源自评;判定器的校准门槛是与事后规则化判定"逐题一致",使 RAGAS 结果继承事后规则偏置;以 MT-Bench 上 GPT-4 与人工一致率 85% 对 81% 的通用域结论[115]作为本封闭小语料场景"去人工化协议为主"的依据,外推缺乏直接证据。准确性维度最终无任何已签核人工证据。
Evidence: L1236"judge 为 deepseek-v4-flash……逐题一致方可用于新批次";L1434"盲评表中的人工评分与签名列仍为空白"。缺的证据:独立第三方评判或已签核人工评分。
Recommendation: 将 LLM-judge 明确定位为"先导性、非确认性"证据线,主结论措辞避免"准确/忠实"级别断言;完成至少一份盲评签核后再保留"评价协议以去人工化为主"的表述。
Confidence: High

### ISSUE-007
Severity: Major
Priority: P1
Location: 1.5 创新点一(L116)、1.2.2(L53)、表 1-1(L69-74)
Category: academic/unsupported-comparative-claims
Problem: "该机制……是通用 RAG 框架不具备的"(L116)是对整个方法类的否定性比较主张,仅有表 1-1"文献未报告"式的文献推断支撑,无系统对比或综述级引证;与 GraphRAG/LightRAG/GraphSearch 的差异只有理论性能力陈述,没有任何同语料对照实验,1.2.2"不能以'更轻量'为由回避比较"之后也确实未给出比较。
Evidence: L116 原句如上;L53"本文把它们作为能力参照……理论上无法完成需要社区级概括、多跳路径或代理式扩展的问题"。缺的证据:支撑"不具备"的引文定位或一项最小对照(如同语料运行 GraphRAG)。
Recommendation: 将"是通用 RAG 框架不具备的"改写为"在本文所综述的代表性 RAG 文献中未见报告(表 1-1)",与表 1-1 口径对齐;GraphRAG 差异保持"能力参照"表述并删去防御性语句。
Confidence: High

### ISSUE-008
Severity: Major
Priority: P2
Location: 2.2(L166)、参考文献[14](L1664)、[21](L1678)、[72](L1780)、[116](L1866)
Category: academic/citation-accuracy
Problem: 引文与内容错配:2.2"Trivedi 等把链式思维推理与检索过程交替进行……[21]"所引 [21] 为 Wei 等 CoT 论文,Trivedi 的交错检索工作实为 [72];参考文献 [14] Toolformer 的作者表(首列 Cancedda、含 Hambro E)与原文献(第一作者 Schick,无 Hambro)不符;[116](Gao 等,citations 生成)列入文献表但正文无任何引用点。
Evidence: L166 与 L1678、L1780 对照;L1866 [116] 仅出现在文献表。缺的证据:与原文一致的作者表与引用对应关系。
Recommendation: 将 L166 的引号改为 [72];核对 [14] 作者顺序与名单;删除 [116] 或在正文(如 5.2 受约束生成处)补引。
Confidence: High

### ISSUE-009
Severity: Minor
Priority: P2
Location: 6 章导语(L899)、6.7(L1161)、5.1.4(L722)、1.2.2(L53)、7.9(L1456)
Category: academic/register-and-revision-residue
Problem: 多处语体不符合学位论文客观陈述规范:"看得见的证据""系统不是纸面设想"为口语化强调,"早期把置信度写成 1.0/0.8/0.6 三档经验参数的做法……应予纠正"是修订指令残留,"不能以'更轻量'为由回避比较""归因链条由此闭合"为论辩性表述。
Evidence: L899"以'看得见的证据'呈现系统实现";L722 末句"应予纠正"。
Recommendation: 统一改为陈述语体(如"以可复核的实物证据呈现"),删除修订指令句与论辩句。
Confidence: High

### ISSUE-010
Severity: Minor
Priority: P2
Location: 7.8 场景化验证与审计追溯(L1438-1450)
Category: academic/verification-without-metrics
Problem: 7.8 以"验证"命名,但内容为四类角色操作流程的文字重述,与 7.2 浏览器端到端走查场景重叠,无任何独立量化产出或新证据;末段"该流程对应课题组……典型场景"亦无使用数据支撑。
Evidence: L1438-1448 四段角色描述均无指标;L1201 已报告的走查场景与之重合。缺的证据:场景通过率、耗时或差异于 7.2 的新验证记录。
Recommendation: 将 7.8 压缩为 7.2 走查的场景索引,或补充各场景的通过/失败计数与对应测试脚本名。
Confidence: High

### ISSUE-011
Severity: Minor
Priority: P2
Location: 摘要(L7-11)、1.4/1.5(L96-124)、8.1/8.2(L1468-1488)
Category: academic/redundant-contribution-restatement
Problem: 三项创新点在 1.5 与 8.2 以近乎相同的结构完整重述两次,验证数字(4→14、3→12、10%/20%/70%/55%、78.6%)在摘要、1.5、7.6/7.9、8.1、8.4 至少五处整组重复,稀释了贡献陈述并放大数字间口径不一致的暴露面。
Evidence: L118 与 L1482 逐条对应;四臂完成率在 L9、L118、L1388-1393、L1456、L1474、L1496 重复出现。
Recommendation: 8.2 仅保留创新点名与一句验证指针(引用 7.x 节),数字集中在一处陈述。
Confidence: High

### ISSUE-012
Severity: Minor
Priority: P2
Location: 6.1(L914)对照 7.5(L1273-1280)、6.4/7.7 阶段报告来源
Category: academic/corpus-reproducibility-gap
Problem: 项目一 15 条笔记中有 11 条"没有独立保存的种子源文件,其存在性由阶段报告智能体工件……佐证,完整正文需回溯当时的数据库实例方能复现",而这 11 条进入 35 条语料基数、357 实体/445 关系全库统计与阶段报告(15 条来源笔记)的证据链,削弱"读者可按路径复核"的全文承诺。
Evidence: L914 原文如上;6 章导语(L899)称"读者可按路径复核"。缺的证据:该 11 条笔记的数据库导出存档或等价种子文件。
Recommendation: 导出当时的笔记记录为离线存档(含哈希)补入附录,或在正文明确该 11 条不参与任何结论性统计。
Confidence: High

## 最严重三个问题
- TOP3:ISSUE-001(式(5-3) 未定义,核心创新不可复核), ISSUE-002(事后答案规则配 McNemar 推断统计), ISSUE-003(以 paper_ready=false 批次宣布归因闭合)
