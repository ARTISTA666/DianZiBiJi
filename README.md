# 智能电子实验笔记系统

面向科研过程管理与论文实验验证的 ELN 系统，包含权限、审批、实验笔记、资料库、知识图谱、本地 RAG、DeepSeek 问答、固定任务智能体和成对对照实验。

后端已完整迁移到 Rust 1.88 + Axum，认证、权限、项目、实验笔记、文件/OCR、检索、知识图谱、RAG、智能体与成熟度门禁均由单个 Rust 进程直接执行，不再启动或代理 Python/FastAPI 服务。接口路径、请求/响应结构、PostgreSQL 数据库和前端保持不变；响应头 `x-backend-runtime: axum` 可用于确认运行时。

工程协作采用分工明确的多 Agent 组织与独立发布复审，分层、所有权、RACI 和门禁见 [工程 Agent 组织、分类与发布责任制](docs/engineering-agent-organization.md)。

## AI 架构

- 文档解析：TXT/Markdown/CSV/TSV/SOFT/JSON/XML/HTML/PDF，以及上述文本格式的 gzip 压缩文件
- 文本分块：可配置块大小与重叠长度
- 嵌入实现：`rust-hash-512-v1`（纯 Rust、确定性、512 维）
- 生成推理：Rust 后端通过 HTTPS 调用 DeepSeek 官方 OpenAI 兼容接口
- 向量存储：PostgreSQL 16 + pgvector
- 检索：向量相似度与词法相关度混合排序；普通问题返回 6 个资料块，集合型问题可扩展到 12 个
- 图谱增强：按问题匹配相关实体关系，未命中时显式降级
- 生成模型：DeepSeek 官方 OpenAI 兼容接口
- 实验复现：保存模型、提示词版本、检索参数、语料哈希、耗时和 token 用量
- 实验执行：支持固定随机种子、随机运行顺序和每个“问题—模式”重复运行
- 长任务：实验提交后进入后台队列，页面轮询进度；后端异常重启会将运行中的批次标记为 `interrupted`，必须显式续跑

系统不会在 AI 服务失败时生成模拟回答。失败会返回明确错误并写入日志。

## 服务地址

- 前端：http://localhost:3000
- 后端：http://localhost:8001
- 后端存活检查：http://localhost:8001/health
- 后端就绪检查：http://localhost:8001/ready（同时检查 PostgreSQL 与持久存储）
- 后端运行指标：http://localhost:8001/metrics（请求数、状态码分组、in-flight、平均/最大/p95 延迟）

## 开发环境初始账号

```text
账号：admin
密码：admin123
```

该账号仅由 `.env` 中的开发配置创建。生产环境必须关闭演示数据、替换初始密码和签名密钥；登录页不会展示或预填初始凭据。

## 配置

复制 `.env.example` 为 `.env`，至少配置：

```env
APP_ENV=production
SECRET_KEY=replace-with-at-least-32-random-characters
BOOTSTRAP_ADMIN_PASSWORD=replace-with-at-least-12-characters
POSTGRES_PASSWORD=replace-with-at-least-12-characters
SEED_DEMO_DATA=false
CORS_ORIGINS=https://eln.example.org
NEXT_PUBLIC_API_BASE_URL=/api
DEEPSEEK_API_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=your-official-api-key
DEEPSEEK_MODEL=deepseek-v4-flash
EMBEDDING_BACKEND=hash
EMBEDDING_MODEL=rust-hash-512-v1
EMBEDDING_DIMENSION=512
APP_REVISION=0123456789abcdef0123456789abcdef01234567
```

DeepSeek 密钥只注入后端容器，不会传给前端。

生产模式会在启动时强制校验上述安全项；仍使用默认签名密钥、默认数据库/管理员密码、空 AI 密钥、未设置发布版本或启用演示数据时，后端拒绝启动。退出、管理员重置密码和用户自助改密都会使旧访问令牌失效。

