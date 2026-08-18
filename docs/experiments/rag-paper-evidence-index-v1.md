# RAG 论文证据索引 v1

## 用途与证据边界

本索引把论文中的 RAG 主张映射到仓库中的原始材料、分析脚本和门禁结果。它只整理已有证据，不生成新的实验结果，也不把自动规则化评价、内部开发批次或系统可运行性包装为确认性效果证据。

当前论文引用必须区分三类材料：

1. **历史开发批次**：可用于描述性结果、失败案例和机制诊断，但不能支持外部有效性或稳定优越性。
2. **可复核协议与工具**：可证明实验如何冻结、导出、校验和分析，但本身不证明模型效果。
3. **确认性证据**：必须同时具备外部冻结题集/金标准、完整 v1 证据包、版本与参数绑定、独立双人盲评和预先规定的统计分析；当前尚未齐备。

## 主张—证据矩阵

| 论文主张 | 允许引用的材料 | 当前状态 | 允许表述 | 禁止表述 |
| --- | --- | --- | --- | --- |
| 一跳图谱关系可补足部分资料未覆盖事实 | `rag-experiment-4.csv`、`rag-experiment-4-objective-analysis.md`、`rag-experiment-4-internal-*` 相关材料 | 历史开发批次 | “在单项目、20 题、单次生成的探索性批次中观察到……” | “图谱增强 RAG 普遍优于基线” |
| 当前批次的规则化完成率差异 | `rag-experiment-4-objective-analysis.md`、`rag-experiment-4-evaluation-sheet.csv` | 事后规则化、非预注册 | “规则化任务完成率为描述性结果；答案规则在运行后建立” | “预注册准确率”“无偏准确率” |
| 失败来自一跳检索边界 | 原始 CSV、失败案例和分析报告 | 可用于机制诊断 | “案例暴露了集合列举、指代和多关系聚合缺口” | “已证明某一算法在所有场景失败” |
| 系统可保存回答、来源、图谱证据和配置 | `rag-evidence-package-protocol-v1.md`、Rust 导出实现、通过的验证器测试 | 工程/协议证据 | “系统定义并测试了可回放证据包结构” | “已完成正式确认性实验” |
| 确认性人工准确率、可追溯率和质量评分 | `confirmatory-human-review-export.csv`、完成门禁和证据 manifest | 当前缺失；完成门禁 FAIL | 暂不报告数值 | 使用内部自动分数代替人工结果 |
| 跨项目、外部题集上的泛化效果 | 外部冻结题集、至少 3 个项目的 v1 运行包及盲评结果 | 当前缺失 | 暂不作结论 | 从单项目开发题集外推到真实课题组 |

## 当前可直接复核的材料

证据包契约现将 `graph_schema_version` 作为顶层实验绑定字段公开，并要求新运行的顶层值与 `config_snapshot.graph_schema_version` 一致。该字段用于把图谱结构/展开规则版本纳入论文材料的可审计输入绑定；历史内部批次仍不会因此获得缺失的外部版本证据。

### 历史开发批次

- `docs/experiments/rag-experiment-4.csv`：40 条原始问答及来源、图谱、Token、时延等记录。
- `docs/experiments/rag-experiment-4-objective-analysis.md`：规则化指标、配对比较、McNemar 描述性检验、P95 长尾和失败边界。
- `docs/experiments/rag-experiment-4-evaluation-sheet.csv`：事后建立的答案要点和机械判定；不能视为运行前金标准。
- `docs/experiments/rag-experiment-4-run.json`：旧版运行记录，不是 `rag-evidence-package-v1`。

这些文件可以支持透明的探索性报告，但不能与未来确认性批次混合统计。论文应同时报告题集规模、单项目范围、单次生成、答案规则建立时序和人工盲评未签核等限制。

