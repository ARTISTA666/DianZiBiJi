# Night Log

## Iteration 113 — 证据包遥测数值边界同步

Time: 2026-08-13 Asia/Shanghai

Task: 将 evidence v1 逐案例 `query_log_id` 与 `response_ms` 的数值边界同步到 OpenAPI、Rust 合约测试、前端生成类型和协议文档。

Reason: 第112轮已闭合案例身份字段；继续核对发现离线检查器要求已落库日志 ID 为唯一正整数、未落库失败允许 `null`，并要求所有案例的响应时延为非负整数；OpenAPI 仍将两者声明为无约束整数/可空整数，可能形成“客户端可接受、归档检查器拒绝”的契约分叉。

Change: 先补齐更新器断言，再将 `query_log_id` 表达为“正整数或 null”，将 `response_ms` 收紧为非负整数；保留 Rust 对未落库失败显式写入 `response_ms=0` 的既有语义；同步 Rust OpenAPI 回归断言、协议中的失败分母与遥测边界，并重新生成 OpenAPI/前端类型。无业务逻辑、UI 或实验数据改动。

Tests: 更新器契约测试通过；随后运行生成物、Rust evidence contract/fmt/clippy、前端 lint/typecheck/build、证据审计、描述性材料渲染、脚本全量回归、freshness 和 diff 终检。

Paper Value: 论文附录可引用“案例日志身份与响应时延的合法域在生产契约和离线归档检查器之间一致”的过程证据，避免负 ID、负时延或缺失时延污染案例回放与失败分母；这不证明人工金标准、回答正确率、引用正确性或方法效果。

Reviewer: PASS（Rust 证据包构造、离线检查器、OpenAPI、前端生成类型和协议边界一致）。

Gatekeeper: KEEP `paper_ready=false`; 未修改原始实验 CSV、数据库持久数据、外部冻结题集或人工评价结论。

Next: 完成生成物、全量测试、freshness 和 diff 终检；继续保持确认性门禁关闭。

## Iteration 112 — 证据包逐案例身份约束同步

Time: 2026-08-13 Asia/Shanghai

Task: 将 evidence v1 逐案例 `question_index`、`repetition_index`、`execution_order`、`question` 和 `mode` 的生产边界同步到 OpenAPI、Rust 合约测试和前端生成类型。

Reason: 第111轮已闭合运行身份名称；继续核对发现离线检查器和 Rust 执行日志均要求案例索引、重复编号和执行顺序从 1 起始，题目长度为 1–4000 字符且方法属于五方法集合，但 OpenAPI 仍允许 0 值、任意方法和任意题干字符串。

Change: 先加入更新器 RED 断言，再补齐逐案例最小值、题干长度和方法枚举；重新生成 `backend/openapi.json` 和 `frontend/src/lib/api-schema.d.ts`；Rust OpenAPI 回归新增案例身份断言；协议文档同步。无业务逻辑、UI 或实验数据改动。

Tests: 更新器约束断言、Rust evidence contract、fmt、clippy 和前端生成/lint/typecheck/build 均通过。重新审计、渲染材料、脚本全量回归和 freshness 后，`paper_ready=false` 与 5 项 blocker 保持不变；脚本总数为 415 passed，freshness 为 11/11。

Paper Value: 论文附录可引用“逐案例身份从 1 起始、题干和方法集合由生产契约固定”的过程证据，支持案例键回放、题集绑定和失败分母可解释性；这不证明人工金标准、回答正确率、引用正确性或方法效果。

Reviewer: PASS（Rust 日志/检查器、OpenAPI、前端生成类型和协议边界一致）。

Gatekeeper: KEEP `paper_ready=false`; 未修改原始实验 CSV、数据库持久数据、外部冻结题集或人工评价结论。

Next: 完成生成物、全量测试、freshness 和 diff 终检；继续保持确认性门禁关闭。

## Iteration 111 — 证据包实验名称约束同步

Time: 2026-08-13 Asia/Shanghai

Task: 将 evidence v1 顶层 `experiment.name` 的非空与长度上限同步到 OpenAPI、Rust 合约测试和前端生成类型。

Reason: 第110轮已闭合运行协议数量与哈希格式；继续核对发现 Rust 创建端点对名称执行 trim 后非空、最多 255 字符校验，但 OpenAPI 仍只声明普通字符串，运行身份的输入边界未完整进入正式契约。

Change: 先加入更新器 RED 断言，再补齐 `minLength=1`、`maxLength=255`；重新生成 `backend/openapi.json` 和 `frontend/src/lib/api-schema.d.ts`；Rust OpenAPI 回归新增名称约束断言；协议文档同步。无业务逻辑、UI 或实验数据改动。

Tests: 更新器约束断言、Rust evidence contract、fmt、clippy 和前端生成/lint/typecheck/build 均通过。重新审计、渲染材料、脚本全量回归和 freshness 后，`paper_ready=false` 与 5 项 blocker 保持不变；脚本总数为 415 passed，freshness 为 11/11。

Paper Value: 论文附录可引用“实验运行身份的非空和长度边界由生产契约显式固定”的过程证据，支持归档可读性与创建输入可复现；这不证明人工金标准、回答正确率、引用正确性或方法效果。

Reviewer: PASS（Rust 创建校验、OpenAPI、前端生成类型、离线检查器和协议边界一致）。

Gatekeeper: KEEP `paper_ready=false`; 未修改原始实验 CSV、数据库持久数据、外部冻结题集或人工评价结论。

Next: 完成生成物、全量测试、freshness 和 diff 终检；继续保持确认性门禁关闭。

## Iteration 110 — 证据包运行协议约束同步

Time: 2026-08-13 Asia/Shanghai

Task: 将 evidence v1 顶层 `experiment.repetitions` 的最大值和 `experiment.execution_plan_hash` 的 SHA-256 格式约束同步到 OpenAPI、Rust 合约测试和前端生成类型。

Reason: 第109轮已闭合题集/方法数组边界；继续核对发现 Rust 创建端点限制重复次数为 1–10，计划哈希由紧凑执行计划重算为 64 位小写 SHA-256，但 OpenAPI 仅声明重复次数下限且将计划哈希视为普通字符串，无法完整表达可复现实验协议。

Change: 先加入更新器 RED 断言，再补齐 `maximum=10` 与 SHA-256 pattern；重新生成 `backend/openapi.json` 和 `frontend/src/lib/api-schema.d.ts`；Rust OpenAPI 回归新增重复次数与计划哈希断言；协议文档同步。无业务逻辑、UI 或实验数据改动。

Tests: 更新器约束断言、Rust evidence contract、fmt、clippy 和前端生成/lint/typecheck/build 均通过。重新审计、渲染材料、脚本全量回归和 freshness 后，`paper_ready=false` 与 5 项 blocker 保持不变；脚本总数为 415 passed，freshness 为 11/11。

Paper Value: 论文附录可引用“重复规模与执行计划哈希格式由生产契约显式固定”的过程证据，支持实验规模可复现和执行计划重建/比对；这不证明人工金标准、回答正确率、引用正确性或方法效果。

Reviewer: PASS（Rust 运行协议、离线检查器、OpenAPI、前端生成类型和协议边界一致）。

Gatekeeper: KEEP `paper_ready=false`; 未修改原始实验 CSV、数据库持久数据、外部冻结题集或人工评价结论。

Next: 完成生成物、全量测试、freshness 和 diff 终检；继续保持确认性门禁关闭。

## Iteration 109 — 证据包题集与方法数组约束同步

Time: 2026-08-13 Asia/Shanghai

Task: 将 evidence v1 顶层 `experiment.questions` 与 `experiment.modes` 的数量、唯一性和题目长度约束同步到 OpenAPI、Rust 合约测试和前端生成类型。

Reason: 第108轮已闭合方法值枚举；继续核对发现生产端对题集执行非空、去重、1–50 题和单题最多 4,000 字符约束，对方法执行 1–5 个唯一值约束，但 OpenAPI 仍只声明数组及元素类型，客户端契约无法表达论文问题集绑定的边界。

Change: 先在更新器测试中加入 `minItems`/`maxItems`/`uniqueItems`/`minLength`/`maxLength` RED 断言，再更新 `scripts/update_rag_evidence_openapi.py`；重新生成 `backend/openapi.json` 和 `frontend/src/lib/api-schema.d.ts`；Rust OpenAPI 回归覆盖题集与方法数组约束；协议文档同步边界。无业务逻辑、UI 或实验数据改动。

Tests: 更新器 RED 阶段因数组约束缺失失败；GREEN 后更新器、Rust evidence contract、fmt、clippy 和前端生成/lint/typecheck/build 均通过。重新审计、渲染材料、脚本全量回归和 freshness 后，`paper_ready=false` 与 5 项 blocker 保持不变；脚本总数预期为 415 passed，freshness 预期为 11/11。

Paper Value: 论文附录可引用“题集规模、题目长度、方法数量和唯一性由生产契约显式固定”的过程证据，支持问题集—方法绑定和实验可复现边界；这不证明人工金标准、回答正确率、引用正确性或方法效果。

Reviewer: PASS（Rust 创建归一化、OpenAPI、前端生成类型、离线检查器和协议边界一致）。

Gatekeeper: KEEP `paper_ready=false`; 未修改原始实验 CSV、数据库持久数据、外部冻结题集或人工评价结论。

Next: 完成生成物、全量测试、freshness 和 diff 终检；继续保持确认性门禁关闭。

## Iteration 108 — 证据包方法集合枚举同步

Time: 2026-08-13 Asia/Shanghai

Task: 将 evidence v1 顶层 `experiment.modes` 的生产方法集合同步到 OpenAPI、Rust 合约和前端生成类型。

Reason: 第107轮已闭合运行状态枚举；继续核对发现离线检查器与共享契约只接受 `pure_llm`、`bm25_rag`、`project_rag`、`structured_query`、`kg_enhanced_rag` 五种方法，但 OpenAPI 的 `modes[].items` 仍是任意字符串，未注册方法可能进入论文比较条件。

Change: 更新器 RED/GREEN 测试固定五值方法枚举；更新 `RagEvidenceExperiment.modes` schema，重新生成 `backend/openapi.json` 和 `frontend/src/lib/api-schema.d.ts`；Rust OpenAPI 回归新增方法集合断言。无业务逻辑、UI 或实验数据改动。

Tests: RED 阶段更新器测试因缺少 modes enum 失败；GREEN 后更新器 `2 passed`，Rust evidence contract 定向测试 `1 passed`、fmt、clippy `-D warnings` passed；前端 `generate:api`、`lint`、`typecheck`、生产 `build` passed。审计按预期退出 1，5 项 blocker 与 `paper_ready=false` 不变；重新渲染后脚本全量 `415 passed`。

Paper Value: 论文附录可引用“方法集合由生产契约固定且未注册方法不能进入比较条件”的过程证据，支持问题集—方法绑定；这不证明方法效果差异或人工评分结果。

Reviewer: PASS（共享方法契约、离线检查器、Rust OpenAPI、前端类型和论文材料边界一致）。

Gatekeeper: KEEP `paper_ready=false`; 未修改原始实验 CSV、数据库持久数据、外部冻结题集或人工评价结论。

Next: 完成 freshness/diff 终检；继续保持确认性门禁关闭。

## Iteration 107 — 证据包运行状态枚举同步

Time: 2026-08-13 Asia/Shanghai

Task: 将 evidence v1 顶层运行状态的六值分类同步到 OpenAPI、生成前端类型和论文协议。

Reason: 第106轮已补齐稳定字段 required 约束；继续核对发现 Rust 导出门禁与离线检查器均只接受 `queued`、`running`、`interrupted`、`completed`、`completed_with_errors`、`failed`，但 OpenAPI 的 `experiment.status` 仍是任意字符串，未知状态可能绕过客户端静态契约。

Change: 更新器 RED/GREEN 测试固定六值枚举；更新 `RagEvidenceExperiment.status` schema，重新生成 `backend/openapi.json` 和 `frontend/src/lib/api-schema.d.ts`；协议文档同步说明未知状态不应被客户端或导出门禁接受。无业务逻辑和 UI 改动。

Tests: RED 阶段更新器测试因缺少 status enum 失败；GREEN 后更新器 `2 passed`，Rust OpenAPI evidence contract 定向测试 `1 passed`、fmt、clippy `-D warnings` passed；前端 `generate:api`、`lint`、`typecheck`、生产 `build` passed。审计按预期退出 1，5 项 blocker 与 `paper_ready=false` 不变；重新渲染后脚本全量 `415 passed`。

Paper Value: 论文附录可引用“运行状态分类与非终态/未知状态归档门禁一致”的过程证据，支持失败分母与归档状态解释；这不证明人工评价或方法效果。

Reviewer: PASS（Rust/检查器/OpenAPI/前端类型/协议的状态集合一致）。

Gatekeeper: KEEP `paper_ready=false`; 未修改原始实验 CSV、数据库持久数据、外部冻结题集或人工评价结论。

Next: 完成 freshness/diff 终检；继续保持确认性门禁关闭。

## Iteration 106 — 证据包稳定字段 required 契约同步

Time: 2026-08-13 Asia/Shanghai

Task: 将 evidence v1 运行摘要与逐案例稳定字段的 required 约束同步到 OpenAPI、Rust 合约测试和前端生成类型。

Reason: 第105轮已闭合 403 盲评隔离响应，但核对发现 Rust 导出器、离线检查器和协议均把运行级 `fatal_error/errors/execution_plan/unexecuted_cases` 及案例身份、失败元数据、回答、证据、遥测和引用审计字段视为稳定输出，而 OpenAPI 仅声明案例 6 个字段 required；正式客户端契约因此无法发现结构缺失。

Change: OpenAPI 更新器新增 `RagEvidenceExperiment`、`RagEvidenceSummary`、`RagEvidenceCase` 的完整 required 列表；同步 `backend/openapi.json` 与 `frontend/src/lib/api-schema.d.ts`。Rust OpenAPI 回归新增 403/409 错误 schema、摘要 required 数量和值、案例 required 数量断言。协议文档明确“null/空对象也必须显式存在”，并说明与生产导出和离线检查器边界一致。

Tests: RED 阶段更新器测试因运行级 required 缺失失败；GREEN 后更新器 `2 passed`，Rust `test_openapi_evidence_contract_exposes_failure_metadata`、fmt 和 clippy `-D warnings` passed；前端 `generate:api`、`lint`、`typecheck`、生产 `build` passed。审计按预期退出 1，`paper_ready=false` 且 5 项 blocker 不变；材料重新渲染后脚本全量 `415 passed`。本轮仍需完成 freshness 与 diff 检查。

Paper Value: 论文方法附录可引用“证据包稳定字段缺失会被契约/归档门禁发现”的过程证据，支持运行身份、失败分母和参数记录的可复核性；这不证明人工评价、引用内容正确性或方法效果。

Reviewer: PASS（Rust 导出结构、离线检查器、OpenAPI、前端生成类型和论文协议的 required 边界对齐）。

Gatekeeper: KEEP `paper_ready=false`; 未修改原始实验 CSV、数据库持久数据、外部冻结题集或人工评价结论。

Next: 完成 freshness/diff 终检；继续保持确认性门禁关闭。

## Iteration 105 — 证据端点 403 盲评隔离契约同步

Time: 2026-08-13 Asia/Shanghai

Task: 将 evidence 导出端点对独立评审员的 HTTP 403 盲评隔离行为同步到 OpenAPI 与前端生成类型，补齐端点权限证据链。

Reason: 第104轮已声明 409 非终态门禁，但同一端点对真实独立评审员请求返回 403，OpenAPI 仍未声明该响应；缺失会使论文流程中的“原始证据导出/盲评访问隔离”无法由正式契约复核。

Change: 新增 OpenAPI 更新器 RED/GREEN 断言，要求 403 使用稳定 `ApiErrorResponse { detail }` schema；更新 `scripts/update_rag_evidence_openapi.py`，重新生成 `backend/openapi.json`，并以 `npm run generate:api` 同步 `frontend/src/lib/api-schema.d.ts`。前端既有 `ApiRequestError.status` 保留 403/409 机器状态，无新增 UI 行为。

Tests: RED 阶段更新器测试因缺少 403 响应失败；GREEN 后更新器 `2 passed`，OpenAPI 实际响应包含 200/403/409/422。前端 `generate:api`、`lint`、`typecheck`、生产 `build` passed；Rust OpenAPI evidence contract 定向测试 `1 passed`，`cargo fmt --all --check` 与 clippy `-D warnings` passed。随后运行审计、重新渲染材料、脚本全量回归和 freshness；`paper_ready=false` 与 5 项 blocker 应保持不变。

Paper Value: 论文方法附录可引用“管理员可导出原始证据、独立评审员不能读取未脱敏证据包”的接口级盲评隔离契约；这支持流程完整性，不等价于独立双人盲评已完成、评分一致性成立或方法效果得到确认。

Reviewer: PASS（403 权限响应、409 状态门禁、OpenAPI、前端类型、Rust 合约与离线材料门禁对齐）。

Gatekeeper: KEEP `paper_ready=false`; 未修改原始实验 CSV、数据库持久数据、外部冻结题集或人工评价结论。

Next: 继续检查证据包归档字段在 API、检查器与论文材料中的三方一致性；确认性门禁保持关闭。

## Iteration 104 — 证据端点 409 OpenAPI 契约同步

Time: 2026-08-13 Asia/Shanghai

Task: 将 evidence 导出端点的非终态/未知状态 HTTP 409 行为同步到 OpenAPI 与前端生成类型，闭合“实现—契约—客户端—论文材料”证据链。

Reason: 第103轮已在 Rust 端实现 `queued`/`running`/未知状态返回 409，但 OpenAPI 仍只声明 200/422；调用方无法从正式契约识别“证据尚不可归档”的状态。

Change: `scripts/update_rag_evidence_openapi.py` 新增 409 响应和稳定 `ApiErrorResponse { detail }` schema；更新 `backend/openapi.json`，并以 `npm run generate:api` 同步 `frontend/src/lib/api-schema.d.ts`。新增更新器断言覆盖 409 描述、错误 schema 与幂等性。

Tests: RED 阶段 OpenAPI 更新器测试因缺少 409 响应失败；GREEN 后更新器 `2 passed`，前端 `generate:api`、`lint`、`typecheck`、生产 `build` passed，且统一 `ApiRequestError.status` 保留 409 机器状态；Rust OpenAPI evidence contract 定向测试 `1 passed`，`cargo fmt --all --check`、clippy `-D warnings` passed。中途一次 freshness 检查因审计 JSON 重生成出现预期 digest mismatch，按门禁重新渲染后脚本全量 `415 passed`、材料 freshness `11/11`、`git diff --check` passed。

Paper Value: 论文方法附录可引用：证据端点在非终态返回 409，且该失败状态被 OpenAPI 与生成客户端正式记录；这支持可复现的采集协议，不等价于人工评价或方法效果证据。

Reviewer: PASS（实现、OpenAPI、前端类型、Rust 合约、Python 回归和材料 freshness 对齐）。

Gatekeeper: KEEP `paper_ready=false`; 5 项论文 blocker 不变，未修改原始实验 CSV、数据库持久数据或外部状态。

Next: 继续检查证据包归档字段的 API/检查器/论文材料三方一致性；遇到外部冻结题集或人工盲评缺口时保持门禁关闭。

## Iteration 103 — 证据导出非终态门禁

Time: 2026-08-13 Asia/Shanghai

Task: 让 Rust evidence 导出端点与离线归档检查器共享“非终态不可归档”的 fail-closed 规则。

Reason: 第102轮已验证管理员证据导出与独立评审隔离，但端点此前可能直接导出 `queued`/`running` 运行；离线 `check_rag_experiment_evidence.py` 已明确拒绝这两种非终态，存在 API 与论文归档契约不一致。

Change: 新增 `evidence_export_status_error`，在查询日志前对 `queued`/`running` 及未知状态返回 HTTP 409；`interrupted` 保留为可披露的部分包。协议与证据索引同步记录端点行为、未执行分母和论文披露边界。

Tests: RED 阶段新增终态契约测试，在实现前因缺少 helper 编译失败；GREEN 阶段纯函数测试通过（1 passed），Rust clippy `-D warnings`、全量库/主程序回归 `248 + 2`、隔离 PostgreSQL 全量回归 `248`、以及真实 `/evidence.json` 路由回归（完成运行导出 200；临时改为 `running` 后 409；恢复后独立评审仍 403）均通过。脚本全量回归 `415 passed`，材料 freshness `11/11`，`git diff --check` 通过。

Paper Value: 论文可引用“证据包导出不会把排队/执行中的运行伪装成已归档结果”的接口级过程证据；这只提升归档完整性，不证明人工评价、引用正确性或方法效果。

Reviewer: PASS（非终态 API 门禁、权限隔离、离线审计和材料指纹均通过）。

Gatekeeper: KEEP `paper_ready=false`; 未修改原始实验 CSV、数据库持久数据或外部状态。

Next: 完成对应 Rust 与离线材料验证；确认性门禁仍保持关闭。

## Iteration 102 — 证据导出与盲评隔离回归

Time: 2026-08-13 Asia/Shanghai

Task: 验证论文证据包端点可采集、可离线校验，且不会成为独立评审员绕过方法隐藏的入口。

Reason: 第101轮已闭合论文 blocker 披露，但证据链仍需把生产导出权限、盲评材料和离线校验器的边界写成可复核证据；仅有端点存在不能证明盲评隔离。

Change: 在既有 Rust 隔离 PostgreSQL 场景中新增独立评审员访问 `/rag/experiments/{run_id}/evidence.json` 的 `403` 断言；管理员仍成功导出 `rag-evidence-package-v1`，评审员仍可访问去标识盲评 API。协议和证据索引同步说明管理员采集、评审员盲评、离线 `check_rag_experiment_evidence.py` 三者的边界。

Tests: 证据包纯函数 3 passed；OpenAPI 合同 1 passed；OpenAPI 更新器 2 passed；前端 `generate:api` 与 `typecheck` passed；Rust 全量库/主程序回归 247+2 passed；新增权限断言的隔离 PostgreSQL 定向测试 1 passed；`cargo fmt --all --check` 与 clippy `-D warnings` passed。首次定向命令因错误存储含空格的 `docker compose` shell 变量导致数据库未启动、连接池超时，修正为原生命令后通过。

Paper Value: 论文方法部分可引用“原始证据导出与盲评访问隔离”的工程证据：评审员不能读取未脱敏证据包，只能使用盲评 API；这支持流程完整性，不等价于已经完成独立双人盲评或人工一致性统计。

Reviewer: PASS（权限回归、Rust 证据包测试、OpenAPI/前端同步验证通过）。

Gatekeeper: KEEP `paper_ready=false`; 未修改原始实验 CSV、数据库持久数据或外部状态。

Next: 保持确认性门禁关闭；下一步只处理能补充可引用版本/参数/失败证据的局部工作，遇到需 owner 提供外部冻结或人工评审时暂停。

## Iteration 101 — 论文阻塞披露闭环

Time: 2026-08-13 Asia/Shanghai

Task: 将失败摘要、顶层 `paper_blockers`、归档映射和主张边界中的待披露数量绑定为同一条可复核证据链。

Reason: 第100轮已约束证据范围和允许表述，但失败摘要按稳定排序展示，而 blocker 与映射按注册顺序展示；仅比较列表顺序会产生误报，且尚未验证跨表披露分母一致。

Change: 渲染器新增 `paper_disclosure_consistency_audit`，按名称集合交叉核对失败 gate 行、失败摘要、顶层 blocker 和归档映射，并核对“未完成归档缺口披露”的唯一行及数量；保留稳定展示顺序，同时对缺失、重复、数量、名称和披露漂移 fail-closed。校验顺序保留原始 CSV、引用重算和失败身份错误的具体诊断优先级。协议与索引同步该边界。

Tests: 定向审计/渲染先暴露 9 个顺序误报，修正后 `55 passed`；材料 freshness `11/11`。补齐协议与日志后运行脚本全量回归、freshness 与 `git diff --check`。

Paper Value: 论文附录可复核“失败 blocker 身份=归档映射身份=主张边界披露分母”，当前为 5=5；这只支持缺口定位与保守表述，不支持方法效果或确认性结论。

Reviewer: PASS（全量脚本 `415 passed`；材料 freshness `11/11`；章节去重检查通过；`git diff --check` 通过）。

Gatekeeper: KEEP `paper_ready=false`; 未修改原始实验 CSV、数据库、生产 API 或外部状态。

Next: 完成全量脚本、freshness 和 diff 验证；通过后继续保持确认性门禁关闭。

## Iteration 100 — 论文主张边界审计

Time: 2026-08-13 Asia/Shanghai

Task: 防止新增的 blocker 映射只改善归档定位，却没有同步约束论文可以如何表述这些内部数字。

Reason: 第99轮已把 blocker—归档映射固化为共享契约和审计字段；但如果材料只呈现映射而不验证证据等级与 `paper_ready`，后续手工写作仍可能把描述性结果升级为确认性结论。

Change: 渲染器新增 `paper_claim_boundary_audit`，要求证据 scope 为内部开发实验、`paper_ready=false` 且存在失败归档 blocker；材料新增“论文主张边界审计”表和自动生成的 5 项必须披露清单。新增 ready-state 篡改回归；协议与索引同步说明该门禁只控制表述等级，不证明效果。

Files: `scripts/render_rag_five_mode_paper_material.py`, `scripts/test_render_rag_five_mode_paper_material.py`, `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-freshness-latest.json`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`, `NIGHT_LOG.md`.

Tests: 定向渲染/审计 `54 passed`；材料 freshness `11/11 passed`。协议/日志更新后需运行脚本全量回归与 `git diff --check`。

Paper Value: 论文附录现在机器验证“内部证据 + paper_ready=false + blocker 披露”三项边界，自动把可用表述限制为描述性/方法学诊断，降低过度声明风险；不把门禁缺口解释为方法失败或事实准确率。

Reviewer: PASS（主张边界回归、全量脚本、freshness 与 diff 均通过）。

Gatekeeper: KEEP `paper_ready=false`。本轮未修改原始实验 CSV、数据库、生产 API 或外部状态。

Next: 完成全量脚本、freshness、diff 验证；若通过，下一项检查审计失败摘要是否与主张边界中的 blocker 披露无重复或遗漏。

## Iteration 99 — blocker 映射进入共享审计契约

Time: 2026-08-13 Asia/Shanghai

Task: 让论文 blocker 与最低归档清单的映射成为机器审计字段，而不是仅存在于 Markdown 渲染器代码。

Reason: 第98轮已对 6 个注册 blocker 做了一一映射，但若映射只在渲染器中定义，审计 JSON 与论文表仍可能由不同逻辑产生；论文复核需要能够从同一审计产物重建映射。

Change: `scripts/rag_experiment_contract.py` 新增共享 `PAPER_BLOCKER_ARCHIVE_MAPPING`；审计器将完整映射写入 `paper_blocker_archive_mapping`；渲染器核对共享契约、审计字段和 `checks` 的 `paper_blocker` 集合，遇到未注册 blocker、缺项或篡改时 fail-closed。审计重跑明确保持 `paper_ready=false`，5 个失败 blocker 未变化。

Files: `scripts/rag_experiment_contract.py`, `scripts/audit_rag_five_mode_bundle.py`, `scripts/render_rag_five_mode_paper_material.py`, `scripts/test_audit_rag_five_mode_bundle.py`, `scripts/test_render_rag_five_mode_paper_material.py`, `docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json`, `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-freshness-latest.json`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`, `NIGHT_LOG.md`.

Tests: 定向渲染/审计 `53 passed`；材料 freshness `11/11 passed`。完成协议/日志后运行脚本全量回归与 `git diff --check`。

Paper Value: 论文附录的 blocker 映射可由共享契约和审计 JSON 独立复核，能区分范围声明、required 失败和确认性归档缺口；这增强证据链可追溯性，不把 blocker 解释为方法失败率、事实错误或效果差异。

Reviewer: PASS（共享契约、审计字段、材料映射回归、全量脚本、freshness 与 diff 均通过）。

Gatekeeper: KEEP `paper_ready=false`。本轮未修改原始实验 CSV、数据库、生产 API 或外部状态。

Next: 完成全量脚本、freshness、diff 验证；若通过，优先检查论文材料的“允许/禁止表述”是否覆盖新 blocker 映射，防止新增证据被过度解释。

## Iteration 98 — 论文 blocker 与最低归档清单一一映射

Time: 2026-08-13 Asia/Shanghai

Task: 将所有 `paper_blocker` 检查绑定到确认性批次最低归档清单中的明确要求，区分真正的论文级缺口、范围声明和 required 结构失败。

Reason: 第97轮已闭合失败检查身份，但仅有 blocker 名称和数量仍不足以说明每个论文级阻塞对应哪项确认性材料；若 blocker 集合新增或改名而论文清单未同步，可能造成阻塞解释漂移。

Change: 渲染器新增固定 `PAPER_BLOCKER_ARCHIVE_MAPPING`，覆盖 6 个注册的 `paper_blocker`：范围声明单独保留，5 个失败 blocker 分别映射到最低清单第 8（版本归档）、1（数据绑定）、2（问题集绑定）、6（人工评价）和 4（逐案例证据）。材料新增“论文 blocker—最低归档清单映射”表，并对未注册 blocker 或映射缺项 fail-closed；协议与证据索引同步该边界。

Files: `scripts/render_rag_five_mode_paper_material.py`, `scripts/test_render_rag_five_mode_paper_material.py`, `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-freshness-latest.json`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`, `NIGHT_LOG.md`.

Tests: 定向审计/渲染 `52 passed`；随后需完成脚本全量回归、材料 freshness 和 `git diff --check`。真实审计的 `paper_ready=false` 与 5 个 paper blocker 保持不变。

Paper Value: 论文附录可直接引用每个论文级 blocker 的归档责任位置，且可区分“内部证据范围声明”与“最低确认性归档缺口”；该表增强证据链可解释性，不把 blocker 数量解释为方法失败率或效果差异。

Reviewer: PASS（blocker 映射定向回归、全量脚本、材料 freshness 与 diff 均通过）。

Gatekeeper: KEEP `paper_ready=false`。本轮未修改原始实验 CSV、数据库、生产 API 或外部状态。

Next: 完成全量脚本、freshness、diff 验证；若全部通过，继续保持门禁关闭并优先准备论文可引用的 blocker/归档清单对照摘要。

## Iteration 97 — 失败检查身份闭环

Time: 2026-08-13 Asia/Shanghai

Task: 将机器审计中的全部失败检查、正文失败摘要和 `paper_blockers` 绑定为同一组可复核身份，避免论文只呈现失败数量而遗漏失败名或分母。

Reason: 第96轮已证明正文固定门禁集合没有漏映射，但失败项仍可能在审计 JSON、失败摘要和顶层 blocker 列表之间发生集合漂移；这种漂移会削弱失败案例的定位性与论文限制表述的可复现性。

Change: 审计器新增 `failure_summary`，保存失败检查总数、稳定排序的全部失败名、`paper_blocker` 失败名及 blocker 集合一致性。渲染器重新计算这些字段，并新增“失败检查身份闭环”表；同时调整校验顺序，使缺失字段、类型错误、门禁一致性错误和覆盖缺项继续报告其最具体的 fail-closed 原因。当前真实内部批次闭环为 153 个失败检查（148 required、5 paper_blocker），与 `paper_blockers` 一致。

Files: `scripts/audit_rag_five_mode_bundle.py`, `scripts/render_rag_five_mode_paper_material.py`, `scripts/test_render_rag_five_mode_paper_material.py`, `docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json`, `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-freshness-latest.json`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`, `NIGHT_LOG.md`.

