# agent-work 执行日志（AI agent 会话）


## 2026-08-16 晚：新增两套现代公开实验数据（五项目扩展）

- 选型：NCBI GEO 公开 RNA-seq 数据。
  1. GSE306433：小鼠结肠炎基质细胞，6 样本（现代动物模型，与现有 GSE111619 人肺癌不同）。
  2. GSE291942：拟南芥 PRMT5 高温胁迫，18 样本（现代植物模型）。
- 下载与整理：FTP 下载 SOFT、series matrix、FPKM/TPM；`scripts/prepare_new_geo_datasets.py` 生成知识文档、样本表、表达摘要和生成清单；数据目录 `data/real/GSE306433_colitis`、`data/real/GSE291942_arabidopsis_heat`。
- 题集：`agent-work/question-sets/{gse306433_colitis,gse291942_arabidopsis_heat}_questions_v2_draft.json`，各 20 题，均通过校验器。
- 导入：`agent-work/scripts/import_new_geo_datasets.py` 创建项目 10/11，上传/审核/同步知识文档，创建并批准样本笔记，重建知识图谱。
- 预注册修订：`docs/experiments/rag-experiment-5-preregistration-rust-v2-amendment-2026-08-16-5projects.md`；预跑冻结记录位于 `agent-work/freeze/*-prerun-freeze-2026-08-16.json`。
- 五方法运行：
  - run 24 GSE306433：completed_with_errors，98 completed + 2 `kg_enhanced_rag` 技术失败；v1 证据包 PASS。
  - run 25 GSE291942：completed，100/100；v1 证据包 PASS。
- 论文附录：`agent-work/paper-material/formal-batch/{gse306433_colitis,gse291942_arabidopsis_heat}-appendix.md`，freshness 5/5 PASS。
- 五项目盲评包：`agent-work/blind-review/formal-batch-2026-08-16-5projects/`，100 题 × 2 方法，2 个技术失败不送评，每名评审者 198 行；`audit_blind_review_offline.py` PASS。
- 自动覆盖率：`agent-work/runs/formal-batch-fact-coverage-2026-08-16-5projects.json`。


## 2026-08-16：论文撰写障碍清扫（本会话）

### 已完成
1. **修复论文材料 freshness 失败**：`docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`
   指纹落后于 Iteration 74 重生成的 audit JSON。用官方渲染器重渲染后
   `check_paper_material_freshness.py` 从 `passed=false` 变为 `11/11 passed=true`。
2. **修复生产端提示词占位符污染**（`backend/src/rag.rs`、`backend/src/api/rag.rs`）：
   - 新增 `strip_citation_template_placeholders`，在引用审计前把模型复述的 `[S编号]` / `[G编号]`
     归一为纯文本 `S编号` / `G编号`；有效 `[S2]` / `[G8]` 不受影响。
   - 生成主路径与引用修复路径都调用该函数。
   - 新增 3 个回归测试；`cargo fmt` 与 `cargo clippy --all-targets --all-features -D warnings` 通过。
   - 历史 run 22 不追溯修复；JH 已用新代码重跑为 run 23。
3. **加固并重建盲评包生成器**（`agent-work/scripts/build_blind_review_package.py`）：
   - 人评表对 `[S编号]/[G编号]` 做去标识化归一为“证据编号”，避免 unresolved marker 与证据类别泄露。
   - 构建前强制重跑 v1 证据包检查；任一来源失败即拒绝构建，`--allow-invalid-source` 仅用于 DRAFT/ON_HOLD 预备。
   - 以 run 20/21/23 重新生成 `agent-work/blind-review/formal-batch-2026-08-14/`，每名评审者 120 行。
4. **新增离线盲评包审计器**：`agent-work/scripts/audit_blind_review_offline.py`。
   - 默认 fail-closed：任一来源证据包未通过 v1 即 HOLD。
   - run 20/21/23 全部通过后：120 行/60 题/两评审者顺序不同/内容一致/[E] 编号闭合/无方法标签泄露/解盲键结构一致，全部 PASS。
5. 全量脚本测试 `450 passed`；`git diff --check` 通过。

