# Rust 检索探索性同部署重复性实验协议 v1

## Material Passport

- Origin Skill: academic-research-suite / experiment-agent
- Origin Mode: plan
- Origin Date: 2026-08-13
- Verification Status: DRAFT / NOT FROZEN（独立 QA 复核通过；实现与运行门禁仍为 BLOCKED）
- Version Label: rust_retrieval_pilot_protocol_v1
- Lifecycle: `INTERNAL_EXPLORATORY` / `DRAFT` / `NOT_FROZEN` / `BLOCKED`

## 1. 论文用途与证据等级

本实验只回答一个前置问题：**当前 Rust/Axum 检索实现能否在固定题集和固定语料上产生身份可绑定、结果可复核的探索性检索证据？**这里的“重复性”仅指同一部署、同一数据库状态下的即时重复运行，不等同于跨机器、跨部署或重建数据库后的可复现性。

它不是实验 4/5 的“补签名”，也不能把历史 legacy FastAPI 结果改写成 Rust 结果。由于题集只有 GSE111619 单项目 20 题、答案要点由项目内部人员建立，且没有独立人工盲评，本实验即使全部通过，也只能标记为 `INTERNAL_EXPLORATORY`，不能标记为确认性实验或跨项目泛化证据。

本实验可支撑论文中的内容：

- 区分历史原型批次与当前 Rust 实现，消除“论文方法等于当前系统”的版本混写；
- 报告 Rust 实现中 BM25、混合检索和一跳图谱增强检索在同一 20 题上的内部描述性表现；
- 验证题集、语料、运行时、代码、镜像、嵌入配置和输出哈希能否形成闭合证据链；
- 暴露迁移后算法行为变化和失败机制，为后续预注册消融及确认性实验选定变量。

本实验不得支撑以下结论：

- “当前 Rust 系统优于历史 FastAPI 系统”；
- “KG-RAG 显著提高事实准确率”或“达到 90% 准确率”；
- 跨项目泛化、独立人工准确性、可用性或生产性能；
- BGE-M3 的实际效果，除非本批次确实运行在已绑定的 BGE-M3 工件上；
- 生成答案质量、Token 成本或端到端时延；
- 标准信息检索意义上的 Recall@k、nDCG@k 或 MRR，除非另行建立人工 chunk-level qrels；
- 跨环境可复现性。数据库重建可能改变内部 ID，即使语义证据未改变，也不能仅以内部 ID 的逐字节哈希判定跨环境复现。

历史评测入口调用生成式 `/rag/query`，在检索后仍会调用生成模型，初检无结果时还可能查询重写。当前未冻结工作树已出现 retrieval-only 候选实现，但在它通过 G5A、形成稳定 revision 并完成部署核验以前，本协议仍保持 `BLOCKED`；不得把历史端到端输出或未验收工作树输出命名为已通过的纯检索证据。

## 2. 研究问题与分析对象

- P-RQ1：在固定 GSE111619 题集上，当前 Rust 实现的 BM25、混合检索和一跳图谱增强检索分别覆盖多少冻结答案要点？
- P-RQ2：三种模式的差异集中在哪些问题类型和失败机制？
- P-RQ3：在代码、数据、数据库和运行配置均不变化时，完整有序检索证据及其规范化哈希能否在同一部署中精确重复？

分析单位是“问题”，不是单个答案要点，也不是三种方法返回的证据条目。主报告保留全部 20 题；按问题类别进行的结果只作分层描述，不进行选择性排除。

## 3. 固定输入