历史 CSV 的结构对账与引用审计必须分开报告。对 `rag-experiment-4.csv` 的 40 行结构检查显示：两种模式各 20 行、日志 ID 唯一、来源/图谱 JSON 均可解析、评价表键集合一致；但严格引用审计发现 4 个非法范围标记（`[S2-S6]`、`[S1-S6]` 和两处 `[G1-G10]`）。历史分析报告中的图谱模式 85.0% 是宽松的 `"[G"` 子串口径（17/20），不是合法数字引用标记覆盖率；按生产端失败关闭规则，严格有效引用标记覆盖率为 15/20（75.0%）。历史报告不改写，但论文不得把 85.0% 作为有效引用率；应将该差异作为历史批次的审计失败案例和指标口径漂移记录。

### 协议与验证工具

- `docs/experiments/rag-evidence-package-protocol-v1.md`：证据包字段、状态语义、失败分母、案例来源和归档边界。
- `scripts/check_rag_experiment_evidence.py`：校验 schema、执行计划、哈希、状态、案例计数、失败摘要和 `query_log_id` 来源。
- `scripts/test_check_rag_experiment_evidence.py`：覆盖非终态、终态计数、计划漂移、失败映射、日志来源边界，以及对答案引用标记、来源/图谱数组边界和 `citation_audit` 字段的独立重算；其中 `passed` 还复现生产端证据类别覆盖和关键事实段落同段引用规则，拒绝真值或假值漂移。
- `scripts/audit_rag_csv_consistency.py`：对历史 CSV 与规则化评价表做标准库离线对账，检查案例分母、问题—模式配对、唯一日志 ID、来源/图谱 JSON、回退、错误行和人工评价字段填充情况。
- `scripts/audit_rag_five_mode_bundle.py`：对实验 5 内部五方法批次做报告—CSV—题集—运行参数—冻结清单交叉审计，并区分结构一致性、严格引用一致性和论文可用性门禁。
- `docs/experiments/rag-experiment-5-preregistration.md`：确认性实验的题集、五方法、重复、指标、失败归因和盲评预注册要求；当前状态仍为待执行。

当前 Rust 端的 `GET /rag/experiments/{run_id}/evidence.json` 已通过路由级回归：导出包包含 `rag-evidence-package-v1`、完整的重复/随机化协议字段、案例分母、唯一 `query_log_id`、逐案例 citation audit，并保留未落库失败。实验创建入口现在会在题目 trim 后拒绝重复题目，使生产运行域与归档检查器的唯一题集约束一致；同一执行序号已有落库失败日志时，导出器不会再次从 `summary.errors` 补入重复案例。新增的 `questions_sha256`、`corpus_snapshot_hash` 和 `rag_index_version` 将运行绑定到题集以及生产检索实际使用的已批准/已同步/当前索引版本文档块；检查器会复算题集哈希，并要求数据集依赖模式提供语料快照哈希。执行器领取队列后、且每个后续案例开始前，会复核这些输入绑定及嵌入/生成模型；隔离数据库回归证明语料哈希漂移会把运行置为 `failed` 并记录运行级 fatal error，而不是产出 completed 结果。新增的 `failure_scope`/`failure_code` 进一步把 `input_binding_drift` 等运行级故障与 `query_error` 等案例级失败机器可读地区分，检查器拒绝范围错配和未知代码，不再依赖错误文本推断。原始 evidence 端点还复用了 `require_unblinded_access`：管理员可下载，独立评审员访问返回 `403`，评审员仍可访问去标识的盲评 API；该隔离数据库回归防止证据导出绕过方法隐藏。端点对 `queued`/`running` 和未知状态返回 `409`，与离线检查器的非终态/未知状态拒绝一致；`interrupted` 保留未执行分母并按部分包披露。OpenAPI 路径现在显式引用 `RagEvidencePackage`，并暴露稳定的实验绑定字段、失败枚举和摘要 fatal error；前端类型由 `npm run generate:api` 幂等生成，证据扩展对象保持可扩展。上述是工程契约证据，不改变当前内部批次缺少外部冻结题集、版本 revision、独立盲评和确认性 v1 证据包的结论。

