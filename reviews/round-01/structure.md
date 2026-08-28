# Structure Review — Round 01

## Review Summary
总体评分:6/10
风险等级:High
骨架完整:RQ1–3 → 需求(Ch3)→ 总体设计(Ch4)→ 方法(Ch5)→ 实现(Ch6)→ 实验(Ch7)→ 结论(Ch8)的闭环在章节层面成立,7.1 的双运行时口径统一和各章导语-小结配套是亮点;但存在两类高危缺陷——方法章核心公式式(5-3)被全文 11 处引用却从未定义、5.2 导语承诺的 5.2.5/5.2.6 两节不存在,叠加第六章图号三套并存、多处整句编辑残留与结论章依赖未确认批次,盲审可轻易抓住。

## Issues
### ISSUE-001
Severity: Critical
Priority: P0
Location: 5.2 导语(L746)与 5.2.4 融合知识图谱的检索增强策略(L781-843);引用处 1.5(L118)、5.1.4(L722)、5.4(L893)、6.5 及图 6-3/6-4(L1017/L1035/L1056)、7.9(L1456)、8.2(L1482)、8.4(L1496)
Category: structure/missing-core-method
Problem: 本文核心方法"图谱关系打分注入"对应的式(5-3)被全文 11 处引用(含系数 4.0/2.0/1.0 的消融讨论),但全文没有任何一处给出该公式的定义,已定义的公式只有式(4-1)、(5-1)、(5-2)、(7-1)–(7-5)。
Evidence: 5.2 导语称"5.2.4 节定义图谱关系的打分与注入策略",但 5.2.4 只有图 5-3 节点文字"式(5-3)单关系评分 top-10";grep 全文 "tag{5-" 仅命中 5-2,7.9 却在讨论"式(5-3)的评分系数(含权重最大的角色命中项 4.0 分)"。
Recommendation: 在 5.2.4 补出式(5-3)完整定义(评分项、权重、top-k 截断),或将 5.1.7 末段已散落的定性描述(L742)收拢改写为正式公式,并使 7.6.4 的阈值/系数敏感性与之对应。
Confidence: High

### ISSUE-002
Severity: Major
Priority: P0
Location: 5.2 导语(L746)vs 实际小节 5.2.1–5.2.4(L748-843);三层来源追溯内容混入 5.2.4 末尾(L839-843,图 5-4 在 L814-836)
Category: structure/intro-vs-actual-sections
Problem: 5.2 导语承诺"5.2.5、5.2.6 节给出权限约束下的问答执行流程和三层来源追溯机制",但实际小节只到 5.2.4;被承诺的内容被无标题地塞进 5.2.4"融合知识图谱的检索增强策略"末尾,与该节标题不符。
Evidence: grep "5\.2\.5|5\.2\.6" 全文仅命中导语 L746 一处;L839-843 的"第一层,资料来源层……第三层,评价层"直接跟在图 5-4 后,无任何小节标题;"权限约束下的问答执行流程"只在 5.2.3 末尾一段(L779)带过。
Recommendation: 二选一:补设 5.2.5(权限约束下的问答执行流程)与 5.2.6(三层来源追溯)两个小节并把现有段落移入;或改写 5.2 导语,使承诺与小节一一对应。
Confidence: High

### ISSUE-003
Severity: Major
Priority: P0
Location: 7.6.6 预注册五方法扩展批次(L1399-1417)与 7.9 实验结果分析(L1456)、8.1(L1474)、8.4(L1496)
Category: structure/evidence-conclusion-mismatch
Problem: 实验 5 批次自标 paper_ready=false、存在审计未通过项,正文也声明"不构成确认性结论",但 7.9 随即用它宣布"归因链条由此闭合",8.1/8.4 又引用其数字(exact 83.3%、F1 95.1%、配对 27 胜 0 负)作为贡献与展望依据,结论强度与证据状态错位。
Evidence: L1401"标记为 paper_ready=false……不构成确认性结论"vs L1456"归因链条由此闭合"、L1496"图谱增强 exact 83.3%、F1 95.1%,对普通 RAG 配对 27 胜 0 负"。
Recommendation: 统一降格表述:7.9 改为"归因方向获得初步印证(内部描述性证据)",8.1/8.4 引用处显式携带 paper_ready=false 限定,或把该批次数字全部移入"待完成验证"叙述。
Confidence: High