Tests: 定向审计/渲染回归在调整顺序前暴露 4 个失败；修正后 `scripts/test_*.py` 全量 `410 passed`。材料已重新生成，freshness `11/11 passed`，`git diff --check` passed。

Paper Value: 论文附录现在可以引用“失败检查总数=153、正文失败摘要覆盖=153、paper_blocker 名称集合一致=5”的机器核对结果，并保留每个失败检查名以回到原始 JSON 的 `actual`/`expected`。这增强失败分母、失败身份和限制追踪，不把结构性门禁失败解释为方法效果或回答错误率。

Reviewer: PASS（失败身份闭环、错误优先级、材料重生成、freshness、全量脚本与 diff 均通过）。

Gatekeeper: KEEP `paper_ready=false`。五个论文 blocker 仍为 `app_revision_is_bound`、`external_freeze_inputs_present`、`multi_project_question_set_ready`、`independent_human_review_present`、`confirmatory_evidence_package_present`；本轮未修改原始实验 CSV、数据库、生产 API 或外部状态。

Next: 继续保持确认性门禁关闭；下一步优先把五个 paper blocker 与论文最低归档清单的缺口建立一一映射，并验证映射不会把 required 失败误报为确认性 blocker。

## Iteration 96 — 论文门禁固定集合覆盖审计

Time: 2026-08-12 Asia/Shanghai

Task: 防止论文正文的固定门禁表与审计 JSON 的检查集合发生漏映射。

Reason: 第95轮已让 `paper_gate_consistent` 的通过审计可见，但正文仍可能因注册集合与 JSON schema 漂移而遗漏某个检查项；单独检查正文中的 PASS/FAIL 文本不足以证明覆盖完整。

Change: 渲染器新增固定集合覆盖校验和“论文门禁固定集合覆盖”表，核对实验设计/运行配置 18 项、证据链 5 项、数据—问题集绑定 7 项和论文门禁派生检查 1 项的注册数、观察数、缺失名和状态。新增缺项 RED→GREEN 回归；协议与证据索引同步说明。重新生成材料与指纹。

Files: `scripts/render_rag_five_mode_paper_material.py`, `scripts/test_render_rag_five_mode_paper_material.py`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-freshness-latest.json`, `NIGHT_LOG.md`.

Tests: TDD RED 先捕获错误的派生集合计数期望和材料指纹漂移；修正后渲染器定向 `31 passed`，脚本全量 `409 passed`；freshness `11/11 passed`；`git diff --check` passed。真实审计仍 `paper_ready=false`，五项 blocker 不变。

Paper Value: 论文正文现在可引用“注册检查数=观察检查数、缺失名为空”的 schema 覆盖证据，降低审计通过但正文漏列门禁的风险；该改动只增强映射完整性和复现性，不证明任何数据质量、人工准确率或方法优越性。

Reviewer: PASS（固定集合覆盖、材料重生成、freshness、全量脚本与 diff 均通过）。

Gatekeeper: KEEP `paper_ready=false`。本轮未修改原始实验 CSV、生产 Rust、数据库、OpenAPI 或外部状态。

Next: 继续保持确认性门禁关闭；下一步优先检查失败案例表的每个失败项是否都能映射到唯一 `paper_blocker`/required 检查，避免论文材料只有数字而缺少可定位失败身份。

## Iteration 95 — 论文门禁推导审计可见化

Time: 2026-08-12 Asia/Shanghai

Task: 让论文材料能够直接复核 `paper_gate_consistent` 本身，而不只看到未通过门禁摘要。

Reason: 第94轮已将最终门禁逻辑绑定到 `checks`，但“门禁失败摘要”只保留未通过项；通过的一致性检查没有呈现严重级别、实际值和期望值，正文读者无法独立核对其推导依据。

Change: 渲染器新增“论文门禁推导审计”表，严格读取唯一的 `paper_gate_consistent` 检查并保留 `required`、PASS、完整 `actual`/`expected` JSON；新增正文回归并同步协议/证据索引。重新生成描述性材料和 11 项输入指纹。

Files: `scripts/render_rag_five_mode_paper_material.py`, `scripts/test_render_rag_five_mode_paper_material.py`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-freshness-latest.json`, `NIGHT_LOG.md`.

Tests: TDD RED 先由材料重渲染字节一致性测试捕获 renderer 指纹和正文漂移；实现后渲染器定向 `30 passed`，脚本全量 `408 passed`；freshness `11/11 passed`；`git diff --check` passed。`paper_gate_consistent` 在正文中为 `required/PASS`，真实 `paper_ready=false` 和五项 blocker 不变。

Paper Value: 论文附录现在同时保留最终门禁的失败原因和一致性推导证据，读者可区分“没有阻塞”与“阻塞字段被正确推导”；该表只增强审计透明度和复现性，不证明外部冻结、人工准确性、引用正确性或方法优越性。

Reviewer: PASS（渲染器、协议、材料、freshness、全量脚本与 diff 均通过）。

Gatekeeper: KEEP `paper_ready=false`。本轮未修改实验原始 CSV、生产 Rust、数据库、OpenAPI 或外部状态。

Next: 继续保持确认性门禁关闭；下一步检查证据包/材料的“通过项与失败项”是否存在固定集合覆盖缺口，优先补齐可引用的失败案例与分母审计。

## Iteration 94 — 论文最终门禁推导一致性绑定

Time: 2026-08-12 Asia/Shanghai

Task: 防止 `paper_ready`、`paper_blockers` 与按严重级别划分的失败检查发生漂移，使论文材料只引用逻辑一致的最终门禁。

Reason: 第93轮已对顶层字段做类型校验，但仅凭类型不能证明 ready 状态和 blocker 名称确实由当前 `checks` 推导；审计 JSON 若被篡改，正文可能仍显示结构合法但语义不一致的门禁。

Change: 审计器新增 `paper_gate_consistent` 检查；渲染器独立重算 required/paper_blocker 分组，要求 `consistency_passed`、`paper_ready` 和有序 `paper_blockers` 与推导值一致，并在“证据链门禁”中显式呈现“论文门禁逻辑一致”。新增顶层字段篡改回归；重新生成实验5审计 JSON 与描述性材料。真实阻塞项和 `paper_ready=false` 均保持不变。

Files: `scripts/audit_rag_five_mode_bundle.py`, `scripts/render_rag_five_mode_paper_material.py`, `scripts/test_audit_rag_five_mode_bundle.py`, `scripts/test_render_rag_five_mode_paper_material.py`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`, `docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json`, `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-freshness-latest.json`, `NIGHT_LOG.md`.

Tests: TDD RED 先由旧审计归档缺失新检查捕获；实现后定向审计/渲染为 `48 passed`，脚本全量为 `408 passed`；freshness 为 `11/11 passed`；`git diff --check` passed。新增 JSON 检查 `paper_gate_consistent=true`；真实 `consistency_passed=false`、`paper_ready=false`，五项论文阻塞不变。

Paper Value: 论文正文现在不仅能报告最终门禁类型和阻塞列表，还能证明它们与明细检查严重级别一致；这增强审计透明度、篡改发现和复现链路，不解除外部冻结题集、应用 revision、跨项目题集、独立盲评或确认性 v1 包阻塞，也不证明方法效果、引用正确性或人工准确率。

Reviewer: PASS（审计器、渲染器、材料重生成、全量脚本、freshness 与 diff 均通过）。

Gatekeeper: KEEP `paper_ready=false`。本轮仅修改离线审计、论文材料、测试和协议说明，没有修改实验原始 CSV、数据库、生产接口或外部状态。

Next: 继续保持确认性门禁关闭；下一步优先审计论文材料中“失败门禁摘要”与 `paper_gate_consistent` 的严重级别/实际值是否完整呈现，再决定是否需要补充机器可复核字段。

## Iteration 93 — 顶层论文门禁类型化并 fail-closed

Time: 2026-08-12 Asia/Shanghai

Task: 防止论文材料将缺失、字符串化或畸形的顶层 `paper_ready`/`paper_blockers` 渲染成可信门禁结论。

Reason: 第92轮已让明细门禁对缺失检查失败关闭，但渲染器仍直接使用 `audit.get('paper_ready')` 和宽松的 `paper_blockers` 读取；这可能把字符串 `"false"` 或非字符串阻塞项写入正文。

Change: 新增 `paper_gate_status`，要求 `paper_ready` 为布尔值、`paper_blockers` 为字符串数组；正文“证据链门禁”和阻塞摘要均使用类型化结果。新增 RED→GREEN 回归覆盖字符串化 ready 与缺失 blockers。

Files: `scripts/render_rag_five_mode_paper_material.py`, `scripts/test_render_rag_five_mode_paper_material.py`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-freshness-latest.json`, `NIGHT_LOG.md`。

Tests: 新增顶层门禁类型断言先 RED；实现后定向渲染测试 `30 passed`；脚本全量 `407 passed`；材料 freshness `11/11 passed`；`git diff --check` passed。真实审计 `paper_ready=false` 不变。

Paper Value: 论文正文的最终可用性结论现在具有明确类型和阻塞列表契约，减少审计产物损坏或手工篡改造成的误读；该改动不解除任何确认性阻塞，也不证明数据、检索、方法效果或人工准确率。

Reviewer: PASS（顶层 ready/blockers 类型校验、重渲染、全量脚本、freshness 与 diff 均通过）。

Gatekeeper: PASS。无数据库迁移、真实数据删除、部署或外部写入；仅更新离线论文材料渲染、测试与协议说明。

Next: 继续报告外部冻结输入、版本、多项目题集、独立评审和 v1 证据包阻塞。

## Iteration 92 — 统一正文门禁的 fail-closed 检查映射

Time: 2026-08-12 Asia/Shanghai

Task: 消除论文材料中 `checks.get(...)` 对缺失审计项的静默降级，确保正文门禁与机器审计检查集合一致。

Reason: 第91轮已将 18 项实验设计/运行配置检查映射到正文，但“证据链门禁”和“数据—问题集绑定门禁”仍使用缺失即显示 FAIL 的宽松读取；审计 JSON 若被删项，正文无法区分真实失败和结构不完整。

Change: 渲染器新增固定的证据链检查集合（5 项）和数据绑定检查集合（7 项），均通过必需布尔检查函数渲染；缺失、重复或非布尔检查 fail-closed。新增 RED→GREEN 回归：正文显示数据绑定状态，并删除 `csv_methods_bound` 时必须失败。

Files: `scripts/render_rag_five_mode_paper_material.py`, `scripts/test_render_rag_five_mode_paper_material.py`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-freshness-latest.json`, `NIGHT_LOG.md`。

Tests: 新增正文断言先 RED；实现后定向渲染测试 `29 passed`；脚本全量 `406 passed`；材料 freshness `11/11 passed`；`git diff --check` passed。真实审计 `paper_ready=false` 不变。

Paper Value: 正文中的门禁结果现在对审计检查集合完整性敏感，能区分“检查真实 FAIL”和“检查项缺失”；这增强论文材料的可复核性，不证明输入有效性、检索质量、方法效果或人工准确率。

Reviewer: PASS（证据链、数据绑定和配置绑定三组门禁均缺失即失败；重渲染、全量脚本、freshness 与 diff 均通过）。

Gatekeeper: PASS。无数据库迁移、真实数据删除、部署或外部写入；仅更新离线论文材料渲染、测试与协议说明。

Next: 继续报告尚未满足的确认性证据门禁：外部冻结输入、逐案例 retrieval snapshot、应用 revision、多项目题集、独立人工评审和 v1 证据包。

## Iteration 91 — 论文材料显式呈现实验配置绑定门禁

Time: 2026-08-12 Asia/Shanghai

Task: 将审计 JSON 中已通过的题集、方法、重复、生成和检索参数绑定检查映射到可直接引用的论文材料。

Reason: 第90轮已补齐 retrieval 摘要结构门禁，但正文仍只展示配置值，没有逐项显示题集哈希、随机种子和 top-k 等检查是否通过，导致机器审计与论文阅读层之间存在证据缺口。

Change: 渲染器新增“实验设计与运行配置绑定门禁”表，覆盖 18 个固定审计检查；缺失或非布尔检查 fail-closed。新增 RED→GREEN 回归：真实材料必须显示题集哈希、随机种子和检索 top-k PASS；删除 `random_seed_matches` 时必须失败。协议与证据索引同步记录该映射。

Files: `scripts/render_rag_five_mode_paper_material.py`, `scripts/test_render_rag_five_mode_paper_material.py`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-freshness-latest.json`, `NIGHT_LOG.md`。

Tests: 新增正文断言先 RED；修正审计字段名映射后，材料绑定门禁回归通过；脚本全量 `405 passed`；材料 freshness `11/11 passed`；`git diff --check` passed。真实审计的 `paper_ready=false` 不变。

Paper Value: 论文正文现在可直接引用“配置记录与冻结实验设计一致”的逐项证据，并与“输入冻结缺失、逐案例 retrieval snapshot 缺失、版本未绑定”等更高层阻塞区分。该改动不证明数据有效性、检索质量、方法效果或人工准确率。

Reviewer: PASS（18 项设计/配置绑定门禁均在正文显式呈现；删除或改类型时 fail-closed；重渲染、全量脚本、freshness 与 diff 均通过）。

Gatekeeper: PASS。无数据库迁移、真实数据删除、部署或外部写入；仅更新离线论文材料渲染、测试与协议说明。

Next: 继续保留并报告尚未满足的确认性证据门禁：外部冻结输入、逐案例 retrieval snapshot、应用 revision、多项目题集、独立人工评审和 v1 证据包。

## Iteration 90 — 论文材料显式呈现 retrieval 摘要门禁

Time: 2026-08-12 Asia/Shanghai

Task: 将审计 JSON 中的 `retrieval_gap_summary_valid` 显式映射到论文材料的“证据链门禁”，并防止渲染器在检查项缺失时静默生成不完整正文。

Reason: Iteration 89 已新增审计级 retrieval 摘要结构门禁，但正文渲染器只展示通用门禁表；若该检查从审计 JSON 删除或改成非布尔值，材料可能仍被渲染，论文读者也看不到该结构性结论。

Change: 渲染器新增必需审计检查读取函数，要求 `retrieval_gap_summary_valid` 存在且为布尔值；证据链门禁表新增“Retrieval 缺口摘要结构一致”行。新增回归覆盖真实材料显示 `PASS` 以及缺失/非布尔检查失败。协议与论文证据索引同步说明 JSON—正文映射和 fail-closed 约束。

Files: `scripts/render_rag_five_mode_paper_material.py`, `scripts/test_render_rag_five_mode_paper_material.py`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-freshness-latest.json`, `NIGHT_LOG.md`。

Tests: 新增正文门禁断言先 RED（旧渲染器不显示该行），实现后渲染器测试 `27 passed`；脚本全量 `404 passed`；材料 freshness `11/11 passed`；`git diff --check` passed。真实审计仍按预期 `paper_ready=false`，本轮不改变确认性结论。

Paper Value: 论文可引用材料现在明确区分“retrieval 摘要结构内部一致”与“论文可用门禁失败”；审计 JSON 的关键结构性结论不会只存在于机器文件而在正文中丢失。该改动只加强证据链映射和失败关闭，不证明检索质量、方法效果或人工准确率。

Reviewer: PASS（正文门禁映射、缺失/非布尔检查 fail-closed、真实材料重渲染和 freshness 均有回归）。

Gatekeeper: PASS。无数据库迁移、真实数据删除、部署或外部写入；仅更新离线论文材料渲染、测试与协议说明。

Next: 完成全量脚本与材料 freshness 校验；随后继续处理仍未满足的外部冻结、版本、多项目题集、独立盲评和确认性证据包门禁。

## Iteration 89 — 审计 JSON 增加 retrieval 摘要一致性门禁

Time: 2026-08-12 Asia/Shanghai

Task: 将 retrieval gap summary 的分区、规范字段和计数上界检查前移到审计 JSON 生成阶段。

Reason: Iteration 88 统一了审计器和渲染器的字段契约，Iteration 86–87 已在渲染器验证分区与字段键，但若审计摘要在写出后被篡改，直到材料渲染才会发现，且 JSON 本身缺少结构化违规定位。

Change: 审计器新增 `retrieval_gap_summary_violations`，逐方法验证规范字段顺序、完整/缺口行分区、字段键集合、非负整数类型、适用行上界和有任一缺口行上界；结果写入 `row_integrity.retrieval_gap_summary_violations`，并新增必需检查 `retrieval_gap_summary_valid`。合成篡改测试验证同时报告 `row_partition` 与 `field_count_exceeds_any_gap_rows`。

Files: `scripts/audit_rag_five_mode_bundle.py`, `scripts/test_audit_rag_five_mode_bundle.py`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`, `docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json`, `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-freshness-latest.json`, `NIGHT_LOG.md`。

Tests: 合成不可能摘要测试先 RED（缺少校验函数），再 GREEN；审计器+渲染器定向 `43 passed`；脚本全量 `403 passed`；真实审计 CLI 按预期退出 1，阻塞仍为版本、外部冻结输入、多项目题集、独立人工评审和确认性证据包；材料 freshness `11/11 passed`；`git diff --check` passed。

Paper Value: 审计 JSON 现在直接携带 retrieval 摘要的结构化一致性结论与违规类型，论文材料可从原始审计产物定位统计分母错误，而不依赖渲染器二次推断。该改动只增强证据链与失败案例定位，不解除 `paper_ready=false`，不证明检索质量、方法效果或人工准确率。

Reviewer: PASS（规范字段、行分区、字段键、计数类型与双重上界均有审计级回归；真实摘要通过该内部一致性门禁）。

Gatekeeper: PASS。无数据库迁移、真实数据删除、部署或外部写入；仅更新离线审计器、材料说明与回归测试。

Next: 继续从仍未满足的论文证据门禁中选择可局部验证缺口；历史实验 5 仍缺少真实逐案例 retrieval snapshot，不能以审计门禁改进替代补采数据。

## Iteration 88 — 审计器与渲染器共享 retrieval 契约

Time: 2026-08-12 Asia/Shanghai

Task: 消除审计器与论文材料渲染器各自维护 retrieval 方法/字段规范造成的契约漂移风险。

Reason: Iteration 87 已在渲染器内约束字段集合和固定顺序，但审计器仍有独立字段常量；任一侧新增参数时，可能出现审计摘要与论文表格解释不一致。

Change: 新增 `scripts/rag_experiment_contract.py`，集中定义五种方法顺序及逐案例 retrieval snapshot 必需字段；审计器和渲染器改为导入该契约。新增跨脚本回归确认两端模式和字段映射对象相同，并将共享契约纳入描述性材料 SHA-256 指纹，源码漂移会使 freshness 检查暴露。

Files: `scripts/rag_experiment_contract.py`, `scripts/audit_rag_five_mode_bundle.py`, `scripts/render_rag_five_mode_paper_material.py`, `scripts/test_render_rag_five_mode_paper_material.py`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-freshness-latest.json`, `NIGHT_LOG.md`。

Tests: 跨脚本契约回归通过；渲染器测试 `26 passed`；脚本全量 `402 passed`；材料 freshness `11/11 passed`；`git diff --check` passed。真实内部批次数值未改变，审计仍保持 `paper_ready=false`，材料仍明确历史四种检索方法缺少逐案例快照。

Paper Value: 论文材料中的 retrieval 字段名称、方法顺序和审计摘要来源现在来自同一可引用契约，并由材料指纹绑定，降低“审计通过但表格语义漂移”的风险。该改动只增强证据链可复现性，不解除 `paper_ready=false`，不证明检索质量、方法效果或人工准确率。

Reviewer: PASS（共享契约、跨脚本一致性、字段集合/顺序、计数边界和 freshness 指纹均有验证）。

Gatekeeper: PASS。无数据库迁移、真实数据删除、部署或外部写入；新增仅为离线证据契约与回归测试。

Next: 继续从仍未满足的论文证据门禁中选择可局部验证缺口；历史实验 5 仍缺少真实逐案例 retrieval snapshot，不能以契约改进替代补采数据。

## Iteration 87 — Retrieval 缺口字段集合与规范绑定

Time: 2026-08-12 Asia/Shanghai

Task: 防止 retrieval gap summary 通过加入未知字段或遗漏规范字段生成看似完整的论文表格。

Reason: Iteration 86 已验证完整快照行与缺口行的分区，但渲染器只检查字段计数字典是整数，未检查其键集合和顺序是否仍与各方法的规范必需字段一致；摘要若被拼接或篡改，可能把未知字段当成参数缺口或静默遗漏关键字段。

Change: 渲染器新增五种方法的规范字段映射，要求 `required_fields` 的固定顺序、`missing_by_field` 键集合和 `mismatch_by_field` 键集合三者与规范完全一致；新增未知字段回归测试先 RED 后 GREEN。协议与论文证据索引同步记录字段集合/顺序绑定。

Files: `scripts/render_rag_five_mode_paper_material.py`, `scripts/test_render_rag_five_mode_paper_material.py`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-freshness-latest.json`, `NIGHT_LOG.md`。

Tests: 新增未知/未绑定字段测试先失败（旧实现未抛出规范字段错误），修正测试夹具后实现通过；渲染器测试 `25 passed`；脚本全量 `401 passed`；材料 freshness `10/10 passed`；`git diff --check` passed。真实历史审计摘要字段集合与规范映射一致，材料数值保持不变，`paper_ready=false` 继续成立。

Paper Value: 论文附录的字段级缺口表现在受方法规范参数集合和稳定顺序约束，不会因未知键、漏键或字段重排而改变统计含义。该改动只增强材料结构与引用审计，不解除 `paper_ready=false`，不证明检索质量、方法效果或人工准确率。

Reviewer: PASS（字段键集合、固定顺序、计数类型、双重分母上界、行分区及纯 LLM 不适用语义均有回归覆盖）。

Gatekeeper: PASS。无数据库迁移、真实数据删除、部署或外部写入；仅更新离线论文材料渲染、测试与协议说明。

Next: 继续从仍未满足的论文证据门禁中选择可局部验证缺口；历史实验 5 仍缺少真实逐案例 retrieval snapshot，不能以统计门禁改进替代补采数据。

## Iteration 86 — Retrieval 快照行分区一致性门禁

Time: 2026-08-12 Asia/Shanghai

Task: 继续收紧 retrieval snapshot 缺口统计的分母口径，要求完整快照行与有任一缺口行恰好覆盖方法适用行数。

Reason: Iteration 85 已限制字段缺失/漂移计数不得超过有任一缺口行数，但若完整行与缺口行本身不构成适用行的划分，论文中的完整率、缺口率仍可能同时被错误报告。

Change: `retrieval_field_gap_summary` 新增分区校验：`rows_with_complete_snapshot + rows_with_any_gap == row_count`，并拒绝负数、布尔值或超出行数的完整行计数；新增合成不分区摘要测试先 RED 后 GREEN。协议与论文证据索引同步记录该分区约束。

Files: `scripts/render_rag_five_mode_paper_material.py`, `scripts/test_render_rag_five_mode_paper_material.py`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-freshness-latest.json`, `NIGHT_LOG.md`。

Tests: 新增不分区摘要测试先失败（旧实现未抛出 `must partition row count`），再通过；渲染器测试 `24 passed`；脚本全量 `400 passed`；材料 freshness `10/10 passed`；`git diff --check` passed。重新审计历史批次仍按预期退出 1，`paper_ready=false`；真实材料的五种方法适用行均满足完整/缺口分区，四种检索方法仍为 `0/36` 完整、`36/36` 有缺口。

Paper Value: 论文附录中的 retrieval 完整率与缺口率现在不仅共享适用行分母，还被强制为互补分区，减少统计摘要内部重叠、遗漏或分母错配。该改动只增强描述性证据的结构一致性，不解除 `paper_ready=false`，不证明检索质量、方法效果或人工准确率。

Reviewer: PASS（完整/缺口分区、字段计数双重上界、类型边界及纯 LLM 不适用语义均有回归覆盖）。

Gatekeeper: PASS。无数据库迁移、真实数据删除、部署或外部写入；仅更新离线论文材料渲染、测试与协议说明。

Next: 继续从仍未满足的论文证据门禁中选择可局部验证缺口；历史实验 5 仍缺少真实逐案例 retrieval snapshot，不能以统计门禁改进替代补采数据。

## Iteration 85 — Retrieval 字段缺口计数增加双重分母门禁

Time: 2026-08-12 Asia/Shanghai

Task: 防止字段级 retrieval snapshot 缺失/非空漂移计数超过方法的有任一缺口行数，避免论文材料出现内部不可能的统计口径。

Reason: Iteration 84 已将字段级计数渲染为 `字段=n/%`，但仅校验了适用行数上界；如果审计摘要同时给出过小的 `rows_with_any_gap`，字段计数仍可能大于所有缺口行，导致分层统计无法成立。

Change: `retrieval_field_gap_summary` 现在校验有任一缺口行数是适用行数的有界整数，并要求每个字段的缺失与非空漂移计数不超过该有任一缺口行数；新增回归测试先 RED 后 GREEN。协议与论文证据索引同步写明字段级计数受适用行数和有任一缺口行数双重上界约束。

Files: `scripts/render_rag_five_mode_paper_material.py`, `scripts/test_render_rag_five_mode_paper_material.py`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-freshness-latest.json`, `NIGHT_LOG.md`。

Tests: 新增不可能计数测试先失败（旧实现未抛出 `exceeds any-gap rows`），再通过；渲染器测试 `23 passed`；脚本全量 `399 passed`；材料 freshness `10/10 passed`；`git diff --check` passed。真实材料未改变数值，仍显示检索方法 `36/36 (100.00%)` 有缺口，字段级缺失计数均为 `36/36 (100.00%)`。

Paper Value: 论文附录中的字段级缺口比例不仅可回溯到适用行数，还满足“字段缺口 ⊆ 任一缺口行”的可解释约束，降低分母错配和审计摘要篡改的风险。该改动只增强描述性材料的内部一致性，不解除 `paper_ready=false`，不证明检索质量、方法效果或人工准确率。

Reviewer: PASS（字段计数类型、适用行数上界、有任一缺口行数上界及纯 LLM 不适用语义均有回归覆盖）。

Gatekeeper: PASS。无数据库迁移、真实数据删除、部署或外部写入；仅更新离线论文材料渲染、测试与协议说明。

Next: 继续从仍未满足的论文证据门禁中选择可局部验证缺口；历史实验 5 仍缺少真实逐案例 retrieval snapshot，不能以统计门禁改进替代补采数据。

## Iteration 84 — Retrieval 字段缺口呈现字段级 n/%

Time: 2026-08-12 Asia/Shanghai

Task: 将实验 5 retrieval snapshot 的字段级缺失与非空漂移从原始 JSON 计数改为论文可读的 `字段=n/%`。

Reason: Iteration 83 已呈现每个方法的完整快照行/有缺口行比例，但 `missing_by_field` 与 `mismatch_by_field` 仍以字典形式展示，容易把字段计数误解为行级分母，也无法直接比较具体缺失字段。

Change: 渲染器新增 `retrieval_field_gap_summary`，对每个适用字段按方法行数做有界计数率校验；缺失和漂移以稳定排序的 `字段=n/%` 输出，纯 LLM 无适用字段显示“不适用”。新增字段值类型失败关闭回归；协议与论文证据索引同步说明字段级分母口径。

Files: `scripts/render_rag_five_mode_paper_material.py`, `scripts/test_render_rag_five_mode_paper_material.py`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-freshness-latest.json`, `NIGHT_LOG.md`。

Tests: 先 RED（字段级 n/% 呈现断言失败），再 GREEN；渲染器测试 `22 passed`；脚本全量 `398 passed`；材料 freshness `10/10 passed`；`git diff --check` passed。正文示例：`corpus_snapshot_hash=36/36 (100.00%)` 缺失、漂移 `0/36 (0.00%)`；纯 LLM 字段为“不适用”。

Paper Value: 论文附录可直接定位“哪一个逐案例参数字段缺失、占适用行数多少、是否存在非空漂移”，避免把汇总配置当成逐案例证据。该改动只增强缺口统计透明度，不解除 `paper_ready=false`，不证明检索质量、方法效果或人工准确率。

Reviewer: PASS（字段计数类型、分母边界和纯 LLM 不适用语义均有回归覆盖）。

Gatekeeper: PASS。无数据库迁移、真实数据删除、部署或外部写入；仅更新离线论文材料渲染、测试与协议说明。

Next: 继续从仍未满足的论文证据门禁中选择可局部验证缺口；历史实验 5 仍缺少真实逐案例 retrieval snapshot，不能以呈现改进替代补采数据。

## Iteration 83 — Retrieval snapshot 缺口呈现分子分母

Time: 2026-08-12 Asia/Shanghai

Task: 将实验 5 参数绑定缺口从按方法裸计数扩展为以适用行数为分母的 `n/%`，并保证 Markdown 表格结构与数据口径一致。

Reason: 既有审计已按方法输出 `rows_with_complete_snapshot` 与 `rows_with_any_gap`，但论文材料读者仍需自行换算缺口比例；对于纯 LLM 与检索方法的适用分母不同，裸计数容易误读。

Change: 渲染器复用有界计数率校验，将完整快照行和有任一缺口行输出为单一 `n/%` 表格单元；新增表格列数回归，防止生成器把计数和比例拆成多余 Markdown 列。协议与论文证据索引明确分母为方法适用行数。

Files: `scripts/render_rag_five_mode_paper_material.py`, `scripts/test_render_rag_five_mode_paper_material.py`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-freshness-latest.json`, `NIGHT_LOG.md`。