本轮进一步将逐案例检索参数纳入归档门禁：有 `query_log_id` 的案例必须保留嵌入模型、索引版本、`graph_schema_version`、检索策略、普通/集合 top-k、向量候选数、图谱 top-k、分块大小/重叠和两个最低相关度阈值；图谱版本必须与顶层实验绑定逐字一致，同一证据包内这些稳定参数不得漂移。生产执行器也会在运行开始/恢复和每个后续案例前复核图谱 schema 版本，漂移时以 `input_binding_drift` 运行级失败关闭，避免队列跨版本继续产出案例。`RagEvidenceRetrievalConfig` 已进入 OpenAPI，前端类型由生成脚本同步。`check_rag_experiment_evidence.py` 的输出新增 `statistics.rag-evidence-statistics-v1`，从答案、证据数组和案例遥测独立重算状态/失败分层、来源/图谱对象数、引用计数、按方法时延中位数/P95和运行参数快照；它不读取可篡改的 `citation_audit` 计数字段，也不把结果解释为人工准确率、引用正确性或显著性证据。该统计输出可作为论文附录的可重生成描述性材料，但正式效果结论仍需外部冻结题集、金标准、独立双人盲评与确认性运行包。

为避免统计输出与论文材料再次分叉，新增 `scripts/render_rag_evidence_paper_material.py` 作为唯一的 v1 描述性附录渲染入口。它只接受通过 `check_rag_experiment_evidence.py` 的 `passed=true` 结果，并从同一 `cases[]` 再次重算 `rag-evidence-statistics-v1`；输入 schema、检查状态或统计任一漂移即失败关闭。生成内容限定为分母、失败代码、证据对象、按方法时延、引用标记重算和运行参数绑定，并明确不证明人工准确率、引用正确性、显著性检验或方法优越性。当前仓库仍无可通过 v1 的确认性运行包，因此本轮只提交渲染器、测试和协议，不生成虚假的论文结果附件。

该渲染器同时生成按 `execution_order` 排序的失败案例逐项清单，保留题目序号、方法、重复编号、`query_log_id`、失败范围/代码、来源与图谱证据数量及原始错误文本，包含未落库失败。清单用于论文失败案例复核和分母审计；原始错误不等于因果解释，证据对象数量不等于检索相关性或答案正确性。

生成的附录还内嵌五项输入材料的完整 SHA-256：实际 v1 证据包、离线检查器、附录渲染器、v1 协议和本论文证据索引；输出使用仓库相对路径，并可由 `check_paper_material_freshness.py` 独立重算。该版本绑定只支持材料可追溯性，不把当前工作树状态、代码 revision 或指纹本身误写成外部冻结和人工确认性证据。

截至本索引生成时，仓库没有可通过 `rag-evidence-package-v1` 校验的确认性运行包；旧版 `rag-experiment-2/3/4-run.json` 已由 CLI 失败关闭验证。`docs/experiments/confirmatory-review-completion-latest.md` 当前为 `FAIL`，缺少外部冻结包、人工评审导出和完成证据 manifest。

实验 5 的内部五方法批次另有 180 行 CSV、12 题单项目题集、3 次重复和 5 种方法；行完整性检查通过，但不能作为确认性结果。`docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json` 记录了两类关键失败：CSV 中 4 个 `[S1-S12]`/`[S6-S12]` 范围标记未被旧报告的引用审计识别，且内部冻结清单因若干源码文件缺失或哈希漂移而无法复核。该批次还标记为 `app_revision=unversioned`、单项目、人工评价字段为空且缺少 v1 证据包。因此内部自动覆盖数字只能作为方法学诊断，不能写成论文确认性准确率、引用有效率或跨项目泛化结论。

实验 5 审计器还从 180 条原始 CSV 逐案例重算 5 个模式汇总和 4 组相对 `project_rag` 的配对比较，并与内部报告逐字段核对；当前两类统计核对通过，说明报告中的描述性数字具有内部可重算链路，但不改变上述引用语法、冻结、版本、单项目和人工盲评门禁。因此“统计可重算”只能支持方法学透明度，不能替代独立金标准或确认性人工评价。