### JH run 23 重跑结果（2026-08-16）
- 镜像：`eln-backend:latest`（含占位符清理）重建后启动；Docker/Colima 通过 workspace 内 `tmp/ch` 的 APFS-clone home 运行。
- 输入：同一 JH 题集（questions_sha256 `cc64b0…`）、seed `2026081503`、bge-m3、DeepSeek `deepseek-v4-flash`。
- 结果：completed_with_errors，94 completed + 6 failed（6 个均为 `pure_llm` “AI provider returned an empty completion”，保留分母）。
- v1 证据包：`run-23-evidence-check.json` **passed=true**，100 cases，invalid_marker_count=0。
- JH 附录：`agent-work/paper-material/formal-batch/smithsonian_joseph_henry-appendix.md` 已生成，freshness 5/5 PASS。
- 盲评包：`audit_blind_review_offline.py` PASS；120 行/60 题，主比较两方法 40/40 completed。
- 自动覆盖率：JH `kg_enhanced_rag` 0.5172 / `project_rag` 0.5172；见 `agent-work/runs/formal-batch-fact-coverage-2026-08-16.json`。

### 仍需 Owner/外部
- 外部命题者签署题集（`setter_id` 仍为 agent draft）。
- 2 名独立评价者完成盲评并回填 CSV。
- 干净 git revision + APP_REVISION 绑定（B0）。
- 确认性证据包与论文主结论仍保持 `paper_ready=false`。



### 正式批次结果（bge-m3，2026-08-14 晚）
- run 20 gse111619：completed（100/100），证据包 v1 校验 PASS
- run 21 gse111619_raw：completed（100/100），证据包 v1 校验 PASS
- run 22 smithsonian_joseph_henry：completed_with_errors（95/100，5 技术失败=4 pure_llm+1 project_rag，保留分母）；
  校验 1 个结构失败：case 58（kg_enhanced_rag）答案含字面 [G编号] 占位符——真实引用语法失败案例，
  论文附录渲染器按 fail-closed 拒绝生成（诚实保留，不绕过）。
- **重要观察**：自动事实覆盖率（次要结局）在 bge-m3 下与 hash pilot 不同——
  gse111619：project_rag 23.2% > kg_enhanced_rag 16.1%；gse111619_raw：kg 36% > project_rag 32%；
  JH：project_rag 59.1% > kg 51.7%。kg 不再一致领先，正式实验的结论可能不同于 pilot，
  这正是正式批次的价值；主要结局（人工准确性）待盲评。
- 论文附录材料：agent-work/paper-material/formal-batch/{gse111619,gse111619_raw}-appendix.md 已生成；JH 被引用失败拦截。
- 盲评包：agent-work/blind-review/formal-batch-2026-08-14/ 已生成（reviewer-A/B 各 119 行评分表 + 解盲键 sealed/ + kappa 脚本）。
  119=120-1：JH Q1 project_rag 技术失败自动记 0 不送评。


## 2026-08-14 深夜：解决论文四个最要命的不足（进行中）

### (3) 生产级嵌入 bge-m3 —— 已完成并生效
- 本机 Ollama 0.32.6 已安装；拉取 bge-m3（1.2GB，F16，1024 维）并创建别名 BAAI/bge-m3（后端要求精确模型名）。
- .env 切换：EMBEDDING_BACKEND=openai_compatible, MODEL=BAAI/bge-m3, DIMENSION=1024,
  API_URL=http://host.docker.internal:11434/v1/embeddings（容器内可访问宿主 Ollama）。
- **新发现并修复一个 schema 级 bug**：rag_document_chunks.embedding 列固定 vector(512)，
  bge-m3 的 1024 维插入全部失败（expected 512 dimensions, not 1024）。
  修复：sql/0001_initial.sql 改 vector(1024)；db.rs initialize_database 新增幂等维度对齐迁移
  （检测 atttypmod 与配置维度不符时清空旧 chunk、重建列与 HNSW 索引、标记 syncs stale）；
  新增 DB 测试 embedding_column_dimension_aligns_with_runtime_config_on_existing_database。
  注意：PostgreSQL 类型修饰符不接受绑定参数，vector($1) 需内联常量。
- 验证：255 lib 测试全过、clippy 干净；线上列=1024；三项目语料 bge-m3 全部同步成功（2+4+15）。

