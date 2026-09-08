# RAG 实验证据包协议 v1

## 目的

`GET /rag/experiments/{run_id}/evidence.json` 将一次 RAG 对照实验的运行级配置、逐案例日志、检索证据、知识图谱上下文、引用审计和失败案例导出为同一份 JSON。它是论文实验复核与材料归档的规范证据包；同一运行的 CSV 兼容导出也会携带逐案例检索快照，但两者都不把自动规则结果包装成人工盲评结果。

该端点在 `backend/openapi.json` 中声明为 `RagEvidencePackage`，并由
`npm run generate:api` 生成前端类型。OpenAPI 只把论文归档所依赖的稳定字段设为显式契约，证据来源、图谱上下文、检索配置、用量和引用审计等扩展对象保持可扩展；因此客户端类型同步不会阻止后续增加证据字段。
当前 v1 契约同时要求运行摘要的 `fatal_error`、`errors`、`execution_plan`、
`unexecuted_cases`，以及每个案例的身份、状态、失败元数据、回答、证据数组、检索配置、
运行遥测和引用审计字段显式存在（即使值为 `null` 或空对象）。这与 Rust 导出器对已落库
案例/系统补入失败案例的稳定输出一致，也与离线检查器的必需字段边界一致；字段缺失会在
OpenAPI 客户端校验或归档检查阶段暴露，而不会被解释为“没有失败”或“没有证据”。

### 运行版本契约

证据包及其运行时配套证据使用拆分的版本身份：`R=runtime_source_revision` 必须由
`/ready`/`/metrics` endpoint、OCI image、runtime config 和 Rust runtime contract 一致指向；
endpoint 的 `revision` 字段语义也是 R。`T=experiment_tooling_revision` 仅表示生成/执行证据时
的 clean Git `HEAD`，并绑定 runner、preflight、协议和 evaluator 的内容 SHA，不能写入 endpoint
revision 或冒充部署运行时版本。冻结 preregistration 的 `E=evidence_revision` 是按
`path+sha256+R+T` 稳定排序生成的内容摘要，排除 manifest 自身；任何输入或 E 篡改都必须被
复算拒绝。旧的单一 revision 包没有可验证的 R/T 契约，必须 fail-closed 并显式标记为
`legacy blocked`，不得升级为 v1 确认性证据。
外部 authority 的 SSH 签名消息是绑定该 canonical freeze-content commitment 的固定摘要；
authority artifact 必须同时给出 `freeze_content_sha256` 与 `commitment_sha256`，任何 status、
题集/gold/config/corpus/graph、文件 SHA 或 R/T 变化都会使旧签名失效。

题集与方法数组的数量约束也在 OpenAPI 中显式声明：`questions` 必须包含 1–50 个唯一题目，
每题长度为 1–4000 个字符；`modes` 必须包含 1–5 个唯一方法，且方法值来自生产五方法集合。
这些约束与 Rust 创建端点的归一化规则、离线归档检查器和论文题集—方法绑定边界一致。
运行协议的 `repetitions` 也固定为 1–10；`execution_plan_hash` 必须是 64 位小写 SHA-256
十六进制摘要。前者限制实验规模，后者使执行计划的重建与归档比对具有机器可校验的格式边界。
实验名称 `experiment.name` 同样必须是去除首尾空白后非空、且不超过 255 个字符的字符串，
用于让论文材料中的运行身份保持稳定、可读且可被创建端点拒绝畸形输入。
运行级 `experiment.status` 也固定为 `queued`、`running`、`interrupted`、`completed`、
`completed_with_errors` 或 `failed` 六种状态；未知状态不会被客户端类型或导出门禁静默接受。

## 与论文实验章节的对应关系

