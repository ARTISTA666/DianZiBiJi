# Technical Review — Round 06

评审对象:`docs/毕业论文重构稿.md`(1949 行,scope:全文,技术密集章节 Ch2/4/5/6/7)
代码对照:`backend/sql/0001_initial.sql`、`backend/src/permissions.rs`、`backend/src/rag/graph.rs`、`backend/src/rag/bm25.rs`、`backend/src/api/mcp.rs`
说明:本报告由证据线主会话在两个技术评审子代理连续无产出后按同一角色定义直接执行(定点核实约 20 处)。创新评审代理已先行完成大量代码比对(式(5-3) 系数与 `rag/graph.rs:452-494` 逐项一致、BM25 公式与 `bm25.rs:183-184` 一致、12 工具注册表与 `api/mcp.rs` 一致、知识门禁 `knowledge_graph.rs:340` 仅处理 APPROVED),本报告独立复核了其中关键项并补充新发现。

## Review Summary
总体评分:7.5/10
风险等级:Medium
技术描述与代码实现总体对齐良好:式(5-3) 评分系数、BM25 参数(k1=2.2/b=0.75)、12 个受控工具五项安全属性、userrole 枚举、审核门禁链路均可逐条在代码中定位;第七章对 legacy 批次与 Rust 交付系统的口径分离(表 7-1)是诚实且清晰的处理。遗留的主要技术性问题集中在:一处口径自相矛盾(7.6.6"五个项目…180 案例"vs 同节"单项目 12×5×3=180")、第五章混入界面实现细节(5.1.7)、需求-设计角色模型不对齐(GROUP_LEADER/PI)、以及少量图文/表述残留。全部 Major 均为文字层可修复;没有发现"听起来高级但未实现"的虚构描述。

## Issues

### ISSUE-001
Severity: Critical
Priority: P0
Location: 7.6.6 首段 L1479 vs 同节第二段 L1481(表 7-12 上下文);扩散至 7.9 L1534"五项目"、摘要 L9、8.2 L1558
Category: technical/fact-error(口径自相矛盾)
Problem: L1479 称实验 5"五种方法在五个项目……下完成 180 个案例",L1481 立即给出"GSE111619 内部题集(12 题 × 5 方法 × 3 重复 = 180 案例)"——同节内两句话直接矛盾。证据文件证实 180 案例为单项目批次(`docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md` L67"单一公开 GEO 项目、12 个问题、5 种方法、3 次重复,共 180 个计划案例";L68 CSV 实际 180 行)。五项目正式批次(run 20/21/23/24/25,各 100 案例)另存于 `agent-work/reports/status-2026-08-16-paper-blockers.md`,未纳入论文表格。L1534 与摘要 L9 的"27 胜 0 负"均出自该单项目 180 案例批次,却以"五项目/预注册五方法扩展批次(180 个案例)"口径引用。
Evidence: 论文 L1479 vs L1481;证据文件 L67-68。
Recommendation: Editor 文字代劳——将 L1479 的设计描述改写为如实两段口径:该批次按预注册协议(草案)在 GSE111619 内部题集上运行 12 题×5 方法×3 重复=180 案例;五项目修订批次已完成运行与证据包但尚未通过外部签署与版本绑定门禁,其结果未纳入本文表格。L9/L1534/L1558 同步修正归属。数字本身(180、27 胜 0 负)不动,仅修正其归属口径。
Confidence: High

### ISSUE-002
Severity: Major
Priority: P1
Location: 4.2 L456、L470-481(表 4-1);对照 3.1 L219-223(表 3-1)
Category: technical/arch-inconsistent(需求-设计角色不对齐)
Problem: 4.2 的 `userrole` 枚举含 `PI` 与 `GROUP_LEADER` 两个系统级角色,其中 `GROUP_LEADER` 全文仅此一处、无任何需求来源与解释(3.1 的两层角色模型与表 3-1 均为五类,无 PI/GROUP_LEADER);PI 的"非敏感项目读取豁免"作为权限判定式(4-1)的独立分支出现在设计章,需求章无对应需求条目。
Evidence: `backend/sql/0001_initial.sql:95-102` 枚举确含两者(论文如实反映代码);`backend/src/permissions.rs` 中无 GROUP_LEADER 专属判定逻辑(grep 无命中)。
Recommendation: Editor 文字代劳——在 4.2 枚举首次出现处补一句说明:PI 为全局课题组负责人角色,对非敏感项目有读取豁免(业务动因:负责人需跨项目巡检),GROUP_LEADER 为 schema 保留枚举、当前判定逻辑未使用(与代码一致,`permissions.rs` 无其专属分支)。或最小化:仅补 PI 一句、标注 GROUP_LEADER 为保留值。数字与式(4-1) 不动。
Confidence: High