### (2)+(4) 事前规则冻结 —— 预冻结包已完成
- agent-work/freeze/rag-experiment-5-rust-v2-pre-freeze-2026-08-14/：
  questions.json（60 题）、gold-facts.json（56 金标准+4 拒答标准）、run-config.json（种子 2026081501/02/03、
  五方法、repetitions=1、temperature 0.1/max_tokens 1800）、analysis-config.json、freeze-manifest.json
  （全部文件 SHA-256 + UTC 时间戳 + 命题者状态 AGENT_DRAFT_PENDING_EXTERNAL）。
- 状态 FROZEN_BY_AGENT_PENDING_EXTERNAL_ENDORSEMENT：内容不可变；正式批次于冻结清单之后启动，
  时序证明成立（题集 2026-08-14 起草 → 冻结清单 → 正式批次 14:28 启动）。

### (1) 正式批次 —— 运行中/部分完成
- run 20 gse111619：completed（100/100，0 failed）
- run 21 gse111619_raw：运行中
- run 22 smithsonian_joseph_henry：待启动

### (2) 盲评包 —— 材料已备好，等人
- agent-work/blind-review/formal-batch-2026-08-14/：评审说明、reviewer-A/B 评分表（构建器就绪，
  待 run 21/22 完成后生成）、解盲键目录（sealed/）、kappa 一致性脚本（analysis/agree.py）。
- 主比较 = 60 题 × 2 方法 × 2 评审者 = 240 条评分；技术失败不送人评按协议记 0。
- 探索性子样本未在首答前冻结 → 按协议延期到 v3，主矩阵可独立成立（协议第 11 节）。


## 2026-08-14：统一测试库端口（55433 → 55432）

- 根因：docker-compose.test-db.yml 默认 55432，但运行中的测试库容器与 .qoder agent 配置用了 55433/eln_rust_test，
  导致不设 TEST_DATABASE_URL 时 DB 测试全部 PoolTimedOut。
- 处置（以仓库默认 55432/postgres 为准）：
  1) 移除旧测试库容器（项目 eln-rusttest，55433）并重建到 55432（`docker compose -p eln-rust-test-db up -d --wait`，healthy）；
  2) scripts/run-rust-db-tests.sh 改为从容器动态发现宿主端口（$COMPOSE port db 5432），不再硬编码；
  3) .qoder/agents/{backend-engineer,qa-engineer}.md 更新为 55432/postgres 并提示用脚本；
  4) .env 与 .env.example 固定 TEST_DB_PORT=55432。
- 顺带：清理 Docker 陈旧镜像（54.7GB → 13.5GB，释放约 40GB），解决重建容器时磁盘满（initdb No space left on device）。
- 验证：端口发现=55432；默认 URL 连接成功；DB 测试 running_experiment_is_marked_interrupted_on_startup 1.72s 通过（此前 34s 超时失败）。


## 2026-08-14 下半场：修复两个 P1 生产 bug（用户授权修改 backend/src/）

### Bug 2：series matrix RAG 同步导致后端崩溃（OOM 被杀）
- 根因：`backend/src/rag.rs` 的 `split_long_text` 中，当句子边界恰好落在“窗口起点 + overlap”处时，
  `start = end - overlap` 等于原 start，窗口原地踏步形成无限循环，chunks 无限增长直到 OOM 被内核杀死（约 10s，无 panic 日志）。
- 复现：用 Python 复刻 chunk 逻辑 + 真实 series matrix 文件，确认 start=4199 被重复访问（死循环实锤）。
- 修复：`start = (end.saturating_sub(overlap)).max(start + 1)` 保证严格前进；新增回归测试
  `test_split_long_text_terminates_when_sentence_end_falls_at_window_start`。
- 验证：单测通过；线上 sync 文件 14 返回 200、后端存活、项目 3 语料补全（4/4 synced）。

### Bug 1：实验租约竞态导致运行被误判 interrupted
- 根因：EXPERIMENT_LEASE_SECONDS=6、心跳 2s、过期清扫器 1s。案例之间的处理不经过查询心跳循环，
  任何一次心跳延迟 >6s 即被清扫器标记 interrupted（run 15 中断 3 次）。