| 证据包字段 | 论文用途 |
| --- | --- |
| `experiment.questions`、`experiment.modes` | 说明测试问题与对照方法 |
| `experiment.questions_sha256` | 绑定题集内容；按 Rust `serde_json::to_vec` 的紧凑 UTF-8 JSON 字节重算 |
| `experiment.corpus_snapshot_hash`、`experiment.rag_index_version` | 绑定实际检索使用的已批准、已同步、当前索引版本文档块快照；纯 LLM/结构化查询模式为 `null` |
| `experiment.graph_schema_version` | 绑定知识图谱结构/展开规则版本，并与 `config_snapshot.graph_schema_version` 一致；历史包可为 `null`，新配置快照必须为非空字符串 |
| `experiment.repetitions`、`experiment.randomize_order` | 说明重复次数与执行顺序是否随机化 |
| `experiment.random_seed`、`experiment.execution_plan_hash` | 说明随机化和执行计划可重建 |
| `experiment.embedding_model`、`experiment.generation_model` | 记录模型与实验条件 |
| `config_snapshot` | 复核分块、top-k、图谱阈值、融合算法、索引版本和提示版本 |
| `cases[].sources`、`cases[].graph_context`、`cases[].source_count`、`cases[].graph_hit_count` | 支撑来源追溯与关系证据分析；来源必须保留正整数 `chunk_id`/`file_id`，图谱关系必须保留正整数 `relation_id`/`source_entity_id`/`target_entity_id`，计数必须分别等于两个证据数组长度 |
| `cases[].citation_audit` | 统计引用完整性、无效引用和人工复核触发情况 |
| `cases[].retrieval_config` | 逐案例保留嵌入模型、索引版本、检索策略、chunk/top-k、图谱 top-k/阈值和最低相关度；用于检查参数是否漂移 |
| `cases[].response_ms`、`cases[].usage` | 汇总时延与 Token 开销 |
| `cases[].error`、`cases[].failure_scope`、`cases[].failure_code` 及运行摘要中的失败案例 | 保留失败分母，并以机器可读范围/代码区分案例失败与运行级故障，避免选择性删除或靠错误文本推断 |

### CSV 兼容导出的逐案例快照契约

生产 Rust 端点 `GET /rag/experiments/{run_id}/export.csv` 从新运行开始输出 35 列：保留原有 20 列，并追加原始 `retrieval_config_json`、运行级 `corpus_snapshot_hash`/`rag_index_version`/`graph_schema_version`，以及嵌入模型、索引版本、检索策略、top-k、候选数、chunk、图谱阈值和最低相关度等稳定字段。追加列保持表格消费者的前 20 列兼容，同时让离线审计器能直接检查每一条已落库日志的 retrieval snapshot，而不是用运行级汇总配置推断逐案例条件。实验执行器在领取队列和继续每个案例前还会将配置快照中的图谱 schema 版本与当前生产常量比较；漂移时运行级失败关闭并记录 `input_binding_drift`，不允许在同一运行中混入不同图谱规则。

`graph_schema_version` 由生产 Rust 检索器固定记录为 `kg-v3-numbered-list-expansion`，与现有知识图谱抽取管线的版本契约一致。若实验失败但没有生成 `query_log_id`，CSV 仍保留失败行，新增快照列留空；这表示“没有可伪造的逐日志检索快照”，不能被解释为检索条件已绑定。规范 JSON evidence 端点仍是完整嵌套证据和归档检查的首选来源。

本契约只约束新生成的 CSV。历史 CSV 不会被回填或改写；历史批次仍需按当时实际字段重新审计，并在缺少逐案例快照时保持 `paper_ready=false`。

## 导出与复核

新运行会将 `graph_schema_version` 从配置快照提升到 `experiment.graph_schema_version`。当配置快照包含该字段时，归档检查器要求顶层值为非空字符串且逐字匹配；历史包可保持 `null`，但不得把缺失的图谱版本解释为已完成版本绑定。

```bash
curl -H "Authorization: Bearer $ELN_ACCESS_TOKEN" \
  -o rag-experiment-<run_id>-evidence.json \
  "http://localhost:8001/rag/experiments/<run_id>/evidence.json"
```

下载后可在归档前运行一致性检查：