生产公网入口应放在 TLS 反向代理之后。仓库提供 [deploy/nginx.conf.template](deploy/nginx.conf.template)，包含 HTTP→HTTPS、证书占位符、HSTS、上传体积限制、反代超时、`X-Forwarded-*` 和 `X-Request-ID` 透传。使用前必须替换 `${ELN_DOMAIN}`、`${TLS_CERT_PATH}`、`${TLS_KEY_PATH}`、`${CLIENT_MAX_BODY_SIZE}`、`${BACKEND_PORT}` 和 `${FRONTEND_PORT}`，并运行：

```bash
backend/.venv/bin/python scripts/check_reverse_proxy_config.py \
  --output docs/system-evidence/reverse-proxy-latest.json
```

密钥轮换流程见 [docs/operations/secret-rotation.md](docs/operations/secret-rotation.md)，覆盖 `SECRET_KEY`、管理员/用户密码、`POSTGRES_PASSWORD` 和 `DEEPSEEK_API_KEY` 的备份、变更、验证、回滚和旧凭据撤销。修改该手册后运行：

```bash
backend/.venv/bin/python scripts/check_secret_rotation_runbook.py \
  --output docs/system-evidence/secret-rotation-latest.json
```

`SYSTEM_STORAGE_PATH` 指定上传文件的宿主持久化目录，默认是 `./storage`；容器内后端使用 `STORAGE_ROOT=/storage`，非容器运行和测试可指向独立可写目录。数据库和该目录必须作为同一恢复点管理。正式发布的 `APP_REVISION` 必须是与证据清单一致的 40 或 64 位小写 Git revision。

`UPLOAD_MAX_BYTES` 限制原始上传体积，超限文件和数据库写入失败的文件不会残留在存储目录。`DOCUMENT_TEXT_MAX_CHARS` 控制单个文件返回和入库的最大字符数，超过上限时系统会明确标记截断。`OCR_LANGUAGES` 控制 Tesseract 语言，业务默认值为 `chi_sim+eng`，面向中文和英文实验记录、标签及仪器截图；`OCR_PREPROCESSING` 默认使用 `grayscale_otsu`，`OCR_PAGE_SEGMENTATION_MODE` 默认值为 `3`。识别原文和校对文本分别保存，只有经审核人确认的图片文本才能进入 RAG 知识库。RUKOPYS 实验单独使用 `ukr` 配置，只是乌克兰语连续手写体的跨语种压力测试，不代表中英文部署准确率。

## 启动

macOS 或 Linux：

```bash
cd /path/to/full-system
cp .env.example .env
docker compose up -d --build
```

Windows PowerShell：

```powershell
Set-Location C:\path\to\full-system
Copy-Item .env.example .env
docker compose up -d --build
```

项目使用同一套 Docker 配置，不需要维护 Windows 和 macOS 两套代码。Compose 默认构建生产前端并通过 `next start` 运行，不挂载源代码或使用开发服务器；代码变更后需要重新构建镜像。

后端构建镜像固定使用 `rust:1.88-slim-bookworm`，仓库中的 `backend/rust-toolchain.toml` 同时把本地工具链固定为 Rust 1.88.0。纯 Rust 哈希嵌入无需下载模型。

## 备份与恢复

创建一致性系统备份（执行时短暂停止前后端写入）：

```bash
scripts/backup-system.sh
```

备份同时包含 PostgreSQL 自定义格式 dump、上传文件归档、发布版本与 SHA-256 清单。恢复会替换当前数据，因此必须显式确认；脚本会先生成一份恢复前回滚包，并在恢复后等待 `/ready`：

```bash
scripts/restore-system.sh backups/eln-YYYYMMDDTHHMMSSZ --confirm-replace
```

详细操作、验证记录和未覆盖风险见 [docs/operations/backup-restore.md](docs/operations/backup-restore.md)。该手册同时定义加密、异地复制、保留周期、RPO/RTO 和恢复抽检要求，可用以下命令预检：

```bash
backend/.venv/bin/python scripts/check_backup_policy.py \
  --output docs/system-evidence/backup-policy-latest.json
```