### ISSUE-004
Severity: Major
Priority: P1
Location: 第六章 6.1-6.4(L901-963)对照第七章 7.5(L1282-1295)、7.6.3(L1346-1352)、7.7 表 7-11(L1423-1430)
Category: structure/chapter-responsibility-blur
Problem: 标题为"系统实现"的第六章,前四节(约占全章 2/3)实际是实验材料与实验结果:6.2 给出金标准核验判定(TP/FP/F1),6.3 给出按答案要点规则判定的双模式对照,6.4 的四条生成记录与 7.7 表 7-11 数字完全重复,实现与实验职责互相渗透。
Evidence: 6.4"实验总结(id=55……2191 Token,9844 ms)"与表 7-11"实验总结|完成|3|7|38|2191|9844"逐项相同;6.3 L944 已解释 Q18/Q19 失败机制("一跳排序器在多关系聚合任务上不仅无效,还可能挤占上下文"),7.6.3 L1352 再次解释同一机制。
Recommendation: 第六章只保留实现载体与样例指针(截图、代码路径、接口),把带判定结论的对照与核验结果统一收敛到第七章;6.3/6.4 保留原始回答摘录但删去与 7.6/7.7 重复的判定与机制解释,改为指针引用。
Confidence: High

### ISSUE-005
Severity: Major
Priority: P1
Location: 第六章 6.5-6.6:正文引用 L740/L967/L993/L1017/L1045/L1083/L1450,素材表 L1113-1122,题注 L1124-1157
Category: structure/figure-numbering-chaos
Problem: 第六章同一组截图存在三套互斥编号:素材表写"图 6-11-7/图 6-12-8",题注写"图 6-11-10/图 6-12-11",正文引用又出现"图 6-9-9、图 6-10-11、图 6-11-11、图 6-12-12、图 6-13-13"与不带后缀的"图 6-13";跨章引用(5.1.7 L740、7.5 L1295)指向"图 6-11-11",与题注"图 6-11-10"不符。
Evidence: L1120"| 图 6-11-7 |"vs L1147"图 6-11-10"vs L1017"(图 6-11-11)";L1135-1155 题注依次为 6-8-7、6-9-8、6-10-9、6-11-10、6-12-11、6-13-12,为重编号残留。
Recommendation: 对第六章全部截图统一重编为图 6-6~图 6-13,清理所有"-N"后缀,并全文回扫 5.1.7、6.5、7.5、7.8 的引用。
Confidence: High

### ISSUE-006
Severity: Major
Priority: P1
Location: 多处:L775、L1432、L1456、L1472-1474、L1496;参数矛盾 L762 vs L893
Category: structure/duplication-and-contradiction
Problem: 至少五处整句级重复(编辑管线残留)与一处参数矛盾:式(5-2)免责声明、6.4 指针句、式(5-3)系数句、8.4 预注册流程句均连续写两遍;8.1"对照实验提供两类证据。"后紧跟变体句"实验提供两类证据。";5.4 小结写"13 组同义词展开"而 5.2.2 正文写"17 组同义词展开表"。
Evidence: L775 与 L1456 均为同句逐字连写两遍;L1472-1474"对照实验提供两类证据。/实验提供两类证据。";L762"17 组"vs L893"13 组"。
Recommendation: 全文跑一次重复句检测并逐处删除;核对同义词展开表实际条数后统一 13/17 口径。
Confidence: High

### ISSUE-007
Severity: Major
Priority: P1
Location: 1.2.1/2.1(L43/L156、L45/L154)、1.2.2/2.2(L49/L166、L53/L166)、1.2.4/2.4(L63/L186)
Category: structure/chapter-overlap
Problem: 绪论研究现状与第二章相关理论大面积重复:1.2.4 与 2.4 有三句逐字相同(ReAct、Toolformer、自主智能体综述),Self-RAG、GraphRAG/LightRAG、openBIS 的介绍在两章各写一遍,差异仅在措辞与引文密度。
Evidence: L63 与 L186:"ReAct 将推理轨迹与行动过程交替组织,使模型能在执行任务时调用外部环境并更新中间状态[13]。Toolformer 研究了语言模型学习调用外部工具的能力[14]。"两处逐字一致。
Recommendation: 按"绪论只留差距引出、第二章承担综述"分工:1.2 每个方向压缩为 2-3 句边界陈述并前跳引用第二章,删除逐字重复句。
Confidence: High