Tests: 先 RED（新增缺口率断言失败），再 GREEN；期间捕获并修复一次渲染表列数不一致；渲染器测试 `21 passed`；脚本全量 `397 passed`；材料 freshness `10/10 passed`；`git diff --check` passed。当前正文显示 `pure_llm` 完整快照 `36/36 (100.00%)`、缺口 `0/36 (0.00%)`；其余四种方法完整快照 `0/36 (0.00%)`、缺口 `36/36 (100.00%)`。

Paper Value: 论文附录可直接报告各方法逐案例 retrieval snapshot 的完整/缺口分母与比例，避免把汇总配置误写成逐案例参数证据。该改动只增强参数缺口的可读性和结构校验，不解除 `paper_ready=false`，不证明检索质量、方法效果或人工准确率。

Reviewer: PASS（计数率边界沿用失败关闭规则；表格列数和真实归档重渲染回归通过）。

Gatekeeper: PASS。无数据库迁移、真实数据删除、部署或外部写入；仅更新离线论文材料渲染、测试与协议说明。

Next: 继续从仍未满足的论文证据门禁中选择可局部验证缺口；历史实验 5 的逐案例 retrieval snapshot 仍缺失，不能用本轮呈现替代真实数据补采。

## Iteration 82 — 方法级引用覆盖呈现分子分母

Time: 2026-08-12 Asia/Shanghai

Task: 将实验 5 描述性材料中的方法级引用审计从裸计数扩展为可直接引用的 `n/%`，并保持严格引用语法与完成答案分母绑定。

Reason: Iteration 81 已把报告—重算差异呈现到正文，但方法分层表仍只展示计数。论文读者无法在同一表格中快速核对各方法的分母和比例，容易把非法标记行误读为答案级引用有效率。

Change: 渲染器新增有界 `citation_count_rate`，对布尔值、负数、超分母和零分母失败关闭；方法级表将来源、任一证据、图谱和非法标记行统一输出为 `n/完成答案数 (百分比)`。协议与论文证据索引明确该表的分母和证据边界。

Files: `scripts/render_rag_five_mode_paper_material.py`, `scripts/test_render_rag_five_mode_paper_material.py`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-freshness-latest.json`, `NIGHT_LOG.md`。

Tests: 先 RED（新增 n/% 呈现断言失败），再 GREEN；渲染器测试 `20 passed`；脚本全量 `396 passed`；材料 freshness `10/10 passed`；`git diff --check` passed。当前正文显示 `bm25_rag` 来源标记 `32/36 (88.89%)`、非法标记行 `4/36 (11.11%)`。

Paper Value: 论文附录可以同时引用方法、分子、分母和比例，避免把格式审计计数写成引用正确率；分母固定为已完成答案，非法范围标记仍不计入合法覆盖。该改动只增强统计呈现和输入约束，不解除 `paper_ready=false`，不证明引用内容正确、来源支持命题、检索质量、人工准确率或方法优越性。

Reviewer: PASS（新增计数率边界回归；真实材料重渲染逐字节回归通过）。

Gatekeeper: PASS。无数据库迁移、真实数据删除、部署或外部写入；仅更新离线论文材料渲染、测试与协议说明。

Next: 继续从仍未满足的论文证据门禁中选择可局部验证缺口；外部冻结题集、版本化应用 revision、独立人工盲评和确认性 v1 证据包仍需项目所有者/外部流程完成。

## Iteration 81 — 将引用摘要漂移呈现到论文材料

Time: 2026-08-12 Asia/Shanghai

Task: 将实验 5 描述性材料从“仅展示方法级引用计数”扩展为同时呈现报告值与原始 CSV 重算值的逐字段差异。

Reason: Iteration 80 已把全局和方法级引用摘要漂移纳入审计 JSON，但读者若只阅读 Markdown 仍需展开门禁的完整 JSON 才能定位差异。论文证据链需要让“报告—重算”不一致在可引用材料正文中可见，同时明确它是报告完整性证据，不是引用内容正确性或方法效果证据。

Change: 渲染器新增 `citation_summary_mismatch_rows`，严格校验 `reported_audit_mismatch`、差异数组、层级/字段身份以及重算值/报告值；新增“引用审计报告—重算差异”表，稳定输出全局范围判定和 `bm25_rag` 非法标记行差异。新增真实材料回归，协议与论文证据索引同步渲染语义。

Files: `scripts/render_rag_five_mode_paper_material.py`, `scripts/test_render_rag_five_mode_paper_material.py`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`, `docs/experiments/rag-experiment-5-internal-descriptive-results-freshness-latest.json`, `NIGHT_LOG.md`。

Tests: 先 RED（新增渲染差异断言失败），再 GREEN；渲染器测试 `18 passed`；脚本全量 `394 passed`；真实批次审计按预期退出 1 并保持 `consistency_passed=false`、`paper_ready=false`；材料 freshness `10/10 passed`；`git diff --check` passed。正文现在显示 `all_citation_indices_in_range: false → true`、`bm25_rag / invalid_marker_rows: 4 → 0` 和 `invalid_source_marker_rows: 4 → 0`。

Paper Value: 论文附录可直接引用“报告值与原始 CSV 重算值不一致”的定位表，不把方法级统计漂移隐藏在 JSON 深层；这只证明报告完整性/失败定位链路，不证明引用内容正确、来源支持命题、检索质量、人工准确率或方法优越性。`paper_ready=false` 与既有五项论文阻塞保持不变。

Reviewer: PASS（先 RED 后 GREEN；缺失、类型错误、重复或状态与差异数组不一致时渲染失败关闭）。

Gatekeeper: PASS。无数据库迁移、真实数据删除、部署或外部写入；仅更新离线论文材料渲染与协议说明。

Next: 继续从仍未满足的论文证据门禁中选择可局部验证缺口；在外部冻结题集、版本化应用 revision、独立人工盲评和确认性 v1 证据包到位前，不生成确认性效果结论。

## Iteration 80 — 引用审计方法分层统计绑定

Time: 2026-08-12 Asia/Shanghai

Task: 将实验 5 五方法引用审计从全局计数绑定扩展到逐方法计数、比例和非法行类型绑定。

Reason: Iteration 79 已精确比较失败案例身份，但全局完成数、来源标记数和任一证据标记数相同，并不保证报告的 `by_mode` 统计没有被改写。真实报告还把四个 `bm25_rag` 范围标记失败记录为零，需让方法分层差异成为可定位的门禁结果。

Change: 新增 `citation_audit_summary_mismatches`，逐项比较全局完成/标记计数、严格比例、图谱上下文比例、范围合法性，以及每个方法的完成数、来源/图谱/任一证据标记数、非法行数和比例；将 `reported_summary_mismatches` 纳入 `citation_audit_recomputed_matches_report`。重算器把非法语法和越界标记归并为方法级失败行，并分别统计来源/图谱失败行，避免同一行多个标记造成重复计数；同时补齐离线重算的 `kg_graph_marker_rate_when_context_available` 和逐方法比例。新增单元与报告篡改回归；协议和索引补充方法分层精确绑定语义。

Files: `scripts/audit_rag_five_mode_bundle.py`, `scripts/test_audit_rag_five_mode_bundle.py`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`, `docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json`, `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`, `NIGHT_LOG.md`。

Tests: 引用审计定向 `4 passed`；脚本全量在刷新材料后 `392 passed`；审计 CLI 仍预期退出 1，且输出 `consistency_passed=false`、`paper_ready=false`，论文阻塞项不变。真实批次新增诊断只显示 `bm25_rag` 的 `invalid_marker_rows=4`、`invalid_source_marker_rows=4` 以及全局 `all_citation_indices_in_range` 与旧报告不一致，其他方法级计数和比例一致；材料重渲染成功；freshness `10/10`；`git diff --check` 通过。

Paper Value: 论文附录可以区分“全局计数一致”与“逐方法分层一致”，并准确指出四个范围引用失败属于 `bm25_rag`，支持失败案例与分层统计的可复核性。这只证明自动引用格式/边界和报告数字的内部一致性，不证明引用内容正确、来源支持命题、检索质量、人工准确率或方法优越性。

Reviewer: PASS（先 RED 后 GREEN；方法级字段语义按实际生成器结构修正，避免将失败标记数误作失败标记 token 数）。

Gatekeeper: PASS。无数据库迁移、真实数据删除、部署或外部写入；审计 JSON 与描述性材料按最新源码刷新。

Next: 完成 freshness、差异检查与最终审计状态复核；在外部冻结题集、版本化应用 revision、独立人工盲评和确认性 v1 证据包到位前，不生成确认性效果结论。

# Iteration 79 — 引用审计失败对象精确绑定

Time: 2026-08-12 Asia/Shanghai

Task: 将实验 5 五方法审计器的引用一致性从“失败是否非空”的布尔比较提升为失败对象级精确比较。

Reason: 原审计器只比较重算失败列表与报告失败列表是否同为非空；真实 CSV 重算发现 4 个 `bm25_rag` 范围标记（`[S1-S12]`/`[S6-S12]`），而历史报告的 `invalid_source_marker_rows` 与 `invalid_graph_marker_rows` 为空。即使未来报告写入了错误但同样非空的案例，布尔比较也可能掩盖失败对象漂移，削弱“原始 CSV—审计报告—论文材料”的可复现链路。

Change: 新增纯函数 `citation_audit_matches_report`，将重算的非法/越界标记与报告的来源/图谱失败记录规范化为题目 ID（或报告 case ID）、重复编号、方法和标记的集合，并同时核对 `all_citation_indices_in_range`；精确集合不一致时 `reported_audit_mismatch=true`，且该字段进入 `citation_audit_recomputed_matches_report` 门禁。越界标记重算记录也补齐题目、重复、方法和查询日志身份，便于定位与回放。新增 RED→GREEN 测试覆盖“双方均有失败但失败对象不同”和真实历史报告差异；协议与论文证据索引同步精确绑定语义。

Files: `scripts/audit_rag_five_mode_bundle.py`, `scripts/test_audit_rag_five_mode_bundle.py`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`, `docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json`, `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`, `NIGHT_LOG.md`。

Tests: 引用审计定向 `2 passed`（含 RED→GREEN 对象漂移回归）；脚本全量 `390 passed`；刷新历史审计后保持 `consistency_passed=false`、`paper_ready=false`，并明确保留 5 个论文阻塞项；重新渲染内部描述性材料成功；`git diff --check` 待本轮收尾执行。当前审计摘要为 `reported_audit_mismatch=true`、4 个非法范围标记，不能把该内部批次当作确认性引用有效率结果。

Paper Value: 论文附录可逐案例解释引用语法失败，而不是只报告一个失败计数；同时能检测“报告修改为另一个同数量失败案例”的结果完整性问题。这只证明格式/边界/报告内部一致性审计能力，不证明引用内容正确、来源支持命题、检索质量、人工准确率或方法优越性。

Reviewer: PASS（先加失败测试，再实现精确签名；新增逻辑局限于离线审计与论文协议，真实历史失败事实未被掩盖）。

Gatekeeper: PASS。无数据库迁移、真实数据删除、部署或外部写入；历史材料按审计器源码变更重新生成并通过全量脚本回归。

Next: 继续从论文证据门禁中选择可局部验证的缺口；在外部冻结题集、版本化应用 revision、独立人工盲评和确认性 v1 证据包到位前，不生成确认性效果结论。

## Iteration 78 — 执行器图谱版本漂移失败关闭

Time: 2026-08-12 Asia/Shanghai

Task: 将图谱 schema 版本从“归档时逐案例校验”前移到实验执行器的运行/恢复输入绑定门禁。

Reason: Iteration 77 已要求每个已落库案例的 `retrieval_config.graph_schema_version` 与顶层绑定一致，但队列领取或恢复时若生产图谱规则已切换，旧运行仍可能继续执行并产生跨版本分母；归档阶段才失败会留下不应生成的混合条件日志。

Change: Rust `validate_experiment_input_bindings` 新增当前生产 `GRAPH_SCHEMA_VERSION` 参数与严格比较；运行开始/恢复及每个后续案例复核因此会在图谱版本漂移时返回 `input_binding_drift` 运行级失败。新增回归覆盖同版本通过和 `kg-v2` 漂移拒绝；同步 v1 协议与论文证据索引，明确该门禁不等于检索质量或人工准确率证据。

Files: `backend/src/api/rag.rs`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`, `NIGHT_LOG.md`。

Tests: Rust 定向 `api::rag::tests::test_experiment_input_bindings_fail_closed_on_runtime_drift` `1 passed`；Rust `cargo fmt --all -- --check`、`cargo clippy --locked --all-targets --all-features -- -D warnings` 通过；Rust 全量 `247` 个库测试与 `2` 个二进制测试通过；脚本全量 `388 passed`；前端 `npm run typecheck` 通过。历史实验 5 审计保持 `consistency_passed=false`、`paper_ready=false`，阻塞项仍为应用 revision、外部冻结输入、多项目题集、独立人工评审和 v1 证据包；按最新审计产物重渲染描述性材料成功，freshness `10/10` 通过；`git diff --check` 通过。

Paper Value: 实验不会在执行过程中跨越图谱结构/展开规则版本，形成“排队快照—执行前门禁—逐案例快照—归档审计”的闭环；这是输入一致性与可复现性证据，不是效果、准确率或显著性证据。

Reviewer: PASS（最小 Rust 变更、同文件回归、全量门禁、历史审计和材料 freshness 均已覆盖）。

Gatekeeper: PASS。无数据库迁移、数据删除、部署或外部写入；仅收紧实验输入绑定失败关闭。

Next: 继续处理仍属论文证据门禁的下一项缺口；在外部冻结题集、版本化应用 revision、独立人工盲评和确认性 v1 证据包到位前，不生成确认性效果结论。

## Iteration 77 — 逐案例图谱版本快照绑定

Time: 2026-08-12 Asia/Shanghai

Task: 将 `retrieval_config.graph_schema_version` 纳入每个已落库案例的证据回放门禁，并同步 OpenAPI、前端生成类型与论文协议。

Reason: Iteration 76 已完成运行级 `experiment.graph_schema_version` 绑定，但逐案例 `retrieval_config` 仍可能遗漏或漂移图谱 schema 版本；仅有顶层字段不足以证明每个案例可按同一图谱版本回放。

Change: `check_rag_experiment_evidence.py` 将 `graph_schema_version` 加入稳定检索字段集合，并要求有 `query_log_id` 的案例在顶层实验绑定存在时逐字匹配该版本；同一证据包的稳定检索参数继续禁止漂移。OpenAPI updater、生成的前端类型、v1 协议和论文证据索引同步该字段。新增案例漂移回归与 OpenAPI schema 回归；未修改 Rust 生产写入逻辑，因为其逐案例 `retrieval_config` 已记录生产图谱版本。

Files: `scripts/check_rag_experiment_evidence.py`, `scripts/test_check_rag_experiment_evidence.py`, `scripts/update_rag_evidence_openapi.py`, `scripts/test_update_rag_evidence_openapi.py`, `backend/openapi.json`, `frontend/src/lib/api-schema.d.ts`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`。

Tests: 定向证据校验器与 OpenAPI 回归 `61 passed`；Rust 逐案例生产 graph schema 与 CSV 绑定回归各 `1 passed`；脚本全量 `388 passed`；前端 `npm run typecheck` 通过；Rust `cargo fmt --all -- --check`、`cargo clippy --locked --all-targets --all-features -- -D warnings` 通过；Rust 全量 `247` 个库测试与 `2` 个二进制测试通过。历史实验 5 审计保持预期 `consistency_passed=false`、`paper_ready=false`，5 个阻塞项未被掩盖；描述性材料重渲染成功，freshness `10/10` 通过；`git diff --check` 通过。不得把新增绑定门禁解释为检索质量或人工准确率证据。

Paper Value: 每个可回放案例都携带并校验图谱 schema 版本，形成“运行级绑定—逐案例快照—稳定参数组”的可审计链路，避免将不同图谱结构版本混入同一分母；历史内部批次仍需外部冻结题集、应用 revision、独立盲评和确认性 v1 证据包，`paper_ready=false` 不变。

Reviewer: PASS（逐案例漂移回归、契约生成、全量 Rust/脚本验证和文档边界均已覆盖）。

Gatekeeper: PASS。修改局限于证据校验、OpenAPI/前端生成契约和论文协议记录；无数据库迁移、真实数据删除、部署或外部写入。

Next: 完成全量 Rust、历史材料审计/渲染/freshness 与工作树一致性检查；继续优先补齐论文证据而非界面功能。

## Iteration 76 — 证据包顶层图谱版本绑定

Time: 2026-08-12 Asia/Shanghai

Task: 将 `graph_schema_version` 从运行配置快照提升为论文证据包顶层稳定绑定字段，并同步归档校验与客户端契约。

Reason: 生产 Rust 已在运行级和逐案例检索配置记录图谱 schema 版本，但 evidence JSON 的 `experiment`、OpenAPI 和前端生成类型未显式公开；缺少顶层绑定会使论文归档依赖任意扩展字段，增加版本遗漏风险。

Change: 先新增 Rust RED 回归，确认顶层字段在实现前为 `null`；随后在 `build_experiment_evidence_package` 输出 `experiment.graph_schema_version`，OpenAPI updater 与生成 TypeScript 类型同步该字段。归档检查器在配置快照包含该字段时，要求顶层值为非空字符串且逐字匹配；历史未含该字段的包保持兼容，但不能被解释为完成了图谱版本绑定。协议文档和证据索引补充字段语义与历史边界。

Files: `backend/src/api/rag.rs`, `scripts/check_rag_experiment_evidence.py`, `scripts/test_check_rag_experiment_evidence.py`, `scripts/update_rag_evidence_openapi.py`, `scripts/test_update_rag_evidence_openapi.py`, `backend/openapi.json`, `frontend/src/lib/api-schema.d.ts`, `docs/experiments/rag-evidence-package-protocol-v1.md`, `docs/experiments/rag-paper-evidence-index-v1.md`。

Tests: RED 目标 Rust 测试按预期失败（顶层值 `null`）；实现后目标 Rust 测试通过；证据校验器与 OpenAPI updater 定向回归 `60 passed`；OpenAPI 生成与前端类型同步成功。`cargo fmt --all -- --check`、`cargo clippy --locked --all-targets --all-features -- -D warnings` 通过；Rust 全量 `247` 个库测试与 `2` 个二进制测试通过；脚本全量 `387 passed`；前端 `npm run typecheck` 通过。历史实验 5 审计仍按预期 `consistency_passed=false`、`paper_ready=false`，阻塞项为版本绑定、外部冻结输入、多项目题集、独立人工评审和 v1 证据包；描述性材料重渲染成功，freshness `10/10` 通过。

Paper Value: 论文材料可以直接审计图谱结构/展开规则版本，并将其与不可变运行配置逐字核对；该工程证据仍不等价于外部冻结题集、人工盲评或确认性效果结论，历史内部批次的 `paper_ready=false` 保持不变。

Reviewer: PASS（RED-GREEN 回归、生成契约、全量测试和历史材料门禁结果一致）。

Gatekeeper: PASS。修改局限于证据导出、归档校验、契约生成和论文协议记录；无数据库迁移、真实数据删除、部署或外部写入。

Next: 完成对应全量验证；若证据材料 freshness 受协议指纹影响，重新渲染并核验，不生成虚假确认性结果。

## Iteration 0

Time: 2026-08-11 Asia/Shanghai

Task: 初始化只读审计并建立夜间上下文、问题池、日志。

Reason: 协议要求先确认项目真实架构、核心流程、测试面、AI 实现和工作树边界；当前仓库有大量用户既有未提交修改。

Files: `NIGHT_CONTEXT.md`, `NIGHT_BACKLOG.md`, `NIGHT_LOG.md`

Tests: `GET http://127.0.0.1:8001/health` → 200；实时响应头确认 `x-backend-runtime: axum`；`GET http://127.0.0.1:3000` → 307 到未认证项目页（符合登录保护）；未执行业务代码测试。

Result: PASS。已确认 `full-system` 为目标项目；未覆盖或恢复任何既有修改。发现成熟度门禁与人工评审/生产证据仍有明确阻塞。

Paper Value: 建立需求—实现—证据—阻塞的可追溯基线，直接支撑系统架构、实现、测试和论文实验边界说明。

Reviewer: PASS（只读审计；架构、运行时、测试和证据均有仓库来源）。

Gatekeeper: PASS（安全、小范围、可逆、可验证；仅新增协议记录）。

Next: 运行基线静态检查，识别不触碰既有业务改动的第一个高价值任务。

## Iteration 1

Time: 2026-08-11 Asia/Shanghai

Task: 真实浏览器核心导航冒烟与工程基线验证。

Reason: 协议要求按用户真实点击路径检查登录、项目、笔记、资料、AI、图谱和新建实验记录入口。

Files: 无业务文件修改；更新本日志及上下文/问题池记录。

Tests: `cargo fmt --all -- --check`；`cargo check --workspace`；`cargo clippy --workspace --all-targets -- -D warnings`；`cargo test --workspace`（236 个库测试 + 2 个二进制测试通过）；`backend/.venv/bin/python -m pytest tests -q`（355 passed，10 warnings）；`npm run lint`；`npm run typecheck`；`npm run build`；Playwright 真实浏览器 `http://localhost:3000` 登录与项目 8 页面导航通过。

Result: PASS。核心演示路径在文档推荐入口可用；未发现值得在当前大规模既有 diff 上冒险修改的 P1/P2 代码缺陷。仅观察到 loopback host 别名导致 cookie 会话失败的环境约束。

Paper Value: 为论文系统测试、答辩 Demo 和“可运行但需统一 host 入口”的边界提供真实操作证据；自动测试与 Rust 生产运行时均有独立结果。

Reviewer: PASS。正确性、回归、范围、复杂度和可维护性检查均通过；Python 测试的历史兼容层定位已明确。

Gatekeeper: PASS。修改范围为新增记录文件，低风险、可逆、可验证；N-007 留作 owner decision，不擅自改变认证安全策略。

Next: 最终审计；若没有新的高价值低风险任务，停止开发并生成最终报告。

## Iteration 2

Time: 2026-08-11 Asia/Shanghai

Task: 新增验证脚本的单测与真实 Rust 运行时契约复核。

Reason: 在不触碰用户既有业务 diff、数据库真实数据或部署配置的前提下，验证新增的本地健康、RAG 证据、Agent 质量、Rust 检索和契约导出检查仍可复现，并确认测试结果与当前 Axum 实例一致。

Files: 无业务文件修改；仅补充本日志和 `NIGHT_WORK_REPORT.md` 的结果记录。

Tests: `backend/.venv/bin/python -m pytest -q scripts/test_check_local_health.py scripts/test_check_rag_evidence.py scripts/test_evaluate_agent_quality.py scripts/test_evaluate_rust_retrieval.py scripts/test_export_rust_contract_evidence.py scripts/test_freeze_rag_evidence.py`（20 passed）；`GET /health` 200；`GET /ready` database/storage 均为 `ok`；实时 `/openapi.json` 为 70 paths/85 operations；实时 `/metrics` runtime 为 `rust-axum`；`git diff --check` 通过。

Result: PASS。未发现新的可稳定复现 P1/P2 缺陷；当前剩余项仍是 host 入口选择、人工评审和生产级外部证据。

Paper Value: 为系统证据链提供独立、可重复的验证层，并再次确认仓库记录的 API 契约与真实 Rust 运行时没有明显漂移。

Reviewer: PASS。测试范围明确、结果可复现、未把运行时开发快照冒充论文实验数据。

Gatekeeper: PASS。无业务代码、数据、部署或版本历史变更；只更新夜间记录和报告。

Next: 重新启动后继续做局部、低风险、可验证迭代；不再假定存在未持久化的 06:00 自动汇总。

## Iteration 3

Time: 2026-08-12 Asia/Shanghai

Task: 修复认证表单语义并补齐应用图标。

Reason: 真实浏览器检查发现密码输入缺少浏览器可识别的 `autocomplete` 语义，且当前源码没有应用图标入口；两项均为低风险、局部可验证的用户体验问题。

Files: `frontend/src/app/login/page.tsx`, `frontend/src/app/icon.svg`, `frontend/src/components/shared/TopNav.tsx`, `frontend/src/app/(dashboard)/admin/user-management.tsx`。

Tests: `npm run lint`、`npm run typecheck`、`npm run build` 通过；当前源码临时启动于 3300 端口时 `/icon.svg` 返回 200，登录页生成图标链接；旧的 3000 容器未重建，未将其陈旧结果误判为当前源码结果。

Result: PASS。认证协议未改变，改动只补充表单语义和 Next 应用图标。

Paper Value: 提升答辩 Demo 的完成度与可访问性，减少浏览器/密码管理器对登录流程的误判。

Reviewer: PASS。局部 diff、构建产物和当前源码运行结果一致；未把 `/favicon.ico` 误报为已直接提供。

Gatekeeper: PASS。4 个文件、无依赖/数据/部署变更，可逆且已验证。

Next: 修复前端/API host 配置错误的可发现性，不改变认证安全边界。

## Iteration 4

Time: 2026-08-12 Asia/Shanghai

Task: 为本地健康检查增加前端/API host 一致性诊断。

Reason: `127.0.0.1` 与 `localhost` 混用会使开发浏览器会话恢复失败；应在登录前给出明确配置错误，而不是尝试夜间改动 cookie 策略。

Files: `scripts/check_local_health.py`, `scripts/test_check_local_health.py`。

Tests: 健康检查脚本测试 4 passed；`py_compile` 通过；选定脚本回归 21 passed；真实 `localhost:3000`/`localhost:8001` 健康检查 `local_ready=true`；直接函数测试能识别 loopback host mismatch；`git diff --check` 通过。

Result: PASS。检查会区分同 host、loopback 别名混用和一般 host 不一致；未修改认证、CORS 或 cookie 策略。

Paper Value: 为系统部署前置检查和可复现实验环境提供明确失败诊断，减少因入口配置差异造成的假阴性。

Reviewer: PASS。新增分支有回归测试，默认值与 README 推荐的 `localhost` 一致，失败信息包含修复方向。

Gatekeeper: PASS。2 个脚本文件、无业务运行时变更，低风险、可逆、可验证。

Next: 统一导出下载调用的认证与错误处理。

## Iteration 5

Time: 2026-08-12 Asia/Shanghai

Task: 将 CSV 实验导出和盲评批量导出统一到主 API 请求封装。

Reason: 两个下载调用虽然带 cookie，但绕过了主封装，认证失效时不会复用统一的 401 跳转、request-id 和错误解析。

Files: `frontend/src/lib/api.ts`（仅 `apiFetch` 响应解析扩展及两个 CSV 导出调用）。

Tests: `npm run lint`、`npm run typecheck`、`npm run build`、`git diff --check` 通过；源码中底层 `fetch` 仍只有主 `apiFetch` 一处；Blob 返回类型保持不变。

Result: PASS。导出成功路径保持 Blob，失败路径复用统一会话和错误处理。

Paper Value: 强化实验数据导出的可追溯性和登录态一致性，降低答辩演示或评估数据导出时的隐性失败。

Reviewer: PASS。未改变导出 URL、响应格式或数据内容，只收敛请求生命周期处理。

Gatekeeper: PASS。无 schema、依赖、真实数据或部署变更；相关前端质量门禁通过。

Next: 执行最终全局回归和停止条件审计。

## Iteration 6 — Final Gate

Time: 2026-08-12 Asia/Shanghai

Task: 全局回归、运行时只读探针和停止条件审计。

Tests: `cargo fmt --all -- --check`、`cargo check --workspace`、`cargo clippy --workspace --all-targets -- -D warnings` 通过；`cargo test --workspace` 为 234 个库测试 + 2 个二进制测试通过；`backend/.venv/bin/python -m pytest tests -q` 为 355 passed、10 warnings；选定脚本回归 21 passed；`npm run lint`、`npm run typecheck`、`npm run build` 通过；`/health`、`/ready`、`/openapi.json`、`/metrics` 均 200；健康检查 `local_ready=true`。

Result: PASS。未发现新的可稳定复现 P1/P2 缺陷。临时 Playwright 快照已清理；未 push、部署、删除真实数据或重建既有服务容器。

Reviewer: PASS。代码、测试、构建和运行时证据一致；报告数字已按最终命令结果修正。

Gatekeeper: PASS。剩余 N-004/N-005/N-006 以及 N-007 的策略选择需要 Owner、人工评审或外部生产条件；当前没有同时满足高价值、低风险、无需 Owner 决策的下一项任务。

Stop Condition: 达到协议停止条件：剩余任务均为 Owner 决策、外部环境或高风险既有大 diff 交界事项。本轮长程工作在完成真实迭代、验证和交付审计后停止。

## Iteration 7 — 论文证据包导出

Time: 2026-08-12 Asia/Shanghai

Task: 为 RAG 对照实验增加可复核的 JSON 证据包导出契约。

Reason: 论文实验需要把运行级协议、检索参数、逐案例回答、来源/图谱证据、引用审计和失败分母绑定在同一份材料中；现有 CSV 适合表格分析，但不够完整地支撑重跑与误差审计。

Change: 新增 `GET /rag/experiments/{run_id}/evidence.json`；保留 CSV 导出不变。证据包版本为 `rag-evidence-package-v1`，包含随机种子、执行计划哈希、模型、配置快照、逐案例证据与引用审计；运行摘要中未落库的失败案例也会保留。新增前端下载封装、OpenAPI/TypeScript 契约同步和协议文档 `docs/experiments/rag-evidence-package-protocol-v1.md`。

Files: `backend/src/api/rag.rs`、`backend/openapi.json`、`frontend/src/lib/api-schema.d.ts`、`frontend/src/lib/api.ts`、`docs/experiments/rag-evidence-package-protocol-v1.md`。

Tests: 证据包单测 2 passed；`cargo fmt --all -- --check`、`cargo clippy --locked --all-targets --all-features -- -D warnings`；OpenAPI 路由注册与匿名访问测试各 1 passed；前端 `npm run lint`、`npm run typecheck`、`npm run build`；`git diff --check`。Python 脚本回归未执行，当前系统 `python3` 未安装 pytest，未将其计入通过结果。

Result: PASS。未改变数据库 schema、认证、人工盲评规则或生产配置；新增端点继承项目访问与解盲权限。

Paper Value: 可直接支撑论文第七章的实验配置、可复现性、证据追溯和失败案例审计；明确证据包不能替代独立人工盲评和签字。

Reviewer: PASS。证据包对已落库和未落库失败案例均保留，避免选择性删除或缩小分母；OpenAPI、Rust 路由和前端生成类型一致。

Gatekeeper: PASS。局部 Rust API + 契约同步，未覆盖初始化前用户既有工作；无真实数据删除、部署或外部网络写入。

Next: 正式确认性实验仍需 Owner 冻结多项目题集、金标准和独立人工盲评；本端点只负责把已完成运行固化为可复核材料。

## Iteration 8 — 证据包完整性验证器

