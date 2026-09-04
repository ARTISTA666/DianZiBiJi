# Structure Review — Round 06

## Review Summary
总体评分:7.5/10
风险等级:Medium
八章框架完整、各章职责有显式声明,"问题→需求→设计→方法→实现→实验→结论"闭环意识强(表 3-2、表 4-3、7.10、8.1-8.4 逐问回收),交叉引用纪律好;但存在五处 Major 级结构问题——RQ 编号与子问题映射不一致、绪论与第二章句子级重复、第六章前置第七章的机制解读、第二章把具体方案前置于问题定义、第四章引入第三章未定义的 PI 角色——以及多处跨章重复披露。本轮全部 issue 的 Recommendation 均为纯结构调整/文字收敛,不涉及新增实验、数据、引用或任何数字改动,Editor 可代劳。

## Issues
### ISSUE-001
Severity: Major
Priority: P1
Location: 1.3 现有研究存在的问题, L74-80;第七章章首, L1211;7.9 实验结果分析, L1532
Category: structure/逻辑链一致性
Problem: "子问题一/二/三与 RQ1/RQ2/RQ3 一一对应"的核心索引声明与正文实际绑定关系不一致,RQ3 的内涵在三处表述各不相同,削弱"问题→实验→结论"主链的索引闭合。
Evidence: L74 声称"与第七章的 RQ1/RQ2/RQ3 一一对应",但 L80 把 RQ3 定义为子问题三的"反面刻画(固定 top-k 一跳检索…失效机制,RQ3)同时给出子问题二方法的适用边界";L1211 又将 RQ3 绑定为"生成可控性与一跳检索边界",而 L1532 回答 RQ3 时仅用 Q13/Q15/Q17-Q19 失败案例,7.7 的生成可控性验证全程无 RQ 编号。
Recommendation: 统一 RQ3 口径(Editor 可代劳,无需新增实验/数据):在 1.3 明确 RQ3 覆盖"生成可控性的正向验证 + 一跳检索失效边界"两面,或将 L74 改为"子问题一/二与 RQ1/RQ2 一一对应,子问题三对应 RQ3,其反面刻画兼作子问题二方法的适用边界",并使 7.7、7.9、8.1 的回收表述与该定义一致。
Confidence: High

### ISSUE-002
Severity: Major
Priority: P1
Location: 1.2.1/1.2.4, L37-63;2.1/2.4, L155-195
Category: structure/章节重复
Problem: 第一章研究现状与第二章相关理论存在内容与句子级重复,两条综述线的分工未彻底划清,是盲审最常指出的"绪论与第二章重复"问题。
Evidence: "ReAct 将推理轨迹与行动过程交替组织,使模型能在执行任务时调用外部环境并更新中间状态[13]。Toolformer 研究了语言模型学习调用外部工具的能力[14]。"在 L59 与 L189 逐字出现;openBIS ELN-LIMS 在 L39(1.2.1)与 L159(2.1)两处重复介绍,引用文献 [2][3][4] 两章共用。
Recommendation: 按"1.2 承担研究现状与差距、第二章承担理论原理与设计启示"分工(Editor 可代劳):已在 1.2 详述的 ReAct/Toolformer/openBIS 等条目,第二章改为一句带过或从原理/机制角度改写,消除逐字重复。
Confidence: High

### ISSUE-003
Severity: Major
Priority: P1
Location: 6.3 普通 RAG 与图谱增强 RAG 的真实回答对照, L980-991;对照 7.6.3 证据覆盖分解与失败机制, L1420-1432 与 7.9, L1532
Category: structure/章节职责边界
Problem: 第六章自称"实物呈现、机制分析留给第七章"(L945、L1207),但 6.3 实际包含了 7.6.3/7.9 层级的机制结论与价值综合,实现章与实验章职责模糊并形成部分重复。
Evidence: L988 "三臂对照把 RAG 的价值刻画得更完整:普通 RAG 解决了可溯源但证据不足,图谱增强补上了关系证据缺失,而裸 LLM 的短板不是答不出,而是答了无法核对";L990 "这说明一跳排序器在多关系聚合任务上不仅无效,还可能挤占上下文"——均为第七章 7.6.3 对 Q18/Q19 失败机制分析的结论性表述。
Recommendation: 6.3 保留原始回答摘录与最简对照(Editor 可代劳):机制性结论句下放至 7.6.3/7.9,或改为"机制见 7.6.3"式指针,使第六章回到"看得见的证据"这一自身声明职责。
Confidence: High

