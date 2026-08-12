# ELN 项目 AI 功能检测流程 v1

> 用途：论文答辩、独立评审或外部验收前，对系统 AI 相关能力做一次"真实可信、公平公正"的检测。
> 面向对象：检测人（独立方）、被测方（开发方）、命题/评价人（第三方）。
> 原则：**凡声称即必可证伪**。每个"通过"都必须有可执行的失败条件；检测以运行态指纹、数据库、日志和哈希绑定为准，不以文档、截图和口头演示为准。

## 1. 检测原则

| 原则 | 要求 |
| --- | --- |
| P1 可证伪 | 每个检查项写明"通过标准"和"证伪条件"，任一证伪条件成立即该项 FAIL |
| P2 证据链 | 检测动作 → 原始证据文件 → SHA-256 绑定 → 判定结论，证据不可事后替换 |
| P3 运行态优先 | 以 `/metrics` 指纹、DB 内容、后端日志为准；文档与截图只作线索，不作证据 |
| P4 独立与盲评 | 命题、执行、评价三方分离；评价人看不到方法标签和对方结果 |
| P5 无挑选 | 不利案例一律保留；门禁的"完整性"检查兜底，检测人抽查行数对账 |

## 2. AI 功能矩阵与伪造风险点

| 功能 | 实现位置 | 声称能力 | 主要伪造风险 |
| --- | --- | --- | --- |
| 生成推理 | `backend/src/ai_provider.rs` | HTTPS 直调 DeepSeek 官方 OpenAI 兼容接口，重试 3 次 | 本地假 LLM、预存答案、失败时降级为模拟回答 |
| 嵌入 | `backend/src/embedding.rs` | 生产 bge-m3（1024 维）；hash 仅 dev/test | 用 `rust-hash-512-v1` 冒充 bge-m3 |
| 向量检索 | `backend/src/rag.rs` + pgvector | 余弦 + BM25 + RRF 混合检索 | 检索结果写死、来源块与回答无关 |
| 知识图谱 | `backend/src/knowledge_graph.rs` | 审核笔记自动抽取关系，图谱增强 RAG | 图谱上下文造假、降级不记录 |
| 固定任务 Agent | `backend/src/api/agent_runtime.rs` | 真实工具调用循环（MAX_TOOL_STEPS=8），计划需人工确认 | 伪造工具结果、声称完成未执行 |
| OCR | `backend/src/ocr.rs` | Tesseract 真实识别，审核后才进 RAG | 硬编码识别结果、未过审文本入库 |
| 对照实验 | `backend/src/api/rag.rs`（实验段） | 五方法、固定种子、随机顺序、provenance 落库 | 运行顺序造假、失败案例被丢弃 |
| 盲评 | `backend/src/api/rag.rs`（盲评段） | 方法隐藏、双评价人、kappa 一致性 | 解盲、评价人不独立、评价可事后修改 |

## 3. 检测域 A：运行态指纹（防配置造假）

| 检查项 | 方法 | 通过标准 | 证伪条件 |
| --- | --- | --- | --- |
| A1 运行时身份 | `curl -i /health` | 响应头 `x-backend-runtime: axum`；`/ready` 同时检查 PG 与存储 | 无该头或值为非 axum |
| A2 嵌入指纹 | `curl /metrics` 的 `runtime` 段（`state.rs:381`） | `embedding_backend=openai_compatible`、`embedding_model=BAAI/bge-m3`、`embedding_dimension=1024` | 任一项不匹配；或为 `hash`/`rust-hash-512-v1` |
| A3 版本绑定 | `/maturity/status` | `source_revision` = 运行时 `APP_REVISION` = 当前 git commit（40/64 位小写 hex） | 三者不一致；revision 非法 |
| A4 生产配置 | `scripts/check_production_config.py` + 运行中二进制 `--config-check` | 全部 `passed`，含 `SEED_DEMO_DATA=false`、非默认密钥 | 任一 `skipped`/`failed` |
| A5 配置强校验 | 读 `backend/src/config.rs` 的 `validate_embedding`（L353-404） | 生产模式拒绝 `hash` 后端、拒绝非 bge-m3/非 1024 维、`EMBEDDING_API_URL` 必须 https | 生产镜像接受 `hash` 组合 |
| A6 hash 冒充检测 | 从语料文本按 `embedding.rs` 的 `hash_embedding` 逻辑本地重算，与 DB 中已存向量比对 | 与 DB 向量不一致（真实 bge-m3 向量不可由该算法重算复现） | 抽样向量与本地重算结果相等 → 判定生产在用 hash 后端，A2-A5 全部连带 FAIL |
| A7 语义合理性 | 用同义改写与无关文本各一组经 `/metrics` 或 API 间接验证检索相似度 | 同义文本相似度显著高于无关文本（bge-m3 语义特性）；hash 后端对"字面不同但同义"文本区分度差 | 语义相似度剖面与 hash 后端行为一致 |