Time: 2026-08-12 Asia/Shanghai

Task: 为 `rag-evidence-package-v1` 增加独立的归档前一致性检查。

Reason: JSON 导出已经绑定运行配置、案例和失败分母，但论文归档还需要一个不连接数据库、不重新运行模型的纯材料检查器，防止 `case_count`、执行顺序、协议哈希或失败记录在复制/整理时发生静默漂移。

Change: 新增 `scripts/check_rag_experiment_evidence.py` 与 `scripts/test_check_rag_experiment_evidence.py`。检查 schema 版本、案例分母、完成/失败计数、执行顺序唯一性与连续性、失败案例错误信息、摘要错误映射、随机种子和执行计划哈希一致性；完成或带错误完成的实验必须覆盖完整执行计划。协议文档新增 CLI 归档检查示例，并明确该检查器不证明模型重跑结果或人工评价有效性。

Tests: `backend/.venv/bin/python -m pytest -q scripts/test_check_rag_experiment_evidence.py scripts/test_check_rag_evidence.py scripts/test_freeze_rag_evidence.py`（14 passed）；Python 标准库直接执行验证器测试（6/6）；CLI 有效样本通过、故意篡改 `case_count` 的样本按预期拒绝；`py_compile` 和 `git diff --check` 通过。系统 `python3 -m pytest` 仍因缺少 pytest 不可用，未把环境失败计入代码失败。

Result: PASS。未修改 Rust/Next 业务运行时、数据库、认证或生产配置；验证器只读取用户显式提供的 JSON 文件，可复现且失败关闭。

Paper Value: 为论文实验材料增加独立的归档完整性门，支持在写作/答辩前发现分母缩减、执行计划漂移和失败案例丢失；保持“自动检查不等于人工盲评”的方法边界。

Reviewer: PASS。测试同时覆盖正常包和故意损坏包；验证器不会把缺失/不完整的已完成实验标记为合格。

Gatekeeper: PASS。2 个新增脚本 + 1 个协议文档局部变更，无外部网络写入、无真实数据修改、无部署或版本历史变更。

Next: 正式确认性实验仍需 Owner 冻结多项目题集、金标准、运行时绑定和独立人工盲评；本轮可停止，等待下一次状态检查。

## Iteration 9 — 执行计划逐案例绑定

Time: 2026-08-12 Asia/Shanghai

Task: 强化 `rag-evidence-package-v1` 的归档完整性检查，使每个案例与正式执行计划逐字段绑定。

Reason: 上一轮已检查案例数量、分母和顺序，但若案例的题目、模式或重复次数在导出/整理过程中被替换，单纯的数量检查仍可能放行；论文重现性需要验证实际案例元数据与计划一致。

Change: `scripts/check_rag_experiment_evidence.py` 现在读取 `summary.execution_plan`，逐项核对 `question_index`、`question`、`mode`、`repetition_index` 和 `execution_order`；同时检查执行计划自身的顺序唯一性与完成运行的连续性。新增对应篡改测试，并更新协议文档说明。

Tests: `backend/.venv/bin/python -m pytest -q scripts/test_check_rag_experiment_evidence.py scripts/test_check_rag_evidence.py scripts/test_freeze_rag_evidence.py`（15 passed）；Python 标准库直接执行验证器测试（7/7）；`py_compile`、CLI 正反例和 `git diff --check` 通过。系统 Python 缺少 pytest，未将其环境失败计入代码失败。

Result: PASS。未修改 Rust/Next 业务运行时、数据库、认证或生产配置；验证器仍是纯 JSON、失败关闭、无外部写入。

Paper Value: 降低实验材料被部分替换后仍通过数量门槛的风险，增强论文中“预注册执行计划—实际案例—失败分母”的可审计链路。

Reviewer: PASS。新增测试覆盖案例模式漂移；验证器同时检查计划和案例，且保留中断运行与正式完成运行的边界。

Gatekeeper: PASS。仅修改验证脚本、测试、协议文档和夜间记录，无真实数据、部署或版本历史变更。

Next: 正式确认性实验仍需 Owner 冻结多项目题集、金标准、运行时绑定和独立人工盲评；本轮停止，等待下一次状态检查。

## Iteration 10 — 中断运行分母校验

Time: 2026-08-12 Asia/Shanghai

Task: 补齐中断 RAG 实验的未执行案例分母校验。

Reason: 协议允许中断运行保留部分案例，但若 `summary.unexecuted_cases` 在归档时漂移，论文复核仍可能误读完成率和失败分母。

Change: 验证器新增 `summary.unexecuted_cases = total_cases - completed_cases - failed_cases` 校验；仍允许中断运行通过部分案例检查，但要求未执行分母准确。新增中断包通过测试和未执行数量篡改拒绝测试，协议文档同步说明。

Tests: `backend/.venv/bin/python -m pytest -q scripts/test_check_rag_experiment_evidence.py scripts/test_check_rag_evidence.py scripts/test_freeze_rag_evidence.py`（17 passed）；Python 标准库直接执行验证器测试（10/10）；`py_compile`、CLI 正反例和 `git diff --check` 通过。系统 Python 缺少 pytest，未将其环境失败计入代码失败。

Result: PASS。未修改 Rust/Next 业务运行时、数据库、认证或生产配置；验证器仍是纯 JSON、失败关闭、无外部写入。

Paper Value: 保证中断运行的未执行案例仍进入论文分母，避免把部分运行误写成完整实验结果。

Reviewer: PASS。测试覆盖完整运行、中断运行和分母篡改；验证器边界与协议文档一致。

Gatekeeper: PASS。仅修改验证脚本、测试、协议文档和夜间记录，无真实数据、部署或版本历史变更。

Next: 正式确认性实验仍需 Owner 冻结多项目题集、金标准、运行时绑定和独立人工盲评；本轮停止，等待下一次状态检查。

## Iteration 11 — 执行计划哈希重算

Time: 2026-08-12 Asia/Shanghai

Task: 让证据包验证器重新计算执行计划哈希，而不是只比较导出字段。

Reason: 若归档材料同时被修改了执行计划和其哈希字段，单纯的字段互比仍可能放行；论文复现性需要验证计划内容本身的摘要。

Change: 新增 `execution_plan_sha256`，使用与 Rust 生产端一致的 UTF-8 紧凑 JSON 字节规则计算 `summary.execution_plan` 哈希，并与配置协议中的 `execution_plan_hash` 比较。新增“执行计划内容改变但同步旧字段”拒绝测试，并调整夹具字段顺序以验证跨语言兼容。

Tests: RED 阶段新增测试按预期失败；修复后 `backend/.venv/bin/python -m pytest -q scripts/test_check_rag_experiment_evidence.py scripts/test_check_rag_evidence.py scripts/test_freeze_rag_evidence.py`（18 passed）；跨语言规范哈希检查通过；`py_compile` 和 `git diff --check` 通过。

Result: PASS。未修改 Rust/Next 业务运行时、数据库、认证或生产配置；只增强纯 JSON 归档验证。

Paper Value: 防止执行计划被改写后通过同步修改哈希字段绕过检查，增强预注册计划与最终实验材料之间的完整性证据。

Reviewer: PASS。验证逻辑与 Rust `serde_json::to_vec` 的字段顺序和紧凑编码对齐，并有跨语言哈希回归。

Gatekeeper: PASS。仅修改验证脚本、测试、协议文档和夜间记录，无真实数据、部署或版本历史变更。

Next: 正式确认性实验仍需 Owner 冻结多项目题集、金标准、运行时绑定和独立人工盲评；本轮停止，等待下一次状态检查。

## Iteration 12 — 执行计划重建校验

Time: 2026-08-12 Asia/Shanghai

Task: 根据实验协议重建 RAG 执行计划，防止计划内容与哈希字段同时被篡改。

Reason: 上轮已重算导出计划哈希，但若攻击/误操作同时改写计划和哈希，仍可能通过；真正的完整性校验需要从问题集、模式、重复次数、随机种子和随机化开关独立重建预期计划。

Change: 新增 `regenerated_execution_plan`，复刻 Rust 生产端的计划生成、随机排序、字段顺序和执行序号规则；验证器将重建计划与导出 `summary.execution_plan` 逐字节比较。新增同步重写哈希仍拒绝的测试，以及 `randomize_order=true` 的计划重建测试。协议文档同步更新。

Tests: RED 阶段测试按预期发现当前逻辑会放行同步重写哈希；修复后相关 pytest（含 RAG 证据冻结回归）20 passed；标准库直接测试 13/13；`py_compile` 和 `git diff --check` 通过。

Result: PASS。未修改 Rust/Next 业务运行时、数据库、认证或生产配置；只增强纯 JSON 归档验证。

Paper Value: 将“协议输入—预期执行计划—实际案例—哈希”连成独立可重建链路，降低实验材料被同步改写后仍被误认为原始结果的风险。

Reviewer: PASS。随机化和非随机化路径均有覆盖，重建规则与 Rust 端生成逻辑对齐。

Gatekeeper: PASS。仅修改验证脚本、测试、协议文档和夜间记录，无真实数据、部署或版本历史变更。

Next: 正式确认性实验仍需 Owner 冻结多项目题集、金标准、运行时绑定和独立人工盲评；本轮停止，等待下一次状态检查。

## Iteration 13 — 随机化跨语言语义对齐

Time: 2026-08-12 Asia/Shanghai

Task: 修正验证器随机化计划重建与 Rust `serde_json::Value` 显示规则之间的差异。

Reason: 跨语言审计发现 Rust 随机排序键中的字符串包含 JSON 引号和转义，而 Python 初版使用裸字符串；当问题包含冒号、引号等字符时，两端会产生不同的执行顺序。

Change: 新增 `rust_value_display`，让 Python 对数字和字符串采用与 Rust `Value` 格式化一致的排序键；新增包含冒号和引号的问题文本回归测试，并更新协议文档明确该规则。

Tests: RED 阶段特殊字符测试按预期失败；修复后相关 pytest（含 RAG 证据冻结回归）21 passed；`py_compile`、`git diff --check` 通过。

Result: PASS。未修改 Rust/Next 业务运行时、数据库、认证或生产配置；只修正归档验证器的跨语言语义。

Paper Value: 避免含特殊字符的正式题集在验证阶段被错误判定为执行计划漂移，或因算法差异漏检实际漂移，增强实验复现校验可信度。

Reviewer: PASS。新增边界用例覆盖 JSON 引号/转义，验证器与生产排序逻辑对齐。

Gatekeeper: PASS。仅修改验证脚本、测试、协议文档和夜间记录，无真实数据、部署或版本历史变更。

Next: 正式确认性实验仍需 Owner 冻结多项目题集、金标准、运行时绑定和独立人工盲评；本轮停止，等待下一次状态检查。

## Iteration 14 — 总案例数与计划长度绑定

Time: 2026-08-12 Asia/Shanghai

Task: 将 `experiment.total_cases` 与协议重建出的执行计划长度绑定。

Reason: 若只同步修改总案例数、完成/失败计数和未执行数量，材料可能形成内部自洽但与问题集/模式/重复次数不符的错误分母。

Change: 验证器在成功重建执行计划后，要求 `experiment.total_cases == len(regenerated_execution_plan)`；新增总案例数漂移拒绝测试，协议文档同步说明。

Tests: RED 阶段测试按预期捕获总案例数缺少重建约束；修复后相关 pytest（含 RAG 证据冻结回归）22 passed；`py_compile` 和 `git diff --check` 通过。

Result: PASS。未修改 Rust/Next 业务运行时、数据库、认证或生产配置；只增强纯 JSON 归档验证。

Paper Value: 防止论文实验分母通过同步修改计数字段脱离正式题集、对照模式和重复次数，增强实验规模声明的可审计性。

Reviewer: PASS。总案例数现在同时受协议重建计划和逐案例状态计数约束。

Gatekeeper: PASS。仅修改验证脚本、测试、协议文档和夜间记录，无真实数据、部署或版本历史变更。

Next: 正式确认性实验仍需 Owner 冻结多项目题集、金标准、运行时绑定和独立人工盲评；本轮停止，等待下一次状态检查。

## Iteration 15 — 实验协议输入合法性

Time: 2026-08-12 Asia/Shanghai

Task: 拒绝空题集、空模式和超出生产契约的重复次数/模式组合。

Reason: 仅依赖计划重建时，篡改材料可以把题集或模式改为空数组，并同步将总案例数和哈希改为 0，形成表面自洽但没有科研意义的“空实验”。

Change: 验证器新增非空题集、非空模式、模式白名单、模式去重和 `repetitions` 1–10 范围校验；新增空输入与零重复次数拒绝测试，协议文档同步说明。

Tests: RED 阶段成功捕获空实验可被放行；修复后相关 pytest 24 passed；标准库直接测试 17 passed；`py_compile` 和 `git diff --check` 通过。

Result: PASS。未修改 Rust/Next 业务运行时、数据库、认证或生产配置；只增强纯 JSON 归档验证。

Paper Value: 防止论文实验材料通过构造空题集/空模式制造虚假的零案例结果，确保实验规模与生产 API 契约一致。

Reviewer: PASS。验证器输入约束与 Rust 实验创建接口的模式集合和重复次数范围一致。

Gatekeeper: PASS。仅修改验证脚本、测试、协议文档和夜间记录，无真实数据、部署或版本历史变更。

Next: 继续检查失败摘要、运行级故障和案例来源的归档一致性。

## Iteration 16 — 失败摘要一一对应校验

Time: 2026-08-12 Asia/Shanghai

Task: 加强 RAG 证据包中失败案例与 `summary.errors` 的一一对应约束。

Reason: 原校验器只检查错误摘要能否映射到失败案例；重复摘要、失败案例缺少摘要或摘要元数据漂移仍可能影响论文失败分母和错误归因。

Change: 新增失败案例与错误摘要按 `execution_order` 的唯一性、完备性和元数据一致性校验；同步协议文档，明确错误摘要必须与案例的问题序号、问题文本、模式、重复次数和错误文本一致。

Tests: RED 阶段新增 3 项测试并按预期失败；修复后完整相关 pytest 27 passed；标准库直接测试 20 passed；`py_compile` 和 `git diff --check` 通过。

Result: PASS。仅修改纯 JSON 验证器、测试、协议文档和夜间记录；未修改 Rust/Next 业务运行时、数据库、认证或生产配置。

Paper Value: 保证失败案例的分母、错误类型和执行序号在证据包摘要与逐案例材料之间可审计对应，降低论文统计重复计数、漏计和错配风险。

Reviewer: PASS。覆盖重复、缺失和元数据漂移边界。

Gatekeeper: PASS。未触碰既有业务改动、真实数据或版本历史。

Next: 继续检查运行级致命错误与题集输入边界。

## Iteration 17 — 运行级致命失败边界

Time: 2026-08-12 Asia/Shanghai

Task: 约束证据包中运行级 `fatal_error` 与实验状态的一致性。

Reason: 原校验器会原样接受 `summary.fatal_error`，无法区分单案例失败与整个运行失败，可能导致论文归档缺少运行级故障原因或在已完成运行中残留误导性故障字段。

Change: `failed` 运行必须包含非空 `summary.fatal_error.error`；其他状态不得包含 `fatal_error`。新增失败运行缺失、格式错误、合法失败和非失败残留四类测试，并同步协议说明。

Tests: RED 阶段新增测试按预期失败；修复后完整相关 pytest 31 passed；标准库直接测试 24 passed；`py_compile` 和 `git diff --check` 通过。

Result: PASS。仅修改纯 JSON 验证器、测试、协议文档和夜间记录；未修改 Rust/Next 业务运行时、数据库、认证或生产配置。

Paper Value: 让论文能够分别报告案例级失败与运行级失败，防止故障原因缺失、残留或分类混淆。

Reviewer: PASS。边界覆盖失败状态、完成状态和中断状态，且不改变现有执行流程。

Gatekeeper: PASS。未触碰既有业务改动、真实数据或版本历史。

Next: 继续检查题集输入与案例来源构成。

## Iteration 18 — 题集输入边界校验

Time: 2026-08-12 Asia/Shanghai

Task: 收紧证据包题集和模式的输入合法性边界。

Reason: 生产运行接口会清理空题但允许重复题目；若重复题目进入论文证据包，可能被误计为独立样本。畸形的非字符串题目或模式还可能让计划重建阶段出现未处理类型错误。

Change: 证据包校验器现在要求题目为非空字符串、唯一且不超过 4,000 字符；模式必须为字符串，再执行生产模式白名单和去重检查。协议文档同步说明。

Tests: RED 阶段新增重复、空白、非字符串、超长题目及畸形模式测试；修复后完整相关 pytest 34 passed；标准库直接测试 27 passed；`py_compile` 和 `git diff --check` 通过。

Result: PASS。仅修改纯 JSON 验证器、测试、协议文档和夜间记录；未修改 Rust/Next 业务运行时、数据库、认证或生产配置。

Paper Value: 保证论文题集的样本单位清晰、输入边界可复核，并让损坏的归档材料失败关闭。

Reviewer: PASS。覆盖重复题目、空白题目、非字符串值、超长题目和非字符串模式。

Gatekeeper: PASS。未触碰既有业务改动、真实数据或版本历史。

Next: 继续检查案例来源构成。

## Iteration 19 — 案例来源构成校验

Time: 2026-08-12 Asia/Shanghai

Task: 明确证据包 `case_count` 的案例来源构成。

Reason: 导出器将数据库日志案例与运行摘要中的未落库失败案例合并；原校验器虽检查总数和状态，却未约束日志 ID 的来源类型与唯一性，可能出现完成案例无日志、重复日志或畸形日志 ID。

Change: 校验器现在要求已落库案例使用唯一正整数 `query_log_id`，无日志案例只能是失败案例；同步协议文档说明 `case_count = logged cases + unlogged failed cases` 的来源含义。

Tests: RED 阶段新增完成案例缺日志、非法日志 ID 和重复日志 ID 测试；修复后完整相关 pytest 36 passed；标准库直接测试 29 passed；`py_compile` 和 `git diff --check` 通过。

Result: PASS。仅修改纯 JSON 验证器、测试、协议文档和夜间记录；未修改 Rust/Next 业务运行时、数据库、认证或生产配置。

Paper Value: 让论文归档中的案例总数可拆解、可追溯，避免数据库日志重复引用或无日志完成案例污染实验分母。

Reviewer: PASS。覆盖 null、布尔值、字符串、非正整数和重复日志 ID。

Gatekeeper: PASS。未触碰既有业务改动、真实数据或版本历史。

Next: 正式确认性实验仍需 Owner 冻结多项目题集、金标准、运行时绑定和独立人工盲评；本轮停止，等待下一次状态检查。

## Iteration 20 — 夜间日志顺序修复

Time: 2026-08-12 Asia/Shanghai

Task: 修复夜间迭代日志的顺序与记录边界。

Reason: 前几轮自动追加时，第10–19轮出现逆序，且第17轮附近混入旧轮次内容；这会削弱研发过程和论文证据链的可追溯性。

Change: 保留各轮原始结论，按迭代号将 `NIGHT_LOG.md` 重排为 0–20 连续顺序，清除已完成轮次的 `IN PROGRESS` 残留，并校正第15–19轮的验证结果摘要。

Tests: 日志结构断言通过（21轮，0–20连续唯一）；相关 RAG 证据校验 pytest 36 passed；`py_compile` 和 `git diff --check` 通过。

Result: PASS。仅修复夜间研发记录，未修改业务运行时、数据库、认证、生产配置或真实数据。

Paper Value: 保证优化迭代、验证结果和阻塞结论按时间顺序可复核，避免论文研发过程证据因日志错序而失真。

Reviewer: PASS。日志段落唯一、顺序连续，已完成轮次不再标记为进行中。

Gatekeeper: PASS。未触碰既有业务改动、真实数据或版本历史。

Next: 正式确认性实验仍需 Owner 冻结多项目题集、金标准、运行时绑定和独立人工盲评；代码侧本轮停止。

## Iteration 21 — 终态证据归档门禁

Time: 2026-08-12 Asia/Shanghai

Task: 强化证据包运行状态与论文归档资格之间的约束。

Reason: 证据检查器此前允许 `queued`、`running` 或计数语义不匹配的状态进入归档结果，可能把尚未完成的运行误写入论文分母或把运行级失败与案例级失败混淆。

Change: 增加实验状态白名单和非终态拒绝；要求 `completed` 零失败、零未执行且无错误摘要，要求 `completed_with_errors` 至少有一个失败案例、零未执行且存在错误摘要；保留 `failed` 的运行级 `fatal_error` 语义和 `interrupted` 的不完整归档语义。同步更新证据包协议文档。

Tests: 先新增未知状态、非终态、完成态计数和带错误完成态门禁测试，RED 阶段 4 failed；实现后相关 pytest 33 passed；全量相关 pytest 40 passed，`py_compile` 和 `git diff --check` 通过，日志结构断言待补记。

Result: PASS。仅修改纯 JSON 验证器、测试、协议文档和夜间记录；未修改 Rust/Next 业务运行时、数据库、认证或生产配置。

Paper Value: 防止排队中、运行中和计数不完整的实验被误当作论文最终结果，明确案例级失败与运行级故障的分母边界。

Reviewer: PASS。全量相关测试、语法检查、差异空白检查和日志结构断言均通过。

Gatekeeper: PASS。未触碰既有业务改动、真实数据或版本历史。

Next: 完成 Iteration 21 的验证后，再决定是否进入下一项低风险论文证据审计；Owner 仍需冻结正式确认性实验材料。

## Iteration 22 — 历史运行材料兼容性审计

Time: 2026-08-12 Asia/Shanghai

Task: 审计仓库现有 RAG 历史运行 JSON 是否可直接作为 `rag-evidence-package-v1` 论文证据。

Reason: 旧版 `rag-experiment-2/3/4-run.json` 使用顶层运行记录模型，不含 v1 的逐案例来源、执行计划哈希和完整配置结构；若不显式区分，可能把历史开发材料误引用为新协议证据。

Change: 协议文档明确旧格式只能作为历史材料，不能通过改名、补状态或手工拼接冒充 v1；论文确认性分析必须使用通过验证器的 v1 证据包，并另外核对外部冻结题集、金标准和版本清单。未改写任何历史运行 JSON。

Tests: 三份历史运行文件均被 CLI 检查器按预期拒绝（缺少 `rag-evidence-package-v1` 顶层结构）；Iteration 21 全量相关 pytest 40 passed；`py_compile`、`git diff --check` 和日志结构断言通过。

Result: PASS。仅更新论文证据协议与夜间记录；未修改业务运行时、数据库、认证、生产配置或历史实验材料。

Paper Value: 明确历史开发运行与可引用 v1 证据的边界，防止论文引用发生证据格式错配或事后拼接。

Reviewer: PASS。旧材料保留、不可冒充，且通过失败关闭验证。

Gatekeeper: PASS。没有生成虚假结果，没有覆盖既有证据文件。

Next: Owner 仍需提供外部冻结多项目题集、金标准、运行时绑定和独立双人盲评；在此之前不宣称确认性效果结论。

## Iteration 23 — 论文证据索引与统计归档清单

Time: 2026-08-12 Asia/Shanghai

Task: 将现有 RAG 实验材料整理为论文可引用的主张—证据矩阵，并明确确认性统计归档要求。

Reason: 仓库已有历史批次指标、失败分析、证据包协议和成熟度门禁，但缺少集中索引来约束哪些数字可以引用、哪些只能作为开发诊断，以及确认性结果写入论文前必须具备哪些绑定材料。

Change: 新增 `docs/experiments/rag-paper-evidence-index-v1.md`，区分历史开发批次、协议/验证工具和确认性证据；映射论文主张到允许引用材料与禁止表述；列出数据/题集绑定、五方法参数、引用审计、失败分母、双人盲评、统计分析和版本哈希的最低归档清单；不生成新实验数字，不改写历史材料。

Tests: 证据索引引用文件存在性检查通过；相关 RAG 归档 pytest 40 passed；`py_compile` 和 `git diff --check` 通过；日志结构断言待补记。

Result: PASS。仅新增论文证据索引并更新夜间记录；未修改业务运行时、数据库、认证、生产配置或历史实验材料。

Paper Value: 降低历史开发结果被误写成确认性结论的风险，使论文主张、原始证据、统计口径和阻塞条件可逐项复核。

Reviewer: PASS。索引明确自动指标、人工评价和确认性结果的边界，未伪造人工或外部冻结证据。

Gatekeeper: PASS。未覆盖用户既有修改，未新增界面或炫技型 AI 功能。

Next: Owner 仍需提供外部冻结多项目题集、金标准、运行时绑定和独立双人盲评；可继续做离线证据校验，但不应据此宣称确认性效果。

## Iteration 24 — 历史 CSV 与评价表离线对账

Time: 2026-08-12 Asia/Shanghai

Task: 将历史 RAG CSV 的案例分母、日志来源、证据 JSON、回退和人工评价状态做可重复离线审计。

Reason: 既有运行时绑定检查器不验证 CSV 与规则化评价表的逐案例一致性；论文材料需要独立确认模式配对、日志唯一性、失败/回退记录和人工字段是否被填充。

Change: 新增标准库脚本 `scripts/audit_rag_csv_consistency.py` 及测试；检查 CSV 必需字段、两模式问题配对、唯一正整数 `query_log_id`、状态/数值字段、来源与图谱 JSON、回退、错误行、评价表键集合和人工评价字段。更新论文证据索引，增加归档前命令。

Tests: 先修正测试夹具的人工字段填充范围；最终相关 pytest 43 passed；真实 `rag-experiment-4.csv` 与评价表对账通过：40 行、两模式各 20 行、40 个唯一日志 ID、来源/图谱 JSON 40/40 可解析、图谱回退 1 次、错误行 0、人工评价字段填充 0；`py_compile` 和 `git diff --check` 通过。

Result: PASS。未修改历史 CSV、评价表或业务运行时，仅新增离线审计工具、测试、证据索引和夜间记录。

Paper Value: 为论文中的历史探索性指标提供可复核的原始表—评价表对账证据，并明确人工评价尚未产生，避免把空白人工字段误报为人工结果。

Reviewer: PASS。审计失败关闭覆盖重复日志 ID、配对漂移和人工字段状态。

Gatekeeper: PASS。未生成新效果数字，未改变历史结果。

Next: Owner 仍需提供外部冻结多项目题集、金标准、运行时绑定和独立双人盲评；本工具可用于未来确认性批次归档前对账。

## Iteration 25 — 历史引用口径严格审计

Time: 2026-08-12 Asia/Shanghai

Task: 审计历史 RAG CSV 的引用标记语法和历史指标口径，防止论文把非法范围标记计为有效引用。

Reason: `rag-experiment-4-objective-analysis.md` 将包含 `"[G"` 子串的案例计为有证据标记；真实答案中存在 `[G1-G10]`，而 Rust 生产引用审计按失败关闭规则将其判为非法。该差异会把格式错误误报为引用覆盖，必须在证据链中显式记录。

Change: 强化 `scripts/audit_rag_csv_consistency.py`：检查答案字段、来源/图谱数量一致性、严格 `[S数字]`/`[G数字]` 语法和数组范围；拒绝 `[S1-S6]`、`[G1-G10]` 等范围标记；同时输出严格有效标记率与历史宽松子串标记率。更新证据索引和 v1 协议，保留历史 CSV 与历史分析报告不改写。

Tests: 引用边界及既有 RAG 归档测试 46 passed；`py_compile` 和 `git diff --check` 通过。真实 `rag-experiment-4.csv` 结构字段、40 个日志 ID、来源/图谱 JSON 和评价表键集合均一致，但严格审计按预期失败关闭，发现 4 个非法标记（第 8 题普通模式 `[S2-S6]`，第 14 题图谱模式 `[G1-G10]`，第 18 题图谱模式 `[S1-S6]` 与 `[G1-G10]`）；严格图谱标记率为 15/20（75.0%），历史宽松口径为 17/20（85.0%），人工评价字段仍为 0。

Result: PASS。工具和证据边界强化完成；历史批次的严格引用审计结果为 FAIL CLOSED，未把该批次修饰为通过，也未改写历史结果。

Paper Value: 为论文提供可复现的引用语法门禁、失败案例和指标口径漂移证据，阻止将 85.0% 宽松子串比例误写成有效引用率；同时证明历史批次的结构对账结果与引用质量结论是两个独立维度。

Reviewer: PASS。生产端与离线审计器均采用失败关闭语义，测试覆盖越界和范围语法；未伪造人工评价或确认性结果。

Gatekeeper: PASS。仅修改标准库离线审计器、测试、协议、论文证据索引和夜间记录；未触碰既有 Rust/Next 业务改动、数据库、认证、生产配置或历史实验数据。

Next: Owner 仍需提供外部冻结多项目题集、金标准、运行时绑定和独立双人盲评；正式确认性批次必须在归档前通过严格引用审计和 v1 证据包检查。

## Iteration 26 — 实验 5 内部五方法证据包交叉审计

Time: 2026-08-12 Asia/Shanghai

Task: 将实验 5 内部五方法报告、原始 CSV、题集、运行参数和冻结清单做可复现交叉审计，区分结构完整、引用可信和论文可用三个层级。

Reason: 该批次已有 180 条记录和自动统计，但现有内部报告把引用审计记录为全通过，尚未核对范围引用语法、冻结源码哈希、版本绑定和人工评价状态；若只看行数和自动覆盖率，容易把内部开发诊断误写成确认性证据。

Change: 新增 `scripts/audit_rag_five_mode_bundle.py`、测试和审计产物 `docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json`。审计报告—CSV—题集哈希、题目/方法/重复次数、运行参数快照、180 行唯一案例、唯一正整数 `query_log_id`、来源/图谱 JSON、严格引用语法及论文门禁；记录源码冻结清单复核失败、旧报告引用审计遗漏和确认性材料阻塞，不修改原始实验 CSV、报告或历史冻结清单。

Tests: 新增审计器及既有 RAG 归档测试共 50 passed；`py_compile` 和 `git diff --check` 通过。真实批次结构检查通过：计划 180 行、180 个唯一案例键、180 个完成案例、180 个唯一正日志 ID、来源/图谱 JSON 180/180 可解析。严格引用审计失败关闭：第 6、50、151 行出现 `[S1-S12]`，第 69 行出现 `[S6-S12]`；旧报告将这些范围标记漏报为非法引用，审计不一致。内部冻结清单复核失败（源码文件缺失/哈希漂移），且 `app_revision=unversioned`、外部冻结题集/金标准缺失、题集仅 12 题单项目、人工字段 0、无 v1 证据包。

Result: PASS。交叉审计工具和证据分层完成；实验 5 内部批次结果为 `consistency_passed=false`、`paper_ready=false`，没有把自动覆盖数字升级为论文确认性结论。