本地备份尚不等于异地灾备；生产使用前仍需真正落实加密对象存储或离机副本。

## 论文对照实验

1. 登录系统并进入目标项目的“资料库”。
2. 初始化 AI 知识库。
3. 将审核通过的资料执行“本地向量入库”。
4. 在“论文对照实验”中逐行输入问题。
5. 设置重复次数（确认性实验建议至少 3 次）和预先冻结的随机种子。
6. 系统按纯 LLM、BM25 RAG、混合 RAG、直接结构化查询和图谱增强 RAG 五种方法随机化“问题—模式—重复”执行顺序，并保存实际顺序和配置哈希。提交成功只表示已进入后台队列，页面可安全离开；运行中断后必须在实验记录中显式续跑。
7. 只有批次到达终态后才能导出 CSV，并由独立评价人通过方法隐藏入口评价准确性、可追溯性和 1-5 分质量。五方法入口可运行不等于确认性实验已经完成。

模拟数据脚本不再生成 AI 问答、评价或智能体结果，论文统计应只使用真实接口运行产生的数据。

详细配置与复现方法见 [docs/ai-rag-setup.md](docs/ai-rag-setup.md)。
人工试评与正式确认性评审的启动条件见 [docs/experiments/human-review-readiness-2026-07-16.md](docs/experiments/human-review-readiness-2026-07-16.md)。

## GSE111619 真实数据导入

先检查本地文件、样本映射和 GEO 压缩包哈希，不写入系统：

```bash
backend/.venv/bin/python scripts/import_gse111619_via_api.py --dry-run
```

系统启动后，通过正式 API 创建项目、提交和审核 4 条样本笔记、上传 6 份来源文件、构建图谱并同步知识库：

```bash
ELN_PASSWORD=admin123 backend/.venv/bin/python scripts/import_gse111619_via_api.py --verify-query
```

导入过程可重复执行；同名同哈希文件会复用，同名但内容不同的文件会被拒绝。验证报告写入 `data/real/GSE111619/system_import_report.json`。

执行 20 个固定问题、普通 RAG 与图谱增强 RAG 的正式成对实验：

```bash
backend/.venv/bin/python scripts/run_gse111619_experiment.py --dry-run
ELN_PASSWORD=admin123 backend/.venv/bin/python scripts/run_gse111619_experiment.py
```

正式结果写入 `data/real/GSE111619/gse111619_paired_experiment.csv` 和 `gse111619_paired_experiment_report.json`。`validation_report.*` 仅为独立 SQLite/测试向量后端的离线预检，不得作为部署系统效果引用。

run #3 使用只有 12 个向量块的汇总语料，两种模式均达到 56/56 事实覆盖，属于语料饱和诊断，不能用于证明图谱增益。为避免这一问题，系统另建了只索引 GEO 原始资料的内部冻结评测项目：

```bash
ELN_PASSWORD=admin123 backend/.venv/bin/python scripts/import_gse111619_via_api.py --benchmark
ELN_PASSWORD=admin123 backend/.venv/bin/python scripts/run_gse111619_experiment.py --benchmark
```

内部评测 run #4 使用 984 个原始语料块和 12 道项目内部冻结的问题。普通 RAG 命中 9/32 个预设事实，图谱增强 RAG 命中 25/32 个。这是自动文本匹配结果，不是答案准确率。题目和规则由项目开发方编写，因此该结果只用于开发诊断，不作为论文的最终效果证据。完整账目和限制见 `data/real/GSE111619/gse111619_kg_holdout_analysis.md`。

## 验证

macOS 或 Linux 本地开发环境：

```bash
docker compose build backend

cd backend
cargo +1.88.0 fmt --all --check
cargo +1.88.0 clippy --all-targets -- -D warnings
cargo +1.88.0 test --all-targets --locked

cd ../frontend
npm run lint
node node_modules/next/dist/bin/next build --webpack

cd ..
# 可选：验证仓库中不参与服务运行的离线证据脚本
backend/.venv/bin/python -m pytest -q scripts/test_*.py
docker compose config --quiet
npm --prefix frontend audit --omit=dev --audit-level=low
```