```bash
python3 scripts/gates/check_rag_experiment_evidence.py \
  --package rag-experiment-<run_id>-evidence.json \
  --output rag-experiment-<run_id>-evidence-check.json
```

生产端点在查询日志前对运行状态做同一项归档门禁：`queued` 和 `running` 返回 HTTP 409，避免把尚未完成的包误标为论文证据；未知状态同样拒绝导出；`interrupted` 仍可导出为部分包，但检查器会保留未执行分母并要求论文单独标记。该规则与离线检查器对非终态及未知状态的拒绝保持一致。

证据包下载权限与盲评权限分离：原始 `evidence.json` 只允许项目成员在允许解盲的上下文中导出；独立评审员访问该端点会返回 HTTP 403，只能通过 `/projects/{project_id}/rag/blind-review/*` 获取去除方法、文件名和内部来源标记的盲评材料。Rust 隔离 PostgreSQL 回归同时验证管理员证据包下载、评审员端点拒绝和盲评 API 可用，防止论文证据包成为绕过方法隐藏的入口。

若要把导出结果写入自动生成的论文描述性材料，还必须对材料内的输入指纹运行
`scripts/gates/check_paper_material_freshness.py`。该门禁对缺少指纹章节、空表或格式错误表行
失败关闭，并逐项检查 Markdown 所列 SHA-256 是否仍与实际输入一致；它不会把内部自动
统计升级为确认性结果。输出 `paper-material-freshness-v1` 的 `material` 使用相对于
校验根目录的 POSIX 路径，`root` 固定为 `"."`，不记录机器相关的绝对工作区路径；材料
和所有指纹输入仍必须位于校验根目录内，材料本身越界时以 `material_outside_root` 失败。

检查器只验证导出材料内部的一致性，不连接数据库、不重新运行模型，也不证明人工评价的有效性。它会先验证题集和模式非空、模式属于生产允许集合且无重复、重复次数在 1–10 范围内；再根据 `questions`、`modes`、`repetitions`、`random_seed` 和 `randomize_order` 重建计划，要求 `experiment.total_cases` 等于重建计划长度，并逐项比对 `summary.execution_plan` 与 `cases` 的问题序号、问题文本、模式、重复次数和执行顺序；随机化排序键也复刻 Rust 对 `serde_json::Value` 的显示规则，包含字符串引号与转义。随后按 Rust 生产端相同的紧凑 JSON 字节规则重新计算 `execution_plan_hash`，并校验 `summary.unexecuted_cases = total_cases - completed_cases - failed_cases`。`queued` 和 `running` 是非终态，不能作为论文归档材料通过检查；`completed` 必须零失败、零未执行且无错误摘要，`completed_with_errors` 必须至少包含一个失败案例、零未执行且有错误摘要。完成或带错误完成的运行必须包含完整执行计划；中断运行可以保留部分案例，但应在论文材料中单独标记并保留未执行分母。失败案例与 `summary.errors` 必须按 `execution_order` 一一对应：不允许重复错误摘要、缺失错误摘要或问题序号、问题文本、模式、重复次数及错误文本漂移。对每个有 `query_log_id` 的案例，检查器还要求逐案例检索参数快照完整，并要求同一证据包的已落库案例共享稳定的模型/索引/检索参数绑定；任何漂移均失败关闭。
逐案例身份字段也有同样的机器边界：`question_index`、`repetition_index` 和 `execution_order` 均从 1 起始，`question` 为 1–4000 字符，`mode` 必须属于同一生产五方法集合。这样案例键、题集位置、重复轮次和执行顺序可以被客户端校验并回放，不会因 0 值或未注册方法进入论文分母。
若运行状态为 `failed`，还必须存在非空的 `summary.fatal_error.error`，且必须同时提供 `failure_scope="run"` 与注册的运行级 `failure_code`（当前包括 `creator_user_missing`、`input_binding_drift`、`worker_error`）；`completed`、`completed_with_errors` 和 `interrupted` 运行不得残留 `fatal_error`。逐案例失败必须提供 `failure_scope="case"` 与当前注册的 `failure_code="query_error"`；`summary.errors` 必须逐字段复制该范围和代码。完成案例必须显式使用 `null` 失败元数据。检查器拒绝范围错配、未知代码和摘要—案例不一致，因此“单案例失败”与“运行级故障”不再依赖错误文本推断。题集中的问题必须是非空字符串、互不重复且不超过生产查询上限 4,000 字符；模式也必须是字符串，避免把重复题目误当作独立样本或让畸形归档材料在计划重建阶段产生未处理异常。
案例来源也必须可解释：已落库案例的 `query_log_id` 必须是唯一正整数；只有由 `summary.errors` 补入的未落库失败案例可以使用 `null`，完成案例不得缺少日志 ID。每个案例还必须保留非负整数 `source_count` 与 `graph_hit_count`，并分别与 `sources`、`graph_context` 数组长度严格一致；`response_ms` 必须是非负整数，未落库失败使用生产端显式写入的 `0`，不能用缺失或负数伪造时延分母。每个来源对象必须保留正整数 `chunk_id`/`file_id`，每个图谱对象必须保留正整数 `relation_id`/`source_entity_id`/`target_entity_id`，使 `[S数字]`/`[G数字]` 能回指稳定的数据库证据对象。这能发现证据对象身份缺失和冗余统计字段漂移，但不把命中数量或稳定 ID 当作相关性或正确性指标。未落库失败仍必须保留稳定的 `prompt_version="experiment-unlogged-failure-v1"`，以便区分“系统补入的失败记录”和真正缺失遥测的案例。由此 `case_count` 才能明确表示“已落库案例 + 未落库失败案例”的总数。

