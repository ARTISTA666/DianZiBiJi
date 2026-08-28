# Overnight Autonomous Work Report

## Executive Summary

本次重新启动后完成 3 个新增迭代任务；累计夜间记录 6 个协议任务，修复业务缺陷 1 个，新增业务能力 1 个，并完成多轮验证脚本、真实运行时和源码构建复核。没有覆盖或恢复初始化前的用户既有修改，没有 push、部署、真实数据删除或生产配置变更。

当前健康度：内部开发环境可运行、核心演示路径可用、自动化验证较完整；尚未达到生产发布或独立论文结论冻结条件。

本轮不再声称安排自动汇总；此前的 06:00 任务未持久化成功。本报告以当前实际执行结果为准，剩余 Owner 决策会在本次交付中明确列出。

## Completed Tasks

### Task 1 — 初始化系统地图与问题池

Problem: 工作区包含多个项目，目标项目有大规模未提交改动，需要先确认真实生产运行时和改动边界。

Why it mattered: 防止把历史 Python 代码误判为生产能力，也防止夜间工作覆盖用户现有修改；为论文的需求—实现—证据追溯建立基线。

Change: 新增 `NIGHT_CONTEXT.md`、`NIGHT_BACKLOG.md`、`NIGHT_LOG.md`，记录架构、核心流程、测试面、AI/RAG/MCP 实现、成熟度阻塞和任务评分。

Files: 3 个新增 Markdown 文件。

Tests: 工作树审计；`GET /health` 200；实时响应头 `x-backend-runtime: axum`。

Result: PASS。

Paper Value: 直接支撑第 3 章需求分析、第 4/5 章系统设计与实现、第 6 章测试边界。

Commit: 未提交；为保护既有大规模工作树改动，保留为未提交新增文件。

### Task 2 — 真实浏览器与完整工程基线验证

Problem: 需要确认用户按文档入口操作时，登录、项目、笔记、资料、AI、图谱和新建笔记入口不是静态页面或假按钮。

Why it mattered: 这些是答辩 Demo 和真实用户测试的主路径，单纯静态检查不能证明路由、会话和数据加载正常。

Change: 无业务代码改动；用 Playwright 通过 `http://localhost:3000` 登录，进入项目列表和项目 8 的笔记、资料、AI 问答、图谱页面，打开并取消新建笔记对话框。

Files: 无业务文件修改；审计结论记录在 `NIGHT_CONTEXT.md`、`NIGHT_LOG.md`。

Tests: Rust fmt/check/clippy；Rust 全量测试 236 个库测试 + 2 个二进制测试；Python 历史兼容测试 355 passed；前端 lint/typecheck/build；真实浏览器冒烟全部通过。

Result: PASS。README 推荐的 `localhost` 入口登录和核心页面导航正常。

Paper Value: 可作为系统测试、用户验收和答辩演示可用性的真实操作证据。

Commit: 未提交。

### Task 3 — 验证脚本与真实 Rust 运行时契约复核

Problem: 新增的本地健康、RAG 证据、Agent 质量、Rust 检索和契约导出检查需要确认可复现，且不能只依赖离线单测。

Why it mattered: 为系统测试和论文证据链增加独立验证层，避免把静态脚本通过误认为生产运行时契约已验证。

Change: 无业务代码改动；运行 6 组相关脚本单测，并对当前 Axum 实例进行只读 health/ready/OpenAPI/metrics 复核。

Files: 仅更新 `NIGHT_LOG.md` 与本报告。

Tests: 20 个脚本单测通过；`/health` 200；`/ready` database/storage 均为 `ok`；OpenAPI 70 paths/85 operations；metrics runtime 为 `rust-axum`；`git diff --check` 通过。

Result: PASS。没有发现新的可稳定复现 P1/P2 缺陷。

Paper Value: 证明离线验证脚本与实际 Rust 运行时的关键契约可以相互校验，同时保留开发快照不等同于论文实验样本的边界。

Commit: 未提交。

### Task 4 — 认证表单语义与应用图标

Problem: 登录、改密和创建账号表单缺少密码管理器可识别的 `autocomplete` 语义，当前源码也没有应用图标入口。

Why it mattered: 这是低风险但直接影响登录体验、浏览器提示和答辩 Demo 完成度的问题。

Change: 为账号、当前密码、新密码和初始密码补齐语义；新增 Next `src/app/icon.svg`。未改变认证协议或 cookie 策略。

Files: `frontend/src/app/login/page.tsx`、`frontend/src/app/icon.svg`、`frontend/src/components/shared/TopNav.tsx`、`frontend/src/app/(dashboard)/admin/user-management.tsx`。