## 4. 检测域 B：真实外呼（防假调用/贴牌）

| 检查项 | 方法 | 通过标准 | 证伪条件 |
| --- | --- | --- | --- |
| B1 日志证据 | 后端日志检索 `AI provider request completed`（`ai_provider.rs:212`） | 含 `provider=deepseek`、实际 `model`、`prompt_tokens`、`completion_tokens`、`duration_ms` | 日志无此类记录；模型名与配置不符 |
| B2 请求 ID 对账 | 日志/`query_logs` 中保存的 provider `request_id`（响应头 `x-request-id`），与 DeepSeek 官方用量明细核对 | 时间、模型、token 数与官方平台记录匹配 | 对不上、官方平台无对应记录 |
| B3 网络层取证 | 在容器网络侧抓包（tcpdump）或把 `AI_BASE_URL` 临时指向自建记录代理跑 1 题探针 | 请求真实发往 `api.deepseek.com/chat/completions`，请求体含 model/messages/tools，响应体含 usage 与真实文本 | 无外呼；外呼目的地不是宣称端点；请求/响应被本地伪造 |
| B4 流式真实性 | AI 会话页发起提问，观察 SSE 事件 | 增量 delta 逐块输出，结束事件含 usage | 一次性整段返回（非流式但声称流式）；usage 缺失 |
| B5 token 合理性 | 自算一次问答的提示词字节/token 估算，与日志 `prompt_tokens` 对比；回答字符数与 `completion_tokens` 对比 | 数量级吻合（估算方法注明误差） | 系统性偏离（如固定假值、与上下文长度无关） |
| B6 错误密钥注入 | 用错误 `AI_API_KEY` 重建后端，发起 RAG 提问 | HTTP 502/503 明确错误，`query_logs` 记录错误详情，页面展示失败 | 仍返回"正常回答"或模拟回答 |
| B7 端点不可达 | 阻断 AI 端点（防火墙/DNS 指向黑洞）后提问 | 重试 3 次后失败，无回答落库 | 失败时生成替代答案 |

## 5. 检测域 C：无伪造回答（防预存答案/降级造假）

| 检查项 | 方法 | 通过标准 | 证伪条件 |
| --- | --- | --- | --- |
| C1 代码搜查 | `grep -rn "mock\|stub\|dummy\|模拟回答\|fake" backend/src` | 生产代码路径无模拟回答实现；仅测试文件允许显式 test double | 生产路径存在硬编码答案/降级回答分支 |
| C2 语料变异探针 | 修改资料中一个关键数值 → 重新索引 → 同问题再问 | 回答随之变化，或明确"无证据"；引用指向新内容 | 回答与修改前逐字相同（疑似预存答案） |
| C3 无证据拒答 | 问语料外问题（纯 LLM 模式） | 回答以"无项目证据"前缀开头（`rag.rs:851` 强制）；RAG 模式无来源时直接报错（`rag.rs:764`） | 语料外问题给出具体事实性结论 |
| C4 引用可追溯 | 对正式实验导出 CSV 抽查回答的每个 `[E]`/`[S]`/`[G]` 引用 | 每条引用都能在对应来源块/图谱关系中找到原文 | 引用编号不存在或指向无关内容 |
| C5 引用审计标记 | 触发引用不足场景 | 回答被标"需要人工复核："前缀，`fallback_reason=needs_review` 落库 | 引用缺失但回答照常输出 |
| C6 非确定性 | 同配置同题连续提问 2 次（temperature>0） | 语义一致但非逐字相同 | 两次逐字相同（疑似缓存/模板） |
| C7 失败不留痕篡改 | 制造一次失败后查 `query_logs` | 失败记录 `error` 字段完整、无回答文本 | 失败记录被改写成成功 |

## 6. 检测域 D：检索与图谱真实性