引用标记采用严格的单项格式：来源必须写作 `[S1]`、`[S2]` 等，图谱关系必须写作 `[G1]`、`[G2]` 等；每个编号必须落在该案例对应的 `sources` 或 `graph_context` 数组范围内。范围写法（例如 `[S1-S6]` 或 `[G1-G10]`）、非数字编号和越界编号均视为非法，归档审计应失败关闭，而不是按出现了引用字符进行宽松计数。`check_rag_experiment_evidence.py` 会对有答案案例重新扫描标记，重算 `citation_count`、`invalid_citations` 和 `has_evidence`，并按生产端同样的证据类别覆盖与关键事实段落同段标记规则重算 `passed`，再与 `citation_audit` 逐字段核对；`passed` 的真值或假值都不能偏离独立重算结果。五方法离线审计还会将原始 CSV 重算出的非法标记按题目 ID、重复编号、方法和标记，与报告中的 `invalid_source_marker_rows`/`invalid_graph_marker_rows` 做精确集合比较，并核对 `all_citation_indices_in_range`；只要失败对象不同，即使双方都报告“存在失败”，也必须失败关闭；同时逐方法核对完成数、来源/图谱/任一证据标记数、非法行数和对应比例，避免全局计数相同而分层结果被改写。描述性 Markdown 进一步以完成答案数为分母呈现各类标记的 `n/%`，使分子、分母和口径在论文阅读层可直接复核。该门禁只证明引用语法、数组边界、生产端强制引用规则和导出字段内部一致，不证明引用内容正确、来源支持命题或人工评价有效。

导出文件的顶层 `schema_version` 当前为 `rag-evidence-package-v1`。`experiment.repetitions` 和 `experiment.randomize_order` 是从 `config_snapshot.experiment_protocol` 提升的冗余核验字段；题集哈希、语料快照哈希和索引版本也从配置快照提升，计划重建仍以配置快照为准，提升字段用于人工阅读和论文材料引用。题集哈希对规范化后的 `experiment.questions` 计算 SHA-256；语料快照哈希对生产检索实际筛选的 `(file_id, chunk_index, content_hash)` 集合及 `rag_index_version` 计算 SHA-256，排序规则固定，空索引也会得到确定哈希。数据集依赖模式必须提供 64 位小写语料哈希和索引版本；`pure_llm`、`structured_query` 不声称使用文档语料，哈希为 `null`。`case_count` 应等于已落库日志案例与运行摘要中未落库失败案例之和；复核时应检查它与 `experiment.total_cases` 的关系，并核对 `execution_plan_hash`、语料哈希、问题集哈希和正式冻结清单是否一致。

