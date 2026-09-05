# Readability&Focus — ch1

评审范围:`docs/毕业论文重构稿.md` L1-150(摘要、Abstract、第一章绪论至 1.6 组织图开头;图内 TikZ 代码不评)。规则:`.zcode/skills/qu-ai-wei/SKILL.md` + `references/pattern-catalog.md`,叠加"表述过于晦涩""没有重心"两条用户标准。硬红线已遵守:数字、引文 [n]、术语与缩写全称、式(5-3)、[S]/[G] 编号全部原样未动;诚实性限定语(数据校正口径、内部诊断口径、盲评待签核等)语义与强度不变,仅可移位;摘要三问三答、1.3 三子问题、1.5 三创新的问题链结构未拆,只做句内拆句、重心前置与分段。按改善幅度降序,共 10 条。

## Issues

### 1. L13(摘要第二问)— 约 290 字一句,破折号/分号两层嵌套,收益结论被埋

- **Location**:L13,"第二"整段主体句(冒号后至句号前为一句)
- **原句**:第二,关系型问题的证据缺失可由图谱补足:在以项目一封闭语料为对象、资料通道为近乎空载 SOP 提要的对照条件下(三个场景合计 35 条已审核笔记、357 个实体、445 条关系),普通 RAG 与图谱增强 RAG 分别完成 4 题和 14 题(McNemar p=0.0020),18 个事实型任务的证据覆盖数 3 对 12、与完成数完全一致——收益来自图谱补进了资料检索覆盖不到的证据结构,代价仅 103.20 ms 与 325.70 Token;消融基线(裸 LLM 10%、直接 SQL 在可查子集 78.6%)进一步确定图谱增强与直接 SQL 是互补而非替代,按预注册协议草案运行的单项目五方法扩展批次并以独立题集复现了同一方向(图谱增强对普通 RAG 零恶化,内部诊断口径,见 7.6.6 节)。
- **问题类型**:晦涩 a(全篇最重:破折号与分号内各含括号组、长状语前置压住主干)+ 没重心 a/d(收益机制结论埋在 290 字句中段;一句塞入条件、结果、收益、消融、复现五个重心)。
- **改写句**:第二,关系型问题的证据缺失可由图谱补足。对照在项目一封闭语料上进行,资料通道为近乎空载 SOP 提要(三个场景合计 35 条已审核笔记、357 个实体、445 条关系)。在此条件下,普通 RAG 与图谱增强 RAG 分别完成 4 题和 14 题(McNemar p=0.0020),18 个事实型任务的证据覆盖数为 3 对 12,与完成数完全一致——收益来自图谱补进了资料检索覆盖不到的证据结构,代价仅 103.20 ms 与 325.70 Token。消融基线(裸 LLM 10%、直接 SQL 在可查子集 78.6%)进一步确定图谱增强与直接 SQL 是互补而非替代。按预注册协议草案运行的单项目五方法扩展批次以独立题集复现了同一方向(图谱增强对普通 RAG 零恶化;内部诊断口径,见 7.6.6 节)。
- 说明:论断句独立成主题句后接条件、结果、消融、复现四句;全部数字与括号注原样,破折号收益句原位保留;"并以独立题集复现"跨句后删去"并","内部诊断口径"前逗号升为分号。

### 2. L7(摘要第二段首句)— 约 150 字五重一套句,"组织为"缺行动者

- **Location**:L7,第 1 句
- **原句**:系统以项目为隔离边界,笔记、资料、人员、实验类型、试剂、仪器、样本与结果组织为带来源编号的一跳关系,实验笔记的业务审核状态是 AI 可用知识的前置条件——只有审核通过的记录才进入知识层,回答中的每项事实以 [S]/[G] 编号([S] 指资料来源块,[G] 指图谱关系)引用资料块或图谱关系,语料哈希、提示版本、Token 与时延全程固定留痕。
- **问题类型**:晦涩 a/b(破折号内含定义括号,五个独立断言一逗到底,读者需回找主干)+ 没重心 d。
- **改写句**:系统以项目为隔离边界,将笔记、资料、人员、实验类型、试剂、仪器、样本与结果组织为带来源编号的一跳关系。实验笔记的业务审核状态是 AI 可用知识的前置条件:只有审核通过的记录才进入知识层。回答中的每项事实以 [S]/[G] 编号引用资料块或图谱关系([S] 指资料来源块,[G] 指图谱关系),语料哈希、提示版本、Token 与时延全程固定留痕。
- 说明:按"边界与建模 / 审核门禁 / 引用与留痕"三件事拆为三句;"将"补出行动者,破折号改冒号;[S]/[G] 定义括号原样随迁。