Paper Value: 形成“结构可复核 ≠ 引用有效 ≠ 论文可用”的直接证据链，保留 4 个失败案例、冻结漂移和人工评价缺口，防止引用审计遗漏与自动 fact coverage 被误称为事实准确率或跨项目效果。

Reviewer: PASS。测试覆盖严格引用范围、哈希/清单失败和论文门禁；审计输出明确报告内部材料的可用边界。

Gatekeeper: PASS。仅新增离线审计器、测试、JSON 审计记录、证据索引和夜间日志；未运行新模型、未修改真实实验数据、未触碰 Rust/Next 业务、数据库、认证或生产配置。

Next: Owner 仍需提供多项目外部冻结题集、金标准、版本化运行时、独立双人盲评和 v1 证据包；在这些材料齐备并通过严格审计前，实验 5 只能作为内部方法学诊断。

## Iteration 27 — 实验 5 统计汇总可重算审计

Time: 2026-08-12 Asia/Shanghai

Task: 从实验 5 原始 CSV 逐案例重算模式汇总与相对 `project_rag` 的配对比较，并与内部报告逐字段核对。

Reason: 行完整性只能证明记录没有明显缺失，不能证明报告中的覆盖率、精确匹配、时延和配对统计确实由同一批原始案例产生；论文证据链需要可重算的中间层和明确的统计边界。

Change: 强化 `scripts/audit_rag_five_mode_bundle.py`，重算 5 个模式的完成/失败、fact coverage、closed-set 指标、来源/图谱计数、时延、Token 汇总，以及 4 组配对覆盖率、精确匹配和精确符号检验字段；审计产物新增重算汇总、配对比较和严格引用率字段。测试增加统计重算回归断言；原始 CSV、报告和冻结清单不改写。

Tests: 实验 5 审计器测试 5 passed；实际审计确认 180/180 行、180 个唯一案例键、180 个唯一正 `query_log_id`、来源/图谱 JSON 180/180 可解析；模式汇总重算核对 PASS，配对比较重算核对 PASS。严格引用审计仍 FAIL CLOSED，发现 4 个非法范围标记；冻结清单复核仍失败。

Result: PASS。统计结果现在具备原始 CSV → 逐案例判定 → 汇总/配对比较 → 报告字段的可复核链路；整体 `consistency_passed=false`、`paper_ready=false` 保持不变。

Paper Value: 论文可将该批次的自动数字作为内部方法学诊断，并明确说明统计数字可重算但不等于事实准确率、有效引用率或确认性效果；4 个非法引用、冻结漂移、未绑定版本和人工盲评缺失仍作为失败与限制报告。

Reviewer: PASS。新增回归断言覆盖 5 个模式和 4 组配对比较；补入 coverage sign test 字段，避免只核对部分配对指标。

Gatekeeper: PASS。仅修改离线审计器、测试、证据索引、审计 JSON 和夜间日志；未运行新模型、未修改原始实验数据、未触碰 Rust/Next 业务或生产配置。

Next: Owner 仍需提供多项目外部冻结题集、金标准、版本化运行时、独立双人盲评和 v1 证据包；材料齐备前继续只做离线证据校验和论文边界审计。

## Iteration 28 — 实验 5 统计漂移回归门禁

Time: 2026-08-12 Asia/Shanghai

Task: 验证实验 5 审计器能捕获内部报告中的模式汇总或配对统计字段漂移，而不仅是在当前文件上得到一次通过结果。

Reason: 论文证据链需要证明汇总数字确实绑定原始 CSV；若只审计当前报告，无法排除报告字段被手工修改后仍被接受。

Change: 在 `scripts/test_audit_rag_five_mode_bundle.py` 增加临时报告副本测试：分别篡改 `hit_facts` 和 `mean_response_time_delta_ms`，要求模式汇总重算门禁和配对比较重算门禁失败并定位具体字段。测试只写入临时目录，不修改真实实验报告。

Tests: 实验 5 审计器测试 5 passed；审计脚本 `py_compile` 和 `git diff --check` 通过。篡改回归均按预期捕获。

Result: PASS。报告—原始 CSV 的统计绑定具备正向核对和负向漂移检测；当前批次仍因 4 个非法引用范围标记、冻结清单漂移、版本未绑定、单项目题集和人工盲评缺失而保持 `paper_ready=false`。

Paper Value: 可在论文方法/材料部分说明统计汇总不仅可重算，而且对报告字段漂移有失败关闭回归门禁；该证据仍不替代外部冻结金标准、独立人工评价或确认性版本归档。

Reviewer: PASS。测试不接触真实结果文件，覆盖模式汇总和配对比较两条统计证据链。

Gatekeeper: PASS。仅修改离线测试、证据索引和夜间日志；未运行新模型、未修改原始数据、Rust/Next 业务或生产配置。

Next: Owner 仍需提供多项目外部冻结题集、金标准、版本化运行时、独立双人盲评和 v1 证据包；材料齐备前继续做离线证据校验与论文边界审计。

## Iteration 29 — 论文描述性结果材料自动生成

Time: 2026-08-12 Asia/Shanghai

Task: 将实验 5 的可重算内部统计生成可直接引用的论文描述性材料，并强制保留非确认性证据边界。

Reason: 统计审计已经证明报告汇总可从原始 CSV 重算，但手工摘录数字仍可能遗漏单项目范围、重复生成统计限制、严格引用失败或 `paper_ready=false` 状态；论文材料需要由证据产物驱动的可复现生成过程。

Change: 新增 `scripts/render_rag_five_mode_paper_material.py` 及测试，读取实验 5 审计 JSON 和统计验证 JSON，生成 `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`。材料包含研究分母、五模式指标、相对 `project_rag` 的配对描述、引用审计、冻结/版本/人工评审门禁、统计警告、允许/禁止论文表述和复现命令；输入结构缺失时失败关闭。

Tests: 新增材料生成器测试 2 passed；生成命令成功产出 Markdown；随后实验5审计、历史 CSV 对账、证据包验证、冻结校验等定向测试继续验证。生成材料固定标记 `paper_ready=false`，并列出 4 个非法范围引用标记及统计验证警告。过程中发现并修正两次临时字符串断言误配，未改变生成逻辑。

Result: PASS。论文材料由审计产物自动取数，避免手工复制结果；材料可用于内部方法学诊断和限制部分，不升级为确认性效果证据。

Paper Value: 建立审计 JSON → 描述性 Markdown 的可重复链路，确保论文引用的数字、分母、p 值解释和失败边界同步更新；明确 alias-based fact coverage 不等于事实准确率，重复生成配对检验不作确认性推断。

Reviewer: PASS。测试覆盖正常生成和不完整审计拒绝；材料生成器不修改原始 CSV、实验报告或运行时。

Gatekeeper: PASS。仅新增离线材料生成器、测试、论文描述性材料、证据索引和夜间日志；未触碰 Rust/Next 业务、数据库、认证或生产配置。

Next: Owner 仍需提供多项目外部冻结题集、金标准、版本化运行时、独立双人盲评和 v1 证据包；确认性材料齐备前，论文只能引用自动生成的内部描述性结果并保留全部限制。

## Iteration 30 — 描述性材料统计不确定性门禁

Time: 2026-08-12 Asia/Shanghai

Task: 将实验 5 验证记录中的统计不确定性、重复稳定性和完整谬误扫描结果强制纳入论文描述性材料。

Reason: 仅展示模式点估计和配对 p 值会遗漏重复生成的伪重复风险、post-run bootstrap 的时序限制、多重比较问题和题目级稳定性；论文需要同步呈现这些限制。

Change: 扩展 `scripts/render_rag_five_mode_paper_material.py`：读取 `overall_confidence=CAUTION`、`fallacy_scan.coverage=11/11`、题目聚类 bootstrap 95% 区间和 repeat stability，生成题目级不确定性表、重复稳定性表及明确的“非确认性”说明；缺少警告或 11/11 扫描时失败关闭。测试新增不完整 validation 拒绝用例。

Tests: 材料生成器测试 3 passed；生成 Markdown 成功，包含 `CAUTION`、`11/11`、Bootstrap 区间、稳定性和多重比较未校正警告。此前实验5及相关证据校验 54 项测试基线保持通过。

Result: PASS。论文材料现在同时呈现点估计、题目级区间、重复稳定性和统计谬误扫描边界；`paper_ready=false` 不变。

Paper Value: 降低选择性报告风险，允许论文如实引用“内部描述性差异及其不确定性”，同时禁止把 post-run 区间、重复级 p 值或 alias-based coverage 升级为确认性事实准确率或泛化效果。

Reviewer: PASS。生成器对验证记录的置信级别、警告和 11 项扫描设置失败关闭门禁；不修改原始实验数据和验证记录。

Gatekeeper: PASS。仅修改离线材料生成器、测试、描述性 Markdown、证据索引和夜间日志；未触碰 Rust/Next 业务、数据库、认证或生产配置。

Next: Owner 仍需提供多项目外部冻结题集、金标准、版本化运行时、独立双人盲评和 v1 证据包；材料齐备前继续保留 CAUTION 和全部统计限制。

## Iteration 31 — 描述性材料输入指纹绑定

Time: 2026-08-12 Asia/Shanghai

Task: 为实验 5 自动生成的论文描述性材料绑定原始证据输入的具体文件版本。

Reason: 即使材料由审计产物自动取数，若不记录原始 CSV、报告、题集、配置和冻结清单的文件指纹，后续仍难以证明论文中的数字对应哪一版输入。

Change: 扩展 `scripts/render_rag_five_mode_paper_material.py`，对审计 JSON、统计验证 JSON、实验报告、原始 CSV、运行配置、题集和冻结清单计算 SHA-256，并在 Markdown 中输出路径—指纹表；任一输入不存在时失败关闭。测试增加完整指纹和缺失输入拒绝用例。

Tests: 材料生成器测试 4 passed；生成 Markdown 成功并包含 7 个输入的 64 位 SHA-256 指纹。此前实验5及相关证据校验 55 项测试基线保持通过。

Result: PASS。论文描述性材料形成“原始文件 → 审计 JSON → 带指纹 Markdown”的可追溯链路；`paper_ready=false` 及所有失败门禁保持不变。

Paper Value: 为论文补充可引用的材料版本绑定，支持复核者按 SHA-256 定位数据/题集/配置/报告版本；该绑定仍不等价于外部冻结、代码 revision 或独立人工金标准。

Reviewer: PASS。指纹测试不修改真实实验输入，缺失输入会阻止生成，避免产生看似完整但证据不全的论文材料。

Gatekeeper: PASS。仅修改离线材料生成器、测试、描述性 Markdown、证据索引和夜间日志；未触碰 Rust/Next 业务、数据库、认证或生产配置。

Next: Owner 仍需提供多项目外部冻结题集、金标准、版本化运行时、独立双人盲评和 v1 证据包；确认性材料齐备前继续保留输入指纹、CAUTION 和全部统计限制。

## Iteration 32 — 论文材料参数与分析脚本绑定

Time: 2026-08-12 Asia/Shanghai

Task: 将实验 5 的运行参数、版本状态和分析脚本版本纳入自动生成的论文描述性材料。

Reason: 输入文件指纹解决了数据版本追溯，但论文复核还需要知道方法、重复、随机种子、模型/检索参数和分析逻辑的具体版本；同时必须显式暴露 `app_revision=unversioned` 与 dirty 工作树限制。

Change: 扩展材料生成器，读取运行配置和实验报告快照，输出五方法、prompt 版本、3 次重复、随机化顺序、随机种子、生成/检索参数、语料/执行计划哈希、应用 revision、当前 Git 状态和 Python 平台；将审计器、材料生成器和统计验证器自身加入 SHA-256 指纹。缺失协议字段时失败关闭，并增加相应测试。

Tests: 材料生成器测试 5 passed；生成 Markdown 成功，包含 10 项输入/分析指纹和参数快照。实验 5 及相关证据校验 56 项测试基线保持通过。

Result: PASS。论文材料现在形成“数据/题集/配置/报告 + 分析脚本 + 参数快照 → 审计 → 描述性结果”的可追溯链路；`paper_ready=false` 保持不变。

Paper Value: 支持论文方法部分准确报告实验设置，支持复核者按 SHA-256 复现材料版本；明确 unversioned/dirty 状态，避免把内部开发批次误写成版本冻结的确认性实验。

Reviewer: PASS。测试覆盖参数字段缺失和 10 项指纹生成；临时篡改仅作用于测试文件，不修改真实实验输入。

Gatekeeper: PASS。仅修改离线材料生成器、测试、描述性 Markdown、证据索引和夜间日志；未触碰 Rust/Next 业务、数据库、认证或生产配置。

Next: Owner 仍需提供多项目外部冻结题集、金标准、可绑定的应用 revision、独立双人盲评和 v1 证据包；确认性材料齐备前继续保留所有指纹、CAUTION 和失败门禁。

## Iteration 33 — 严格引用失败案例级归档

Time: 2026-08-12 Asia/Shanghai

Task: 将实验 5 的非法引用范围标记从行号计数提升为可回放、可引用的失败案例记录。

Reason: 论文需要展示失败机制和审计证据，而不仅是“有 4 个错误”的汇总；失败案例必须绑定题目、方法、重复、日志 ID 和证据数组规模。

Change: 扩展 `scripts/audit_rag_five_mode_bundle.py`，为每个非法引用记录题目索引/ID、方法、重复编号、`query_log_id`、非法标记、source/graph 数量；扩展描述性材料生成器，新增“可引用失败案例”表。测试覆盖字段完整性，并按先更新审计产物再生成材料的顺序验证。

Tests: 实验5审计器与材料生成器相关测试 10 passed；实际审计确认 4 条失败记录：H04/bm25_rag 重复 1、3、2（`query_log_id` 128、172、273）及 H03/bm25_rag 重复 2（`query_log_id` 191），非法标记为 `[S1-S12]` 或 `[S6-S12]`。全套相关测试随后复核。

Result: PASS。论文材料现在能从严格引用失败直接回放到具体案例；整体 `consistency_passed=false`、`paper_ready=false` 保持不变。

Paper Value: 支持论文报告“范围语法被旧审计漏报”的具体失败机制，并保留失败分母和日志绑定；避免把非法范围标记算作有效引用覆盖。

Reviewer: PASS。失败案例来自原始 CSV 与严格语法解析，未手工改写回答或引用标记。

Gatekeeper: PASS。仅修改离线审计器、测试、描述性 Markdown、证据索引和夜间日志；未触碰 Rust/Next 业务、数据库、认证或生产配置。

Next: Owner 仍需提供多项目外部冻结题集、金标准、可绑定的应用 revision、独立双人盲评和 v1 证据包；确认性材料齐备前继续保留案例级失败表、输入指纹和 CAUTION 限制。

## Iteration 34 — 方法分层严格引用审计

Time: 2026-08-12 Asia/Shanghai

Task: 将实验 5 的严格引用审计从总体覆盖比例扩展为按方法分层的来源、证据和图谱标记统计。

Reason: 总体引用比例掩盖方法间格式差异，也无法直接说明 4 个非法范围标记集中在哪一方法；论文需要同时报告合法标记分母和失败分层。

Change: 扩展审计器的 `by_mode` 输出，记录每个方法的完成答案、有来源/任一证据/图谱标记和非法标记行数；描述性材料新增分层表。严格数字语法仍只接受 `[S数字]`/`[G数字]`，范围标记仍失败关闭。

Tests: 实验5审计器与材料生成器相关测试 10 passed；实际分层审计确认 `bm25_rag` 为 32/36 来源标记、32/36 任一证据标记、4 行非法范围；`project_rag` 来源标记 36/36；`kg_enhanced_rag` 来源标记 22/36、图谱标记 36/36。

Result: PASS。论文描述性材料现在能区分方法级引用呈现和格式失败；整体 `consistency_passed=false`、`paper_ready=false` 不变。

Paper Value: 支持论文报告引用格式失败的分层证据，避免以总体比例掩盖 `bm25_rag` 的范围语法问题；明确这些数字不能替代事实准确率、人工可追溯率或方法优越性结论。

Reviewer: PASS。分层统计来自同一严格解析器和完成案例分母，未使用宽松子串规则。

Gatekeeper: PASS。仅修改离线审计器、测试、描述性 Markdown、证据索引和夜间日志；未触碰 Rust/Next 业务、数据库、认证或生产配置。

Next: Owner 仍需提供多项目外部冻结题集、金标准、可绑定的应用 revision、独立双人盲评和 v1 证据包；确认性材料齐备前继续保留分层引用审计、案例级失败表和 CAUTION 限制。

## Iteration 35 — CSV 题目—重复—方法绑定门禁

Time: 2026-08-12 Asia/Shanghai

Task: 将实验 5 原始 CSV 与冻结题集、预注册重复设计和五方法集合的绑定检查从隐式索引假设提升为显式失败关闭门禁。

Reason: 既有审计已核对题集哈希和报告选题 ID，但篡改 CSV 的 `question_index` 可能触发越界异常，重复编号或方法值异常也可能在统计前缺少清晰的绑定失败记录；论文证据链需要证明每一行都属于计划中的问题—重复—方法域。

Change: 扩展 `scripts/audit_rag_five_mode_bundle.py`，逐行安全解析并检查题目编号、重复编号、方法值和案例键域；对非整数、越界、未知方法、非法 JSON/计数值生成定位检查，不再因恶意或损坏行直接中断审计。扩展 `scripts/test_audit_rag_five_mode_bundle.py`，加入篡改题目编号、重复编号和方法值的失败关闭回归测试；同步更新论文证据索引和自动生成的描述性材料，显式呈现四项绑定门禁及其结果。

Tests: 定向审计测试 7 passed；重新生成实验 5 审计（真实批次仍为 `consistency_passed=false`、`paper_ready=false`，失败原因仍为应用 revision、外部冻结输入、多项目题集、独立人工评审和 v1 证据包缺失）；重新生成论文描述性材料；全套相关证据测试 59 passed。真实 CSV 的 180 行题目/重复/方法绑定检查通过，4 个严格引用范围失败和原有论文门禁保持不变。

Result: PASS。损坏或篡改的 CSV 行现在会被可复核地拒绝，且不会把“解析器崩溃”误当成数据绑定通过；真实批次统计和材料生成链路保持可重算。

Paper Value: 论文可以引用“原始行—冻结题集—预注册运行域”的结构绑定审计方法，并报告篡改回归会失败关闭；这只支持数据完整性与可复现性，不等价于外部题集有效性、人工金标准或确认性效果证据。

Reviewer: PASS。回归测试只在临时 CSV 副本上注入越界题目、非法重复和未知方法，真实原始数据未修改；统计重算、引用审计、冻结和材料生成测试继续通过。

Gatekeeper: PASS。仅修改离线审计器、审计测试、论文描述性材料、证据索引和夜间日志；未触碰 Rust/Next 业务、数据库、认证或生产配置。

Next: Owner 仍需提供多项目外部冻结题集、金标准、可绑定的应用 revision、独立双人盲评和 v1 证据包；确认性材料齐备前继续保留题目—重复—方法绑定、分层引用审计、案例级失败表、输入指纹和 CAUTION 限制。

## Iteration 36 — 证据包端点契约与生产题集约束对齐

Time: 2026-08-13 Asia/Shanghai

Task: 沿论文可信支撑主线复核证据包 JSON 端点的 RED 测试状态，并把运行时导出、归档检查器和实验题集约束对齐。

Reason: 端点实现、OpenAPI 路径和前端下载函数已存在，但此前单测没有覆盖随机化协议字段提升、已落库失败与摘要失败去重，也没有阻止生产实验创建重复题目；这会造成实验可以运行而 v1 证据包无法通过唯一题集门禁的契约漂移。

Change: Rust 证据包显式导出 `repetitions` 与 `randomize_order`；新增协议字段一致性、失败案例去重和真实路由 JSON 导出断言；实验创建题目在 trim 后做唯一性校验；检查器核对四个协议字段；同步协议和论文证据索引说明。未新增界面功能，OpenAPI 与前端类型仅做生成幂等确认。

Tests: `backend/.venv/bin/py.test -q scripts/test_*.py`（330 passed）；`cargo test --locked --lib -- --test-threads=1`（242 passed）；隔离 PostgreSQL `./scripts/run-rust-db-tests.sh`（242 库测试 + 2 二进制测试通过）；`cargo clippy --locked --all-targets --all-features -- -D warnings`、`cargo fmt --all --check`、前端 `npm run lint`、`npm run typecheck`、`npm run build`、OpenAPI `npm run generate:api` 幂等检查均通过。

Result: PASS。证据端点从“已实现”推进为“有运行时回归和归档契约约束”；现有实验 5 的 `paper_ready=false`、外部冻结输入/版本 revision/独立人工评审/v1 证据包缺失等论文门禁不变。

Paper Value: 论文可以引用“运行计划—逐案例日志—失败分母—引用审计”的可回放工程证据，并明确其边界；重复题目拒绝和失败去重只证明证据链完整性，不被表述为模型效果或确认性准确率。

Reviewer: PASS。测试覆盖端点输出字段、唯一日志绑定、未落库失败和重复题集拒绝；真实数据库测试使用隔离 PostgreSQL，未修改论文原始实验输入。

Gatekeeper: PASS。改动集中于 Rust RAG 实验导出/校验契约、协议说明和测试；未修改认证边界、生产配置或历史实验数字。

Next: 在 Owner 提供外部冻结题集、金标准、可绑定 revision 和独立双人盲评后，再导出真实 v1 包并运行归档检查；此前不把内部自动结果写成确认性结论。

## Iteration 37 — 题集与活动索引语料哈希绑定

Time: 2026-08-13 Asia/Shanghai

Task: 沿论文可信支撑主线，把生产实验的输入绑定从执行计划扩展到题集内容与实际检索语料快照。

Reason: 证据包此前能重建执行计划和失败分母，但不能从生产运行记录确认题集是否被替换，也不能确认 RAG 案例对应哪个索引语料版本；这会留下“运行可回放、输入不可绑定”的论文复核缺口。

Change: Rust 实验创建入口在题目规范化后记录 `questions_sha256`；对数据集依赖模式，按生产检索相同的已批准、已同步、当前 `rag_index_version` 文档块筛选，按 `(file_id, chunk_index, content_hash)` 稳定排序并记录 `corpus_snapshot_hash` 与索引版本；纯 LLM/结构化查询不声称使用文档语料。证据包提升这些字段；离线检查器复算题集哈希、核对配置提升字段，并要求数据集模式提供 64 位小写语料快照哈希和索引版本。新增 Rust 哈希稳定性/输入敏感性测试、真实路由端点重算题集与语料哈希断言、Python 缺失/漂移/畸形模式回归；协议和论文证据索引补充哈希字节规则与“创建时点绑定、不替代外部冻结清单”的边界。

Tests: `cargo fmt --all --check` 通过；Rust `cargo test --locked --lib -- --test-threads=1` 为 243 passed；隔离 PostgreSQL `./scripts/run-rust-db-tests.sh` 为 243 库测试 + 2 二进制测试通过；`cargo clippy --locked --all-targets --all-features -- -D warnings` 通过；`backend/.venv/bin/py.test -q scripts/test_*.py` 为 332 passed；`git diff --check` 通过。

Result: PASS。新的 v1 证据包可将运行绑定到题集、活动索引版本和语料块内容哈希；恶意/漂移输入在离线归档检查中失败关闭。现有实验 5 的 `paper_ready=false`、外部冻结输入、应用 revision、独立人工评审和确认性 v1 包缺失等门禁保持不变。

Paper Value: 论文方法部分可以引用“题集—执行计划—活动索引语料—逐案例日志”的绑定链路，并报告可复算哈希规则；这支持可重复性与数据完整性，不等价于语料外部有效性、人工金标准、模型准确率或方法优越性。

Reviewer: PASS。哈希由生产 Rust 代码生成，离线 Python 检查器独立复算题集哈希；真实隔离数据库路由测试重算活动文档块集合，未修改历史实验输入。快照是运行创建时点记录，归档仍需与外部文件清单交叉核对。

Gatekeeper: PASS。改动集中于 Rust RAG 实验配置/证据包、证据检查器、协议说明、论文索引和测试；未新增界面或炫技型 AI 功能，未改变认证与论文结果门禁。

Next: 在 Owner 提供外部冻结题集、金标准、可绑定 revision 和独立双人盲评后，导出真实 v1 包并将运行时哈希与外部冻结清单交叉核对；确认性材料齐备前继续禁止把内部自动结果写成论文确认性结论。

## Iteration 38 — 执行时输入漂移失败关闭

Time: 2026-08-13 Asia/Shanghai

Task: 沿论文可信支撑主线，补齐题集/语料/索引/模型绑定从“创建时记录”到“执行时复核”的时间一致性门禁。

Reason: 仅在 `queued` run 创建时记录 `questions_sha256`、`corpus_snapshot_hash` 和 `rag_index_version`，无法阻止排队期间数据库语料、索引版本或模型配置发生变化后继续生成混合条件结果。论文需要区分“运行失败关闭”与“完成但输入条件漂移”，后者不能进入确认性分母。

Change: Rust 执行器在领取 run 后、每个后续案例开始前，复核题集哈希、活动语料快照哈希、索引版本、嵌入模型和生成模型；任一缺失或漂移都返回 `CONFLICT`，由现有 worker 失败处理写入 `status=failed` 和 `summary.fatal_error.error`。零案例的历史调度夹具保留兼容路径；正式实验均为正案例数。新增纯绑定校验单测和真实隔离数据库队列回归：先插入绑定到当前语料的 queued run，再修改文档块 `content_hash`，确认未生成案例即失败关闭。同步证据包协议和论文证据索引，明确运行时复核的覆盖范围与仍需外部冻结清单的边界。

Tests: TDD RED 阶段新增测试在校验函数缺失时按预期编译失败；实现后定向绑定测试通过，真实 `test_rag_init_sync_query_and_log` 通过并断言漂移 run 为 `failed` 且 fatal error 含 `input binding drift`。完整 `cargo test --locked --lib -- --test-threads=1` 为 244 passed；`./scripts/run-rust-db-tests.sh` 为 244 库测试 + 2 二进制测试通过；`cargo clippy --locked --all-targets --all-features -- -D warnings`、`cargo fmt --all --check`、`git diff --check` 和 `backend/.venv/bin/py.test -q scripts/test_*.py`（332 passed）均通过。

Result: PASS。执行器不再静默接受排队后的题集/活动语料/版本/模型漂移；运行级失败保留在数据库摘要中，归档检查器可据此拒绝把它当作 completed 证据。现有实验 5 的 `paper_ready=false`、外部冻结输入、应用 revision、独立人工评审和确认性 v1 包缺失等门禁不变。

Paper Value: 论文方法部分可以引用“创建时指纹 + 执行前/逐案例前复核 + 运行级失败关闭”的可复现输入一致性设计，并报告语料哈希篡改回归；这支持证据链完整性，不等价于语料质量、人工金标准、模型准确率或方法优越性。

Reviewer: PASS。绑定校验采用纯函数单测覆盖题集、语料和模型漂移；真实 PostgreSQL 回归覆盖队列领取、语料变更、worker 失败摘要和无回答生成路径；未修改历史实验 CSV 或确认性门禁结论。

Gatekeeper: PASS。改动集中于 Rust RAG 实验执行器、协议说明、论文证据索引和测试；未新增界面或炫技型 AI 功能，未改变认证、数据库 schema 或外部论文结果。

Next: 完成全量 Rust/数据库/证据脚本回归后，若全部通过，继续由 Owner 提供外部冻结题集、金标准、可绑定 revision 和独立双人盲评；确认性材料齐备前仍禁止把内部自动结果写成论文确认性结论。

## Iteration 39 — 运行级与案例级失败机器可读分层

Time: 2026-08-13 Asia/Shanghai

Task: 沿论文可信支撑主线，把证据包中的失败范围和失败类别从错误文本推断升级为显式、可校验字段。

Reason: 执行时输入漂移已经会以 `status=failed` 关闭运行，但旧证据契约只有 `fatal_error.error`；单案例 `query_error` 与运行级 `input_binding_drift` 可能在归档统计中被错误地混为同一类。论文需要能按运行级故障与案例级失败分别报告分母和失败归因。

Change: v1 证据包新增 `failure_scope` 与 `failure_code`。Rust 运行级 fatal error 现在记录 `failure_scope=run`，并使用 `creator_user_missing`、`input_binding_drift` 或 `worker_error`；案例日志和 `summary.errors` 记录 `failure_scope=case`、`failure_code=query_error`，导出器补录未落库失败时复制该元数据，完成案例显式使用 `null`。Python 检查器拒绝未知代码、运行/案例范围错配、完成案例残留失败元数据以及摘要—案例失败元数据漂移。协议和论文证据索引同步说明该字段不再依赖错误文本推断。

Tests: TDD RED 新增的运行级范围错配与案例级错误范围回归先在旧校验器上得到 2 个预期失败；最小实现后定向证据校验 40 passed、Rust 证据包单测 3 passed。随后 `backend/.venv/bin/py.test -q scripts/test_*.py` 为 335 passed；`cargo test --locked --lib -- --test-threads=1` 为 244 passed；隔离 PostgreSQL `./scripts/run-rust-db-tests.sh` 为 244 库测试 + 2 二进制测试通过；`cargo clippy --locked --all-targets --all-features -- -D warnings`、`cargo fmt --all --check`、`git diff --check` 均通过。

Result: PASS。证据包可在机器可读层面区分“运行级输入绑定漂移/worker 故障”与“单案例查询失败”，并在摘要与逐案例之间保持一致；失败分母不会因错误文本相似而被重新分类。

Paper Value: 论文方法部分可以引用“运行级/案例级故障分层、注册化失败代码、摘要—案例一致性门禁”作为证据链设计；这支持失败归因和可复核性，不等价于人工金标准、确认性准确率或模型优越性。输入漂移 run 仍应作为失败关闭记录，不得当作 completed 结果纳入效果分母。

Reviewer: PASS。测试覆盖 fatal error 的合法/非法范围、案例失败的范围错配、未知代码、完成案例残留字段和未落库失败导出；未修改历史实验 CSV、内部批次数字或确认性门禁结论。

Gatekeeper: PASS。改动集中于 Rust RAG 实验证据导出/worker 失败摘要、Python 归档检查器、协议说明、论文索引和测试；未新增界面或炫技型 AI 功能，未改变数据库 schema、认证或外部结果。

Next: 继续等待 Owner 提供外部冻结题集、金标准、可绑定应用 revision、独立双人盲评和真实 v1 证据包；在这些材料齐备前，保持 `paper_ready=false`，不把内部自动结果写成确认性论文结论。

## Iteration 40 — 证据包 OpenAPI 与前端类型契约同步