执行器从 `queued` 领取为 `running` 后，会在首个案例前重新核对题集、语料快照、索引版本、嵌入模型和生成模型；每个后续案例开始前也会再次核对。任一绑定缺失或发生漂移，运行会以 `status=failed` 和非空 `summary.fatal_error.error` 失败关闭，不再继续生成后续回答；因此“排队时创建的绑定”不会静默变成混合输入条件的 completed 结果。零案例的历史调度夹具不执行该复核；正式实验均有正的 `total_cases`。这项运行时检查仍不等价于外部冻结：它不能替代归档时的文件清单交叉核对，也不能消除单个检索请求内部并发更新的极短时间窗口。

该哈希是运行创建时的输入绑定，不替代外部冻结清单；若要形成确认性证据，还需在归档时将其与语料文件哈希、题集文件哈希和版本清单交叉核对。实验级 `embedding_model` 与 `generation_model` 必须同时出现在 `experiment` 和 `config_snapshot`，且两处值严格一致。对于已落库案例，`retrieval_config.embedding_model` 和 `retrieval_config.index_version` 还必须分别等于实验级 `embedding_model` 和 `rag_index_version`；同时必须保留 `retrieval_strategy`、`retrieval_top_k`、`collection_retrieval_top_k`、`vector_candidate_k`、`graph_top_k`、`chunk_size`、`chunk_overlap`、`graph_min_score` 和 `retrieval_min_score`。同一证据包的已落库案例不能出现这些稳定参数的漂移；若案例的 `model` 非空，则还必须等于实验级 `generation_model`。系统兜底或结构化查询可以记录 `model=null`，但不能借此掩盖非空模型漂移。这样逐案例运行参数不会脱离顶层输入绑定。未落库的系统失败案例没有查询日志，只保留失败元数据和空证据容器，不虚构逐案例检索绑定。

检查器结果中的 `statistics` 字段由 `scripts/gates/check_rag_experiment_evidence.py` 从 `cases[]` 独立派生，版本为 `rag-evidence-statistics-v1`。它固定输出状态/失败分层、来源与图谱对象数量、引用审计重算计数、按方法的完成/失败/时延（中位数、P95）以及已落库案例的模型/索引/检索参数快照。统计不读取可被手工修改的 `citation_audit.citation_count` 或 `passed`，而是从答案文本和证据数组重新计算；因此可作为论文附录的可重生成描述性材料，但不等价于人工准确率、引用正确性、显著性检验或方法优越性证据。

论文材料渲染必须继续使用通过该检查器的同一 v1 包：`scripts/render/render_rag_evidence_paper_material.py` 要求检查结果 `passed=true`、无失败项且 `statistics` 与当前 `cases[]` 的再次派生结果完全相等，然后才生成 Markdown 附录。渲染器只输出分母、失败代码、证据容器、时延和运行参数等描述性层，不生成准确率、引用正确性、显著性或方法优越性结论；没有通过检查的确认性包时，不得用旧版运行记录或手工统计替代。

该附录还按 `execution_order` 输出所有 `status=failed` 案例的逐项清单，至少保留题目序号、方法、重复编号、`query_log_id`、`failure_scope`、`failure_code`、来源/图谱证据对象数量和原始错误文本。`query_log_id=null` 的未落库失败不得从清单删除；错误文本只是运行遥测，不能被解释为失败原因的因果证明，来源/图谱数量也不是相关性或正确性指标。

附录的“输入材料指纹”表固定绑定五项字节材料：实际 v1 证据包、`check_rag_experiment_evidence.py`、`render_rag_evidence_paper_material.py`、本协议和论文证据索引。表中路径必须是校验根目录内的可移植相对路径，摘要为完整小写 SHA-256；交付前用 `check_paper_material_freshness.py` 重算并要求 `paper-material-freshness-v1` 通过。该指纹层只证明引用材料未漂移，不等价于外部冻结题集、人工金标准、应用 revision 或独立评审。