### 3. Abstract L25 "Second" 句 — 约 140 词一句,分号+括号+破折号两层嵌套

- **Location**:L25,"Second" 一句
- **原句**:Second, the evidence gap on relation-seeking questions is closed by the graph: on a closed-corpus comparison over project 1 with a near-empty SOP digest document channel (35 approved notes, 357 entities, and 445 relations across the three scenarios), plain RAG and graph-enhanced RAG complete 4 and 14 tasks respectively (McNemar p=0.0020), with evidence coverage of 3 versus 12 on the 18 factual questions exactly matching completion—the gain comes from the graph supplying evidence that document retrieval cannot cover, at a cost of only 103.20 ms and 325.70 tokens; ablation baselines (bare LLM 10%, direct SQL 78.6% on its answerable subset) further establish that graph enhancement and direct SQL are complementary rather than substitutes, and a single-project five-method extension batch run under the draft pre-registration protocol reproduced the same direction on an independent question set (no degraded pairs against plain RAG; internal diagnostic scope, Section 7.6.6).
- **问题类型**:晦涩 a(英文侧最重,与中文 L13 同源:分号前后各含括号与破折号)。
- **改写句**:Second, the evidence gap on relation-seeking questions is closed by the graph. On a closed-corpus comparison over project 1 with a near-empty SOP digest document channel (35 approved notes, 357 entities, and 445 relations across the three scenarios), plain RAG and graph-enhanced RAG complete 4 and 14 tasks respectively (McNemar p=0.0020), with evidence coverage of 3 versus 12 on the 18 factual questions exactly matching completion—the gain comes from the graph supplying evidence that document retrieval cannot cover, at a cost of only 103.20 ms and 325.70 tokens. Ablation baselines (bare LLM 10%, direct SQL 78.6% on its answerable subset) further establish that graph enhancement and direct SQL are complementary rather than substitutes. A single-project five-method extension batch run under the draft pre-registration protocol reproduced the same direction on an independent question set (no degraded pairs against plain RAG; internal diagnostic scope, Section 7.6.6).
- 说明:与中文摘要改法逐句对应,保证中英同构;全部数字、p 值、括号注原样。

### 4. L80(1.3 开头)— 对应关系句 1-3-2 乱序 + 一句塞三重簿记

- **Location**:L80,第 2 句
- **原句**:它们与摘要的三点实际需求一一对应,是可操作的命题:其中,需求一对应子问题一(可追溯),需求三对应子问题三(可控生成),需求二对应子问题二;后续各章逐一给出方法与验证,第八章逐问回收答案;为便于索引,正文以"子问题一/二/三"指称(子问题一、二分别对应第七章的 RQ1、RQ2,子问题三的正向验证与其反面刻画共同对应 RQ3)。
- **问题类型**:没重心 d(对应关系、章节回收、指称约定三件互不相关的事挤进一个冒号句)+ 顺序失配:"需求一、需求三、需求二"的列举顺序与摘要三问及下文 L82-86 的子问题一/二/三顺序相反,读者需自行回配;"子问题二"独缺标签。
- **改写句**:它们与摘要的三点实际需求一一对应,是可操作的命题:需求一对应子问题一(可追溯),需求二对应子问题二(关系证据),需求三对应子问题三(可控生成)。后续各章逐一给出方法与验证,第八章逐问回收答案。为便于索引,正文以"子问题一/二/三"指称(子问题一、二分别对应第七章的 RQ1、RQ2;子问题三的正向验证与其反面刻画共同对应 RQ3)。
- 说明:三重簿记拆为三句;对应关系按 1-2-3 重排(并列项重排不损义,且与 L84"子问题二(关系证据,RQ2)"的既有标签一致,非新增术语);括号内两处映射以分号分层。

### 5. L39(1.1 末段)— 一段塞两个互不相关的重心:问题链 + 研究意义

- **Location**:L39,整段
- **原句**:因此,本文要解决的中心问题可以表述为:……1.3 节将这三个子问题形式化为可验证的研究命题,分别对应本文的三项工作。本文研究的意义也由此体现在三个方面。第一,……(至段末"实现路径。")
- **问题类型**:没重心 d。前半段是中心问题与三子问题(论文的问题链),后半段是三方面意义,两块内容仅一句之隔共居一段;段内无单一主题,读者抓不到本段"要完成什么"。
- **改写句**:文字一字不改,在"本文研究的意义也由此体现在三个方面。"前另起一段;该句即第二段天然主题句,"第一/第二/第三"三方面随后展开。
- 说明:纯分段操作,零语义风险;"意义三方面"各自已有"第一,从……角度"标记,独立成段后重心自明。