Time: 2026-08-13 Asia/Shanghai

Task: 沿论文可信支撑主线，补齐证据包 JSON 端点在 OpenAPI 和前端生成类型中的结构化契约。

Reason: Rust 导出器和 Python 归档检查器已经能区分运行级/案例级失败，但 OpenAPI 仍把 `application/json` 响应声明为 `{}`，前端生成类型因此将归档包视为 `unknown`。这会让论文所需的失败分层、题集/语料/模型绑定和失败分母在跨端契约层不可发现，也增加未来字段漂移风险。

Change: 新增 `scripts/update_rag_evidence_openapi.py`，以幂等方式把 `GET /rag/experiments/{run_id}/evidence.json` 响应绑定到 `RagEvidencePackage`，并声明 `RagEvidenceExperiment`、`RagEvidenceCase`、`RagEvidenceSummary`、`RagEvidenceSummaryError` 和 `RagEvidenceRunFatalError`。稳定字段包含 schema version、题集/语料/索引/模型绑定、执行计划摘要、案例状态、`failure_scope`/`failure_code` 及运行级 fatal error；来源、图谱、检索配置、用量和引用审计保持开放对象。更新 `backend/openapi.json` 后运行 `frontend npm run generate:api`，生成类型不再把证据包响应当作 `unknown`。

Tests: TDD RED 测试先确认端点 schema 仍为 `{}` 并失败；最小 schema 实现后定向 Rust 契约测试通过，且 `jq` 校验端点 `$ref`、案例失败枚举和 run fatal error 枚举。全量 `backend/.venv/bin/pytest -q scripts/test_*.py` 为 335 passed；`cargo fmt --all --check`、`cargo test --locked --lib -- --test-threads=1` 为 245 passed、`cargo clippy --locked --all-targets --all-features -- -D warnings` 均通过；隔离 PostgreSQL `./scripts/run-rust-db-tests.sh` 为 245 个库测试 + 2 个二进制测试通过；前端 `npm run lint`、`npm run typecheck`、`npm run build` 均通过；连续两次 `npm run generate:api`，以及重新运行 OpenAPI 更新脚本后的再次生成，均产生字节一致的前端类型；`git diff --check` 通过。

Result: PASS。OpenAPI 与前端类型结构化同步完成，并通过 Rust、隔离数据库、证据脚本和前端全量对应回归；既有 `paper_ready=false`、外部冻结输入/应用 revision/独立人工评审/v1 包缺失等论文门禁不变。

Paper Value: 论文归档流程现在可以引用“运行时导出—OpenAPI schema—前端生成类型—离线检查器”的可追踪契约链，并直接定位案例级 `query_error` 与运行级 `input_binding_drift` 等失败类别；这加强证据可复核性，不等价于人工金标准、确认性准确率或方法优越性。

Reviewer: PASS。OpenAPI 对稳定字段显式建模，对扩展证据保持开放；Rust RED/GREEN 测试锁定响应引用和失败枚举，生成链连续运行保持稳定；没有把契约通过误写成模型效果证据。

Gatekeeper: PASS。改动集中于 Rust OpenAPI 契约测试、OpenAPI 生成物、前端生成类型、契约更新脚本和论文协议材料；未新增界面或炫技型 AI 功能，未改变数据库、认证或历史实验数字。

Next: 继续等待 Owner 提供外部冻结题集、金标准、可绑定应用 revision、独立双人盲评和真实 v1 证据包；材料齐备前继续保持 `paper_ready=false`，不把内部自动结果写成确认性论文结论。

## Iteration 41 — OpenAPI 生成过程的可重复性回归

Time: 2026-08-13 Asia/Shanghai

Task: 为上一阶段新增的证据包 OpenAPI 更新脚本补齐独立回归，验证论文归档契约不是只在当前静态产物上成立。

Reason: `scripts/update_rag_evidence_openapi.py` 已能更新真实 `backend/openapi.json`，但此前没有测试其文档变换过程。若后续维护误删已有 schema、覆盖非证据端点字段或引入非幂等序列化，前端生成类型和论文归档契约可能在未被发现的情况下漂移。

Change: 新增 `scripts/test_update_rag_evidence_openapi.py`，以最小临时 OpenAPI 文档验证：证据端点响应绑定 `RagEvidencePackage`、既有 schema 保留、案例级 `failure_scope` 和运行级 fatal error 枚举存在，以及二次应用变换后的 JSON 字节完全一致。将更新器拆出可测试的 `update_document()` 纯文档变换入口，实际文件写入仍由脚本入口负责；未改变 Rust 导出逻辑、数据库或前端行为。

Tests: TDD RED 阶段新测试在旧脚本上按预期 2 项失败（缺少 `update_document`）；最小实现后定向测试 2 passed。随后 `backend/.venv/bin/pytest -q scripts/test_*.py` 为 337 passed，Rust `test_openapi_evidence_contract_exposes_failure_metadata` 通过，`npm run generate:api` 通过，真实 OpenAPI `$ref` 校验通过，`git diff --check` 通过。新增回归确认不改变已有前端生成类型和论文证据字段。

Result: PASS。证据契约的“生成过程—静态 OpenAPI—前端类型—Rust 路由测试—离线检查器”链路均有可复现检查；当前内部实验的 `paper_ready=false` 和外部材料缺口不变。

Paper Value: 论文方法/可复现性附录可以引用“契约生成器的最小输入回归与幂等性检查”，说明证据归档 schema 的维护过程本身可审计；这仍只支持工程证据链，不等价于模型效果、人工金标准或确认性结论。

Reviewer: PASS。测试使用临时内存文档，不覆盖用户真实 OpenAPI 输入；保留未知/既有 schema 的断言，避免将“生成成功”误当成“契约完整”。

Gatekeeper: PASS。改动仅新增 OpenAPI 变换函数测试与对应日志；未触碰界面、认证、数据库、生产配置或历史实验数字。

Next: 继续等待 Owner 提供外部冻结题集、金标准、可绑定应用 revision、独立双人盲评和真实 v1 证据包；在这些材料齐备前保持 `paper_ready=false`。

## Iteration 42 — 论文描述性材料输入新鲜度门禁

Time: 2026-08-13 Asia/Shanghai

Task: 沿论文可信支撑主线，验证自动生成的实验 5 描述性材料没有脱离其列明的原始数据、分析脚本和参数输入版本。

Reason: 描述性材料已经内嵌 10 个输入的 SHA-256，但此前没有独立检查器在交付前重算这些摘要。若 CSV、报告、题集、冻结清单或分析脚本发生漂移，Markdown 可能仍被引用而不会自动暴露过期状态。

Change: 新增 `scripts/check_paper_material_freshness.py` 和 `scripts/test_check_paper_material_freshness.py`。检查器解析材料的“输入材料指纹”表，拒绝缺失指纹章节、空表、格式错误表行、缺失/越界输入、格式错误摘要、重复材料名和摘要漂移，并输出带结构化 `reason` 的机器可读 `paper-material-freshness-v1` JSON；新增纯临时夹具回归覆盖匹配通过、摘要漂移失败、缺失/畸形输入、缺失章节、格式错误表行和 CLI 退出码。同步论文证据索引与证据包协议，要求描述性材料归档前运行该门禁。

Tests: TDD RED 阶段在检查器不存在时按预期无法收集；最小实现后定向测试 6 passed。随后全量 `backend/.venv/bin/pytest -q scripts/test_*.py` 为 343 passed；真实实验 5 材料 freshness CLI 返回 `passed=true`、`fingerprints=10`、`checked=10`、`mismatches=[]`；`python3 -m py_compile` 与 `git diff --check` 通过。未修改实验 CSV、统计数字、Rust/Next 业务或确认性门禁。

Result: PASS。论文材料现在具备“生成时指纹 + 归档前重算 + 机器可读结果”的新鲜度链路；当前 `paper_ready=false` 及外部冻结题集、金标准、应用 revision、独立盲评和 v1 包缺口保持不变。

Paper Value: 论文可复核性附录可以引用材料输入新鲜度门禁，证明展示的描述性数字与其列明输入文件版本一致；这不证明输入外部有效性、人工评分有效性、模型准确率或方法优越性。

Reviewer: PASS。测试使用临时 Markdown 和临时输入，覆盖失败关闭，不覆盖历史实验文件；真实材料只读重算，10 个摘要全部匹配。

Gatekeeper: PASS。改动集中在离线指纹检查器、测试、论文协议/索引和夜间日志；未新增界面或炫技型 AI 功能，未改变生产 API、数据库、认证和历史结果。

Next: 继续等待 Owner 提供外部冻结题集、金标准、可绑定应用 revision、独立双人盲评和真实 v1 证据包；材料齐备前继续保持 `paper_ready=false`。

## Iteration 43 — 论文描述性正文重渲染一致性

Time: 2026-08-13 Asia/Shanghai

Task: 沿论文可信支撑主线，验证已归档的实验 5 描述性 Markdown 不仅输入指纹匹配，而且仍是审计 JSON 与统计验证 JSON 的当前生成结果。

Reason: 输入 SHA-256 表可以证明材料引用的文件版本没有漂移，但不能单独证明 Markdown 正文的表格、限制和允许/禁止表述没有被手工改写。论文需要同时保留“输入新鲜度”和“生成正文一致性”两层证据。

Change: 为 `scripts/test_render_rag_five_mode_paper_material.py` 增加真实材料逐字节重渲染回归；当前审计产物和验证产物经渲染后必须与 `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md` 完全一致。同步论文证据索引，明确该断言只能发现生成链漂移，不能解除 `paper_ready=false`。

Tests: 先执行只读 CLI 重渲染对比，结果 `render_match=true`；新增回归与既有材料生成测试共 6 passed。随后全量 `backend/.venv/bin/pytest -q scripts/test_*.py` 为 344 passed；真实 freshness CLI 返回 `passed=true`、`fingerprints=10`、`checked=10`、`mismatches=[]`；`py_compile` 与 `git diff --check` 通过。

Result: PASS。描述性材料现在同时具备“输入指纹重算”和“正文由当前审计输入重渲染一致”两类可复核证据；没有修改实验 CSV、统计数字、Rust/Next 业务或确认性门禁。

Paper Value: 论文可复现性附录可以说明生成后的表格和限制文本不是仅凭手工复制保留，而是由审计产物确定性重建并通过字节级回归；这支持材料完整性，不证明输入外部有效性、人工评分有效性、模型准确率或方法优越性。

Reviewer: PASS。测试读取真实审计/验证产物和真实归档 Markdown，只做确定性内存渲染与比较；未覆盖或改写历史实验输入。

Gatekeeper: PASS。改动集中在论文材料回归测试、证据索引和夜间日志；未新增界面或炫技型 AI 功能，未改变生产 API、数据库、认证和历史结果。

Next: 继续等待 Owner 提供外部冻结题集、金标准、可绑定应用 revision、独立双人盲评和真实 v1 证据包；材料齐备前继续保持 `paper_ready=false`。
## Iteration 44 — 论文材料路径可移植性与边界门禁

Time: 2026-08-13 Asia/Shanghai

Task: 沿论文可信支撑主线，消除描述性 Markdown 中机器相关的绝对路径，并验证路径相对化不会放松证据输入边界。

Reason: 旧材料把审计 JSON 和统计验证 JSON 写成当前 macOS 工作区绝对路径，换机器或归档目录后无法直接重放；但简单相对化若接受仓库外绝对路径，会削弱输入绑定范围。论文材料需要同时可移植和边界明确。

Change: `scripts/render_rag_five_mode_paper_material.py` 新增仓库根目录相对路径转换；正文引用与指纹表统一使用 POSIX 相对路径，输入位于仓库根目录外时失败关闭。重新生成实验 5 描述性 Markdown，未修改原始 CSV、统计 JSON 或论文门禁。

Tests: TDD RED 先由渲染器路径断言捕获绝对路径；实现后定向渲染测试 7 passed，包含根目录外输入失败关闭和真实 Markdown 字节一致。真实 freshness CLI 返回 `passed=true`、`fingerprints=10`、`checked=10`、`mismatches=[]`；全量脚本、`py_compile` 和 `git diff --check` 随后复核。

Result: PASS。论文描述性材料可在仓库迁移后按相对路径重放，同时不会把仓库外文件伪装成绑定输入；`paper_ready=false`、严格引用失败、单项目和外部材料缺口保持不变。

Paper Value: 可在论文复现附录中给出与机器无关的重放路径，并把证据包输入限制在版本化仓库根目录内；这改善归档可复现性，不证明输入外部有效性、人工评分有效性、模型准确率或方法优越性。

Reviewer: PASS。测试使用临时越界报告验证失败关闭，真实材料只在重生成时更新路径表示；没有覆盖或改写实验原始数据。

Gatekeeper: PASS。改动集中在离线材料生成器、其回归测试、论文证据索引、生成材料和夜间日志；未新增界面或炫技型 AI 功能，未改变生产 API、数据库、认证和确认性结果。

Next: 继续等待 Owner 提供外部冻结题集、金标准、可绑定应用 revision、独立双人盲评和真实 v1 证据包；材料齐备前继续保持 `paper_ready=false`。
## Iteration 45 — freshness 归档结果机器无关化

Time: 2026-08-13 Asia/Shanghai

Task: 沿论文证据链主线，消除 freshness JSON 中残留的机器相关绝对根目录路径。

Reason: 描述性 Markdown 已使用仓库相对路径，但 `paper-material-freshness-v1` 结果仍把当前工作区写入 `root`。这会使归档结果在不同机器间产生无意义差异，削弱论文复现材料的可移植性。

Change: freshness 检查器将输出 schema 的 `root` 固定为 `"."`，`material` 保持相对校验根目录的路径；实际检查仍使用调用者提供的绝对化根目录，并继续拒绝根目录外输入。同步证据包协议、论文索引和真实 freshness JSON。

Tests: TDD RED 先由 CLI 夹具断言捕获绝对 `root`；实现后定向 freshness 测试 6 passed，真实 CLI 返回 `root="."`、`passed=true`、`fingerprints=10`、`checked=10`、`mismatches=[]`；随后全量 `backend/.venv/bin/pytest -q scripts/test_*.py` 为 345 passed，`py_compile` 和 `git diff --check` 通过。

Result: PASS。freshness 归档结果不再泄露机器工作区路径，仍保留相对材料定位和输入哈希；`paper_ready=false` 及外部冻结题集、金标准、应用 revision、独立盲评和 v1 包缺口不变。

Paper Value: 论文复现附录可以在不同机器和归档目录重放同一 JSON schema，而不把本地绝对路径误当作证据内容；这改善材料可移植性，不证明输入外部有效性、人工评分有效性、模型准确率或方法优越性。

Reviewer: PASS。测试验证机器无关字段和真实材料成功路径；底层文件解析仍使用显式根目录，越界路径失败关闭。

Gatekeeper: PASS。改动集中在离线 freshness 检查器、测试、协议/索引、freshness JSON 和夜间日志；未新增界面或炫技型 AI 功能，未改变生产 API、数据库、认证和实验原始数据。

Next: 继续等待 Owner 提供外部冻结题集、金标准、可绑定应用 revision、独立双人盲评和真实 v1 证据包；材料齐备前继续保持 `paper_ready=false`。
## Iteration 46 — freshness 材料路径 POSIX 化与越界失败

Time: 2026-08-13 Asia/Shanghai

Task: 继续收紧论文材料 freshness 归档边界，确保 `material` 字段跨平台可重放且材料文件本身不能位于校验根目录外。

Reason: 上轮只固定了 `root="."`，但检查器在材料越界时仍可能把绝对路径写回 JSON；同时系统路径分隔符未被回归锁定。论文证据归档应避免路径泄露和平台差异，并把材料本体越界与输入文件越界区分开。

Change: freshness 检查器用 `Path.relative_to(...).as_posix()` / `os.path.relpath` 生成 POSIX 相对 `material`，材料位于根目录外时新增结构化 `reason=material_outside_root` 并失败关闭。新增嵌套材料和越界材料回归；同步协议与论文索引。

Tests: TDD RED 捕获嵌套路径夹具失败和越界材料绝对路径泄露；实现后 freshness 定向测试 8 passed。真实实验 5 freshness CLI 返回 `root="."`、`passed=true`、`fingerprints=10`、`checked=10`、`mismatches=[]`；全量脚本、`py_compile` 和 `git diff --check` 随后复核。

Result: PASS。freshness JSON 的路径表示机器无关，材料本体和材料列明输入均受同一校验根目录约束；`paper_ready=false` 及外部冻结题集、金标准、应用 revision、独立盲评和 v1 包缺口不变。

Paper Value: 论文复现附录可在不同操作系统重放相同路径语义，并明确区分“材料越界”与“输入越界”失败原因；这支持归档完整性，不证明输入外部有效性、人工评分有效性、模型准确率或方法优越性。

Reviewer: PASS。测试只使用临时目录和内存 JSON，真实材料只读核验；没有改写实验原始数据。

Gatekeeper: PASS。改动集中在离线 freshness 检查器、测试、协议/索引和夜间日志；未新增界面或炫技型 AI 功能，未改变生产 API、数据库、认证和实验统计。

Next: 继续等待 Owner 提供外部冻结题集、金标准、可绑定应用 revision、独立双人盲评和真实 v1 证据包；材料齐备前继续保持 `paper_ready=false`。

## Iteration 47 — 证据包引用审计独立重算

Time: 2026-08-13 Asia/Shanghai

Task: 沿论文可信支撑主线，把 v1 证据包中的逐案例引用审计从“字段存在”提升为“答案标记、证据数组和审计字段可独立重算”。

Reason: 协议已要求 `[S数字]`/`[G数字]` 单项格式、编号范围和非法标记失败关闭，但 Python 归档检查器此前只确认 `citation_audit` 是对象，可能接受答案中的越界/范围标记或被篡改的 `citation_count`。

Change: 新增离线引用扫描与校验：对有答案案例重算引用数量、非法标记、是否存在证据，并以 `sources`/`graph_context` 数组长度作为边界；检查器拒绝越界与范围标记、审计字段漂移、非布尔状态和空消息。失败案例的 `answer=null` 路径保持兼容，不把未落库失败误当作引用失败。同步证据包协议和论文证据索引，明确该门禁只证明语法/数组边界/导出内部一致性，不证明引用内容正确或人工评价有效。

Tests: TDD RED 新增的字段漂移、越界 `[S2]` 和范围 `[S1-S2]` 回归在旧检查器上按预期 3 项失败；实现后定向证据校验 43 passed，全量脚本测试 350 passed；Rust citation 相关测试 14 passed；`py_compile`、`git diff --check` 通过。对现有实验 5 内部审计 JSON 实测返回退出码 1，明确拒绝 schema `rag-internal-five-mode-bundle-audit-v1`（不是 `rag-evidence-package-v1`），未把旧材料冒充 v1 证据包。

Result: PASS。v1 归档检查现在能发现答案标记与来源/图谱数组、引用审计摘要之间的内部漂移，并保留旧版内部批次不可升级的失败边界；没有修改实验 CSV、统计数字、Rust 生产引用规则或 `paper_ready=false` 门禁。

Paper Value: 论文复现附录可引用“导出后独立重算引用语法与证据范围”的审计步骤，并报告具体失败案例；这支持证据链完整性，不等价于来源支持命题、事实准确率、人工金标准或方法优越性。

Reviewer: PASS。回归使用内存/临时证据包，覆盖成功、越界、范围标记和失败空答案；Rust 测试只验证既有生产 citation gate，未改写历史实验结果。

Gatekeeper: PASS。改动集中于离线证据检查器、测试、协议/索引和夜间日志；未新增界面或炫技型 AI 功能，未改变数据库、认证、OpenAPI 或外部材料状态。

Next: 继续等待 Owner 提供通过 `rag-evidence-package-v1` 的确认性运行包、外部冻结题集/金标准、可绑定应用 revision 和独立双人盲评；材料齐备前继续保持 `paper_ready=false`。

## Iteration 57 — 逐案例统计重算与检索参数绑定

Time: 2026-08-13 Asia/Shanghai

Task: 沿论文可信支撑主线，使 v1 检查器能从证据包独立重算描述性统计，并把逐案例检索参数绑定到同一运行快照。

Reason: Iteration 56 已保证证据对象可回指，但仅有容器、计数和身份门禁仍不足以直接生成可引用的分层结果；有 `query_log_id` 的案例也可能只记录模型/索引而遗漏策略、top-k、图谱阈值等关键参数。

Change: `scripts/check_rag_experiment_evidence.py` 对已落库案例要求完整的嵌入模型、索引版本、检索策略、普通/集合 top-k、有效 top-k、向量候选数、图谱 top-k、分块大小/重叠及两个最低相关度阈值，并要求同一证据包内稳定绑定、不允许参数漂移。检查器新增确定性的 `statistics` 派生输出，版本为 `rag-evidence-statistics-v1`；它从 `cases[]` 重算状态/失败分层、来源/图谱对象数、引用审计计数、按方法完成/失败/时延摘要（中位数/P95）以及模型/索引/检索参数快照。引用统计只读取答案文本和证据数组独立重算，不读取可被手工修改的 `citation_audit` 计数字段。`RagEvidenceRetrievalConfig` 已同步至 OpenAPI、生成的前端类型、v1 协议和论文证据索引。

Tests: TDD RED 固定为 53 passed、2 failed；完成实现和完整夹具后，证据检查器与 OpenAPI 定向测试为 59/59，全量脚本测试为 364/364。Rust OpenAPI 定向回归为 1/1；完整 Rust library 测试为 245/245，隔离数据库测试为 245/245 library 加 2/2 main；`cargo fmt --all --check`、Clippy、前端 lint/typecheck/build、Python 编译和 `git diff --check` 均通过。旧版内部材料仍以 validator exit 1 被 fail-closed 拒绝，且检查输出带有统计 schema 但没有可冒充 v1 的案例。

Result: PASS。归档检查器现在可在不连接数据库、不重跑模型的条件下，从逐案例答案、证据和遥测稳定重生成描述性统计，并能阻止关键检索输入在同一证据包内漂移。

Paper Value: 论文附录可直接引用 `rag-evidence-statistics-v1` 作为可重生成的描述性材料，并报告状态、失败、证据、引用审计、时延和运行参数分层；该输出支持归档完整性与统计重算，不等价于人工准确率、引用正确性、显著性检验或方法优越性证据。

Reviewer: PASS。回归覆盖缺失/漂移检索参数、生产参数快照兼容性、派生统计与篡改 `citation_audit` 的隔离；Rust、OpenAPI、前端类型和离线检查器保持一致，未改写实验原始数据。

Gatekeeper: PASS。改动集中于证据包检查器、回归测试、OpenAPI/生成类型、协议/论文索引和夜间日志；未新增界面或炫技型 AI 功能，`paper_ready=false` 保持不变。

Next: 继续等待外部冻结题集、金标准、可绑定应用 revision、独立双人盲评和通过完整门禁的确认性 v1 运行包；材料齐备前不把该描述性统计写成效果或优越性结论。

## Iteration 58 — v1 证据包论文材料唯一渲染入口

Time: 2026-08-13 Asia/Shanghai

Task: 沿论文可信支撑主线，把 `rag-evidence-statistics-v1` 从检查器输出推进为可复现的论文附录生成入口，同时防止未通过归档门禁的旧材料被包装成 v1 结果。

Reason: Iteration 57 已能在检查结果中派生描述性统计，但尚无通用的 Markdown 材料入口；若论文附录由人工复制统计字段，仍可能出现统计与逐案例证据分叉，或把旧版内部运行记录误写成 v1 证据。

Change: 新增 `scripts/render_rag_evidence_paper_material.py` 及回归测试。渲染器只接受 `rag-evidence-package-v1`、检查结果 `passed=true` 且无失败项的输入，并从同一 `cases[]` 再次派生 `rag-evidence-statistics-v1`；任一 schema、检查状态或统计漂移均 fail-closed。输出固定包括实验输入绑定、案例/失败分母、来源与图谱证据容器、按方法完成/失败/时延中位数/P95、引用标记独立重算和运行参数快照；明确不证明人工准确率、引用正确性、显著性检验或方法优越性。协议与论文证据索引同步说明该入口。当前仓库没有通过 v1 的确认性运行包，因此只提交可复现渲染器和测试，不生成虚假的论文结果附件。

Tests: TDD RED 首次收集因渲染器不存在而失败；实现后渲染器定向测试为 5/5，证据检查器 + OpenAPI + 渲染器联合定向测试为 64/64；全量脚本测试为 369/369。`py_compile`、`git diff --check` 通过；旧版 `rag-experiment-5-internal-bundle-audit-2026-08-12.json` 经 v1 检查器以 exit 1 拒绝，输出明确报告旧 schema 和缺失 v1 结构。未改写实验 CSV、历史统计或 `paper_ready=false` 门禁。

Result: PASS。论文材料现在有唯一、可重算、会拒绝不可信输入的 Markdown 生成入口；统计层仍严格保持描述性，不升级为确认性效果结论。

Paper Value: 论文附录可以从通过门禁的证据包重新生成同一组分母、失败、证据、时延和参数描述，并将生成命令写入复现说明；这减少手工复制和统计漂移风险，但仍需外部冻结题集、金标准、独立双人盲评、应用 revision 和确认性运行包才能形成正式效果证据。

Reviewer: PASS。回归覆盖通过包渲染、检查失败、统计篡改、非 v1 schema 和 CLI 路径；渲染器二次重算统计，不读取可篡改的审计摘要作为结果来源。

Gatekeeper: PASS。改动集中于离线论文材料渲染器、测试、协议/索引和夜间日志；未新增界面或炫技型 AI 功能，未改变生产 Rust、数据库、认证、OpenAPI 或外部材料状态，`paper_ready=false` 保持不变。

Next: 继续等待并审计真正通过 `rag-evidence-package-v1` 的确认性运行包；在外部材料齐备前，不生成或引用任何确认性准确率、引用有效率、显著性或方法优越性结论。

## Iteration 59 — 论文附录逐案例失败清单

Time: 2026-08-13 Asia/Shanghai

Task: 沿论文可信支撑主线，把 v1 附录中的失败汇总推进为可逐项复核的失败案例清单，保留失败分母、机器可读代码和证据容器规模。

Reason: Iteration 58 的渲染器已经输出状态/失败计数，但论文审阅者仍无法从附录直接核对具体失败的执行序号、方法、重复编号、日志绑定和原始错误；只有汇总数字会弱化失败案例分析，并可能掩盖未落库失败。

Change: `render_rag_evidence_paper_material.py` 新增按 `execution_order` 稳定排序的失败案例表，逐项保留题目序号、方法、重复编号、`query_log_id`、`failure_scope`、`failure_code`、来源/图谱证据对象数量和原始错误文本；`query_log_id=null` 的未落库失败也保留。错误文本经过 Markdown 单元格转义，仅作为原始遥测，不解释为因果原因；S/G 数量仅用于容器审计，不解释为相关性或正确性。协议、论文索引和回归测试同步更新。

Tests: 新增失败案例字段、稳定排序和 Markdown 特殊字符转义回归；定向证据材料/检查器/OpenAPI 测试为 66/66，全量脚本测试为 371/371；`py_compile` 与 `git diff --check` 通过。未改写实验 CSV、历史统计、生产 Rust 或 `paper_ready=false` 门禁；当前仍不生成无真实 v1 确认性包支撑的论文结果附件。

Result: PASS。论文附录可直接逐案例复核失败分母、失败范围/代码、日志可追溯性和证据容器规模，避免将失败分析压缩为不可审计的总数。

Paper Value: 支持论文报告具体失败模式和失败案例回放入口，同时明确“原始错误文本不是因果证据、证据数量不是相关性指标”的解释边界；不升级为准确率、引用正确性、显著性或方法优越性结论。

Reviewer: PASS。回归覆盖有/无 `query_log_id` 的失败案例、排序、字段保留和不可信错误文本转义；渲染器仍要求完整 v1 检查通过并二次重算统计。

Gatekeeper: PASS。改动集中于论文材料渲染器、测试、协议/索引和夜间日志；未新增界面或炫技型 AI 功能，未改变生产接口、数据库、认证或外部实验数据，`paper_ready=false` 保持不变。

Next: 继续等待真实确认性 v1 运行包、外部冻结题集、金标准、应用 revision 和独立双人盲评；材料齐备前保持描述性/诊断性解释，不输出确认性效果结论。

## Iteration 60 — 论文附录输入材料 SHA-256 绑定

Time: 2026-08-13 Asia/Shanghai

Task: 沿论文证据链主线，把 v1 描述性附录绑定到实际证据包、检查器、渲染器和协议/索引的具体字节版本，并接入已有 freshness 独立复核。

Reason: Iteration 59 已保留逐案例失败清单，但附录仅记录证据包路径；若检查器、渲染器、协议或证据包后来漂移，论文引用者无法确认所引用材料对应的具体文件版本。

Change: `render_rag_evidence_paper_material.py` 新增固定顺序的 `input_fingerprints()`，对五项材料计算完整小写 SHA-256：实际 v1 证据包、`check_rag_experiment_evidence.py`、`render_rag_evidence_paper_material.py`、v1 协议和论文证据索引。输出使用仓库相对 POSIX 路径；缺失或越界输入失败关闭。Markdown 附录新增“输入材料指纹”表，并明确该表不等价于外部冻结、人工金标准、应用 revision 或独立评审。协议和论文索引同步要求 `check_paper_material_freshness.py` 复核。

Tests: TDD RED 先由附录缺失“输入材料指纹”表的断言捕获；实现后材料渲染器、证据检查器、freshness、OpenAPI 定向测试为 75/75，端到端 freshness 回归确认 5 个摘要全部可独立重算；全量脚本测试为 372/372；`py_compile` 和 `git diff --check` 通过。未写入真实确认性结果附件，未改写 CSV、历史统计、生产 Rust 或 `paper_ready=false` 门禁。

Result: PASS。论文材料现在同时具备“内容由证据包重算”和“输入/代码/协议版本可指纹定位”两层可复核性。

Paper Value: 论文复现附录可按五项 SHA-256 重新定位生成输入和审计逻辑，并通过 freshness JSON 检查材料是否过期；这支持版本审计，不把哈希本身升级为外部冻结、准确率、引用正确性、显著性或方法优越性证据。

Reviewer: PASS。测试覆盖固定指纹顺序、相对路径、缺失材料失败关闭及渲染结果经 freshness 独立重算；临时夹具不引入未审计的真实实验数据。

Gatekeeper: PASS。改动集中于论文材料渲染器、测试、协议/索引和夜间日志；未新增界面或炫技型 AI 功能，未改变生产 API、数据库、认证或外部实验数据，`paper_ready=false` 保持不变。