| 输入 | 路径 | 当前已核对状态 |
| --- | --- | --- |
| 题集与答案要点 | `data/real/GSE111619/gse111619_questions.json` | 20 题、56 个答案要点；SHA-256 `f1f4f8e2726129cdf54e4c65cfcc09d6fb9314ca30498ccbd854533fc6f2fe4a` |
| 原始知识文档 | `data/real/GSE111619/gse111619_knowledge_document.txt` | SHA-256 `5a9188ebde46c5707b070c48e85eb6faea543b131cc1a5b6f94179f30afa04ea`；该文件哈希不等于数据库语料快照哈希 |
| Rust 评测入口、指标/trace/canonicalization 主实现 | `scripts/experiments/evaluate_rust_retrieval.py` | 在批次 manifest 中自动计算，不在协议中手工维护“当前哈希” |
| 匹配规范化、题集校验与 fact ID 依赖 | `scripts/experiments/evaluate_retrieval.py` | 在批次 manifest 中自动计算；不得把其中旧 IR 适配器当作本 pilot 的指标公式 |
| 证据冻结实现 | `scripts/freeze/freeze_rag_evidence.py`（仅发布级 BGE-M3 绑定）与 `scripts/freeze/freeze_system_evidence.py --rust-pilot-readiness`（本 pilot 冻结前审计） | 在批次 manifest 中自动计算；两者不得混用 |
| Rust 方法与状态实现 | `backend/src/rag.rs`、`backend/src/api/rag.rs`、`backend/src/api/mod.rs`、`backend/src/models.rs`、`backend/src/state.rs` | 在批次 manifest 中自动计算 |
| 接口与验证实现 | `backend/openapi.json`、`frontend/src/lib/api-schema.d.ts`、`frontend/src/lib/api.ts`、`scripts/experiments/test_evaluate_rust_retrieval.py` | 在批次 manifest 中自动计算 |
| Rust 工具链 | `backend/rust-toolchain.toml`、`backend/Cargo.lock` | 在批次 manifest 中自动计算 |

题集与原始文档哈希只是协议起草时核对的输入身份，不是未来运行的完整冻结清单。正式执行前必须在代码稳定且 commit 固定后自动生成一次性 manifest；manifest 必须包含 UTC `generated_at`、完整 commit、dirty 状态、所有输入和实现文件哈希。所有 manifest 路径必须是该 checkout 内的真实相对路径；缺失必需输入必须写为 `sha256: null`、`status: FAIL` 并使 `local_manifest_inputs_complete: false`，不得以临时文件名或 basename 代替绑定。`local_manifest_inputs_complete` 只表示 manifest 声明的本地文件均存在并已哈希，不表示整个 pilot 已冻结；整体是否满足 revision、镜像/模型、corpus/graph 与 G5A/G5B 等准入项由 `freeze_requirements_complete` 和 `overall_verdict` 表示。禁止手工维护代码“当前哈希”，也不能用原始文档哈希替代数据库实际语料快照哈希。

## 4. 执行准入门槛

只有 G0–G4 与 G5A 的运行前能力门全部通过，才允许开始第一遍运行。G5B 是运行后批次验收，不能作为尚未运行时的循环准入条件。

### G0：代码身份可绑定

- 工作树必须干净；不得只记录一个 HEAD，却在未提交修改上构建镜像。
- `APP_REVISION` 必须等于实际构建的完整 Git commit SHA，不能为 `unversioned`。
- 保存 `git status --porcelain` 的空输出、完整 commit SHA，以及第 3 节所列方法、状态、接口、指标、冻结和测试实现的 SHA-256。
- 保存后端镜像的不可变 digest，并证明运行容器使用该 digest。

当前仓库存在未提交方法实现修改，因此 G0 当前状态为 `BLOCKED`。在获得用户授权并形成干净、可复核 revision 之前，不得执行本实验。

### G1：运行时身份可绑定

- 保存完整 `/metrics` 响应；其 `runtime.api_runtime` 必须为 `rust-axum`。
- `/metrics` 顶层 `revision` 必须与 G0 的完整 commit 完全一致。调用者自报的 `git_revision` 不构成运行时证明。
- 通过容器检查或部署平台证明取得正在运行镜像的 image ID/RepoDigest，并与 G0 对照；命令行传入的任意字符串不构成证明。
- 嵌入模型身份必须绑定可核验的本地文件 SHA、OCI digest、模型仓库 commit 或推理服务 deployment revision；只记录模型显示名称不构成工件身份。
- 保存 Rust 版本、操作系统、CPU、内存、PostgreSQL 与 pgvector 版本。
- 保存非敏感运行配置快照；API key、Token 和数据库口令不得进入证据包。

### G2：语料身份由系统证明