### ISSUE-008
Severity: Major
Priority: P2
Location: 7.6.6 末段"RAGAS 去人工化评测"(L1417),方法定义在 7.3(L1236)
Category: structure/content-misplacement
Problem: 实验 4(40 条回答)的 RAGAS 评测结果被放在标题为"预注册五方法扩展批次(实验 5)"的 7.6.6 小节内,与该节职责不符;读者按标题检索实验 5 的补充评测时会同节混入实验 4 结果。
Evidence: L1417"按 2.2 节引用的 RAGAS 框架……对实验 4 全部 40 条与实验 5 图谱增强臂 36 条回答运行了……",位于"#### 7.6.6 预注册五方法扩展批次(实验 5)"之下。
Recommendation: 将实验 4 的 RAGAS 结果移入 7.6.2/7.6.3(或单设 7.6.6 之前的"RAGAS 自动评测"小节),7.6.6 仅保留实验 5 自身的评测与口径说明。
Confidence: High

### ISSUE-009
Severity: Minor
Priority: P2
Location: 7.7 表 7-11(L1423)出现在 7.6.5 表 7-12(L1386)、7.6.6 表 7-13(L1403)之后
Category: structure/table-numbering-order
Problem: 第七章表编号与出现顺序不一致:表 7-12、7-13 先于表 7-11 出现,破坏"按出现顺序编号"的惯例。
Evidence: L1386"如表 7-12 所示"、L1403"如表 7-13 所示"均在 L1423"如表 7-11 所示"之前。
Recommendation: 将 7.7 的表改为表 7-12、后续顺延,或整体重排第七章表号并回扫引用。
Confidence: High

### ISSUE-010
Severity: Minor
Priority: P2
Location: 5.2.4 图 5-3 与图 5-4 的 latex 代码块(L787-836)
Category: structure/markdown-fence-broken
Problem: 图 5-3 的 ```latex 围栏未在 `\end{center}` 后闭合,图 5-4 的 ```latex 开栏行落在未闭合围栏内部,两块被合并为单个代码块,渲染时内嵌围栏行成为字面文本,两张图都会损坏。
Evidence: L787 开栏后,直至 L836 才出现首个闭合围栏,L814(图 5-4 的"```latex")位于其中。
Recommendation: 在图 5-3 的 `\end{center}` 之后补闭合围栏,使两图各自成块。
Confidence: High

### ISSUE-011
Severity: Minor
Priority: P2
Location: 5.1.4 式(5-1)讨论段末句(L722)
Category: structure/revision-note-leak
Problem: 正文混入修订过程自评语言"早期把置信度写成 1.0/0.8/0.6 三档经验参数的做法既与实现不符,也缺乏实验依据,应予纠正",属于对旧稿的修订指令而非论文论述,类似残留还见于 5.2.3 对"历史 legacy 原型材料"的两遍免责声明。
Evidence: L722 末句原文如上;"应予纠正"的祈使语气与论文陈述体不符。
Recommendation: 删除该句,如需保留演变说明,改为客观陈述"本文最终实现采用两档来源标注"即可。
Confidence: High

### ISSUE-012
Severity: Minor
Priority: P2
Location: 7.10 本章小结首句(L1462);附录 B.1 导语(L1531)
Category: structure/crossref-misplacement
Problem: 7.10 小结首句"本章说明了系统实现"错误描述本章职责(系统实现是第六章);附录 B.1"正文第六章只保留方法复现所需的数据域说明"指向错误——数据域说明实际位于 4.5 节。
Evidence: L1462"本章说明了系统实现,并建立了……评价";L1531"正文第六章只保留方法复现所需的数据域说明"。
Recommendation: 7.10 首句改为"本章建立了系统测试与实验评价";附录 B.1 的"第六章"改为"第四章 4.5 节"。
Confidence: High

## 结构评分与最严重三个问题
- 评分:6/10(章节骨架与 RQ 闭环完整、口径纪律好,但核心公式缺失、导语与实际小节脱节、编号系统与编辑残留多处失守,盲审风险集中在方法章与图表编号)
- TOP3:ISSUE-001, ISSUE-002, ISSUE-003