使用本机 `.env` 中的真实 DeepSeek 密钥执行不落盘提示词/回答的最小回归：

```bash
backend/.venv/bin/python scripts/validate_real_llm.py
```

该脚本只覆盖指令遵循、无证据拒答和单一证据引用三条微型用例，不能替代冻结语料回归。最近一次结果与限制见 [docs/experiments/real-llm-regression-2026-07-16.md](docs/experiments/real-llm-regression-2026-07-16.md)。

项目成熟度门禁汇总内部自动证据，不等于独立人工评审。当前门禁要求同时具备：

- GSE111619 固定题集的检索指标；
- 真实 DeepSeek holdout 实验（五方法完整覆盖，所有方法 planned case 均完成且无失败，再检查 KG 模式事实覆盖、精确率和引用标记）；
- 固定任务型 Agent 探针（实验摘要、周报、阶段报告、图谱概览均覆盖，且零失败、零需复核、零无效引用）；
- 运行态/schema/OCR 语言检查；
- 浏览器端到端流程；
- 短并发读 smoke；
- 运行指标端点；
- 备份包 hash、`pg_restore --list` 可读性验证、隔离恢复演练和灾备策略手册。
- 监控告警探针，检查 `/ready`、错误率、in-flight 和 p95 延迟。
- 反向代理/TLS 模板预检。

一条可复跑的本地验证链如下：