内部五方法描述性材料 `render_rag_five_mode_paper_material.py` 还输出“门禁失败摘要”：按检查名稳定排序保留所有未通过检查的严重级别、实际值和期望值。表中同时提供有限深度、确定性排序的摘要列（供论文阅读）和完整 `actual`/`expected` JSON 列（供机器复核）；两层都保留 `null`、布尔值、数组和对象等类型信息。顶层 `checks` 必须是非空 JSON 数组；每个检查项必须是对象，`passed` 必须为布尔值，检查名和严重级别必须是非空字符串，检查名不能重复；畸形输入失败关闭。正文“证据链门禁”还必须显式呈现 `retrieval_gap_summary_valid`，并在该检查缺失或非布尔时失败关闭，避免审计 JSON 有门禁而论文材料静默遗漏。它不改变审计判定，也不把失败文本解释为因果机制。

该材料还生成“实验设计与运行配置绑定门禁”表，逐项呈现题集哈希、题目/金标准规模、方法顺序、重复与随机种子、生成条件以及检索参数的审计结果。渲染器将这些检查名作为必需集合；任一检查缺失或非布尔值都会失败关闭。表中 PASS 只表示记录值与冻结配置一致，不表示输入本身已经达到确认性实验标准。

“证据链门禁”和“数据—问题集绑定门禁”也由固定的审计检查集合驱动，而不是使用缺失即 `FAIL` 的宽松字典读取。CSV 行完整性、报告重算、引用审计、冻结清单、题目范围、题干逐字一致、运行标签、逐案例检索快照、重复范围、方法集合和案例键域等任一检查缺失或非布尔值，材料渲染均失败关闭，保证论文正文不会把不完整的审计 JSON 当成完整门禁表。

顶层论文门禁同样是类型化字段：`paper_ready` 必须为布尔值，`paper_blockers` 必须是非空字符串数组（可为空数组仅表示无阻塞）。缺失、字符串化布尔值或数组元素类型错误都会使渲染失败，避免把畸形审计产物写成 `paper_ready=false/true` 的可引用结论。

顶层门禁还必须通过 `paper_gate_consistent` 检查：审计器按检查项 `severity` 独立推导 `consistency_passed`、`paper_ready` 和失败的 `paper_blockers`，并将三者与顶层字段逐项比对。渲染器重新按同一规则核对这些字段；检查缺失、失败或 blocker 名称/顺序不一致时失败关闭。正文“证据链门禁”显式列出“论文门禁逻辑一致”，因此 `paper_ready=false` 既不会被错误升级，也不会在顶层字段被篡改时静默进入论文材料。

正文另设“论文门禁推导审计”表，保留 `paper_gate_consistent` 的严重级别、通过状态、`actual` 和 `expected` JSON；因为“门禁失败摘要”只列未通过检查，该独立表避免通过的一致性检查在论文材料中不可见。该表仍只证明审计字段之间的推导一致，不证明外部输入、人工准确性或方法效果。

论文材料还输出固定集合覆盖表，逐组报告实验设计/运行配置 18 项、证据链 5 项、数据—问题集绑定 7 项和论文门禁派生检查 1 项的注册数、观察数、缺失名和状态。缺少任一正文注册检查时渲染失败关闭；观察到只表示检查项存在，不表示其通过。

材料还输出“论文 blocker—最低归档清单映射”表：每个 `paper_blocker` 必须绑定到唯一的确认性归档要求；当前 `app_revision_is_bound`、`external_freeze_inputs_present`、`multi_project_question_set_ready`、`independent_human_review_present` 和 `confirmatory_evidence_package_present` 分别映射到最低清单第 8、1、2、6、4 项。`report_scope_is_internal_only` 是范围声明检查，保留为通过的独立 blocker 记录，不冒充八项清单缺口。该映射由 `scripts/experiments/rag_experiment_contract.py` 注册，审计器原样写入 `paper_blocker_archive_mapping`，渲染器同时核对共享契约和审计 JSON；因此论文表不是依赖隐藏展示逻辑推导。若新增、删除、改名或篡改 blocker 映射，材料生成失败关闭；映射状态只表示归档门禁状态，不表示方法效果。