- 从 Rust 数据集状态或证据端点取得数据库实际使用的 `corpus_snapshot_hash`、`rag_index_version`、`embedding_model` 和有效 chunk 数。
- 对包含 `kg_enhanced_rag` 的批次，同时取得与实际图检索相同活动范围的 `graph_snapshot_hash`、有效实体数和有效关系数；图 schema 版本不能替代图内容快照。
- 图快照的 eligibility 必须复用实际图检索 SQL 的项目、权限、审核、有效性和版本范围；规范化材料包含所有会影响过滤、评分或展示的实体/关系字段，并使用冻结的 canonical ordering。有效实体计数定义为该活动关系集合所引用的 distinct endpoints，不得改用项目中全部实体数。
- “冻结语料”指实际检索活动范围只能包含本批次冻结、已审核、已同步且属于当前 index 的语料；数据库中可以存在 pending、failed 或旧 index 记录，但它们不得进入快照或实际检索。
- 传给评测脚本的 `--corpus-sha256` 与 `--corpus-chunk-count` 必须和 API 返回值逐项一致。
- Rust API 与评测脚本的语料身份失败关闭实现目前只存在于未冻结工作树；在形成稳定 commit、更新并核对 OpenAPI/前端类型、完成路由测试和实际部署验证前，G2 仍为 `BLOCKED`。
- 未冻结工作树中的候选快照已扩展到实际 chunk/relation/entity 主键、内容与 embedding 文本校验和及图关系字段，但只有在契约测试、真实数据库事务测试和稳定 revision 复核均通过后，才能认定为“检索有效语料快照”。数据库主键用于绑定本次部署内实际读取的证据；跨环境比较必须另用内容派生 stable ID，不能把主键相等当作跨环境复现。
- 初始、每题开始前和整批结束后的客户端校验只能作为补充；仅靠这些检查仍有 TOCTOU 空窗，不能证明检索实际读取了已检查输入。每个 retrieval-only 请求必须携带 `expected_corpus_snapshot_hash` 和适用时的 `expected_graph_snapshot_hash`；服务端必须在与该次检索相同的 PostgreSQL 事务/MVCC 快照中计算并核对双快照，再执行检索。任一预期值不符即失败关闭，不返回检索结果；成功响应必须回传实际使用的双快照哈希及相应 chunk/实体/关系计数。
- 评测器必须为每个题—方法请求保存 `snapshot-checks.jsonl`：运行编号、`question_id`、模式、请求中的预期值、服务端回传的实际使用值、文档/图计数、UTC 时间和判定。任何漂移使整批 `invalid`，已完成案例只能留作失败诊断，不能进入同一批指标。
- `snapshot-checks.jsonl` 的双快照字段固定为 `expected`、`actual`、`used`；文档与图各自都必须满足 `expected == actual == used`。每行还必须保存 `equality.expected_actual`、`equality.expected_used`、`equality.actual_used` 三个布尔值，三者全为 `true` 才能写 `verdict=pass`；缺少任一 `used_*` 字段或任一相等性断言失败均失败关闭。

### G3：检索配置身份可绑定

冻结 JSON 至少包括：

- `embedding_backend`、`embedding_model`、`embedding_dimension`；
- `rag_index_version`、`retrieval_strategy`、`retrieval_top_k`、`vector_candidate_k`；
- `chunk_size`、`chunk_overlap`；
- `graph_schema_version`、`graph_top_k`、`effective_graph_top_k`、`graph_min_score`；
- RRF rank constant，以及精确词项查询与普通查询的向量/词项排名权重；
- 题集 SHA-256、语料快照 SHA-256、项目 ID 和数据集 ID；
- 对 KG 批次的 `graph_snapshot_hash`、有效实体数、有效关系数和 graph schema version；
- BM25 确定性同义词扩展的实现哈希、词表/规则哈希或不可变版本。

静态调用参数不足以证明实际使用的检索配置。retrieval-only 响应必须逐题返回 `effective_*` 配置，至少闭环核对实际候选数、结果上限、BM25/向量开关、精确查询判断、RRF 参数、图谱参数和实际权重；同时保存该题的规范化查询及实际扩展 terms。`query_log_id` 只能作为附加审计定位，不能替代响应中的实际配置。