```bash
E2E_BROWSER_CHANNEL=chrome npm --prefix frontend run test:e2e
npm --prefix frontend audit --omit=dev --audit-level=low --json \
  > docs/system-evidence/npm-audit-latest.json
cargo +1.88.0 build --manifest-path backend/Cargo.toml --release --locked
backend/.venv/bin/python scripts/check_production_config.py \
  --env-file .env \
  --rust-config-checker backend/target/release/eln-backend \
  --output docs/system-evidence/production-config-latest.json
backend/.venv/bin/python scripts/check_secret_hygiene.py \
  --output docs/system-evidence/secret-hygiene-latest.json
backend/.venv/bin/python scripts/check_secret_rotation_runbook.py \
  --output docs/system-evidence/secret-rotation-latest.json
backend/.venv/bin/python scripts/check_backup_policy.py \
  --output docs/system-evidence/backup-policy-latest.json
backend/.venv/bin/python scripts/check_reverse_proxy_config.py \
  --output docs/system-evidence/reverse-proxy-latest.json

ELN_PASSWORD=admin123 backend/.venv/bin/python scripts/load_smoke.py \
  --api-base http://127.0.0.1:8001 \
  --username admin \
  --password admin123 \
  --requests 90 \
  --concurrency 10 \
  --max-p95-ms 2000 \
  --output docs/system-evidence/load-smoke-latest.json

backend/.venv/bin/python scripts/check_monitoring_alerts.py \
  --api-base http://127.0.0.1:8001 \
  --max-p95-ms 2000 \
  --max-error-rate 0.01 \
  --max-in-flight 50 \
  --output docs/system-evidence/monitoring-alerts-latest.json

ELN_PASSWORD=admin123 backend/.venv/bin/python scripts/soak_smoke.py \
  --api-base http://127.0.0.1:8001 \
  --username admin \
  --password admin123 \
  --requests 30 \
  --concurrency 5 \
  --duration-seconds 60 \
  --interval-seconds 30 \
  --max-p95-ms 2000 \
  --output docs/system-evidence/soak-smoke-latest.json

scripts/backup-system.sh /private/tmp/eln-maturity-backup-$(date -u +%Y%m%dT%H%M%SZ)

BACKUP_DIR=$(ls -td /private/tmp/eln-maturity-backup-* | head -1)
backend/.venv/bin/python scripts/restore_drill.py "$BACKUP_DIR" \
  --output docs/system-evidence/restore-drill-latest.json

backend/.venv/bin/python scripts/export_validation_evidence.py \
  --retrieval-report data/real/GSE111619/main-retrieval-evaluation/report.json \
  --playwright-results output/playwright/results.json \
  --backend-url http://127.0.0.1:8001/health \
  --metrics-url http://127.0.0.1:8001/metrics \
  --frontend-url http://127.0.0.1:13000 \
  --backup-dir "$BACKUP_DIR" \
  --verify-backup-dump \
  --restore-drill-report docs/system-evidence/restore-drill-latest.json \
  --load-smoke-report docs/system-evidence/load-smoke-latest.json \
  --restart-recovery-report output/playwright/restart-recovery.json \
  --soak-smoke-report docs/system-evidence/soak-smoke-latest.json \
  --npm-audit-report docs/system-evidence/npm-audit-latest.json \
  --production-config-report docs/system-evidence/production-config-latest.json \
  --secret-hygiene-report docs/system-evidence/secret-hygiene-latest.json \
  --secret-rotation-report docs/system-evidence/secret-rotation-latest.json \
  --backup-policy-report docs/system-evidence/backup-policy-latest.json \
  --monitoring-alerts-report docs/system-evidence/monitoring-alerts-latest.json \
  --reverse-proxy-report docs/system-evidence/reverse-proxy-latest.json \
  --output-dir docs/system-evidence

ELN_PASSWORD=admin123 backend/.venv/bin/python scripts/validate_agent_probe.py \
  --api-base http://127.0.0.1:8001 \
  --username admin \
  --password admin123 \
  --report data/real/GSE111619/main_v8_agent_probe_report.json

backend/.venv/bin/python scripts/freeze_system_evidence.py --replace
backend/.venv/bin/python scripts/freeze_system_evidence.py \
  --verify output/release-evidence/maturity-evidence-manifest.json

backend/.venv/bin/python scripts/release_maturity_gate.py \
  --retrieval-report data/real/GSE111619/main-retrieval-evaluation/report.json \
  --experiment-report data/real/GSE111619/main_v8_kg_holdout_experiment_report.json \
  --agent-report data/real/GSE111619/main_v8_agent_probe_report.json \
  --system-evidence-report docs/system-evidence/validation-results.json \
  --evidence-manifest output/release-evidence/maturity-evidence-manifest.json \
  --output docs/experiments/main-maturity-gate-latest.json \
  --markdown docs/experiments/main-maturity-gate-latest.md
```

证据包 SHA-256 清单写入已被 Git 忽略的 `output/release-evidence/maturity-evidence-manifest.json`；它只允许从 clean checkout 冻结，并绑定当前 Git commit、`backend/Cargo.lock` 与 `frontend/package-lock.json`。门禁会重新校验这些来源信息、证据文件和当前 checkout，随后把同一 `source_revision` 贯穿内部门禁、最终门禁和确认性评审完成门禁；运行时 `/maturity/status` 还会要求该 revision 与 `APP_REVISION` 一致。门禁结果写入 `docs/experiments/main-maturity-gate-latest.json` 和 `docs/experiments/main-maturity-gate-latest.md`。只要门禁失败，就不启动人工评审；优先修复报告中的失败项。即使门禁通过，仍需独立人工评审、外部冻结语料和更长时间 soak 后才能声称最终成熟。

最终成熟门禁用于判断是否可以启动论文确认性人工评审：

```bash
backend/.venv/bin/python scripts/freeze_final_maturity_evidence.py --replace
backend/.venv/bin/python scripts/freeze_final_maturity_evidence.py \
  --verify docs/experiments/final-maturity-evidence-manifest.json

backend/.venv/bin/python scripts/final_maturity_gate.py
```