该重算门禁还通过临时篡改报告字段的回归测试：模式 `hit_facts` 或配对时延被修改时，审计结果会明确失败并列出漂移字段。由此可区分“原始数据与报告一致”与“报告数字被事后修改后仍可通过”，为论文材料提供结果完整性审计证据；它不等价于代码版本、输入数据或人工标注的独立确认。

论文可引用的内部描述性汇总由 `scripts/render_rag_five_mode_paper_material.py` 从上述审计产物自动生成至 `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`。该材料固定写入 `paper_ready=false`、严格引用失败、统计验证警告和允许/禁止表述，避免手工抄录内部数字时越过证据边界；若审计 schema、五模式汇总或四组配对比较缺失，生成器会失败关闭。

该材料同时生成“门禁失败摘要”，按检查名稳定排序列出所有未通过检查的严重级别、实际值和期望值。摘要列采用有限深度、确定性排序以便论文阅读，完整 JSON 列保留原始值供机器复核；渲染器要求顶层 `checks` 为非空 JSON 数组，并对非对象检查项、非布尔 `passed`、空检查名、空严重级别和重复检查名失败关闭，避免摘要本身产生歧义。正文“证据链门禁”另外显式呈现 `retrieval_gap_summary_valid`；若审计项缺失或类型不是布尔值，渲染器失败关闭，防止 JSON 层的结构门禁在论文材料层被静默遗漏。当前摘要直接展示 `app_revision=unversioned`、引用审计重算不一致、输入冻结清单失败、单项目/12 题规模、人工评审为空和缺少 `rag-evidence-package-v1` 等阻塞，避免只写一个 `paper_ready=false` 而让读者无法定位原因。该摘要是证据状态解释，不是失败原因的因果证明，也不能把门禁失败反向解释为方法效果。

正文还显式呈现“实验设计与运行配置绑定门禁”，覆盖题集哈希、题目/金标准规模、方法顺序、重复、随机种子、生成 provider/model/temperature/max_tokens 及检索 chunk/top-k/候选数/图谱阈值。该表由审计检查名驱动，缺失或非布尔检查会使渲染失败；PASS 仅证明记录值与冻结配置一致，不把配置一致误写成输入有效性或确认性结果。

“证据链门禁”和“数据—问题集绑定门禁”同样由固定检查集合驱动；CSV 行完整性、重算匹配、严格引用审计、冻结清单、题目范围/题干、逐案例运行与 retrieval 绑定、重复范围、五方法集合及案例键域任一项缺失或类型错误，渲染器均失败关闭。这样正文中的 FAIL 表示真实审计失败，而不是缺失字段被默认解释后的假阴性或假阳性。

顶层 `paper_ready` 与 `paper_blockers` 也经过类型校验：前者必须是布尔值，后者必须是非空字符串数组（可为空数组表示没有阻塞）。字符串化布尔值、缺失字段或畸形阻塞项不会被渲染为论文门禁结论。

此外，审计器会生成 `paper_gate_consistent` 检查，将 `consistency_passed`、`paper_ready` 和 `paper_blockers` 与按严重级别推导的期望值逐项绑定；渲染器再次重算并要求该检查存在且通过。正文证据链表中的“论文门禁逻辑一致”行使这一关系可见，阻止顶层 ready/blocker 字段与失败检查分组发生漂移。

由于门禁失败摘要仅列出未通过项，正文另输出“论文门禁推导审计”表，完整保留 `paper_gate_consistent` 的严重级别、PASS/FAIL、`actual` 和 `expected` JSON。该表用于复核最终门禁的逻辑链，不把一致性通过误写成外部数据、人工评价或方法效果证据。

正文同时输出固定集合覆盖表：实验设计/运行配置 18 项、证据链 5 项、数据—问题集绑定 7 项和论文门禁派生检查 1 项均必须在审计 JSON 中出现，并报告注册数、观察数和缺失名。该覆盖门禁只证明正文与审计 schema 的映射没有漏项，不证明对应检查通过。