Rust 当前默认策略是 `rrf-v1`，不是论文历史实验中的 `0.8 × vector + 0.2 × lexical`。`legacy-weighted` 也只能按当前实现记录为 `0.7/0.3`。任何报告都必须按实际快照命名算法，不能沿用历史公式。

### G4：嵌入后端分层

- 若运行时为 `development + hash + rust-hash-512-v1`，结果只能标记为开发替身探索性 pilot；“embedding artifact hash”应明确是 `backend/src/embedding.rs` 实现哈希，而不是伪称模型文件哈希。该批次只能验证同部署即时重复性，不能生成发布级 BGE-M3 evidence binding，也不得标记 `reproducibility_verified=true`。
- 若运行时为 `openai_compatible + BAAI/bge-m3 + 1024`，必须按 G1 允许的类型保存实际服务/模型的不可变工件身份，且部署配置须满足发布级证据门禁，才可生成 BGE-M3 evidence binding。本地模型文件可得时强制保存文件 SHA-256；远程服务应绑定 deployment revision、OCI digest 或模型仓库 commit，不得虚构不可获得的模型文件 SHA-256。
- 两种后端的结果不得合并，不得用 hash pilot 推断 BGE-M3 效果。

当前 `freeze_rag_evidence.py` 只接受发布级 BGE-M3 配置，不能被 hash-backend pilot 误用为第二遍验证器。内部重复性状态与发布级复现状态必须使用不同字段和验收路径。

### G5A：运行前检索与审计能力门

- 必须使用 retrieval-only API 或等价的显式评测开关，禁用外部生成模型触发的补充查询改写、答案生成和引用修复；若仍调用 `/rag/query`，本 gate 失败。当前 `retrieve()` 内部的确定性 BM25 同义词扩展属于被研究检索方法，必须保留、冻结并在 effective config 中显式记录，不能为了“纯检索”而静默关闭。仅在报告中观察 `query_rewritten=false` 不能证明生成模型未参与。
- retrieval-only 契约必须实现 G2 的预期双快照原子绑定；契约测试、数据库路由测试、漂移失败路径测试、无外部 LLM 调用测试和离线重算夹具必须在运行前通过。
- 每题保存 raw response 和 canonical result projection 两层数据。raw 层保留所有服务端运行字段；canonical 层只包含冻结问题 ID 与题干、模式、完整有序证据、effective config 和服务端实际使用的文档/图快照及计数。
- 每条证据至少保存稳定来源标识、评测实际读取的规范化完整文本/片段、其内容 SHA-256、从 1 开始的 `evidence_presentation_rank`、规范化分数、类型和全部适用图关系字段；内部数据库 ID 可附带，但不得作为跨环境唯一身份。
- canonical 层明确排除 UTC 时间、时延、`query_log_id`、trace/span ID 和其他每次运行必然变化的字段。本项目不宣称采用 RFC 8785/JCS，而冻结仓库自定义 `rust-retrieval-canonical-v1`：UTF-8；字符串值做 NFC；对象 member name 由冻结 schema 限定为 ASCII 且不另做 Unicode 规范化；对象键按 Unicode code point 排序；所有数组保留输入顺序，其中 `ordered_evidence` 在进入 canonicalizer 前必须验证按从 1 开始、连续且唯一的 `evidence_presentation_rank` 排列；冻结 canonical schema 列出的可选键必须显式存在并以 `null` 表示缺失。有限 JSON 数值词法完全采用 manifest 中锁定的 CPython patch 版本 `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)` 实际输出，不宣称数学最短或跨语言稳定；NaN/Inf 使批次失败。`canonicalization_version`、Python patch version、完整 canonical schema 和覆盖组合字符、键序、`-0.0`、极小/极大有限数及非法非有限数的测试向量必须在批次 manifest 或其冻结前门禁输入中逐项列出；算法、schema 或运行时变化必须升级版本，不能沿用旧哈希比较。冻结前审计只能读取本地输入与已保存证据，不得通过 `/rag/query`、`/rag/retrieve` 或其他检索端点补取 corpus/graph hash。
- `result_sha256` 必须从已落盘的 canonical 层重新读取后计算，不得依赖报告外的进程内对象。离线审计必须从已落盘证据文本与冻结题集重新生成逐题指标；`per_query` 对每个 fact 保存 `fact_id`、命中 alias、`evidence_presentation_rank` 和 evidence stable ID 的匹配 trace，再由该 trace 重算 aggregate，不能只复算已有聚合值。raw response 与 canonical projection 必须逐案例重建一致；文档/图文本 SHA-256、内容派生 stable ID、图匹配文本 hash、事实 trace 均须离线重算。
- 任一 gate、第二遍比对或证据绑定失败时，先写出带 UTC 时间、阶段、期望值、实际值和错误类型的 failure record，再以非零状态退出。