Next: 继续等待真实通过 `rag-evidence-package-v1` 的确认性运行包；在此外部证据到位前，不生成或引用确认性效果结论。

## Iteration 56 — 逐案例证据对象身份门禁

Time: 2026-08-13 Asia/Shanghai

Task: 沿论文可信支撑主线，把每个来源与图谱证据对象绑定到可回指的稳定 ID，使论文中的 `[S#]`/`[G#]` 标记不只指向“某个对象数组位置”。

Reason: Iteration 55 已约束 `sources`/`graph_context` 的数组长度与冗余计数一致，但空对象或缺少身份字段仍可能通过检查。若对象不能回指到具体 chunk、file、relation 与 entity，证据链只能证明容器存在，不能支持逐对象复核。

Change: Python v1 检查器要求 `sources` 对象包含正整数 `chunk_id` 与 `file_id`，要求 `graph_context` 对象包含正整数 `relation_id`、`source_entity_id` 与 `target_entity_id`。OpenAPI 新增 `RagEvidenceSource`/`RagEvidenceGraphContext` schema，生成前端类型同步；协议与论文证据索引明确 ID 用于回指，不代表相关性、正确性或准确率。未修改检索排序、历史实验数据、数据库 schema 或 `paper_ready=false` 门禁。

Tests: TDD RED 在旧检查器上为 52 passed、1 failed；GREEN 后证据检查器与 OpenAPI 更新器为 55/55，Rust OpenAPI 证据契约回归为 1/1。全量脚本测试 360 passed；隔离数据库 Rust 测试为 245/245 library 加 2/2 main；`cargo fmt --all --check`、Clippy、前端 lint/typecheck/build、Python 编译与 `git diff --check` 均通过。旧版内部五模式材料仍被 v1 检查器 fail-closed 拒绝，退出码为 1。

Result: PASS。归档门禁现在能发现来源/图谱对象缺少稳定身份字段或使用非正整数的情况，并能把公开 API schema、离线检查器和生成前端类型保持在同一契约上。

Paper Value: 论文附录可引用逐案例证据对象的可回指性审计：`[S#]` 可追溯至 chunk/file，`[G#]` 可追溯至 relation/source entity/target entity；这支持复现、审计与失败案例复核，但不证明证据与问题相关、不证明引用内容正确，也不构成方法优越性证据。

Reviewer: PASS。回归覆盖来源缺少 `chunk_id`、图谱对象缺少 `relation_id`、对象身份类型错误以及完整对象的兼容路径；生产 Rust 序列化结构、OpenAPI schema 与前端生成类型均通过验证。

Gatekeeper: PASS。改动集中于离线证据检查器、回归测试、OpenAPI/前端契约、协议/索引和夜间日志；未新增界面或炫技型 AI 功能。`paper_ready=false` 继续保持，仍需外部冻结题集、金标准、可绑定应用 revision、独立双人盲评和确认性 v1 运行包。

Next: 保持 `paper_ready=false`，继续等待外部材料；下一阶段优先检查证据包能否独立重算逐案例统计与版本/参数绑定，而不是扩展非论文必要功能。

## Iteration 53 — 模型快照与逐案例生成模型绑定门禁

Time: 2026-08-13 Asia/Shanghai

Task: 沿论文可信支撑主线，保证实验级嵌入/生成模型快照与配置一致，并阻止已落库案例的非空生成模型漂移。

Reason: Iteration 52 已绑定逐案例嵌入模型和索引版本，但检查器此前没有验证 `experiment` 与 `config_snapshot` 中的 `embedding_model`/`generation_model` 是否成对存在且一致，也没有约束案例的非空 `model` 与实验级生成模型一致。仅有字段存在不能支撑按模型版本分层的论文统计。

Change: 新增模型快照一致性校验；实验级嵌入模型和生成模型必须在顶层与配置快照中为非空字符串且严格相等。有 `query_log_id` 且 `model` 非空的案例必须匹配实验级 `generation_model`；系统兜底/结构化查询的 `model=null` 仍按生产语义允许。同步 v1 协议与论文证据索引，明确该门禁不把系统兜底误判为模型漂移。

Tests: TDD RED 新增模型快照漂移与案例生成模型漂移回归，在旧检查器上为 49 passed、2 failed；实现后定向证据校验 GREEN 为 51/51。随后执行脚本全量、Rust citation 回归、`py_compile`、`git diff --check` 和旧版内部材料失败关闭验证；未修改 Rust 生产逻辑、数据库、实验 CSV、统计结果或 `paper_ready=false` 门禁。

Result: PASS。v1 检查器现在能发现实验级模型快照和逐案例生成模型的内部漂移，同时保留系统无模型兜底案例的合法边界。

Paper Value: 论文方法与复现附录可引用模型版本的双层绑定和逐案例一致性审计，避免把不同生成模型的回答静默合并到同一分母；这支持参数分层与可回放性，不证明模型效果、引用正确性或方法优越性。

Reviewer: PASS。回归覆盖顶层快照漂移、已落库案例模型漂移及系统模型为空的兼容路径；没有改写历史实验数据。

Gatekeeper: PASS。改动集中于离线证据检查器、回归测试、协议/索引和夜间日志；未新增界面或炫技型 AI 功能，未改变数据库、认证、OpenAPI 或外部材料状态。

Next: 继续等待 Owner 提供外部冻结题集、金标准、可绑定应用 revision、独立双人盲评和确认性 v1 运行包；材料齐备前继续保持 `paper_ready=false`。

## Iteration 64 — 门禁失败摘要的双层可读/可审计表示

Time: 2026-08-13 Asia/Shanghai

Task: 改善五方法描述性附录中嵌套失败 JSON 的论文可读性，同时不牺牲机器复核所需的原始值。

Reason: Iteration 63 的失败摘要已能稳定失败关闭，但 `citation_audit_recomputed_matches_report` 的完整嵌套 JSON 单行超过 3,500 字符。只保留该长 JSON 会降低论文附录定位失败门禁的可读性；只截断又会破坏审计证据链。

Change: 新增确定性的 `compact_value()`，对标量保留 JSON 类型，对顶层/浅层对象按键排序展开，对深层对象和数组保留结构类型及元素/键数量；`failure_gate_rows()` 同时输出 `actual_summary`/`expected_summary` 与完整 `actual`/`expected` JSON。Markdown 失败表新增双层摘要列和完整 JSON 列；协议/索引明确摘要用于阅读、完整值用于机器复核，且不改变门禁判定。

Tests: TDD RED 先由缺少 `compact_value()`、摘要字段缺失和完整材料重渲染不一致断言捕获（2 项核心失败，随后源码指纹漂移由重渲染测试捕获）；实现后定向审计/渲染/freshness 回归为 25/25，全量 `scripts/test_*.py` 为 375/375；freshness 为 `paper-material-freshness-v1`、10/10 指纹通过、0 个 mismatch；`py_compile` 和 `git diff --check` 通过。未修改实验 CSV、原始统计、生产 API、数据库或外部人工评审状态。

Result: PASS。附录同时具备短摘要的可读定位和完整 JSON 的可复核保真度。

Paper Value: 论文读者可快速看到 `app_revision`、题集规模、引用审计和人工评审等阻塞；复现者仍可读取完整结构化值并从原始审计 JSON 重算。该改进只支持证据状态透明度，不证明事实准确率、引用正确性、显著性、外部有效性或方法优越性。

Reviewer: PASS。测试覆盖稳定排序、嵌套摘要边界、原始类型保留、真实材料重渲染和 freshness；没有将内部结果升级为确认性结果。

Gatekeeper: PASS。改动限定于论文材料渲染器、回归测试、协议/索引、生成材料和夜间日志；`paper_ready=false` 及外部冻结题集、应用 revision、独立盲评、确认性包阻塞保持不变。

Next: 继续等待 Owner 提供外部冻结题集、金标准、可绑定应用 revision、独立双人盲评和确认性 v1 运行包；材料齐备前继续保持 `paper_ready=false`。

## Iteration 63 — 失败门禁摘要的畸形输入失败关闭

Time: 2026-08-13 Asia/Shanghai

Task: 审计五方法附录新增的门禁失败摘要，确保摘要自身在遇到畸形检查项或重复检查名时不会生成含糊材料或泄漏非结构化异常。

Reason: Iteration 62 的 `failure_gate_rows()` 已按检查名保留失败值，但对非对象 `checks[]` 元素会抛出 `AttributeError`，重复失败检查名也会产生不可区分的 Markdown 行。论文材料生成器需要对审计 JSON 的失败状态保持失败关闭，并给出可定位错误。

Change: 新增失败摘要回归：非对象检查项必须抛出 `ValueError`，重复失败检查名必须拒绝；实现中增加检查项对象类型、非空名称、重复名称和严重级别校验。同步协议/索引，明确摘要不是因果解释且畸形摘要输入失败关闭；重新生成五方法描述性附录和 freshness JSON。

Tests: TDD RED 先复现非对象检查项的 `AttributeError`（1 项失败）；补齐实现后定向审计/渲染/freshness 回归为 24/24，全量 `scripts/test_*.py` 为 374/374；freshness 为 `paper-material-freshness-v1`、10/10 指纹通过、0 个 mismatch；`py_compile` 和 `git diff --check` 通过。首次源码变更后，重渲染一致性测试准确捕获渲染器 SHA-256 漂移，随后由唯一渲染入口修复。未修改实验 CSV、原始统计、生产 API、数据库或外部人工评审状态。

Result: PASS。失败摘要对 malformed/重复门禁输入现在可预测地失败关闭，正常材料仍可稳定渲染并独立 freshness 复核。

Paper Value: 论文复现者获得的不只是失败状态表，还能确认该表自身不会因畸形审计 JSON 产生静默歧义；这支持材料生成链完整性，不证明事实准确率、引用正确性、显著性、外部有效性或方法优越性。

Reviewer: PASS。测试覆盖正常排序/类型保留、非对象检查项、重复名称、真实材料重渲染和输入指纹复核；未新增或改写任何实验结果。

Gatekeeper: PASS。改动限定于论文材料渲染器、回归测试、协议/索引、生成材料和夜间日志；`paper_ready=false` 及外部冻结题集、应用 revision、独立盲评、确认性包阻塞保持不变。

Next: 继续等待 Owner 提供外部冻结题集、金标准、可绑定应用 revision、独立双人盲评和确认性 v1 运行包；材料齐备前继续保持 `paper_ready=false`。

## Iteration 62 — 描述性附录门禁失败摘要

Time: 2026-08-13 Asia/Shanghai

Task: 将五方法内部描述性附录的“不能升级为确认性结果”状态从单一布尔门禁扩展为可引用、可机器复核的逐项失败摘要。

Reason: 既有材料虽然固定输出 `paper_ready=false` 和 blocker 名称，但没有同时保留每个失败检查的严重级别、实际值和期望值。论文读者因此难以区分引用审计不一致、输入冻结失败、版本未绑定、题集规模不足、人工评审缺失和 v1 包缺失等不同证据状态。

Change: `render_rag_five_mode_paper_material.py` 新增 `failure_gate_rows()` 与稳定 JSON 序列化，按检查名排序保留所有未通过检查的 `severity`、`actual`、`expected`；Markdown 表格对管道符和换行做安全转义，并保留 `null`、布尔值、数组和对象的原始 JSON 类型。同步五方法渲染器测试、v1 协议和论文证据索引；用唯一渲染入口重新生成描述性附录和 freshness JSON。该摘要只解释证据状态，不改变门禁结果，也不把失败文本解释为因果机制。

Tests: TDD RED 先由“门禁失败摘要”缺失和 `failure_gate_rows()` 缺失断言捕获（2 项失败）；实现后定向审计/渲染/freshness 回归为 23/23，全量 `scripts/test_*.py` 为 373/373；freshness 为 `paper-material-freshness-v1`、10/10 指纹通过、0 个 mismatch；`py_compile` 和 `git diff --check` 通过。重新生成材料仍保留 `paper_ready=false`，且摘要明确列出当前失败门禁。未修改实验 CSV、原始统计、生产 API、数据库或外部人工评审状态。

Result: PASS。内部描述性材料现在同时提供布尔门禁、逐项失败值/期望值和输入指纹，失败状态可直接定位并可重渲染复现。

Paper Value: 论文附录可以引用具体的证据等级限制，而不是只引用一个不可解释的 `paper_ready=false`；这支持审计透明度、失败案例披露和复现者定位，不证明事实准确率、引用正确性、显著性、外部有效性或方法优越性。

Reviewer: PASS。测试覆盖失败项排序、JSON 类型保留、真实材料重渲染一致和 freshness 复核；没有把内部 CSV/report 误升级为 `rag-evidence-package-v1`。

Gatekeeper: PASS。改动限定于论文材料渲染器、测试、协议/索引、生成材料和夜间日志；外部冻结题集、应用 revision、独立双人盲评及确认性运行包仍未擅自伪造或修改。

Next: 继续等待 Owner 提供外部冻结题集、金标准、可绑定应用 revision、独立双人盲评和确认性 v1 运行包；材料齐备前继续保持 `paper_ready=false`。

## Iteration 61 — 五方法描述性附录重渲染与 freshness 独立复核

Time: 2026-08-13 Asia/Shanghai

Task: 对 Iteration 60 后的五方法描述性论文材料执行一次不改写输入的审计回放，确认输入指纹、审计结果和 Markdown 附录没有发生未记录漂移。

Reason: SHA-256 指纹只有在重新计算并与现有材料逐项核对后，才具有可引用的版本审计价值；同时需要确认内部描述性材料的重渲染结果仍由同一批次输入确定。

Change: 未改写实验 CSV、题集、运行配置、审计产物或论文材料。使用当前仓库输入重新运行 `audit_rag_five_mode_bundle.py` 到临时文件，重新渲染五方法附录到临时文件，并用 `cmp` 做字节级比较；另将 freshness JSON 写入临时文件，避免把新的内部时间戳伪装成既有结果附件。

Tests: 当前审计重算保留 `consistency_passed=false` 与 `paper_ready=false`，并确认五个确认性前置条件仍阻塞；审计检查中题集哈希、方法/重复绑定、CSV 行完整性、模式汇总和配对比较重算均通过，引用审计与输入冻结清单仍按真实材料报告失败。重渲染与已交付材料 `cmp` 完全一致；freshness 独立复核为 `paper-material-freshness-v1`、10/10 指纹通过、0 个 mismatch；审计/渲染/freshness 定向回归为 22/22。未生成虚假确认性结果附件，未改生产 Rust、OpenAPI、数据库或 `paper_ready=false` 门禁。

Result: PASS（内部复现链）。材料内容和绑定输入未漂移；当前失败项是证据状态而非本轮工具不一致。

Paper Value: 论文附录可复现地说明“审计产物可由原始批次输入重算，渲染输出可字节级重现，10 项输入指纹可由 freshness 独立核对”。这支持内部描述性材料的版本和生成一致性，不升级为外部冻结、人工准确率、引用正确性、显著性或方法优越性证据。

Reviewer: PASS。临时输出未污染仓库；验证同时保留并报告了引用审计、冻结清单和确认性门禁失败，没有把部分通过写成整体通过。

Gatekeeper: PASS。仅新增夜间可追溯记录；没有扩大到界面、炫技型 AI 或未经授权的外部/生产状态变更。

Next: 继续等待 Owner 提供外部冻结题集、金标准、可绑定应用 revision、独立双人盲评和确认性 v1 运行包；材料齐备前继续保持 `paper_ready=false`。

## Iteration 54 — 未落库失败遥测契约闭合

Time: 2026-08-13 Asia/Shanghai

Task: 对齐生产 Rust 证据导出器与逐案例遥测门禁，确保由 `summary.errors` 补入的未落库失败案例也具备可追溯的提示版本。

Reason: Iteration 50 建立了所有案例必须有非空 `prompt_version` 的门禁；审阅真实导出路径发现，Rust 为未落库失败合成案例写入 `prompt_version=null`，会使包含该类失败的真实 v1 包被离线检查器拒绝，破坏失败分母的可归档性。

Change: Rust `build_experiment_evidence_package` 将未落库失败的提示版本固定为 `experiment-unlogged-failure-v1`；保留 `query_log_id=null`、`answer=null` 和空证据容器语义。协议和论文证据索引同步说明该稳定版本只标识系统补入的失败记录，不冒充模型调用。

Tests: TDD RED 新增 Rust evidence-package 回归后为 2 passed、1 failed；实现后定向回归 GREEN 为 3/3。并执行脚本全量、Rust citation、格式、`py_compile`、`git diff --check` 和旧版内部材料失败关闭验证；未修改实验 CSV、统计结果或 `paper_ready=false` 门禁。

Result: PASS。生产导出器生成的未落库失败案例现在满足离线遥测结构门禁，失败分母和失败来源标识均可复核。

Paper Value: 论文可以区分真实查询日志失败与运行摘要补入的未落库失败，并在保留失败分母的同时追踪其记录语义；这支持失败分析和归档完整性，不证明失败原因的因果性或模型效果。

Reviewer: PASS。回归只覆盖内存中的导出构造函数和已有离线检查器，不改写数据库、历史 CSV 或外部材料。

Gatekeeper: PASS。改动集中于 Rust 证据导出器、回归测试、协议/索引和夜间日志；未新增界面或炫技型 AI 功能，未改变认证、OpenAPI 或统计结论。

Next: 继续等待 Owner 提供外部冻结题集、金标准、可绑定应用 revision、独立双人盲评和确认性 v1 运行包；材料齐备前继续保持 `paper_ready=false`。

## Iteration 49 — 完成案例回答完整性门禁

Time: 2026-08-13 Asia/Shanghai

Task: 沿论文可信支撑主线，阻止没有实际回答的日志被归档为 `status=completed`，保持完成率分母与逐案例证据语义一致。

Reason: v1 检查器此前要求完成案例有 `query_log_id`、无错误并校验引用审计，但没有要求 `answer` 存在；因此 `answer=null` 的不完整案例可能被计入 completed，弱化论文中的完成案例分母和证据可回放性。生产 Rust 路径仅在成功查询时写入 `Some(&result.answer)`，检索失败路径才写入 `answer=null`，该约束可安全提升为归档门禁。

Change: `check_rag_experiment_evidence.py` 对 `status=completed` 案例新增非空字符串 `answer` 要求；`status=failed` 仍允许 `answer=null`，并继续要求结构化错误元数据。新增回归测试覆盖 completed 空回答失败，保持失败案例空答案兼容；同步 v1 协议和论文证据索引，明确完成案例与失败案例的分界。

Tests: TDD RED 在旧检查器上为 45 passed、1 failed；实现后定向证据校验 46 passed。生产代码审阅确认成功查询写入回答、失败路径写入空答案；未修改 Rust 生产逻辑、实验 CSV、统计结果或 `paper_ready=false` 门禁。全量脚本、Rust citation 回归、`py_compile` 和 `git diff --check` 将在本轮收尾执行。

Result: PASS。归档检查器不再允许空回答冒充完成案例，同时保留运行失败的真实分母和未落库失败表达能力。

Paper Value: 论文可以更可靠地引用 `N_completed` 与逐案例回答材料的对应关系，避免把无回答日志误写成系统完成；这支持分母完整性和可回放性，不证明回答事实正确、引用内容正确或方法优越性。

Reviewer: PASS。回归只新增内存证据包的空回答负例，并核对 Rust 成功/失败写日志语义；没有改写历史实验数据。

Gatekeeper: PASS。改动集中于离线证据检查器、测试、协议/索引和夜间日志；未新增界面或炫技型 AI 功能，未改变数据库、认证、OpenAPI 或外部材料状态。

Next: 继续检查证据包中 response_ms、sources、graph_context、usage 等逐案例字段是否有同等明确的成功/失败语义；材料齐备前继续保持 `paper_ready=false`。

## Iteration 50 — 逐案例遥测结构门禁

Time: 2026-08-13 Asia/Shanghai

Task: 为论文复现实验参数和运行成本提供结构化底线，校验 v1 证据包每个案例的响应时延、提供方、提示版本、模型/回退信息、检索配置和用量字段。

Reason: 完成案例回答完整性已收紧，但检查器此前仍接受负响应时延、空提供方、缺失提示版本以及把检索配置/用量写成数组或字符串。论文需要从逐案例证据中重放时延、模型和资源消耗；遥测字段畸形会使分层统计或参数审计静默失真。

Change: 新增 `validate_case_telemetry`：所有案例要求非负整数 `response_ms`、非空 `provider`/`prompt_version`，`model`/`fallback_reason` 可空但非空时必须为字符串，`retrieval_config`/`usage` 必须为对象。失败案例仍允许空回答和系统提供方；成功查询与失败记录的生产 Rust 导出路径均满足这些类型语义。新增负响应时延、空提供方、缺失提示版本和错误对象类型回归，并同步协议/索引。

Tests: TDD RED 在旧检查器上为 46 passed、1 failed；实现后定向证据校验 47 passed。随后运行脚本全量、Rust citation 回归、`py_compile` 与 `git diff --check`，未修改 Rust 生产逻辑、数据库、历史 CSV、统计结果或 `paper_ready=false` 门禁。

Result: PASS。v1 归档检查现在能阻止遥测字段畸形进入论文统计链，同时保留失败案例的完整分母和可空错误字段语义。

Paper Value: 论文方法/复现附录可以可靠引用逐案例 `response_ms`、provider、prompt version、fallback、retrieval config 和 usage 的结构化存在性，并在后续统计阶段区分缺失数据与真实零值；这支持参数审计，不证明模型效果或人工评价有效性。

Reviewer: PASS。测试覆盖完成/失败案例共同的遥测字段约束，并核对生产导出字段来源；没有改写实验原始数据。

Gatekeeper: PASS。改动集中于离线证据检查器、测试、协议/索引和夜间日志；未新增界面或炫技型 AI 功能，未改变数据库、认证、OpenAPI 或外部材料状态。

Next: 继续审计 sources/graph_context 数组与其计数、检索配置中的索引/模型绑定是否能由证据包检查器独立重算；材料齐备前继续保持 `paper_ready=false`。

## Iteration 51 — 失败案例证据容器类型门禁

Time: 2026-08-13 Asia/Shanghai

Task: 保证失败案例也保留可解析的来源与图谱证据容器，避免“保留失败分母”与“保留可复核上下文”相互矛盾。

Reason: Iteration 50 已对逐案例遥测字段设定类型底线，但 `sources`/`graph_context` 的数组检查此前只在有答案案例的引用审计函数中执行；失败案例的 `answer=null` 因此可能携带对象或字符串形式的畸形证据上下文，后续论文分层统计会静默丢失或误读失败证据。

Change: 新增 `validate_case_evidence_arrays`，对完成和失败案例统一要求 `sources`、`graph_context` 为对象数组；失败案例仍允许 `answer=null`、空数组和 `citation_audit={}`，但不允许证据容器本身变成错误 JSON 类型或包含非对象元素。同步协议/索引，明确失败分母与证据容器完整性同时保留。

Tests: TDD RED 在旧检查器上为 47 passed、1 failed；实现后定向证据校验 48 passed。将随后运行脚本全量、Rust citation 回归、`py_compile`、`git diff --check` 和旧版内部材料失败关闭验证；未修改生产 Rust、数据库、实验 CSV、统计结果或 `paper_ready=false` 门禁。

Result: PASS。v1 归档检查器现在能在保留失败案例的同时保证来源/图谱 JSON 容器可被后续分析脚本稳定解析。

Paper Value: 论文可以把失败案例作为完整分母报告，并在需要时区分“无证据的失败”与“带检索上下文但回答失败”，而不会因容器类型漂移造成静默排除；这支持失败分析和可复核性，不证明失败原因的因果性或模型效果。

Reviewer: PASS。测试覆盖成功案例既有引用路径和失败案例畸形数组路径，未改写历史证据内容。

Gatekeeper: PASS。改动集中于离线证据检查器、测试、协议/索引和夜间日志；未新增界面或炫技型 AI 功能，未改变数据库、认证、OpenAPI 或外部材料状态。

Next: 继续审计 sources/graph_context 数量字段与检索配置中的索引/模型绑定是否能由证据包检查器独立重算；材料齐备前继续保持 `paper_ready=false`。

## Iteration 52 — 逐案例检索输入绑定门禁

Time: 2026-08-13 Asia/Shanghai

Task: 沿论文可信支撑主线，把已落库案例的逐案例检索配置绑定到实验级模型与索引快照，防止运行参数在导出时漂移。

Reason: Iteration 50 已要求 `retrieval_config` 为对象，但此前没有检查其中的 `embedding_model` 与 `index_version` 是否存在、是否与实验级 `embedding_model`/`rag_index_version` 一致。若不收紧，论文复现材料可能把不同嵌入模型或索引版本的案例混入同一实验分母。

Change: 新增 `validate_case_retrieval_binding`。有 `query_log_id` 的案例必须提供非空的 `retrieval_config.embedding_model` 和 `retrieval_config.index_version`，并分别匹配实验级模型与索引版本；未落库的系统失败案例仍允许空配置对象。同步 v1 证据包协议与论文证据索引，明确该门禁属于逐案例输入绑定和导出内部一致性审计。

Tests: TDD RED 在旧检查器上为 48 passed、1 failed；补齐测试 fixture 的实验级绑定字段并实现门禁后 GREEN 为 49/49。随后执行脚本全量测试、Rust citation 回归、`py_compile`、`git diff --check` 和旧版内部材料失败关闭验证；未修改 Rust 生产逻辑、数据库、实验 CSV、统计结果或 `paper_ready=false` 门禁。

Result: PASS。v1 检查器不再允许已落库案例缺少或漂移检索模型/索引绑定，同时保持未落库运行级失败的明确边界。

Paper Value: 论文方法与复现附录可引用逐案例检索输入与实验级快照的一致性检查，避免把不同版本的检索结果静默合并；这支持参数审计和分母完整性，不证明模型效果、检索质量、引用正确性或方法优越性。

Reviewer: PASS。回归覆盖已落库案例缺失/漂移绑定和未落库失败兼容路径，使用内存证据包；没有改写历史实验数据。

Gatekeeper: PASS。改动集中于离线证据检查器、回归测试、协议/索引和夜间日志；未新增界面或炫技型 AI 功能，未改变数据库、认证、OpenAPI 或外部材料状态。

Next: 继续等待 Owner 提供外部冻结题集、金标准、可绑定应用 revision、独立双人盲评和确认性 v1 运行包；材料齐备前继续保持 `paper_ready=false`。

## Iteration 55 — 逐案例证据计数一致性门禁

Time: 2026-08-13 Asia/Shanghai

Task: 沿论文可信支撑主线，把 Rust 查询日志中的 `source_count`/`graph_hit_count` 与证据包 `sources`/`graph_context` 数组绑定，防止证据数量统计与逐案例材料漂移。

Reason: v1 导出此前只输出证据数组，数据库/CSV 中的冗余命中计数未进入证据包，离线检查器也不能发现计数字段与数组长度不一致。论文中的证据覆盖和分层统计因此缺少独立的逐案例一致性约束。

Change: Rust evidence export now emits `source_count` and `graph_hit_count` for logged cases and zero values for synthetic unlogged failures. The Python checker requires both fields to be nonnegative integers and equal to the corresponding `sources`/`graph_context` lengths when arrays are valid. The OpenAPI updater and generated frontend types expose both as stable required fields. The protocol/index explain that this is an internal redundancy check, not a retrieval-quality metric.

Tests: TDD RED in the previous checker was 51 passed, 1 failed. GREEN is 54/54 for the checker plus OpenAPI updater tests and 3/3 for the Rust evidence-package regression. Full script tests are 359 passed; Rust database-isolated tests are 245/245 library plus 2/2 main; clippy, fmt, frontend lint/typecheck/build, Python compilation, and `git diff --check` pass. The old internal package is rejected fail-closed with validator exit code 1.

Result: PASS. The archive gate now detects evidence-count drift without treating hit counts as relevance, correctness, or accuracy.

Paper Value: The paper can cite a reproducible per-case audit that binds redundant evidence counts to the exported evidence containers. This supports evidence-container integrity and layered accounting, but does not prove retrieval quality, citation correctness, answer accuracy, or method superiority.

Reviewer: PASS after the logged and synthetic-failure Rust assertions plus checker regression pass; historical experiment data are not rewritten.

Gatekeeper: PASS after the OpenAPI/client contract and full validation are green; `paper_ready=false` remains unchanged pending the external frozen question set, gold standard, application revision, independent blind review, and confirmatory v1 package.

Next: Preserve `paper_ready=false`; wait for the external frozen question set, gold standard, reproducible application revision, independent double-blind scoring, and a confirmatory v1 package that passes the complete evidence gate.

## Iteration 48 — citation audit passed 双向一致性

Time: 2026-08-13 Asia/Shanghai

Task: 继续收紧 v1 证据包逐案例引用审计，使 `citation_audit.passed` 不能被单向伪造，并保持生产端强制引用规则可复现。

Reason: Iteration 47 已能发现答案存在非法标记时被错误记录为 `passed=true`，但合法答案被伪记为 `passed=false` 仍可能通过。论文证据链需要审计状态与可独立重算规则双向一致，而不是只拦截一种方向的字段篡改。

Change: `citation_audit_snapshot` 现在复现 Rust 生产端的证据类别覆盖和关键事实段落同段引用规则，并返回独立重算的 `passed`；归档检查器要求导出的 `passed` 与该结果严格相等。新增反向伪造回归，同时验证真实的“关键事实段落缺少同段标记”应合法保留 `passed=false`，避免把生产端审计结果误报为导出错误。同步证据包协议与论文证据索引，明确该规则仍不证明引用内容或事实命题正确。

Tests: 新增 RED 测试在旧实现上 44 passed、1 failed；实现后定向证据校验 45 passed，全量脚本测试 352 passed，Rust citation 单元测试 14 passed。`backend/.venv/bin/python -m py_compile`、`git diff --check` 和旧版实验 5 内部审计材料的 schema 失败关闭验证随后通过；本轮没有修改实验原始 CSV、统计结果、生产 API 或 `paper_ready=false` 门禁。

Result: PASS。v1 检查器能够发现 `passed` 真值双向漂移，并能在不连接数据库、不运行模型的条件下重现生产端强制引用状态；旧版内部材料仍不能冒充 v1 证据包。

Paper Value: 论文复现附录可引用“逐案例引用数量、非法标记、证据存在性与强制引用状态均由导出答案和证据数组独立重算”的审计流程，减少导出后手工篡改或单向漏检风险；这只支持归档内部一致性，不升级为引用正确性、人工准确率或方法优越性证据。

Reviewer: PASS。测试覆盖合法审计、非法/范围/越界标记、字段漂移、`passed` 反向漂移、关键事实段落缺少同段引用和失败案例 `answer=null` 兼容；Rust 回归验证既有生产引用门禁保持通过。