正文另有“论文 blocker—最低归档清单映射”表，要求每个 `paper_blocker` 对应唯一的确认性归档要求。当前 5 个失败 blocker 分别对应最低清单第 1、2、4、6、8 项；通过的 `report_scope_is_internal_only` 仅声明当前材料是内部开发证据，不被算作最低清单缺口。映射由共享契约注册并写入审计 JSON 的 `paper_blocker_archive_mapping`，渲染器同时核对契约、审计字段和检查集合；因此映射不是仅供展示的二次推断。出现未注册名称、缺项或 JSON 篡改时，渲染器 fail-closed；表中 FAIL 只表示论文证据尚未达到对应归档要求。

正文另输出“论文主张边界审计”，将内部证据范围、`paper_ready=false` 和未完成归档项绑定到允许的论文表述等级；当前只允许描述性/方法学诊断，不允许确认性效果主张。渲染器自动列出所有必须披露的 blocker—归档项，且对范围、ready 状态或披露条件篡改失败关闭。该表述门禁是证据链治理，不是方法效果或事实准确率证据。

正文随后输出“论文阻塞披露闭环”表，交叉核对失败摘要、顶层 `paper_blockers`、归档映射和主张边界中的待披露数量。名称按集合而非展示顺序核对，以兼容失败摘要的稳定排序与 blocker 注册顺序；缺失、重复、数量或名称漂移时 fail-closed。该表只证明失败身份与披露分母一致，不提升证据等级或支持方法效果结论。

正文还输出“失败检查身份闭环”表：从 `checks` 重算全部失败检查名，与机器 `failure_summary`、正文失败摘要和 `paper_blockers` 交叉核对，并报告 required 与 `paper_blocker` 失败身份的分母。当前内部批次的 153 个失败检查可拆为 148 个 required 和 5 个 `paper_blocker`；该数字只用于定位证据链与论文门禁缺口，不是回答失败率、方法效果或因果结论。摘要缺失、检查名遗漏/重复、数量不一致或 blocker 集合漂移时，材料生成 fail-closed。

渲染器还单独输出“引用审计报告—重算差异”表：逐字段列出报告摘要值与从原始 CSV 重算值，包含全局范围判定和按方法的非法标记计数等差异。该表避免读者只能从完整 JSON 中发现“报告—重算”漂移；它是报告完整性与失败定位证据，不是引用内容正确性、来源支持性或方法效果证据。若 `reported_audit_mismatch` 与差异数组不一致，或差异项缺少字段、重算值和报告值，渲染失败关闭。

归档回归还要求当前审计 JSON 与验证 JSON 的重渲染结果逐字节等于已保存 Markdown；生成器将审计/验证文件和正文中的引用统一写成仓库根目录相对路径，并拒绝根目录外输入。`scripts/test_render_rag_five_mode_paper_material.py` 已对真实材料执行该断言及越界输入回归。这样输入指纹门禁之外，正文的表格、限制和允许/禁止表述若被手工改写也会被发现；重渲染一致只证明生成链未漂移，不提升 `paper_ready=false` 的论文结论等级。

该材料还强制带入验证记录的 `CAUTION` 总体置信级别、11/11 统计谬误扫描、按题目聚类的 post-run bootstrap 区间、重复稳定性和未作多重比较校正的限制；缺失警告或完整谬误扫描时生成失败关闭。这样论文材料不会只保留有利的点估计，而会同步保留不确定性和分析时序。

描述性材料还绑定 7 个关键输入的 SHA-256：审计 JSON、统计验证 JSON、实验报告、原始 CSV、运行配置、题集和冻结清单。生成器对任一缺失输入失败关闭；因此论文材料的数字、分母和限制可以回溯到具体文件版本，而不是只依赖生成时间或当前工作树状态。