材料还输出“论文主张边界审计”：要求审计范围仍是内部开发证据、`paper_ready=false` 且存在未完成的论文级归档项；正文据此只允许描述性/方法学诊断表述，并自动列出必须披露的 blocker—归档项对照。若范围、ready 状态或缺口披露条件被篡改，材料渲染失败关闭。该边界门禁控制论文表述等级，不把审计失败解释为回答失败率、事实准确率或方法效果。

随后输出“论文阻塞披露闭环”表，交叉核对失败摘要、顶层 `paper_blockers`、共享归档映射和主张边界中的待披露数量。失败检查身份按名称集合核对（不依赖失败摘要与注册映射的展示顺序），同时保留各表的稳定展示顺序；缺失、重复、数量或名称漂移，以及披露数量与失败 blocker 不一致时，渲染器失败关闭。该闭环只证明失败身份和披露分母一致，不证明任何方法效果、回答正确率或因果机制。

材料随后输出“失败检查身份闭环”表：渲染器从 `checks` 重新计算全部失败检查名，并与审计 JSON 的 `failure_summary`、正文“门禁失败摘要”和 `paper_blockers` 逐项交叉核对。闭环同时报告失败总数与 `paper_blocker` 失败名集合；当前内部批次为 153 个失败检查，其中 148 个为 required、5 个为 `paper_blocker`，这只是结构性门禁缺口的身份与分母证据，不是方法失败率、效果差异或因果机制。若摘要缺失、排序/数量不一致、失败名遗漏，或 `paper_blockers` 不是审计失败的 `paper_blocker` 子集，材料渲染失败关闭。

该渲染器还单独输出“引用审计报告—重算差异”表：逐字段列出报告摘要值与从原始 CSV 重算值，包含全局范围判定和按方法的非法标记计数等差异。该表避免读者只能从完整 JSON 中发现“报告—重算”漂移；它是报告完整性与失败定位证据，不是引用内容正确性、来源支持性或方法效果证据。若 `reported_audit_mismatch` 与差异数组不一致，或差异项缺少字段、重算值和报告值，渲染失败关闭。审计器和渲染器共用 `scripts/experiments/rag_experiment_contract.py` 中的模式及逐案例 retrieval 必需字段顺序；该契约脚本也纳入材料指纹，防止两端字段解释漂移而 freshness 仍误报通过。渲染器源码或输入变更后，必须重新生成 Markdown 并再次运行 freshness 检查。

该材料的严格引用失败表还按 CSV 行号稳定排序，并同时保留题目索引、题目 ID、方法、重复编号、唯一 `query_log_id`、非法标记和来源/图谱计数；渲染前拒绝缺失/非正身份、重复行号、重复日志 ID和重复案例键。该约束只保证失败案例与可回放身份的对应关系，不把引用格式失败解释为事实错误或因果机制。

归档渲染还从绑定的原始 CSV 和题集重新扫描 `[S数字]`/`[G数字]` 语法，按 CSV 行号生成失败案例；对每个失败行逐字核对 CSV 的 `question` 与题集对应题干，并同时核对 CSV 显式 `source_count`/`graph_hit_count` 与两个证据 JSON 数组长度，再要求结果与审计 JSON 的 `citation_audit.invalid_marker_rows` 逐字段相等。审计记录、题干或冗余计数字段被单独篡改时材料生成失败关闭。该双层重算支持“原始数据—审计—论文表”的可复现链路，不升级为引用内容正确性或人工准确性证据。