当前实现尚未在稳定 revision 上通过上述能力测试，因此 G5A 当前状态为 `BLOCKED`。

### G5B：运行后批次结果验收

每一遍完成后才验收：全部计划题—方法案例恰好构成冻结题集 × 三模式的唯一笛卡尔积；逐请求双快照原子绑定均通过且 `snapshot-checks.jsonl` 恰好一行对应每个唯一键；raw/canonical 两层数据、完整证据文本和逐 fact 匹配 trace 均已落盘；从落盘材料离线重建的 `per_query`、aggregate 与 `result_sha256` 均一致。每个 gold fact 在 trace 中恰好一行，未命中字段必须为 `null`；`ordered_evidence` 的 presentation rank 从 1 开始、连续且唯一。第二遍还必须与第一遍的 canonical `result_sha256` 精确一致，且只有提供 expected hash 并精确匹配时才写 `same_deployment_repeatability_verified=true`；首遍必须为 `false`，不得写 `reproducibility_verified=true`。G5B 失败时批次标记 `invalid`，不得回写为运行前 G5A 已通过的证据。

## 5. 对照方法与保持不变的条件

当前评测入口只比较：

1. `bm25_rag`；
2. `project_rag`（当前 Rust 混合检索）；
3. `kg_enhanced_rag`（相同资料检索结果上增加一跳关系证据）。

本 pilot 不包含纯向量、纯 LLM、直接结构化查询，也不构成五方法实验。当前脚本输出中的 `ablation` 为空，因此不得把本批次写成消融实验。

题集、项目数据集、索引、嵌入后端、检索配置、图谱 schema 和评测代码在两遍运行之间全部保持不变。两遍运行之间禁止重新同步文件、重建图谱、修改审核状态或改变数据库记录。

## 6. 执行顺序

1. 通过 G0–G4 与 G5A，并用现有 `scripts/freeze/freeze_system_evidence.py --rust-pilot-readiness` 生成 `rust-retrieval-pilot-freeze-readiness-latest.json` 与绑定输入的 manifest。该命令只读审计、不访问检索端点、不生成指标；报告成功写出不等于 gate 通过，`overall_verdict` 必须为 `PASS` 才能进入第一遍。审计命令在发现阻断时仍可返回 0，以便保存报告；`overall_verdict=BLOCKED` 是唯一放行判据。
2. 保存 `/metrics`、项目 RAG 状态和容器镜像检查结果。
3. 用固定题集运行第一遍，保存 raw/canonical 数据、逐 fact 匹配 trace 和 `result_sha256`，随后执行第一遍 G5B。
4. 在相同部署与数据库状态下立即运行第二遍，执行第二遍 G5B，并比较两份已落盘 canonical 完整结果的哈希。
5. 第二遍必须精确重复结果哈希；不允许失败后自动重试或选择性保留成功结果。hash-backend 批次只写 `same_deployment_repeatability_verified`，不得升级为发布级或跨环境 `reproducibility_verified`。
6. 对证据包做离线一致性审计，保存命令、退出码和标准输出。
7. 只有全部通过后生成描述性表格和图；原始 JSON 永远先于派生图表。

示意命令沿用 `docs/ai-rag-setup.md` 第 7 节，但实际执行时必须把占位符替换为 preflight 中已核对的值，并将完整命令写入 `commands.txt`。访问 Token 只通过环境变量注入，不得写入命令记录。

## 7. 指标与分析计划