材料进一步绑定 3 个分析脚本（实验包审计器、材料生成器、统计验证器）的 SHA-256，并原样呈现方法、重复次数、随机种子、模型、温度、最大 Token、检索 top-k、图谱阈值、语料快照哈希和执行计划哈希。它同时标注 `app_revision=unversioned`、当前工作树 dirty 和分析 Python 版本；这些记录支持内部复核，但不能冒充确认性版本归档。

归档前还应运行 `scripts/check_paper_material_freshness.py`，对描述性 Markdown 中的 SHA-256 表逐项重算输入文件。该检查器对材料越界、缺失指纹章节、空表、格式错误表行、缺失输入、越界路径、格式错误摘要、重复材料名和摘要漂移失败关闭，并输出带有结构化 `reason` 的 `paper-material-freshness-v1` JSON；其 `material` 为相对校验根目录的 POSIX 路径，`root` 固定为 `"."`，不把机器绝对路径写入归档。本轮对实验 5 描述性材料核验 11/11 输入通过，其中包含审计器与渲染器共享的 retrieval 字段契约脚本。它只证明材料未脱离所列输入版本，不证明输入本身具备外部有效性，也不解除 `paper_ready=false` 门禁。

严格引用失败现在以案例级字段归档：CSV 行号、题目索引与题目 ID、方法、重复编号、唯一 `query_log_id`、非法标记和来源/图谱数组规模。论文材料渲染器按 CSV 行稳定排序，并拒绝缺失/非正身份、重复行号、重复日志 ID 或重复案例键，避免把失败计数与可回放案例错配。当前 4 条失败记录为 H04/bm25_rag（重复 1、3、2）与 H03/bm25_rag（重复 2），分别可由 `query_log_id` 128、172、191、273 回放；这支持论文报告具体失败模式，不把“引用审计失败”停留在抽象计数。v1 归档检查器还会重新扫描每个有答案案例的 `[S数字]`/`[G数字]` 标记，并要求 `citation_count`、`invalid_citations`、`has_evidence` 与答案及证据数组一致，同时复现生产端的证据类别覆盖和关键事实段落同段引用规则，要求 `passed` 与重算结果严格相等；完成案例还必须存在非空回答，失败案例才允许 `answer=null`，但两类案例都必须保留对象数组形式的 `sources`/`graph_context`，每个来源对象必须保留正整数 `chunk_id`/`file_id`，每个图谱对象必须保留正整数 `relation_id`/`source_entity_id`/`target_entity_id`，且 `source_count`/`graph_hit_count` 必须分别等于对应数组长度。所有案例的响应时延、提供方、提示版本、模型/回退字段和检索配置/用量对象也必须满足导出类型约束；未落库失败也使用稳定的 `prompt_version="experiment-unlogged-failure-v1"`，实验级 `embedding_model`/`generation_model` 必须同时与 `config_snapshot` 一致，有 `query_log_id` 的案例还必须将 `retrieval_config.embedding_model`、`retrieval_config.index_version` 和 `retrieval_config.graph_schema_version` 分别绑定到实验级模型、索引版本与图谱 schema 版本，且非空案例模型必须匹配实验级生成模型。因此导出时漏记审计字段、越界标记、范围标记、`passed` 真值漂移、空回答冒充完成、证据数组畸形、证据对象身份缺失、证据计数漂移、遥测字段畸形、模型快照漂移或逐案例输入绑定漂移会失败关闭。该新增门禁只证明语法、强制引用规则、案例完整性、证据容器、对象身份、冗余计数一致性、遥测结构、输入绑定和导出内部一致性，不升级为引用正确性、检索质量或人工准确率证据。