Tests: `npm run lint`、`npm run typecheck`、`npm run build` 通过；当前源码临时启动验证 `/icon.svg` 200 且登录页生成图标链接。旧的 3000 容器未重建，未将其陈旧结果混入当前源码结论。

Result: PASS。Reviewer/Gatekeeper 均 PASS。

Paper Value: 改善系统可用性与答辩演示的可重复性，降低浏览器表单语义造成的误判。

### Task 5 — 前端/API host 一致性健康诊断

Problem: `127.0.0.1` 与 `localhost` 混用会造成 HttpOnly cookie 会话恢复失败，但此前只能在浏览器登录后观察到 401。

Why it mattered: 将环境配置错误提前暴露，能减少开发、E2E 和演示环境的假阴性，同时避免擅改认证安全边界。

Change: `check_local_health.py` 新增 host 一致性检查和清晰的 loopback mismatch 诊断；增加对应回归测试；默认值与 README 推荐入口统一为 `localhost`。

Files: `scripts/check_local_health.py`、`scripts/test_check_local_health.py`。

Tests: 健康检查单测 4 passed；选定脚本回归 21 passed；`py_compile` 通过；真实本地检查 `local_ready=true`；不一致 host 直接函数检测通过；未改变认证、CORS 或 cookie 策略。

Result: PASS。Reviewer/Gatekeeper 均 PASS。

Paper Value: 为系统部署前检查和实验环境复现提供可执行的配置诊断证据。

### Task 6 — CSV 导出认证与错误处理收敛

Problem: RAG 实验导出与盲评批量导出直接调用 `fetch`，认证失效时绕过统一的 401 跳转、request-id 和错误解析。

Why it mattered: 实验数据导出是评估和答辩证据链的一部分，静默的会话失效会造成难以解释的失败。

Change: 扩展 `apiFetch` 支持响应解析器，并让两个 CSV 下载复用 Blob 解析；保留原 URL、响应格式和数据内容。

Files: `frontend/src/lib/api.ts`（局部修改；该文件其余既有用户 diff 未重写）。

Tests: `npm run lint`、`npm run typecheck`、`npm run build`、`git diff --check` 通过；底层 `fetch` 仍集中在 `apiFetch` 一处；Blob 返回类型保持不变。

Result: PASS。Reviewer/Gatekeeper 均 PASS。

Paper Value: 提升实验数据导出的认证一致性和可追溯性，减少评估流程中的隐性失败。

## Bugs Fixed

- 登录、改密和创建账号表单补齐 `autocomplete`，改善密码管理器和浏览器辅助能力。
- 新增 `src/app/icon.svg`，由 Next 登录页生成应用图标链接。
- 两个 CSV 导出调用统一复用 `apiFetch`，认证失败可进入统一错误/会话处理。

## Features Improved

- 增加夜间工作可追溯性：系统地图、问题池、逐轮日志和最终报告。
- 通过真实用户入口验证了项目列表、项目工作区、笔记表单、资料库、AI 问答和知识图谱导航。
- 本地健康检查新增前端/API host 一致性诊断，不改变认证安全策略。

## AI Capability Improvements

没有改动 Agent/RAG/MCP 业务实现。现有实现已确认包含项目级 RAG、图谱增强、固定任务 Agent、证据引用和实验记录；本轮只验证 AI 页面可达，并保留现有质量实验的限制：5 个 Agent case 自动门禁通过，但 human review 为 pending。

## Testing Improvements

完成了可复现的基线验证，并新增 host 一致性回归测试：

- `cargo fmt --all -- --check`：通过。
- `cargo check --workspace`：通过。
- `cargo clippy --workspace --all-targets -- -D warnings`：通过。
- 最终 `cargo test --workspace`：234 个库测试、2 个二进制测试通过（另有 0 个 doc-test）。
- `backend/.venv/bin/python -m pytest tests -q`：355 passed，10 warnings。
- `npm run lint`、`npm run typecheck`、`npm run build`：均通过。
- 新增验证脚本选定单测：本轮回归 21 passed（含 host 一致性；另有健康检查、RAG 证据、Agent 质量、Rust 检索、契约导出、RAG 冻结）。
- 本地运行时：`/health` 200、`/ready` 200（database/storage ok）、`/openapi.json` 70 paths/85 operations。

## Thesis-Relevant Outcomes

### 第3章 需求分析

- 已将用户、项目、实验笔记、资料/OCR、审批、权限、RAG、Agent、知识图谱和团队复用映射为真实系统流程。
- 明确了开发环境 host 别名不一致会导致 cookie 会话失败的边界条件。