### ISSUE-003
Severity: Major
Priority: P1
Location: 5.1.7 L757-761;对照 6.2 L978、6.5 L1063
Category: technical/content-misplacement
Problem: 5.1.7(方法章)整段描述图谱可视化页面的 UI 细节(顶部统计、SVG 绘制、双筛选器、节点跳转),属第六章实现/界面内容,且与 6.2、6.5 形成三处同内容重复;方法章自身贡献(基于关键词+关系类型提示词的轻量关联检索)反而被淹没。
Evidence: L759"页面顶部展示实体总数、关系总数……以 SVG 方式绘制关系图……实体类型筛选器和关系类型筛选器……直接跳转到对应的实验笔记详情页面";6.5 L1063"前端以 SVG 渲染并支持类型筛选与节点详情跳转(图 6-11)"。
Recommendation: Editor 文字代劳——5.1.7 保留方法段(关键词+提示词评分+前 N 条,指向式(5-3))与"可视化界面见 6.5 节(图 6-11)"指针,删除 UI 细节句;6.2/6.5 单处保留界面描述。
Confidence: High

### ISSUE-004
Severity: Major
Priority: P1
Location: 2.2 末段 L185、2.3 末段 L189-195、2.4 末段 L195(第二章)
Category: technical/layering(实现细节前置)
Problem: 第二章各节末尾给出具体数据库表名(`kg_entities`/`kg_relations`/`kg_extraction_runs` L189、`agent_generation_runs` L195)与实现选型细节,先于需求章(第三章)与设计章(第四、五章)出现,违反"理论章给原理与设计启示"的章节分工;且 2.3 末段的实体/关系枚举与 5.1 节的九类实体八类关系定义重复。
Evidence: L189"本文系统使用关系数据库保存项目级知识图谱,包括 `kg_entities`、`kg_relations` 和 `kg_extraction_runs` 三类核心表";L195"把来源信息写入 `agent_generation_runs` 表"。
Recommendation: Editor 文字代劳——2.2/2.3/2.4 末段改为一句"设计启示/本文取向"(如 2.3 末改"本文在第五 5.1 节给出上述建模的具体 schema 与抽取流程,此处不展开实现细节"),删除具体表名;表结构本就由 4.5/6.1 覆盖。
Confidence: High

### ISSUE-005
Severity: Major
Priority: P1
Location: 6.3 L988-991;对照 7.6.3 L1420-1432、7.9 L1532-1534
Category: technical/layering(实现章承担实验章结论)
Problem: 第六章自称"机制分析在第七章展开"(L980),但 6.3 末两段给出三臂对照的机制性结论句("三臂对照把 RAG 的价值刻画得更完整……裸 LLM 的短板不是答不出,而是答了无法核对";"一跳排序器在多关系聚合任务上不仅无效,还可能挤占上下文")——均为 7.6.3/7.9 层级的分析结论,实现章越位且与第七章部分重复。
Evidence: L988、L990-991 原文。
Recommendation: Editor 文字代劳——6.3 保留原始回答摘录与最简现象描述,机制结论句改为指针("这一现象的机制归因与三臂对照的完整分析见 7.6.3 节与 7.9 节")。
Confidence: High

### ISSUE-006
Severity: Minor
Priority: P2
Location: 摘要 L9、8.1 L1548(修复后 F1=100% 的引用位置)
Category: technical/circular-evidence(表述可被误读)
Problem: "修复后 F1=100%"的生成路径是:核验发现 1 条 FP→按金标准修正数据库→复检满分(7.5 L1371 如实披露)。该数字作为"抽取可靠"的证据出现在摘要与 8.1 时,未随附"修复后"循环性质的口径,盲审易读为独立验证满分;7.5 的诚实表述反而未传导到摘要。
Evidence: L1371"修复批次将该实体归并为'cDNA 样本 2'后复检,52 条关系全部命中金标准";摘要 L9"TP=52、FP=1、FN=0(修复后 F1=100%)"。
Recommendation: Editor 文字代劳——摘要与 8.1 引用处将"(修复后 F1=100%)"改为"(修复后 F1=100%,修复指按金标准归并 1 条误抽实体,见 7.5 节)"或在 F1 后加"数据校正后的一致性记录"定位词,防止读成独立验证。数字不动。
Confidence: High