归档渲染还从绑定的原始 CSV 和题集重新扫描 `[S数字]`/`[G数字]` 语法，按 CSV 行号生成失败案例；对每个失败行逐字核对 CSV 的 `question` 与题集对应题干，并同时核对 CSV 显式 `source_count`/`graph_hit_count` 与两个证据 JSON 数组长度，再要求结果与审计 JSON 的 `citation_audit.invalid_marker_rows` 逐字段相等。五方法审计器另将重算失败与报告的来源/图谱失败记录规范化为题目 ID、重复编号、方法和标记的精确集合，并核对报告的 `all_citation_indices_in_range`；因此“失败数量相同但失败案例不同”不能通过。它还逐方法核对完成数、来源/图谱/任一证据标记数、非法行数和比例，避免只绑定全局分子分母而遗漏 `by_mode` 层面的篡改。审计记录、题干或冗余计数字段被单独篡改时材料生成失败关闭。该双层重算支持“原始数据—审计—论文表”的可复现链路，不升级为引用内容正确性或人工准确性证据。

描述性材料同时按方法分层报告完成答案数，以及以完成答案数为分母的合法来源标记、合法任一证据标记、合法图谱标记和非法标记行 `n/%`。当前非法引用全部落在 `bm25_rag`（4/36 行）；`project_rag` 为来源标记 36/36，`kg_enhanced_rag` 为来源标记 22/36、图谱标记 36/36。该分层结果只能描述格式和证据呈现差异，不等价于事实准确率或方法优越性。

本轮进一步把 CSV 的题目—题干—重复—方法绑定设为结构一致性的显式门禁。审计器现在逐行检查 `question_index` 是否落在冻结题集范围、CSV `question` 是否与对应题集题干逐字一致、`repetition_index` 是否落在运行配置范围、`mode` 是否属于预注册五方法，并检查案例键是否仍覆盖计划域；非整数、越界、题干漂移或未知方法会生成可定位的失败记录，而不是因 Python 索引异常中断。针对篡改 `question_index`、题干、`repetition_index` 和 `mode` 的回归测试均通过，真实 180 行批次的绑定检查通过；这证明数据行能被绑定到既定问题集和实验设计，但不解除单项目、未版本化和人工盲评缺失等论文门禁。

本轮进一步把逐案例运行版本绑定纳入同一门禁：生成方法的 CSV 行必须分别匹配运行配置中的 `provider`、`model` 和该方法 `prompt_version`；`structured_query` 作为非生成方法必须显式记录 `provider=system`、空 `model` 和其预注册提示版本。任一行的提示版本、提供方或模型漂移都会生成定位到 CSV 行和字段的失败检查，并使行完整性失败关闭。该门禁证明导出的逐案例运行标签没有脱离方法配置，不证明外部应用 revision、模型内容稳定性或生成结果正确性。

本轮新增逐案例 retrieval snapshot 门禁：BM25、混合检索和图谱增强行必须保存与配置快照一致的语料快照哈希、嵌入模型（适用时）、chunk/top-k/候选数/图谱阈值等字段；结构化查询行也必须保存图谱 schema/top-k/阈值。当前实验 5 原始 CSV 不含这些逐案例字段，因此审计明确将 `csv_retrieval_bindings_bound` 标记为 FAIL，而不是用汇总级配置替代逐行证据。该失败应在论文中作为版本与参数记录缺口报告；没有补采真实逐案例快照前，不得声称检索条件已逐案例可回放。审计同时输出 `row_integrity.retrieval_binding_gaps`，按方法、适用字段和行数报告 `row_count`、`required_fields`、`rows_with_complete_snapshot`、`rows_with_any_gap`、`missing_by_field` 与 `mismatch_by_field`，从而区分字段不适用、字段缺失和非空漂移；完整快照行与有任一缺口行恰好划分适用行数，字段级计数的键集合和固定顺序与方法规范必需字段完全一致，并受适用行数和有任一缺口行数双重上界约束。审计器同时输出 `retrieval_gap_summary_valid` 与结构化违规列表，便于在 JSON 层定位分区、字段键或计数错误。描述性 Markdown 进一步按方法以适用行数为分母呈现完整快照行和有任一缺口行的 `n/%`，并将每个字段的缺失与非空漂移改写为 `字段=n/%`，使参数绑定缺口规模和字段分布可直接引用。