### 6. L124(1.5 创新二 方案要点)— 一句引入 BM25/HNSW/RRF 三个新缩写,谓语"融合"被埋

- **Location**:L124,"方案要点"第 1 句
- **原句**:方案要点:检索采用 BM25(Okapi BM25,中文 bigram、同义词展开)与分层可导航小世界(Hierarchical Navigable Small World, HNSW)向量双通道 RRF(倒数排名融合,Reciprocal Rank Fusion)融合,并按式(5-3)注入一跳关系证据;回答中的每项事实以 [S]/[G] 编号引用来源块与关系,每次调用保存语料哈希、提示版本、检索配置、Token 与时延,业务、AI 操作与通用审计三层日志贯通,支持按日志编号回放复核。
- **问题类型**:晦涩 b/c(三个新术语的全称括号连排压住谓语,主干"检索采用……融合"直到第三个括号后才闭合;"并注入"再挂尾,一句 5 个动作)。
- **改写句**:方案要点:检索采用双通道 RRF(倒数排名融合,Reciprocal Rank Fusion)融合——一路是 BM25(Okapi BM25,中文 bigram、同义词展开),一路是分层可导航小世界(Hierarchical Navigable Small World, HNSW)向量;一跳关系证据按式(5-3)注入。回答中的每项事实以 [S]/[G] 编号引用来源块与关系。每次调用保存语料哈希、提示版本、检索配置、Token 与时延,业务、AI 操作与通用审计三层日志贯通,支持按日志编号回放复核。
- 说明:先给骨架"双通道 RRF 融合"再展开两路,术语与全称括号逐字保留;"按式(5-3)注入"独立成句;引用 / 留痕两件事断句分层。

### 7. L127(1.5 创新三 与已有工作的差异)— 破折号后五连,内含两处括号

- **Location**:L127,"与已有工作的差异"第 2 句后半
- **原句**:本设计反其道而行——能力边界由系统而非模型决定,任务限定为六类模板(四类完成验证),模型可用的 12 个受控工具全部登记五项安全属性(权限范围、风险等级、需否确认、幂等键、审计动作),高风险动作经人工确认队列执行并以幂等键防重放,生成内容带来源编号可回查。
- **问题类型**:晦涩 a(破折号内一逗到底 5 个断言、嵌两处括号,约 150 字;"能力边界由系统决定"这一总纲与其余四项机制平铺同层,总-分关系被逗号抹平)。
- **改写句**:本设计反其道而行——能力边界由系统而非模型决定。任务限定为六类模板(四类完成验证),模型可用的 12 个受控工具全部登记五项安全属性(权限范围、风险等级、需否确认、幂等键、审计动作);高风险动作经人工确认队列执行并以幂等键防重放,生成内容带来源编号可回查。
- 说明:总纲独立成句,静态约束(模板、工具登记)与运行时约束(确认队列、防重放、可回查)各成一句;全部数字与括号注原样。

### 8. Abstract L25 "First" 句 — 括号内含分号、括号外接破折号,结论尾挂

- **Location**:L25,"First" 一句
- **原句**:First, traceability: the evidence and configuration of every answer can be inspected by a third party against database records, 40 question-answering logs support per-answer replay, and auditing four normalized notes yields TP=52, FP=1, and FN=0 (F1=100% after correcting one mis-extracted entity against the gold standard; an audit-consistency record rather than an independent validation, Section 7.5)—lightweight rule extraction is reliable and auditable on normalized records.
- **问题类型**:晦涩 a(约 85 词:括号内含分号限定,括号闭合后再以破折号拖出结论,读者需跨越双重嵌套才读到落点)。
- **改写句**:First, traceability: the evidence and configuration of every answer can be inspected by a third party against database records, and 40 question-answering logs support per-answer replay. Auditing four normalized notes yields TP=52, FP=1, and FN=0 (F1=100% after correcting one mis-extracted entity against the gold standard; an audit-consistency record rather than an independent validation, Section 7.5). Lightweight rule extraction is reliable and auditable on normalized records.
- 说明:按"可复查 / 核验数字 / 结论"断为三句,TP/FP/FN、F1 与诚实性括号注原位保留;结论独立成句即重心落位。

### 9. L124(1.5 创新二 与已有工作的差异)— 破折号内含三个对照分句