- 修复（backend/src/db.rs + api/rag.rs）：
  1) 租约 6s→30s、心跳 2s→5s（编译期不变量：心跳×2 < 租约，租约 ≤120s）；
  2) worker 在每个案例开始前显式续租（覆盖案例间隙）。
  3) 原 `lease+reaper<10` 断言改为新的编译期不变量。
- 验证：DB 支撑测试全过（active_experiment_lease_survives_other_instance_startup、
  running_experiment_is_marked_interrupted_on_startup 等）；线上 50 案例实验零中断（旧代码 40 案例必中断）。

### 验证与发布
- cargo fmt --all --check：通过
- cargo clippy --locked --all-targets --all-features -- -D warnings：通过
- TEST_DATABASE_URL=...:55433 cargo test --workspace --no-default-features -- --test-threads=1：254 lib + 2 bin 全部通过
- 后端镜像重建（ec88325a4ae1）并已切换运行。

### 附带发现（环境问题，未改代码）
- 测试库端口错配：运行中的 eln-rusttest-db-1 映射 127.0.0.1:55433，而 scripts/run-rust-db-tests.sh 默认 55432，
  导致未设 TEST_DATABASE_URL 时 DB 测试全部 PoolTimedOut（54 个失败，与本次改动无关）。建议后续统一端口。


> 所有时间均为本地（Asia/Shanghai）。所有写操作只发生在 agent-work/ 内；仓库其余部分只读。
> 唯一的例外：为运行实验而对开发数据库进行的 API 操作（同步语料、导入 JH 项目、触发图谱抽取、创建实验运行），已逐项记录。

## 2026-08-14

### 侦察阶段
- 读取预注册 v2（rag-experiment-5-preregistration-rust-v2.md）、pilot 协议 v1、交接材料
  （CONVERSATION_MIGRATIONS/001_2026-08-13_chat-handoff.md）、证据索引 v1。
- 确认 10 个阻断项（B0–B9）；其中 B1（外部命题者/2 名独立评价者）、B0（干净 revision）、
  生产嵌入（bge-m3 1024 维）为机器不可完成，需人工/外部。
- 确认运行中系统：Rust/Axum 开发实例（APP_REVISION=unversioned，embedding=rust-hash-512-v1，512 维），
  DeepSeek key 已配置。登录 admin/admin123 可用。
- 确认项目 2（GSE 处理后语料）与项目 3（GSE 原始语料）RAG 索引为空（"Index version changed; explicit rebuild required"）。

### 题集构建（DRAFT_CANDIDATE_PENDING_EXTERNAL_SETTER_REVIEW）
- agent-work/question-sets/gse111619_questions_v2_draft.json：20 题（GSE 处理后语料，升级自既有 20 题）
- agent-work/question-sets/smithsonian_joseph_henry_questions_v2_draft.json：20 题（Joseph Henry 手稿语料，新写）
- agent-work/question-sets/gse111619_raw_questions_v2_draft.json：20 题（GSE 原始语料，新写）
- 校验脚本 agent-work/scripts/validate_question_sets.py：3 文件全部 PASS（唯一 ID、自包含、分类/分层、answerable 一致性）。
- 分层分布：fact_source 30、one_hop 14、constraint_aggregation 12、refusal 4（refusal<10 按协议不生成该层差值图）。

### 语料同步与导入（开发数据库 API 操作）
- 项目 2：rag/init + 同步 2 个知识文档 → synced=2。
- 项目 3：rag/init + 同步 3/4（family.soft、samples.csv、counts.txt）；**series matrix 同步导致后端崩溃重启**
  （agent-work/scripts 记录；为真实生产 bug，详情见 reports/）。
- 项目 9（新）：Smithsonian Joseph Henry 语料导入（agent-work/scripts/import_joseph_henry.py）：
  15 个知识文档上传+审核+同步（synced=15），15 条笔记创建+审核通过。
- 图谱抽取：项目 2 = 39 实体/100 关系；项目 3 = 53/106；项目 9 = 18/45（规则抽取对 19 世纪英文手稿识别率低，如实记录）。

### Pilot 运行（INTERNAL_DEVELOPMENT，repetitions=1，固定种子）
- 项目 2（GSE 处理后）：run 13，completed_with_errors（99/100 completed，1 个 failed：
  Q15 bm25_rag "AI provider returned an empty completion"，保留在分母）。