为阻止新运行重复产生同一缺口，生产 Rust 的 CSV 导出已将逐日志 `retrieval_config_json` 和稳定快照字段作为追加列原生写出，并同时记录运行级语料快照、索引版本和 `graph_schema_version`。未落库失败行的这些字段保持为空，不会伪造检索条件；因此该修复提升的是未来证据采集能力，不会把历史实验 5 CSV、审计 JSON 或 `paper_ready=false` 结论升级为可引用的确认性结果。

## 确认性批次的最低归档清单

在任何效果数字写入论文主结论前，必须将下列材料绑定到同一批次 ID、代码 revision 和分析脚本版本：

1. **数据绑定**：每个项目的语料快照、文件清单、文件哈希、审核状态和项目 ID；禁止把运行后新增资料混入测试集。
2. **问题集绑定**：至少 3 个项目、至少 60 题、每项目至少 20 题；保存题干、题型、`question_index`、答案要点、可接受同义表达和拒答规则。
3. **方法与参数绑定**：五种方法、模型、提示版本、温度、最大输出、检索 top-k、阈值、重复次数、随机种子和执行计划哈希。
4. **逐案例证据**：每个案例的 `query_log_id` 或明确的未落库失败状态、回答、来源块、图谱关系、引用审计、Token、时延、回退和错误原因。
5. **失败分母**：`total_cases = completed + failed + unexecuted`；不得删除异常案例，不得把运行级故障改写成成功案例。
6. **人工评价**：方法隐藏、两名独立评价者、准确性/可追溯性/质量评分、签核时间、解盲键和一致性统计；人工结果不得由自动规则补填。
7. **统计分析**：运行前冻结主指标、次指标、排除规则、配对比较、置信区间和效应量；二元配对结果可使用 McNemar，连续指标应报告配对差值及分布，不用 P95 单独证明性能优势。
8. **版本归档**：代码 revision、Rust/Node/Python 版本、锁文件、容器或运行时摘要、语料/题集/金标准/配置/分析脚本哈希，以及证据包校验结果。

## 建议的论文统计报告格式

对每个方法报告 `N_total`、`N_completed`、`N_failed`、`N_unexecuted`，并将失败原因按预注册分类汇总。主结果至少包含：

- 人工事实准确率及其配对置信区间；
- 人工可追溯率及其配对置信区间；
- 引用审计的来源命中、引用有效性和证据覆盖率；
- 规则化任务完成率，仅作为预先冻结且独立于回答生成的辅助指标；
- 时延中位数、P95、Token 和成本，并说明异常值及失败案例处理；
- 两名评价者的一致率和 Cohen's kappa（若评价设计满足其适用条件）；
- 按题型、项目和失败类别的分层结果，避免只报告总体平均数。

推荐的归档前检查命令：

```bash
backend/.venv/bin/python -m pytest -q \
  scripts/test_check_rag_experiment_evidence.py \
  scripts/test_check_rag_evidence.py \
  scripts/test_freeze_rag_evidence.py
backend/.venv/bin/python scripts/check_rag_experiment_evidence.py \
  --package rag-experiment-<run_id>-evidence.json \
  --output rag-experiment-<run_id>-evidence-check.json
python3 scripts/audit_rag_csv_consistency.py \
  --csv rag-experiment-<run_id>.csv \
  --evaluation rag-experiment-<run_id>-evaluation-sheet.csv \
  --output rag-experiment-<run_id>-csv-audit.json
python3 scripts/audit_rag_five_mode_bundle.py \
  --output docs/experiments/rag-experiment-5-internal-bundle-audit-YYYY-MM-DD.json
backend/.venv/bin/python scripts/check_paper_material_freshness.py \
  docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md \
  --root . \
  --output docs/experiments/rag-experiment-5-internal-descriptive-results-freshness-latest.json
```

只有证据包检查通过、确认性人工评审完成门禁通过且所有哈希可复核时，才可把对应数字写成论文的确认性结果；否则应明确标注为历史开发证据、内部自动证据或待完成材料。