### ISSUE-004
Severity: Major
Priority: P1
Location: 2.2 末段 L175、2.3 末段 L185、2.4 末段 L195(第二章相关理论与技术)
Category: structure/先方案后问题
Problem: 第二章各节末尾以"本文采用/本文系统使用/因此本文不做…而采用"给出具体实现选型与数据库表名,属于解决方案内容先于问题定义(第三章)与设计章(第四、五章)出现。
Evidence: L185 "本文系统使用关系数据库保存项目级知识图谱,包括 `kg_entities`、`kg_relations` 和 `kg_extraction_runs` 三类核心表";L195 "系统预设…四类任务…把来源信息写入 `agent_generation_runs` 表"——具体表结构与实现细节出现在需求分析之前。
Recommendation: 删除或后移 2.2/2.3/2.4 末段中的具体表名与实现选型(Editor 可代劳):第二章各节以一句"设计启示/本文取向"收尾,细节归 4.5/5.1/5.3 对应位置。
Confidence: High

### ISSUE-005
Severity: Major
Priority: P1
Location: 3.1 角色分析, L211-252(表 3-1 L246-252、图 3-3 L401);4.2 用户类型与能力矩阵, L454-483
Category: structure/需求-设计衔接
Problem: 第四章引入第三章从未定义的系统级角色 PI(含"对全部非敏感项目读取"豁免)与 GROUP_LEADER 枚举值,需求侧五类角色与设计侧六类用户不对齐,权限模型的需求来源缺失。
Evidence: 3.1 仅定义"第一层为系统级角色,其中系统管理员(`SUPER_ADMIN`)…"(L219),表 3-1 与图 3-3 均为五类角色;4.2 L456 列出含 `PI`、`GROUP_LEADER` 的六值枚举并定义 PI(u,p) 读取豁免(L458、L472、表 4-1 L477),其中 GROUP_LEADER 全文仅此一处且无解释。
Recommendation: 在 3.1 补充系统级 PI(课题组负责人)角色的需求来源与"非敏感项目只读"约束,或在 4.2 首次出现处说明其为需求章五类角色之外的系统级扩展及业务动因(Editor 可代劳);同时删除或解释 GROUP_LEADER 枚举。
Confidence: High

### ISSUE-006
Severity: Minor
Priority: P2
Location: 摘要 L9、1.5 L118、2.5 L201、4.1 L421、5.2.1 L769、6.4 L994、6.5 L1039、7.1 L1215-1231;另 7.6.1 L1381 与附录 B.2 L1668
Category: structure/跨章重复
Problem: legacy/当前双运行时口径声明在正文重复出现约 8 处(均以"统一见 7.1 节"收尾),防御性重复拖慢各章节奏;答案规则事后建立的时序披露也在 7.6.1 与附录 B.2 两处近乎同文。
Evidence: "对照实验的运行时口径统一在 7.1 节交代"(L9)、"统一见第七章 7.1 节"(L421)、"与当前实现的口径差异统一见 7.1 节"(L769)等同型声明贯穿 1-6 章;L1381 "正式问答运行于 2026 年 6 月 12 日 00:12 完成,答案规则文件于同日 19:31 后生成"与 L1668 同一时序表述重复。
Recommendation: 口径声明收敛为"7.1 全量对照 + 摘要/结论各一次",正文各章仅保留"见 7.1"短语;答案规则时序以 7.6.1(或附录 B.2)一处为主、另一处简引(均为文字收敛,Editor 可代劳)。
Confidence: High

### ISSUE-007
Severity: Minor
Priority: P2
Location: 5.1.7 实验知识图谱可视化与关联检索, L757-761;6.2 L978;6.5 L1063
Category: structure/内容错位与重复
Problem: 5.1.7 用整段描述知识图谱页面的 UI 细节(顶部统计、SVG 绘制、筛选器、节点跳转),属实现/界面内容,且与 6.2、6.5 的同内容描述形成三处重复。
Evidence: L759 "页面顶部展示实体总数、关系总数…以 SVG 方式绘制关系图…实体类型筛选器和关系类型筛选器…直接跳转到对应的实验笔记详情页面";6.2 L978 与 6.5 L1063 再次出现"SVG 渲染…类型筛选…节点详情跳转"。
Recommendation: 5.1.7 只保留"基于关键词和关系类型提示词的轻量关联检索"方法段与"运行截图见 6.6 节"指针,可视化 UI 描述统一收入 6.2 或 6.5 单处(Editor 可代劳)。
Confidence: High