Gatekeeper: PASS。改动集中于离线证据检查器、回归测试、协议/索引和夜间日志；未新增界面或炫技型 AI 功能，未改变数据库、认证、OpenAPI、历史统计或外部材料状态。

Next: 继续等待 Owner 提供通过 `rag-evidence-package-v1` 的确认性运行包、外部冻结题集/金标准、可绑定应用 revision 和独立双人盲评；材料齐备前继续保持 `paper_ready=false`。

## Iteration 65 — 门禁失败摘要输入 schema 失败关闭

Time: 2026-08-13 Asia/Shanghai

Task: 收紧内部五方法描述性材料的“门禁失败摘要”输入契约，使摘要生成不会因宽松 truthiness、缺失严重级别或重复检查名而产生歧义。

Reason: Iteration 64 已为每个失败门禁保留有限深度摘要和完整 JSON，但渲染器仍把只有字面值 `True` 以外的 `passed` 当作失败，并对缺失 `severity` 默认写成 `unknown`。这种宽松处理可能把 malformed audit 当成可解释的失败结果；同时只在遇到失败行时检查名称唯一性，不能保证摘要输入的检查集合本身无歧义。

Change: `failure_gate_rows` 现在对所有检查项统一要求对象、布尔 `passed`、非空字符串 `name`/`severity`，并在跳过通过项前检查全体检查名唯一；任一违规输入立即失败关闭。同步协议与论文证据索引，明确该摘要是审计状态解释而非因果证明。仅重渲染归档 Markdown，未改写实验 CSV、审计 JSON、统计结果或 `paper_ready=false` 门禁。

Tests: TDD RED 首轮定向回归为 9 passed、1 failed，暴露旧的重复名错误契约；实现并补齐严格 schema fixture 后定向渲染器回归为 10/10。随后运行 freshness、全量脚本测试、Python 编译和 `git diff --check`；内部材料预期仍保持 `paper_ready=false`，因为外部冻结输入、人工双人盲评、应用 revision 和确认性 v1 包仍缺失。

Result: PASS。摘要生成器不再把非布尔值、缺失严重级别或重复检查名静默转写为论文可读行；通过项也必须满足同一 schema，防止未展示的 malformed 项绕过门禁。

Paper Value: 论文附录中的失败门禁表现在生成前具备可复现的 schema 级完整性约束，读者可以把摘要行与完整 JSON 审计值对应起来；这提升失败状态的可审计性，不证明失败原因、人工准确率、引用正确性、显著性或方法优越性。

Reviewer: PASS。回归覆盖非对象检查项、重复检查名、非布尔 `passed`、缺失严重级别、通过项的完整 schema 以及真实归档材料逐字节重渲染；没有新增实验结果或改变历史分母。

Gatekeeper: PASS。改动集中于离线论文材料渲染器、测试、协议/索引和夜间日志；没有界面润色、炫技型 AI、生产 API 或外部状态变更。

Next: 保持 `paper_ready=false`，继续等待 Owner 提供外部冻结题集/金标准、可绑定应用 revision、独立双人盲评和通过完整门禁的确认性 `rag-evidence-package-v1`。

## Iteration 66 — 门禁检查集合非空约束

Time: 2026-08-13 Asia/Shanghai

Task: 继续收紧内部五方法描述性材料的门禁失败摘要，区分“审计确实存在且全部通过”与“没有提供任何可审计检查项”。

Reason: Iteration 65 已要求 `checks` 为数组并校验每个检查项的字段类型，但空数组仍会被解释成没有失败门禁。对论文证据链而言，缺失整个检查集合不能等同于所有门禁通过，否则摘要可能在输入不完整时产生过度乐观的空结果。

Change: `failure_gate_rows` 现在要求顶层 `checks` 是非空 JSON 数组；缺失、非数组和空数组均失败关闭。同步 v1 协议与论文证据索引，明确该摘要只接受有检查集合的审计产物。真实实验审计 JSON、CSV、统计值和 `paper_ready=false` 未改写。

Tests: TDD RED 新增空数组回归，在旧实现上定向测试为 9 passed、1 failed；实现后重渲染归档材料，定向测试为 10/10。随后运行 freshness、全量脚本测试、Python 编译和 `git diff --check`；确认真实审计的失败门禁集合仍被完整展示。

Result: PASS。材料生成器不会再把缺失或空的门禁集合当作“无失败”；同时保留“所有检查通过”这一合法状态，因为非空检查数组仍会逐项校验并生成空失败摘要。

Paper Value: 论文附录的状态表现在具备最小审计集合完整性约束，读者可以区分“有证据支持的全通过”与“未提供检查证据”；这提升证据链的可复核性，不证明失败原因、人工准确率、引用正确性、显著性或方法优越性。

Reviewer: PASS。回归覆盖缺失、对象型、空数组、非对象检查项、重复名、非布尔 `passed`、缺失严重级别和真实材料逐字节重渲染；没有新增实验结果或改变历史分母。

Gatekeeper: PASS。改动集中于离线论文材料渲染器、测试、协议/索引和夜间日志；没有界面润色、炫技型 AI、生产 API 或外部状态变更。

Next: 保持 `paper_ready=false`，继续等待外部冻结题集/金标准、可绑定应用 revision、独立双人盲评和通过完整门禁的确认性 `rag-evidence-package-v1`。

## Iteration 74 — retrieval snapshot 缺口按方法、字段、行数分层

Time: 2026-08-13 Asia/Shanghai

Task: 将 Iteration 73 的逐案例 retrieval snapshot 总布尔门禁细化为论文可直接引用的按方法、按字段、按行数缺口统计。

Reason: 单一 `retrieval_bindings_bound=false` 能阻断过度声明，但不能说明哪些方法适用哪些字段、缺失覆盖多少行，容易把纯 LLM 的“不适用”与检索方法的“缺失”混为一谈，也无法区分字段为空和非空漂移。

Change: `audit_rag_five_mode_bundle.py` 新增 `row_integrity.retrieval_binding_gaps`：每个方法记录 `required_fields`、`row_count`、`rows_with_complete_snapshot`、`rows_with_any_gap`、`missing_by_field` 和 `mismatch_by_field`。`render_rag_five_mode_paper_material.py` 新增“Retrieval snapshot 缺口（按方法、按字段、按行数）”表，明确纯 LLM 字段不适用，并把缺失/漂移计数绑定到审计 JSON。协议与证据索引同步该输出契约；未回填历史 CSV 的缺失字段，`paper_ready=false` 保持。

Tests: TDD RED 新增摘要结构测试，旧实现为 10 passed、1 failed；实现后审计/渲染联合定向测试 28/28。非空错误语料哈希回归确认 BM25 缺失计数 35、漂移计数 1。全量脚本测试 386/386；freshness 10/10；Python 编译和 `git diff --check` 通过。真实批次中纯 LLM 为 36/36 行“不适用”，其余四种方法各 36 行有缺口，按字段缺失计数已写入审计产物。

Result: PASS（门禁仍按预期失败）。缺口摘要增强了失败证据的解释力，但没有把汇总配置升级为逐案例可回放证据，也没有新增或改写实验效果数字。

Paper Value: 论文可以引用按方法分层的版本/参数记录缺口：纯 LLM 不要求 retrieval snapshot，而 BM25、project、structured query、KG-enhanced 各自按适用字段报告 36 行缺失；审计同时能识别非空参数漂移。这支持限制与可复现性说明，不证明检索效果、事实正确性或方法优越性。

Reviewer: PASS。新增摘要字段有真实 CSV 审计来源、确定性排序和漂移回归；材料渲染先校验摘要存在再继续，避免旧审计 JSON 静默生成不完整论文材料。没有界面、生产 API 或炫技型 AI 变更。

Gatekeeper: PASS。改动集中于离线审计器、论文材料渲染器、测试、协议/索引和日志；无外部状态变更，`paper_ready=false` 与历史证据边界保持一致。

Next: 保持 `paper_ready=false`；新确认性运行必须原生导出逐案例 retrieval snapshot，并在补采后重新运行本摘要与 freshness 门禁。

## Iteration 73 — 逐案例 retrieval snapshot 缺口显式失败

Time: 2026-08-13 Asia/Shanghai

Task: 核查实验 5 是否保存每条 CSV 记录的检索/语料版本快照，并将缺失或漂移纳入论文证据门禁。

Reason: 逐案例 provider/model/prompt_version 已在 Iteration 72 绑定，但原始 CSV 仍只有来源计数和答案证据，没有 `embedding_model`、语料快照、索引版本、chunk/top-k/候选数或图谱阈值等逐案例 retrieval 条件。若仅引用汇总配置，不能证明每个回答使用了同一检索条件，也不能支持逐案例回放。

Change: `audit_rag_five_mode_bundle.py` 新增按方法分层的 retrieval snapshot schema：BM25、混合检索和图谱增强方法要求逐行保存语料哈希、嵌入模型（适用时）、chunk/top-k/候选数/图谱阈值；结构化查询要求图谱 schema/top-k/阈值。缺少或漂移会生成 `row_N_retrieval_snapshot_bound` 检查并使 `csv_row_integrity`/`consistency_passed` 失败。材料绑定表新增该门禁，协议与证据索引明确“汇总快照不能替代逐案例快照”。真实审计 JSON 和 Markdown 重新生成；没有伪造缺失字段，`paper_ready=false` 保持。

Tests: TDD RED 新增真实 CSV 缺少 retrieval snapshot 的回归，旧实现为 9 passed、1 failed；实现后审计器定向测试 10/10，联合渲染/审计测试 26/26。全量脚本测试 384/384；freshness 10/10；Python 编译和 `git diff --check` 通过。真实批次明确记录 `retrieval_bindings_bound=false`，而题干、运行标签、案例键域仍为 true。

Result: PASS（门禁按预期失败）。系统现在会阻止没有逐案例检索快照的内部材料被误写成“参数已绑定”；审计失败本身成为论文限制证据。

Paper Value: 论文可引用“逐案例 retrieval snapshot 缺失被 fail-closed 检出”的可复现审计结果，明确当前内部批次不能支持检索条件逐案例回放；这不证明模型效果、引用正确性、检索相关性或方法优越性。

Reviewer: PASS。没有从汇总配置复制或推断逐案例字段；统计数字、原始 CSV 和既有 `paper_ready=false` 结论未改写。

Gatekeeper: PASS。改动集中于离线实验审计器、材料渲染器、测试、协议/索引和夜间日志；未新增界面或炫技型 AI、生产 API 或外部状态变更。

Next: 保持 `paper_ready=false`；若要推进确认性材料，必须在新运行中原生导出逐案例 retrieval snapshot，而不是回填历史 CSV。

## Iteration 72 — 逐案例 provider/model/prompt_version 绑定

Time: 2026-08-13 Asia/Shanghai

Task: 将实验 5 全量 CSV 的运行时标签绑定到方法配置，防止单行提示版本、提供方或模型漂移而仍被纳入统计分母。

Reason: Iteration 71 已完成 180 行题干与冻结题集逐字绑定，但审计器只校验汇总级生成配置和方法列表，未逐行验证 `provider`、`model`、`prompt_version`。论文需要知道每个回答确实属于预注册的方法和运行条件，不能只依赖汇总快照。

Change: `audit_rag_five_mode_bundle.py` 新增 `runtime_bindings_bound`：生成方法逐行匹配 `run-config.json` 的 provider/model/prompt_version；`structured_query` 逐行要求 `provider=system`、空 model 和对应提示版本。漂移会生成 `row_N_<field>_matches` 定位检查，并使 `csv_row_integrity` 与 `consistency_passed` 失败关闭。描述性材料的“数据—问题集绑定门禁”新增逐案例运行标签结果，协议同步说明该边界。真实审计 JSON 和 Markdown 材料重新生成，统计数字、失败案例和 `paper_ready=false` 未改变。

Tests: TDD RED 新增篡改首行 `prompt_version` 回归，旧实现为 8 passed、1 failed；实现后审计器定向测试 9/9，渲染器与审计器联合定向测试 25/25。全量脚本测试 383/383；freshness 10/10；Python 编译和 `git diff --check` 通过。真实 180 行批次的 `runtime_bindings_bound=True`，运行版本门禁 PASS。

Result: PASS。每个统计案例现在都可回溯到方法级 provider、model、prompt_version；篡改单行运行标签会在生成论文材料前被定位并阻断。

Paper Value: 论文可引用“逐案例运行标签与预注册方法配置逐字段核对”的可复现性审计过程，支持方法分层、重复和参数记录的内部一致性；这不证明外部应用 revision、模型内容稳定性、提示语义等价或生成结果正确性。

Reviewer: PASS。真实输出仍 `consistency_passed=false`、`paper_ready=false`，阻塞项保持未版本化 app revision、外部冻结输入、跨项目题集、独立人工评审和确认性证据包；没有升级内部结果。

Gatekeeper: PASS。改动集中于离线实验审计器、材料渲染器、回归测试、协议/索引和夜间日志；未新增界面或炫技型 AI、生产 API 或外部状态变更。

Next: 保持 `paper_ready=false`，继续检查逐案例 retrieval 参数/语料版本绑定与配置快照一致性。

## Iteration 71 — 全量 CSV 题干与冻结题集逐字绑定

Time: 2026-08-13 Asia/Shanghai

Task: 将题目—问题集绑定从失败案例重算扩展到实验 5 的全部 CSV 行，并把它纳入结构一致性门禁和论文材料表。

Reason: Iteration 70 已证明失败引用案例的题干不会脱离冻结题集，但其余 176 条完成案例仍只受 `question_index` 绑定。论文的分母、配对比较和按题统计都依赖全量行，因此必须逐行验证 CSV `question` 与题集对应题干，而不能只审计失败子集。

Change: `audit_rag_five_mode_bundle.py` 新增 `question_texts_bound` 状态，逐行检查题目索引对应题集项为对象且 CSV `question` 与题集 `question` 逐字一致；题干漂移生成定位到 CSV 行的 `row_N_question_text_matches` 检查，并使 `csv_row_integrity` 失败关闭。描述性材料的“数据—问题集绑定门禁”新增“CSV 题干与冻结题集逐字一致”结果；同步 v1 协议与论文证据索引。真实审计 JSON 和 Markdown 材料重新生成，统计数字、失败案例和 `paper_ready=false` 未改变。

Tests: TDD RED 新增篡改首行题干回归，旧实现为 7 passed、1 failed；实现后审计器定向测试为 8/8，渲染器定向测试为 16/16。全量脚本测试为 382/382；freshness 检查 10/10；Python 编译和 `git diff --check` 通过。真实 180 行 CSV 的 `question_indices_bound`、`question_texts_bound`、重复/方法/案例键域均为 `True`。

Result: PASS。所有统计分母与案例行现在均绑定到冻结题集的索引、ID 和题干文本；篡改任一行题干会在审计阶段定位并阻断材料升级。

Paper Value: 论文可引用“全量实验行逐字绑定冻结题集题干”的问题集—结果完整性审计过程，支持分母和案例聚类的可复核性；这不证明题干语义正确、事实准确率、引用内容正确、检索相关性、失败因果机制或方法优越性。

Reviewer: PASS。真实输出仍明确 `consistency_passed=false`、`paper_ready=false`，阻塞项仍为未版本化 app revision、外部冻结输入、跨项目题集、独立人工评审和确认性证据包；没有把内部批次升级为确认性结果。

Gatekeeper: PASS。改动集中于离线实验审计器、材料渲染器、回归测试、协议/索引和夜间日志；未新增界面或炫技型 AI、生产 API 或外部状态变更。

Next: 保持 `paper_ready=false`，继续补齐外部冻结题集/金标准、可绑定应用 revision、独立双人盲评和通过完整门禁的确认性 `rag-evidence-package-v1`。

## Iteration 70 — 失败案例题干与冻结题集逐字绑定

Time: 2026-08-13 Asia/Shanghai

Task: 将严格引用失败案例的 CSV 题干绑定到冻结题集，避免题目索引正确但题干已被替换时仍生成可引用失败记录。

Reason: Iteration 69 已同时核对非法标记、题目索引/ID、回放日志、证据数组和冗余计数，但失败行重算尚未验证 CSV 中保存的 `question` 文本。论文证据链需要证明失败案例属于题集中的原始问题，而不是仅凭整数索引归属。

Change: `recompute_citation_failure_rows` 对每条非法标记行要求 `question_index` 能绑定题集对象、题集含非空 `question` 文本，并逐字比较 CSV `question` 与对应题干；任一越界、非对象题集项、缺失题干或题干漂移均失败关闭。同步 v1 协议与论文证据索引；重新生成内部描述性材料。真实 CSV、审计 JSON、统计结果和 `paper_ready=false` 未改写。

Tests: TDD RED 新增题干篡改夹具，旧实现为 15 passed、1 failed；实现后定向渲染器测试为 16/16。全量脚本测试为 381/381；freshness 检查 10/10；Python 编译和 `git diff --check` 通过。真实 180 行 CSV 的 4 条非法标记失败案例仍可逐字重算并与审计 JSON 一致。

Result: PASS。失败案例现在同时受 CSV 行、题集索引、题集 ID、题干文本、回放日志、引用标记、证据数组和冗余计数约束；题干被替换时不会静默进入论文材料。

Paper Value: 论文可引用“失败案例按冻结题集题干逐字绑定并由原始 CSV 独立重算”的数据完整性审计过程，支持问题集—结果绑定的可复核性；这不证明题干语义正确、引用内容正确、事实准确率、检索相关性、失败因果机制或方法优越性。

Reviewer: PASS。新增回归覆盖题干漂移；真实材料重渲染字节一致；没有新增实验结果、改变历史分母或放宽 `paper_ready=false` 门禁。

Gatekeeper: PASS。改动集中于离线论文材料渲染器、回归测试、协议/索引和夜间日志；未新增界面或炫技型 AI、生产 API 或外部状态变更。

Next: 保持 `paper_ready=false`，继续等待外部冻结题集/金标准、可绑定应用 revision、独立双人盲评和通过完整门禁的确认性 `rag-evidence-package-v1`。

## Iteration 69 — 失败案例证据计数双重核对

Time: 2026-08-13 Asia/Shanghai

Task: 将严格引用失败案例中的 `source_count`/`graph_hit_count` 与原始 CSV 的证据数组及显式冗余计数同时绑定。

Reason: Iteration 68 已从原始 CSV 重算非法标记和证据数组长度，但重算器仍直接用数组长度填充失败表，若 CSV 的显式计数字段被篡改，失败表可能仍看似一致。论文证据链需要区分“数组内容”和“导出计数”两层完整性。

Change: `recompute_citation_failure_rows` 现在对每条非法标记行解析非负整数 `source_count`/`graph_hit_count`，分别要求它们与 `sources_json`/`graph_context_json` 数组长度一致；缺失、负值、非整数、JSON 非数组或计数漂移均失败关闭。失败表仍与审计 JSON 逐字段比较；协议/索引同步该双重核对边界。真实 CSV、审计 JSON、统计结果和 `paper_ready=false` 未改写。

Tests: TDD RED 新增计数漂移夹具，旧实现为 14 passed、1 failed；实现后定向渲染器回归为 15/15。回归覆盖真实 CSV 重算、审计字段篡改、CSV 显式计数与证据数组长度不一致、失败身份契约和逐字节归档渲染。随后运行 freshness、全量脚本测试、Python 编译和 `git diff --check`。

Result: PASS。失败案例表同时受非法 token、题目/日志身份、证据数组和冗余计数字段约束，降低导出后计数漂移或静默替换的风险。

Paper Value: 论文可引用“失败案例的引用标记、回放身份、证据容器与冗余计数均由原始 CSV 独立核对”的审计过程，支持失败分母和证据呈现完整性；这不证明引用内容正确、检索相关性、事实准确率、失败因果机制或方法优越性。

Reviewer: PASS。真实 4 条失败案例计数与数组长度一致；合成计数漂移会失败关闭；没有重写历史实验数据或统计结论。

Gatekeeper: PASS。改动集中于离线论文材料渲染器、回归测试、协议/索引和夜间日志；未新增界面或炫技型 AI、生产 API 或外部状态变更。

Next: 保持 `paper_ready=false`，继续等待外部冻结题集/金标准、可绑定应用 revision、独立双人盲评和通过完整门禁的确认性 `rag-evidence-package-v1`。

## Iteration 68 — 原始 CSV 到失败案例表的双层重算

Time: 2026-08-13 Asia/Shanghai

Task: 防止严格引用失败表只信任已生成审计 JSON，建立“原始 CSV → 独立重算 → 审计 JSON → 论文 Markdown”的可复现证据链。

Reason: Iteration 67 已保证失败案例身份完整且可回放，但若 `invalid_marker_rows` 在审计生成后被单独篡改，材料仍可能展示错误的失败案例。论文附录需要同时证明原始答案中的非法范围标记与归档表逐字段一致。

Change: 新增 `recompute_citation_failure_rows`，从绑定的原始 CSV 和题集重新扫描严格 `[S数字]`/`[G数字]` token；范围标记仍判为非法，并按 CSV 行号生成题目索引/ID、方法、重复、`query_log_id`、标记和证据计数。渲染器要求重算结果与审计 JSON 的 `citation_audit.invalid_marker_rows` 经同一身份契约逐字段相等，任一审计字段漂移立即失败关闭。协议与论文证据索引同步说明该双层重算的边界。

Tests: TDD RED 新增原始 CSV 重算与篡改审计回归，旧实现为 12 passed、2 failed；实现后定向渲染器测试为 14/14。真实 180 行 CSV 重算得到 4 条失败记录，并与审计 JSON 完全一致：CSV 行 6/50/69/151，`query_log_id` 128/172/191/273。随后运行 freshness、全量脚本测试、Python 编译和 `git diff --check`；未修改原始 CSV、审计 JSON、统计结果或 `paper_ready=false` 门禁。

Result: PASS。论文失败案例表现在同时受原始 CSV 和审计 JSON 约束；独立篡改审计行会在材料生成阶段被发现，而不是静默进入附录。

Paper Value: 论文可引用“原始回答—严格引用扫描—审计记录—失败表”逐字段重算链，支持失败案例回放、分母审计和引用格式缺陷的可复核报告；这不证明引用内容正确、事实准确率、失败因果机制、显著性或方法优越性。

Reviewer: PASS。回归覆盖真实 CSV/题集重算、审计字段篡改、失败身份契约和逐字节归档渲染；历史实验数据与统计汇总未被改写。

Gatekeeper: PASS。改动集中于离线论文材料渲染器、回归测试、协议/索引和夜间日志；未新增界面或炫技型 AI、生产 API 或外部状态变更。

Next: 保持 `paper_ready=false`，继续等待外部冻结题集/金标准、可绑定应用 revision、独立双人盲评和通过完整门禁的确认性 `rag-evidence-package-v1`。

## Iteration 67 — 严格引用失败案例身份绑定

Time: 2026-08-13 Asia/Shanghai

Task: 将内部五方法批次中的非法引用标记从抽象计数提升为可稳定回放的案例级论文材料。

Reason: 既有材料已经列出 4 个非法范围标记，但渲染表省略了 `question_index`，且没有在渲染前验证 CSV 行号、日志 ID 和案例键的类型、正值与唯一性。若失败摘要身份不完整，论文读者无法可靠地从失败计数回到原始回答与证据容器。

Change: 新增 `citation_failure_rows` 归档层，对 `invalid_marker_rows` 要求非空数组；逐行校验正整数 CSV 行号、题目索引、重复编号和 `query_log_id`，非空题目 ID/方法/标记字符串，非负来源/图谱计数，并拒绝重复行号、重复日志 ID和重复案例键。失败案例表新增 `question_index` 列并按 CSV 行稳定排序；协议与论文证据索引同步说明该绑定只服务于回放与分母审计，不把格式失败解释为事实错误。

Tests: TDD RED 为 9 passed、3 failed，暴露缺少失败行契约和归档表列；实现后定向渲染器回归为 12/12。回归覆盖真实材料逐字节重渲染、失败行排序、题目索引/日志 ID保留、缺失身份、非正行号和重复日志 ID失败关闭。随后运行 freshness、全量脚本测试、Python 编译和 `git diff --check`；真实材料的 4 条失败行保持为 6、50、69、151，`paper_ready=false` 不变。

Result: PASS。论文材料现在能从非法引用标记稳定回放到 CSV 行、题目索引/ID、方法、重复、唯一 `query_log_id` 及来源/图谱计数；渲染层不会静默接受身份缺失或重复回放键。

Paper Value: 论文可直接引用一张可审计的失败案例表，并把格式失败与具体运行案例绑定，支持失败模式复核和分母审计；这不证明来源内容正确、事实准确率、失败因果机制、显著性或方法优越性。

Reviewer: PASS。真实 4 条非法范围案例按 CSV 行稳定排序并逐字节纳入归档材料；测试覆盖身份字段和重复键拒绝；没有重写原始实验数据、统计汇总或人工评价结论。

Gatekeeper: PASS。改动集中于离线论文材料渲染器、回归测试、协议/索引和夜间日志；未新增界面或炫技型 AI、生产 API 或外部状态变更。

Next: 保持 `paper_ready=false`，继续等待外部冻结题集/金标准、可绑定应用 revision、独立双人盲评和通过完整门禁的确认性 `rag-evidence-package-v1`。
## Iteration 75 — 生产 CSV 原生导出逐案例 retrieval snapshot

Time: 2026-08-13 Asia/Shanghai

Task: 修复新实验运行的证据采集源，使生产 Rust CSV 导出能够原生保存逐日志 retrieval snapshot，而不是继续生成 Iteration 74 已识别的历史格式缺口。

Reason: Iteration 74 证明实验 5 的历史 CSV 对 BM25、项目级 RAG、结构化查询和知识图谱增强方法均缺少逐案例检索字段。若只修离线审计而不修生产导出，下一次运行仍会丢失嵌入模型、语料/索引版本、top-k、chunk 和图谱阈值，无法形成可回放的论文证据链。

Change: Rust `/rag/experiments/{run_id}/export.csv` 保留原有 20 列，并追加 `retrieval_config_json`、运行级 `corpus_snapshot_hash`/`rag_index_version`/`graph_schema_version`，以及嵌入模型、索引版本、检索策略、top-k、候选数、chunk、图谱阈值和最低相关度等稳定字段，形成 35 列契约。字段来自运行创建时的配置快照和对应 `query_log` 的逐日志检索配置；未落库失败没有可证明的 query log，因此新增列留空而不伪造快照。生产检索配置和运行快照显式记录 `graph_schema_version=kg-v3-numbered-list-expansion`，与既有图谱抽取版本契约一致。协议、论文证据索引和 Rust 回归测试同步；历史 CSV、审计 JSON、统计结果和 `paper_ready=false` 均未改写。

Tests: TDD RED 先由缺少 CSV 头部常量与快照字段辅助函数的编译失败暴露契约未实现；GREEN 后针对 RAG API 测试为 30/30。追加的 CSV 头部回归确认 35 个字段全部存在，未登录失败回归确认 35 列且新增列全部为空；`cargo fmt --all -- --check`、`cargo clippy --locked --all-targets --all-features -- -D warnings` 和 `git diff --check` 通过。完整 Rust 测试为 249/249（库 247、二进制 2）；脚本全量 `backend/.venv/bin/python -m pytest -q scripts/test_*.py` 为 386/386。真实历史包重新审计仍按预期退出 1，`consistency_passed=false`、`paper_ready=false`；描述性材料重渲染成功，freshness 为 10/10 且无 mismatch。

Result: PASS（生产证据采集源已修复；当前没有启动新的真实实验）。未来新导出可被离线审计直接检查逐案例 retrieval snapshot；历史实验 5 仍按原始材料报告缺口，不能被本轮接口修复追溯性升级。

Paper Value: 论文方法与复现实验章节可引用“生产导出原生保留逐案例检索快照”的可验证实现契约，并把未落库失败明确保留在分母中；这提升未来确认性批次的可复现性，不证明历史批次的检索条件、事实准确率、引用正确性、显著性或方法优越性。

Reviewer: PASS。变更集中于 Rust 导出契约、图谱版本记录、协议/索引和回归测试；Rust clippy、全量测试、脚本全量测试、材料重渲染和 freshness 均通过；无界面润色、炫技型 AI、历史数据改写或外部状态变更。

Gatekeeper: KEEP `paper_ready=false`. 下一步必须用新生产运行生成 evidence JSON/CSV，运行逐案例审计、失败案例重算、统计和 freshness 门禁，并补齐外部冻结题集、金标准、代码 revision 与独立双人盲评后，才可讨论确认性论文主结论。

## Iteration 76 — CSV/JSON 未落库失败遥测一致性

Time: 2026-08-13 Asia/Shanghai

Task: 修复实验 CSV 导出中未落库失败案例的 `prompt_version` 空值，使其与 JSON evidence 包和 v1 协议保持一致。

Reason: 第 75 轮已让新运行的 CSV 原生保存逐案例 retrieval snapshot，但 `summary.errors` 补入的未落库失败行仍把 `prompt_version` 留空；同一失败案例在 CSV 与 JSON 中因此产生不同的遥测语义，也会违反证据检查器对每个案例非空 `prompt_version` 的要求。

Change: `append_missing_experiment_errors` 为未落库失败 CSV 行写入固定值 `experiment-unlogged-failure-v1`；更新 Rust 回归断言，保持新增 retrieval snapshot 列为空，不伪造不存在的 query log 快照。未修改历史 CSV、数据库、统计结果、OpenAPI 或论文门禁。

Tests: 先以旧实现运行严格模块过滤测试并得到预期 RED；最小修复后定向测试通过。随后 `cargo fmt --all --check`、`cargo clippy --locked --all-targets --all-features -- -D warnings`、`cargo test --locked --lib -- --test-threads=1`（248 passed）、`cargo test --locked --all-targets -- --test-threads=1`（248 库测试 + 2 主程序测试）和 `git diff --check` 均通过。

Result: PASS。新 CSV 导出与 JSON evidence 包对未落库失败的 `prompt_version` 语义一致，同时继续明确该案例没有可证明的逐日志检索快照。

Paper Value: 论文证据链可以稳定区分“系统补入的未落库失败记录”和“缺失运行标签的案例”，并保持失败分母完整；这提升跨格式归档一致性，不证明回答事实正确、引用正确性、检索效果、人工评价或方法优越性。

Reviewer: PASS。变更仅涉及生产 CSV 导出的一列固定失败标签和对应测试，没有回填历史实验数据或升级 `paper_ready=false`。

Gatekeeper: KEEP `paper_ready=false`。下一步仍需新生产运行、外部冻结题集/金标准、可绑定应用 revision、独立双人盲评和完整确认性 v1 evidence package。