- **Location**:L124,"与已有工作的差异"第 1 句
- **原句**:与已有工作的差异:文档片段检索覆盖不到关系证据、而全文答案又必须可回放,这两条约束同时成立时,现有路线均只解决其一——普通 RAG 有来源但不保结构化关系证据,直接 SQL 有结构化证据但绕开可审计的生成链路,GraphRAG/LightRAG 面向通用语料的全局组织而非 ELN 的审核权限约束。
- **问题类型**:晦涩 a + 没重心(两条前提与"只解决其一"的判断挤在破折号前,破折号内再压三个"有 X 但 Y"对照,判断与证据一气读完负担过重)。
- **改写句**:与已有工作的差异:文档片段检索覆盖不到关系证据,而全文答案又必须可回放;这两条约束同时成立时,现有路线均只解决其一:普通 RAG 有来源但不保结构化关系证据;直接 SQL 有结构化证据但绕开可审计的生成链路;GraphRAG/LightRAG 面向通用语料的全局组织而非 ELN 的审核权限约束。
- 说明:仅在前提/判断/证据边界换标点,三个对照项以分号并列,语句一字未增删;"、而"改",而"消解顿号跨分句。

### 10. L35(1.1 第二段)— 三个核心缺口作宾语拖在 120 字句尾,且顺序与问题链不一致

- **Location**:L35,"然而"句
- **原句**:然而,目前多数 ELN(Electronic Laboratory Notebook)系统主要关注记录和检索功能的数字化实现,将纸质笔记迁移为网页表单或在线文档,并未充分解决实验知识之间缺少语义关联、AI 问答缺乏可核查的来源依据以及不同项目之间的知识权限难以隔离等更深层次的问题。
- **问题类型**:没重心 a(全文要打的三个缺口以"并未解决……等"的宾语形式沉在 120 字句末)+ 顺序失配:三缺口列举顺序(语义关联→来源依据→权限)与摘要三问、1.1 中心问题展开顺序(可追溯→关系证据→可控生成)相反。
- **改写句**:然而,目前多数 ELN(Electronic Laboratory Notebook)系统主要关注记录和检索功能的数字化实现,将纸质笔记迁移为网页表单或在线文档。AI 问答缺乏可核查的来源依据、实验知识之间缺少语义关联、不同项目之间的知识权限难以隔离——这些更深层次的问题尚未得到充分解决。
- 说明:三缺口升为后句主语并按"可追溯→关系证据→可控生成"重排(并列项重排不损义,使 1.1 与摘要、1.3 共用一条链);"尚未得到充分解决"原义承接"并未充分解决",否定强度不变。

## 通过项说明

- **问题链结构未拆**:摘要三问三答(L5 提问,L9-15 三答)、1.3 三子问题(L82-86)、1.5 三创新(L114-118)均保持原结构,以上改动全部是句内拆分、标点分层、并列项重排与一处分段,未增删任何一问/一答/一创新。
- **数字、引文、术语零改动**:35/357/445、4/14 题、p=0.0020、3 对 12、103.20 ms、325.70 Token、10%/78.6%、TP=52/FP=1/FN=0、[n] 引文、[S]/[G]、BM25/HNSW/RRF 全称括号、project_id、FAIR、OCR 等全部原样;式(5-3) 引用原位。
- **诚实性限定语强度不变**:"属数据校正后的一致性记录"(7.5)、"内部诊断口径"(7.6.6)、"人工盲评待签核、覆盖单项目单次生成"(8.3)、"完成于迁移前的 legacy 批次"(L124)、"图谱增强对普通 RAG 零恶化"全部原词保留,仅随句拆分移位。
- **1.2 各小节(L45-69)通过**:综述句均短于 70 字、无嵌套,引文紧贴被支持陈述;L47 末句"本文关注的是已有 ELN 文献尚未直接回答的后续问题:……"三分号三问是全节重心句,保留;L55"不在于……而在于……"承载真实技术对照且紧凑,不按对称骨架处理。
- **1.3 四个缺口(L90-96)通过**:每段主题句("第一,……不足/风险/闭环")先行,句长正常。
- **1.4(L100-108)通过**:按"问题→方法→验证"分条,粗体标题 + 冒号 + 分号属设计内清单体,分号承担列表层级,不计晦涩;每条已标注服务的子问题。
- **刻意保留项**:L112"先把三项创新各用一句话说出来"是导航句,告知读者"每句落点=与已有工作的差异",信息有效;L114-116 创新条目整句加粗、L121 与 L114 的"未见报告"复述属"条目预告 + 正文展开"设计;L127 创新三"差异先于方案要点"有"方案要点即差异本身"明示衔接,均未动。
- **可选微调(未计入 10 条)**:L131"后者的定位是权限与审核约束下把关系证据注入可引用生成链路的互补组件"定语约 22 字压住中心语,可改"后者定位为互补组件:在权限与审核约束下,把关系证据注入可引用的生成链路",语义不变。