仓库中早期的 `rag-experiment-*-run.json` 属于旧版运行记录模型（例如顶层 `status`、`questions_json` 和 `config_snapshot_json`），不含 v1 顶层结构和逐案例证据，必须作为历史材料单独标记；不能通过改名、补写状态或手工拼接将其宣称为 `rag-evidence-package-v1`。论文确认性分析只能使用通过本检查器的 v1 证据包，并同时核对外部冻结题集、金标准和版本清单。

建议论文归档至少保留：证据包、预注册文件、语料/问题/答案要点哈希、盲评表与解盲键、分析脚本及运行时版本证据。证据包只能证明系统记录了自动执行过程，不能替代两名独立评价者的盲评、签字和一致性统计。

## 当前边界

- 证据包只读取项目成员有权访问且允许解盲的实验；独立盲评者不能通过该端点绕过方法隐藏。
- 失败案例若没有 `query_log_id`，仍会以 `status=failed` 保留，并明确 `error`，避免把未完成案例从分母中移除；失败案例可以使用 `answer=null`，但 `sources` 和 `graph_context` 仍必须是对象数组，数组中的来源/图谱对象还必须保留可回指的正整数身份字段。相反，`status=completed` 的案例必须有正的 `query_log_id`、非空 `answer` 和无错误字段，避免把没有实际回答的日志计入完成分母。所有案例还必须保留非负整数 `source_count`/`graph_hit_count`（分别等于来源/图谱数组长度）、非负整数 `response_ms`（未落库失败由生产端写入 `0`）、非空 `provider`/`prompt_version`、可空的 `model`/`fallback_reason`，以及对象形式的 `retrieval_config`/`usage`，使论文中的证据数量、运行时参数、模型、回退和资源消耗记录不会被畸形字段静默吞掉；实验级嵌入/生成模型必须与配置快照一致，有 `query_log_id` 的案例还必须在 `retrieval_config` 中保留与实验快照一致的嵌入模型、索引版本和 `graph_schema_version`，且分别匹配实验级绑定，非空案例模型必须匹配实验级生成模型。
- 逐案例运行标签也必须绑定方法配置：生成方法的 `provider`、`model`、`prompt_version` 必须分别等于运行配置对应字段；`structured_query` 等非生成方法必须显式记录 `provider=system`、空 `model` 和预注册提示版本。该约束证明导出标签没有脱离方法条件，但不证明外部应用 revision、模型内容稳定性或生成结果正确性。
- 该协议不冻结外部题集、金标准或人工评分；这些仍需在正式确认性实验前由研究者和独立评价者完成。
- 对内部 CSV 批次，汇总级检索配置不能替代逐案例 retrieval snapshot。BM25、混合检索和图谱增强行至少要保存与配置快照一致的语料快照哈希、嵌入模型（适用时）、`graph_schema_version`、chunk/top-k/候选数/图谱阈值；结构化查询行也要保存图谱 schema/top-k/阈值。v1 JSON 中每个有 `query_log_id` 的案例必须将 `retrieval_config.graph_schema_version` 与顶层 `experiment.graph_schema_version` 逐字匹配；缺少这些字段时应标记 retrieval 绑定失败并保持 `paper_ready=false`，不得从汇总快照推断每行可回放。审计输出还应保留按方法、字段和行数分层的 gap summary：明确适用字段、完整快照行数、有任一缺口行数，以及每个字段的缺失计数和非空漂移计数，避免用单一总布尔值掩盖缺口分布；完整快照行与有任一缺口行必须恰好划分适用行数，字段级计数的键集合和固定顺序必须与该方法的规范必需字段完全一致，计数必须不超过该方法的适用行数，也不得超过该方法的有任一缺口行数。审计器还将这些约束写入 `retrieval_gap_summary_valid` 检查和结构化违规列表，便于在 JSON 层定位分区、字段键或计数错误。论文材料按方法以适用行数为分母展示完整快照行和有任一缺口行的 `n/%`，并将字段缺失与非空漂移呈现为 `字段=n/%`，使参数绑定缺口不依赖读者自行换算。