主指标：每种方法实际返回集合内的 `GoldFactAliasHitCoverage@returned_set`。对题目 (q) 的冻结 fact 集 (F_q)，令 (r_f) 为任一证据首次词法命中 fact (f) 的 `evidence_presentation_rank`，未命中则为无穷；令 (L_q) 为该题该方法实际保存的有序证据条数，则逐题值定义为

\[
\mathrm{AliasHitCoverage}_{q}=\frac{\sum_{f\in F_q}\mathbf{1}(r_f\le L_q)}{|F_q|}.
\]

aggregate 是全部冻结问题逐题 AliasHitCoverage 的等权宏平均，不允许按 fact 数量重新加权。逐题必须同时报告实际 (L_q)。由于 (L_q) 是实际返回条数，`r_f≤L_q` 表示“返回集合中存在词法命中”，而不是对配置上限的等预算评价；KG 模式还会在文档后追加图证据，所以方法间配对差值只能解释为各自实际返回集合的增量 alias 覆盖，不能解释为等预算检索优越性。可附加同一定义下的固定 `@1/@3/@5/@10` 敏感性描述，但不同证据类型没有统一得分顺序时仍不构成标准 IR 比较。

词法命中谓词冻结为：对证据文本和 alias 分别执行 Unicode NFKC、转小写、将 `μ` 统一为 `µ`、删除不属于 `[a-z0-9\u4e00-\u9fffµ><=]` 的字符；规范化 alias 非空且为规范化证据文本的 substring 即命中，同一 fact 按题集中 alias 顺序保存首个命中。它只测词项 alias 是否出现，不证明证据蕴含该命题，更不证明事实正确；报告中不得把它简称为 FactCoverage、Recall 或准确率。

次指标直接从每个 fact 的最低 `evidence_presentation_rank` 计算，不再把 fact 展开成伪文档排名：

- `first_alias_hit_rr_q = 0`（无任何 fact 命中），否则为 (1/\min_{f\in F_q}r_f)；
- `rank_discounted_fact_alias_coverage_q = |F_q|^{-1}\sum_{f:r_f<\infty}1/\log_2(r_f+1)`，取值范围为 `[0,1]`；
- aggregate 同样是逐题值的等权宏平均。

这两个名称是项目自定义的词法命中描述量：前者的 aggregate 可称 mean first-alias-hit reciprocal rank，后者不是标准 nDCG；两者均不得以 MRR/nDCG（包括仅加 surrogate 前缀）出现在论文表头。

rank 单位固定为证据在响应中的 `evidence_presentation_rank`：文档证据保持服务端 sources 顺序；KG 模式把 graph evidence 接在全部文档证据之后，保持 graph_context 内部顺序。这一合成展示顺序不等于跨证据类型的统一检索得分排序，因此一条证据命中多个 fact 时，各 fact 继承同一 presentation rank；同一 fact 被多条证据命中时只保留最低 rank。每个首次命中必须保存 `fact_id`、实际命中 alias、最低 `evidence_presentation_rank` 和内容派生 evidence stable ID。KG 模式及任何不具统一打分序列的方法，其 rank 指标只作机制描述，不能作为优越性主证据；主比较以 Coverage 为准。按既有问题类别的分层结果只作探索性热图，不进行类别层推断。

报告要求：

- 同时报告 aggregate 和全部逐题结果，不能只报告均值；
- 预先报告 `kg_enhanced_rag - project_rag` 与 `project_rag - bm25_rag` 的逐题配对差值；效应量同时给出 paired mean、paired median 和胜/平/负题数；
- 按问题配对重采样的 95% percentile bootstrap 区间使用固定种子 `20260813` 和 `10,000` 次重采样；参数进入 manifest。该区间只描述固定单项目题集上的不确定性，不解释为跨项目总体推断，也不作为通过 gate；
- 单项目 20 题的小样本只作描述，不用 `p < 0.05` 代替外部效度；
- 报告 BM25、混合检索和图谱增强各自的胜/平/负题数；
- 失败记录先写可直接观察的 symptom；人工编码的可能原因可使用语料无答案、资料检索未覆盖、图谱未覆盖、top-k 截断、查询解析、结构化过滤、连接/聚合缺失、评价规则不充分或 `UNKNOWN`，并保存 reviewer、依据、置信度及 `reviewer_coded`/`inferred` 状态，不把归因写成系统自动证明的事实；
- 自动 alias/答案要点覆盖不得命名为“事实准确率”或“人工准确率”。