### ISSUE-007
Severity: Minor
Priority: P2
Location: 7.7 L1510-1512;对照 1.5 L121、8.2 L1560
Category: technical/evidence-scope
Problem: 创新点三的验证层为功能性/安全性证据(生成-来源对账 n=1 每类、只读拦截、3 项集成测试),无生成内容忠实度/质量度量(7.7 自认"内容忠实度未做独立评分");但 1.5/8.2 的"验证证据"句式未把验证性质(功能与安全验证)与验证范围(不含生成质量)分开,存在被读作"生成质量已验证"的空间。
Evidence: L1510"该实验只验证四类任务能生成并保存证据;内容忠实度未做独立评分"。
Recommendation: Editor 文字代劳——1.5 L121 与 8.2 L1560 的"验证证据"句补性质限定(如"经四类任务的生成-来源对账与权限拦截等功能与安全验证(7.7 节),生成内容的忠实度评价不在本轮验证范围")。
Confidence: High

### ISSUE-008
Severity: Minor
Priority: P2
Location: 7.9 L1534
Category: technical/overclaim(措辞超出证据)
Problem: "评价独立性由判定器复现校验与以自动化评价为主的评价协议(7.3 节)保障"——判定器复现校验证明评分器与原规则一致,不产生独立性;judge(deepseek-v4-flash)与生成端同族(7.6.6 L1495 自认"单一 judge 存在自我偏好风险");人工盲评未签核。三项均非独立性证据,"保障"一词过强。
Evidence: L1534 vs L1495、7.3 L1310。
Recommendation: Editor 文字代劳——降格为"评价可信度由判定器复现校验部分支撑;评价独立性缺口(同族 judge、人工盲评未签核)已在 7.3、7.6.6 节明示,由后续独立盲评闭合"。
Confidence: High

### ISSUE-009
Severity: Minor
Priority: P2
Location: 5.2.2 L777("按经典公式")
Category: technical/concept-precision
Problem: 公式为 BM25 变体(分母饱和常数 1.2 硬编码、无 (k1+1) 因子),与实现逐项一致(`bm25.rs:183-184`),但"经典公式"措辞会让熟悉标准 Okapi BM25 的评审以为式子写错;问题在措辞不在公式。
Evidence: L779 公式 vs `backend/src/rag/bm25.rs:183-184`。
Recommendation: Editor 文字代劳——"按经典公式"改"按实现采用的 BM25 变体形式(与代码一致,分母饱和常数为实现选择)";公式本体与本轮红线均不动。
Confidence: High

### ISSUE-010
Severity: Minor
Priority: P2
Location: 第七章开头 L1211;7.8 L1516
Category: technical/reference-residue
Problem: 两处表述残留:L1211"本章按第七章开头声明的同一问题链检验"为自指(该句即章首);L1516"前三节从测试与实验角度验证"——7.8 之前实有 7.2-7.7 六节,"前三节"指代不明。
Evidence: 原文见 writing 报告 ISSUE-009 同位置核对,一致。
Recommendation: Editor 文字代劳——L1211 改"本章按开头声明的同一问题链检验";L1516 改"7.2-7.7 节从测试与实验角度验证"(若原意为 7.5-7.7 则写明)。
Confidence: High

## 需要人工/外部资料核验的清单
1. 摘要 L9 与 8.2 L1558 引用 paper_ready=false 批次的"27 胜 0 负"无限定语——属证据状态管理问题(学术线 ISSUE-001 同源),Editor 加限定语后仍建议作者决策是否在摘要保留该数字。
2. `GROUP_LEADER` 枚举保留值是否有历史业务含义(需求侧)——已确认代码无专属判定分支,论文侧按"保留值"披露即可,无需代码变更。
3. MT-Bench 85% 一致率([115])的引用条件是否与本文用法一致——需人工核对文献。
4. 式(5-3) 系数消融、Rust 侧重跑——需新增实验,超出本轮修改范围(8.4 已列为后续工作)。