| 检查项 | 方法 | 通过标准 | 证伪条件 |
| --- | --- | --- | --- |
| D1 向量取证 | 直连 PostgreSQL 查向量表 | 向量维度=1024；块数、语料哈希与冻结报告一致；`index_version=structured-v1` | 维度≠1024；块数与语料不匹配 |
| D2 检索探针 | 用已知事实的固定问题调 RAG 接口（单题探针） | 前 6 个来源块包含预期内容，相关度排序合理 | 来源块与问题无关或顺序反直觉 |
| D3 删除变异 | 删除某来源块并重建索引后再问相关问题 | 该块不再出现，回答随之变化 | 已删除块仍被引用 |
| D4 图谱抽取 | 审核一条含已知实体关系的笔记 | 图谱表中出现对应关系，图谱页面可见 | 关系未出现或出现无关关系 |
| D5 图谱增益 | 对图谱相关问题分别跑普通 RAG 与图谱增强 RAG | 两者来源/回答可区分；图谱增强含图谱来源 | 两模式输出完全一致（图谱注入疑似失效） |
| D6 降级记录 | 制造图谱未命中场景（auto 模式） | `fallback_reason` 落库；强制图谱模式未命中时返回明确错误而非伪造图谱上下文 | 降级不记录；强制模式未命中仍"正常"回答 |
| D7 OCR 真实性 | 上传含已知文本的截图/扫描件 | 识别文本与图内文字吻合；空白图识别结果为空/低置信；未审核文本不出现在 RAG 来源 | 识别结果与图无关；未审核文本已入库 |
| D8 OCR 范围声明 | 对照 `OCR_LANGUAGES` 配置与 README 声明 | RUKOPYS（ukr）仅作跨语种压力测试，不混入中英文部署准确率统计 | 用 ukr 压力测试结果替代生产语种准确率 |

## 7. 检测域 E：公平性审计（防挑选/失盲/不独立）

| 检查项 | 方法 | 通过标准 | 证伪条件 |
| --- | --- | --- | --- |
| E1 题集冻结 | `scripts/validate_human_review_freeze.py docs/experiments/confirmatory-human-review-freeze.json` | ≥3 项目、≥60 题、每项目≥10 题、题号唯一、`question_index` 唯一、五方法完整、model/prompt_version/random_seed/语料规则 SHA-256 齐全 | 任一项缺失；内部题集冒充外部题集 |
| E2 密封时序 | 检查冻结包 git 提交时间与实验开始时间 | 冻结先于实验；冻结后语料/题集未被修改（哈希复核） | 先跑实验后补冻结；冻结哈希与当前文件不一致 |
| E3 评价人独立 | 查冻结包与账号表 | 两名不同评价人、真实 `user_id`、`can_evaluate=true` 且 `can_read/can_write/can_review/can_manage=false` | 评价人同时有数据访问权；同名账号 |
| E4 盲评完整性 | 抽查导出 CSV 与盲评页面 | 方法标签已中性化（`neutralize_answer/neutralize_method_labels/neutralize_blind_text`，`rag.rs:2513-2571`）；条目经 HMAC 盲评 ID 提交 | CSV 含方法名/模式解码信息；存在 `unblinded` 混入记录 |
| E5 条目完整性 | `scripts/summarize_system_reviews.py --expected-reviewers 2` | 每条回答有两位不同评价人、评价人集合一致、负面判断有备注、每题方法齐全 | 任一缺失；脚本停止即 FAIL |
| E6 导出对账 | `scripts/confirmatory_review_completion_gate.py` | 导出条目数 = 冻结题数 × 方法数；`question_index`、方法、评价人 ID 集合与冻结包完全相等；`review_batch_id` 为 `R`+12 位大写 hex；`export_protocol=confirmatory_human_review_v1` | 任一集合不一致；批量号/协议缺失 |
| E7 无挑选 | 对账 DB 实验运行状态与 CSV 行数；检查 run 状态转换记录 | 失败/中断案例保留在 CSV 与日志中；"所有方法 planned case 均完成且无失败"由门禁校验 | 删除了失败案例行；中断被改写为成功 |
| E8 方法公平 | 对比五方法的输入预算 | 同一题集、同一 top_k/提示预算/种子；运行顺序随机化且落库；纯 LLM 基线一并报告 | 各方法预算不同；只报告"表现好的方法" |
| E9 语料饱和诊断隔离 | 核对 `gse111619_kg_holdout_analysis.md` 与报告 | 12 块汇总语料的 run#3 明确标注为诊断，不作为图谱增益证据；内部 984 块评测仅用于开发诊断 | 用饱和/内部诊断结果宣称图谱增益 |
| E10 评价不可篡改 | 评价提交后重查该条目 | 提交后不可修改（接口/DB 验证） | 存在提交后更新的评价记录 |

## 8. 检测域 F：可复现与证据绑定（防证据事后伪造）