### 第4/5章 方法与设计

- 记录了 Rust/Axum 单进程、PostgreSQL/pgvector、项目级 RAG、知识图谱增强和固定任务 Agent 的实际边界。
- 保留“系统不会在 AI 失败时生成模拟回答”和“证据可追溯”的现有设计结论。

### 系统架构

- `NIGHT_CONTEXT.md` 建立了前端、后端、数据库、认证、AI、存储和测试的架构表及核心流程表。

### 系统实现

- 真实浏览器确认登录、项目工作区、笔记、资料、AI 和图谱页面可以完成基本导航。

### 系统测试

- Rust、Python 兼容层、前端静态检查、生产构建与浏览器冒烟形成相互独立的验证层。

### 实验分析

- 未制造新的论文实验结果；现有 Agent/RAG 结果仍以仓库中的冻结证据为准，并明确区分自动门禁、内部开发证据和人工评审。

### 答辩 Demo

- 推荐入口 `http://localhost:3000` 的登录—项目—笔记/资料/AI/图谱路径已现场验证。

## Quantifiable Metrics Available

以下是可真实采集或已存在于证据文件中的指标，不是本轮编造的实验结果：

- Rust API OpenAPI：70 paths、85 operations。
- 本轮最终自动化测试：Rust 236 个单元测试（234 库 + 2 二进制）、Python 355 tests；前端 lint/typecheck/build 通过。
- 运行时快照：`/ready` database/storage 均为 `ok`；当前开发实例 metrics 记录 6,849 requests，本轮响应未返回 latency_ms（该快照包含既有本地运行和本轮访问，不应直接当作论文实验样本）。
- 既有 Agent quality report：5 cases，fact consistency 0.9333，citation precision 0.9，citation recall 0.9333，boundary pass rate 1.0；human review pending。
- 既有 RAG/系统证据：查询耗时、token、模型、提示版本、语料哈希、来源片段、图谱命中和实验运行状态均有落库/导出字段。

## Remaining Problems

### P0

本轮未发现可稳定复现的 P0；不等于生产安全审计已完成。

### P1

- 最终 maturity gate 未通过：生产配置、独立人工评审冻结、长期 soak、TLS、异地备份和最终证据清单仍缺失或不满足。
- 当前工作树存在大规模既有未提交改动，夜间无法安全判断其整体归属和跨模块回归风险。

### P2

- N-007：使用 `127.0.0.1:3000` 打开前端而 API 配置为 `localhost:8001` 时，HttpOnly cookie 不随跨站请求发送，登录后 `/auth/me` 为 401；现已由本地健康检查提前拦截。仍需 Owner 决定统一 host、同源反代或 cookie 策略。

### P3

- 旧的 3000 前端容器未重建，当前源码变更使用 3300 临时实例验证；交付前应按项目文档重建服务以观察最新构建。

## Blocked Tasks

- 不执行 4 小时长期 soak、真实 TLS/异地备份、生产配置验证或独立人工评审冻结：这些需要外部环境、Owner 决策或长期占用资源。
- 不在 94 个左右既有修改文件中继续修业务代码：会混淆用户工作归属，且违反最小变更原则。

## NEEDS_OWNER_DECISION

### Host consistency

Problem: 是否支持 `localhost` 与 `127.0.0.1` 任意混用。

Option A: 统一文档、`.env`、E2E 和用户入口使用同一 host（推荐，最小风险）。

Option B: 通过同源反向代理或重新设计 cookie 策略支持别名混用。

Recommendation: Option A。

Reason: 不扩大认证安全边界，且 README 入口已经可用。

### Final maturity evidence

Problem: 最终门禁依赖生产配置、TLS、异地备份、长期 soak 和独立人工评审。

Option A: Owner 准备真实环境和人工评审后按门禁逐项冻结（推荐）。

Option B: 继续用本地/内部证据替代外部条件。

Recommendation: Option A。

Reason: Option B 会把内部开发证据错误表述为生产或外部验证结论。

## Tomorrow's Top 5

1. 统一开发、E2E 和演示环境的前端/API host 配置，并决定是否支持 loopback 别名。
2. 完成独立科研人员人工盲评，处理 Agent 文献引用精度与异常检测遗漏。
3. 由 Owner 准备真实生产配置、TLS 和异地加密备份证据。
4. 按计划执行并冻结满足门槛的长期 soak，而不是使用短时 smoke 替代。
5. 在干净分支/提交边界上整理当前大规模未提交改动，再进行下一轮跨模块缺陷修复。