它要求内部门禁通过、`docs/system-evidence/production-config-latest.json` 与 `validation-results.json` 内嵌生产配置快照均为 `passed`，且 env 文件 SHA-256、关键项清单和结构化生产检查 `checks` 完全一致并全部通过；还要求外部冻结包通过、经 `scripts/check_long_soak_report.py` 校验的长时 soak 证据通过、经 `scripts/check_tls_deployment.py` 生成的真实 TLS 部署证据通过、经 `scripts/check_offsite_backup_evidence.py` 校验的异地加密备份证据通过，并且最终证据 SHA-256 manifest 验证通过。当前缺少这些外部/生产证据时，该门禁应当失败，并把阻塞项写入 `docs/experiments/final-maturity-gate-latest.md`。

当前整改状态、代码冻结前置和外部事项的执行顺序见 [发布整改状态（2026-07-30）](docs/operations/release-remediation-2026-07-30.md)。
前端“报告”页会通过 `/maturity/status` 只读显示内部门禁、最终成熟门禁和确认性人工评审完成门禁，并区分 `human_review_allowed`（可启动正式评审）与 `human_review_report_allowed`（可发布人工评审结果）；只要最终成熟门禁失败，页面会明确提示不要启动正式人工评审。
各证据文件的最小结构见 [docs/operations/final-maturity-evidence.md](docs/operations/final-maturity-evidence.md)。

正式确认性人工评审启动前，还必须校验外部冻结包：

```bash
backend/.venv/bin/python scripts/validate_human_review_freeze.py \
  docs/experiments/confirmatory-human-review-freeze.json \
  --root .
```

冻结包至少需要 3 个项目、60 道问题、每项目至少 10 题、题号唯一、`question_index` 唯一、逐题冻结题干文本与 `gold_facts`、完整五方法集合、`model`、`prompt_version`、`random_seed`、两名独立评价人、评价人的真实 `user_id`、评价人仅具备 `can_evaluate=true`（`can_read/can_write/can_review/can_manage` 均为 `false`），以及所有语料/规则文件的 SHA-256。单项目内部题集只能用于开发诊断或受控内部试评，不能作为论文确认性人工评审依据。

确认性人工评审完成后，发表任何人工准确率、可追溯率或质量分前，还必须通过完成门禁：

```bash
backend/.venv/bin/python scripts/freeze_confirmatory_review_evidence.py --replace
backend/.venv/bin/python scripts/freeze_confirmatory_review_evidence.py \
  --verify docs/experiments/confirmatory-review-evidence-manifest.json

backend/.venv/bin/python scripts/confirmatory_review_completion_gate.py
```

该门禁首先要求 `final-maturity-gate-latest.json` 已经 PASS，随后要求冻结包仍可验证、导出的正式评审 CSV 存在、每个“问题—方法”都有两名评价人的 method-masked 评分、导出 `question_index` 集合完全等于冻结 `question_index` 集合、导出方法集合完全等于冻结方法集合、导出评价人 ID 完全等于冻结评价人的 `user_id`，导出条目数等于冻结问题数 × 方法数；正式 CSV 还必须包含一致的 `review_batch_id`（`R` + 12 位大写十六进制）、`export_protocol=confirmatory_human_review_v1` 和匹配当前最终成熟门禁文件的 `final_maturity_gate_sha256`，且评审证据 SHA-256 manifest 覆盖最终成熟门禁、冻结包和导出 CSV 并验证通过。当前最终成熟门禁失败、缺少正式冻结包、正式评审导出或评审证据 manifest 时，该门禁应当失败。

运行隔离的生产构建浏览器闭环、实验中途强杀恢复和短并发探针：

```bash
scripts/run-system-e2e.sh
```

后端质量检查使用固定的 Rust 1.88.0 工具链；Python 文件仅作为离线数据处理和证据校验脚本，不参与后端服务运行：

```bash
cd backend
cargo +1.88.0 fmt --all -- --check
cargo +1.88.0 clippy --all-targets -- -D warnings
cargo +1.88.0 test --all-targets --locked

cd ../
docker compose exec -T frontend npm run lint
```

运行状态：

```bash
docker compose ps
docker stats --no-stream
```