| 检查项 | 方法 | 通过标准 | 证伪条件 |
| --- | --- | --- | --- |
| F1 复现运行 | 同种子同配置重跑冻结题集 | 运行顺序与配置哈希一致；`evaluate_rust_retrieval.py` 二次运行加 `--expected-result-sha256` 可复现 | 顺序/哈希不一致；result_sha256 不匹配 |
| F2 provenance 字段 | 抽查实验导出 CSV 与 `query_logs` | 每条含模型、提供方、prompt_version、嵌入/分块/召回参数、来源块与相关度、图谱关系、耗时、token、语料哈希 | 任一声称字段缺失 |
| F3 证据绑定 | 重新校验 `freeze_system_evidence.py`/`freeze_final_maturity_evidence.py` 产物 | 证据 manifest 绑定 git commit、`backend/Cargo.lock`、`frontend/package-lock.json`、镜像 digest、嵌入模型 SHA-256，且 `--verify` 通过 | 绑定缺失或与当前 checkout 不符 |
| F4 干净重放 | 从 clean checkout 构建镜像并重跑检测域 B/C/D 的探针 | 指纹与结果与冻结证据一致 | 重新构建后行为与声称不一致 |
| F5 中断恢复 | 实验中强杀后端，检查 run 状态 | 运行中批次标记 `interrupted`，必须显式续跑；不会自动改写成成功 | 中断批次自动变成成功/终态 |
| F6 门禁一致性 | `/maturity/status` 与 `docs/experiments/main-maturity-gate-latest.json` | 内部门禁 PASS 才允许人工评审；`human_review_allowed` 与门禁文件一致 | 门禁 FAIL 但页面允许评审；门禁文件被替换 |

## 9. 检测流程编排

检测人按以下阶段执行，每阶段产出原始证据后进入下一阶段；任一硬性门槛失败即停止并向被测方开具整改单。

| 阶段 | 动作 | 关键命令/文件 | 产出 |
| --- | --- | --- | --- |
| S0 环境审计 | clean checkout，核对 git revision、`.env`（无演示数据/生产模式）、`docker compose build` 从源码构建 | `git rev-parse HEAD`；`scripts/check_production_config.py` | 环境快照 |
| S1 静态检测 | 检测域 A 的 A1-A5 + C1 代码搜查 | `curl /health`；`curl /metrics`；grep | 指纹与代码取证 |
| S2 运行时真实性 | 检测域 A 的 A6-A7 + 检测域 B 全部 + C6/C7 | tcpdump/记录代理；错误密钥注入；日志对账 | 外呼取证、故障注入记录 |
| S3 行为探针 | 检测域 C 的 C2-C5 + 检测域 D 全部 | 语料变异、删除块、图谱探针、OCR 上传 | 探针记录 |
| S4 公平性审计 | 检测域 E 全部 | `validate_human_review_freeze.py`；`summarize_system_reviews.py`；`confirmatory_review_completion_gate.py` | 盲评审计报告 |
| S5 交叉验证 | 检测域 F 全部 + DB 与 CSV/报告行数对账 | `evaluate_rust_retrieval.py --expected-result-sha256`；manifest `--verify` | 复现与绑定证据 |
| S6 判定与报告 | 汇总各检查项，出具报告 | 本协议第 10 节模板 | 检测报告（含签名） |

建议执行顺序由检测人自行决定，且至少一个环节使用"检测人自选样本"（如随机抽取 30% 导出条目对账），避免被测方预演。

## 10. 判定规则与报告模板

判定分级：

- **通过**：所有硬性门槛（A2/A3/A5/A6、B6/B7、C2/C3、E1-E6、F1-F4）通过，其余检查项无 FAIL。
- **有条件通过**：仅软性项（D8、C6 等）FAIL 且不影响核心声明，限期整改后复核。
- **不通过**：任一硬性门槛 FAIL；或出现"生产使用 hash 嵌入""失败时生成模拟回答""失盲""评价人不独立""案例被删除"类证伪。

报告模板（每检查项一行）：

```text
| 检查项 | 检测方法 | 原始证据文件 | 结论 | 备注 |
| --- | --- | --- | --- | --- |
| A2 嵌入指纹 | /metrics | evidence/metrics-raw.txt | PASS | bge-m3/1024 |
```

报告必须包含：被测 revision、检测时间窗口、每项证据文件 SHA-256 清单、检测人与复核人签名、局限性声明。

## 11. 局限性声明

- 本流程能证明"检测时间窗口内系统行为真实"，不能证明"评价人从未私下交流"（依赖协议遵守 + E3/E10 审计）；正式确认性评审应配合密封命题与第三方监督。
- F4 干净重放受外部依赖影响（DeepSeek 线上模型版本可能变化），重放结果以运行顺序、配置哈希与指纹一致为准，不要求回答逐字一致。
- 检测人若为被测方兼任，报告须明确声明并降级为"自检报告"，不得对外称独立检测。