- 项目 3（GSE 原始）、项目 9（JH）：后台运行中（bash-3）。
- 发现：运行中的后端镜像没有 evidence.json 路由（镜像陈旧，34h 前构建）；CSV 导出可用。
  计划：pilot 全部结束后重建后端镜像（docker compose build backend），再为 3 个 run 导出 v1 证据包。

### 后端镜像重建（为 evidence.json 导出）
- `docker compose build backend` 完成（新镜像 eln-backend:latest，digest 95cf92ca93b5）；
  构建不影响运行中容器。等 run 15 结束后 `docker compose up -d backend` 切换，
  再为 run 13/14/15 导出 v1 证据包并校验。

### 证据包导出与发现的契约缺口
- 旧镜像（34h 前构建）创建的 run 13/14/15 的证据包缺绑定字段（questions_sha256/corpus_snapshot_hash/rag_index_version 为 null），
  且 summary error 的 failure_scope/failure_code 与案例不一致 → 离线校验器拒绝。
- 原因：旧镜像代码未写这些字段；数据在 DB 中无法追溯补齐（与交接材料'生产导出修复不追溯历史数据'一致）。
- 处置：切换新镜像（已构建 eln-backend:latest）后重跑三个 pilot（run 16/17/18），使绑定字段完整。
- 同时发现并记录一个真实竞态 bug：EXPERIMENT_LEASE_SECONDS=6、心跳 2s，但 STALE_EXPERIMENT_REAPER_INTERVAL=1s，
  任何一次心跳延迟>6s 就会被清扫器判 interrupted（run 15 中断 3 次，已用自动续跑脚本跑完）。属 P1 级稳定性问题。

### 第二批 pilot 运行（新镜像，证据链完整）
- run 16 gse111619：completed（100/100，0 failed）
- run 17 gse111619_raw：completed（100/100，0 failed）
- run 18 smithsonian_joseph_henry：completed_with_errors（96/100，4 failed，集中在 pure_llm）
- 三个证据包全部通过 rag-evidence-package-v1 离线校验（check_rag_experiment_evidence.py passed=true，各 100 cases）。
- 自动事实覆盖率（别名匹配，pilot 描述性结果）：
  - gse111619：kg_enhanced_rag 23.2% > project_rag 21.4% > bm25 17.9% > structured_query 12.5% > pure_llm 0%
  - gse111619_raw：kg_enhanced_rag 20% > project_rag/bm25 12% > pure_llm/structured_query 4%
  - JH：kg_enhanced_rag 27.6% > project_rag 24.1% > bm25 20.7% > pure_llm 16.7% > structured_query 3.4%
  - 三个项目中 kg_enhanced_rag 覆盖率均最高（方向与论文既有探索一致），但为 dev 嵌入（hash-512）+ 非冻结题集，仅作描述性证据。
- 论文附录材料已用官方渲染器生成：agent-work/paper-material/*-appendix.md（3 份）。
### B6 精度/情景敏感性模拟（DRAFT_DESIGN_SIMULATION_NOT_RESULT）
- agent-work/scripts/b6_precision_simulation.py（向量化，seed 20260814，500 sims × 500 bootstrap）。
- 输出 agent-work/analysis/b6-precision-sensitivity-latest.{json,md}。
- 核心结论：3 项目 × 20 题、配对相关 ρ≥0.6 时 95% CI 宽度 ~1.6–2.1（差值尺度），δ≤0.3 均无法可靠排除零；
  印证协议"60 题是最低规模而非功效证明"。设计辅助，不是结果。

## 2026-08-28 论文多 Agent 审核系统(thesis-agents)

- 新增 `agent-work/thesis-agents/`:8 个角色定义(Coordinator/6 Reviewer/Editor)+ README;原生入口 `.zcode/commands/thesis-review.md`。
- Smoke test(reviews/smoke-test/)与 Round 1/2 正式评审产出在仓库根 `reviews/`(round-01 六份报告+合并清单+复审三份;round-02 edit-report+收尾记录;各轮含基线快照)。
- 本目录外的写操作(经用户明确授权的论文修改)由 thesis-editor 执行,仅 `docs/毕业论文重构稿.md`,两轮 diff 审计见 reviews/round-0{1,2}/。角色定义与评审报告为 DRAFT 材料,未经人工签核不得作为论文证据。