建议论文图表仅在结果产生后制作：逐题配对差值图、问题类别 × 方法热图、错误类型计数图。时延和 Token 不属于本脚本的可复现主输出，不在本 pilot 中制作性能图。

## 8. 预期输出与验收

建议输出目录：`output/paper-evidence/rust-retrieval-pilot-<UTC批次时间>/`。

| 输出 | 验收标准 |
| --- | --- |
| `rust-retrieval-pilot-freeze-readiness-latest.json` | 冻结前门禁；至少显示 `base_revision`、`app_revision`、`tracked_worktree_clean`、`in_scope_untracked_files`、Rust runtime、image digest、embedding backend/model/dimension、protocol/questions/evaluator/OpenAPI/corpus/graph hashes、G5A/G5B 状态与 `overall_verdict`；缺值必须为 `null` 并为 `FAIL`/`BLOCKED`，不得以当前 HEAD 或本地文件 hash 伪造稳定绑定 |
| `rust-retrieval-pilot-freeze-readiness-manifest-latest.json` | 自动生成；绑定 readiness 生成脚本、协议、题集、evaluator、evaluator tests、OpenAPI、runtime contract 和实现文件的 checkout-relative 路径及 SHA-256；缺失输入为 `null`/`FAIL`，`local_manifest_inputs_complete` 必须为 `false`；`freeze_requirements_complete` 仍须同时满足稳定 revision、干净工作树、不可变镜像/模型、corpus/graph 及 G5A/G5B；manifest 不自引用自身 |
| `runtime-metrics.json` | 保存完整 `/metrics` 响应；`rust-axum`、顶层 revision、嵌入工件指纹与冻结配置一致 |
| `dataset-status.json` | 文档语料哈希、chunk 数、图快照哈希、实体/关系数、索引和嵌入模型与冻结输入一致；保存初始与结束状态 |
| `snapshot-checks.jsonl` | 每个题—方法请求一行，保存预期/服务端实际使用的双快照、计数、UTC 时间与判定；行数与计划案例数一致 |
| `first-run.json` | 保存 raw response、canonical result、完整逐题有序证据文本、逐 fact 匹配 trace、离线重建的 `per_query` 与首个规范化结果哈希；第一遍 G5B 通过 |
| `second-run.json` | 保存同等完整材料；第二遍 G5B 通过，`same_deployment_repeatability_verified=true` 且 canonical 结果哈希与第一遍精确一致 |
| `failure.json` | 任一失败路径先落盘；包含阶段、期望值、实际值、错误类型和 UTC 时间 |
| `commands.txt` | 无密钥；包含工作目录、命令、退出码和 UTC 时间 |
| `validation.md` | 明确 `INTERNAL_EXPLORATORY` / `DRAFT` / `NOT_FROZEN`；记录异常、失败和不可写结论 |

任一准入项失败时停止运行并保留失败证据，不得为获得“好看结果”更换题目、答案要点或删除案例。外部模型/服务短暂失败也不自动重试；应记录批次失败，由研究者决定是否建立新批次。冻结前门禁若成功生成 `BLOCKED` 报告可返回进程码 0，但不得据此启动 pilot；只有报告 `overall_verdict=PASS` 才是放行。

## 9. 进入下一阶段的条件

本 pilot 验收后，下一阶段仍不是直接宣称论文结果成立，而是：

1. 基于 pilot 观察预注册 Rust 消融变量；
2. 冻结至少 3 个项目、总计至少 60 题的外部题集与 gold facts；
3. 完成方法隐藏的双人独立评价并报告一致性；
4. 以项目/问题为统计单位给出配对效应量、置信区间和多重比较处理；
5. 将确认性批次与本 pilot、历史实验 4/5 分别编号和归档。

只有完成上述外部冻结与人工评价后，才能讨论确认性的人工事实准确率、可追溯率和跨项目适用边界。