### ISSUE-008
Severity: Minor
Priority: P2
Location: 7.8 场景化验证与审计追溯, L1514-1528
Category: structure/章节重复
Problem: 7.8 的四段角色场景(普通成员/审核人员/系统管理员/项目负责人)实质复述表 3-1、表 4-1、图 3-3 已有的权限内容,新增验证信息仅一句,稀释了测试章的信息密度。
Evidence: L1518 "普通成员…可创建实验笔记…上传附件文件…无法评价问答结果"等内容与表 4-1 普通成员行重复;全节新增信息仅 L1528 "上述角色流程通过自动化测试、接口调用和浏览器走查验证"。
Recommendation: 将四段压缩为"走查场景-覆盖角色-验证方式-结果"的一段或一张表,删除与表 3-1/表 4-1 重复的权限复述,保留走查覆盖范围、证据(validation-results.json)与结论(Editor 可代劳)。
Confidence: High

### ISSUE-009
Severity: Minor
Priority: P2
Location: 2.5 系统开发相关技术, L197-201;4.1 系统总体架构设计, L419-421
Category: structure/章节重复
Problem: 2.5 与 4.1 对运行技术栈的描述句式与内容几乎相同(Rust 1.88/Axum/SQLx/pgvector/Next.js),重复交代且均再指向 7.1。
Evidence: L199 "当前后端使用 Rust 1.88 与 Axum 提供 REST API,使用 SQLx 访问 PostgreSQL 数据库,并通过 pgvector 存储文档向量。前端使用 Next.js…";L421 "前端基于 Next.js 提供用户交互界面,当前后端基于 Rust 1.88 与 Axum 提供 RESTful 业务 API,SQLx 访问 PostgreSQL 并通过 pgvector 保存文档向量"。
Recommendation: 2.5 保留技术选型动机(为何选 Rust/pgvector/Next.js),运行栈事实句与 4.1 二选一,建议保留 4.1、2.5 一笔带过(Editor 可代劳)。
Confidence: High

### ISSUE-010
Severity: Minor
Priority: P2
Location: 附录 D L1710;对照 6.1 L962 与 6.2 L964-978
Category: structure/交叉引用
Problem: 附录 D 声称 GSE111619 的自动生成笔记与抽取图谱样例"见第六章 6.2 节",但 6.2 全节未出现 GSE111619 或其图谱样例,交叉引用指向不明或悬空。
Evidence: L1710 "由该数据集自动生成的 4 条 RNA-Seq 结构化笔记与抽取图谱样例见 `data/real/GSE111619/gse111619_notes.json` 与第六章 6.2 节";6.1 L962 仅说明 GSE111619 "作为另一独立项目用于检索诊断,不计入三项目语料",6.2 的 Mermaid 子图(33 节点、50 边)未标注来源项目。
Recommendation: 在 6.2 为 Mermaid 子图明确标注来源项目;若该子图并非 GSE111619,则修正附录 D 的指向(改指 6.1 或由附录 D 自含样例说明)(Editor 可代劳)。
Confidence: Medium

### ISSUE-011
Severity: Minor
Priority: P2
Location: 第七章章首 L1211
Category: structure/表述残留
Problem: 第七章开头出现自指表述"本章按第七章开头声明的同一问题链检验",该句本身即章首,疑为旧稿残留。
Evidence: L1211 "本章按第七章开头声明的同一问题链检验系统是否达成第三章提出的设计目标"——"第七章开头声明"无处可指。
Recommendation: 改为"本章按第一章提出的问题链检验…"或直接删去"第七章开头声明的"(Editor 可代劳)。
Confidence: High

### ISSUE-012
Severity: Minor
Priority: P2
Location: 3.2 系统目标与实验痛点, L254-293(图 3-2 L260-274、四环节 L276-282);对照 4.4 L515-525
Category: structure/章节职责边界
Problem: 3.2 的"可信知识闭环"按"可信输入→结构化转化→知识支撑问答→结果回存"四环节叙述方案流程,与本章开头"实体关系与图谱如何建模属于解决方案设计,留待第四、五章展开"(L209)的自我声明存在张力,且与 4.4 模块协作业务流部分重叠。
Evidence: L209 声明建模属解决方案设计,但 L278 仍详述"已审核的实验笔记进入知识图谱抽取流程,系统从笔记的结构化字段和正文内容中识别试剂、仪器、样本和结果等实体"等设计流程。
Recommendation: 将四环节叙述压缩为需求侧约束描述(图 3-2 保留作总览),流程细节以指针指向 4.4 与 5.1(Editor 可代劳)。
Confidence: Medium

## 结构评分与最严重三个问题
- 评分:7.5/10(章节骨架、职责声明与逐问回收闭环完整且交叉引用纪律好,但 RQ 映射不一致、两处跨章重复簇、第六/七章职责模糊、需求-设计角色不对齐五处 Major 问题拉低结构严密性;全部问题均可经纯文字修改解决,无需新增实验/数据。)
- TOP3:ISSUE-001, ISSUE-002, ISSUE-003
