# Night Context

> 本文件由夜间自主迭代协议初始化阶段建立。所有结论只基于当前仓库文件、运行中的本地服务和现有证据文件；未把历史 Python 实现当作生产能力。

## Audit Baseline

- 项目根目录：`/Users/yusong/Downloads/new/full-system`
- Git branch：`master`，HEAD：`a215cc4bc4b9f3418571a4757c4bf9c73aa49e8d`
- 初始化时工作树：已有大量未提交修改（约 94 个文件，包含 Rust 后端、Next.js 前端、测试、部署与文档），以及若干未跟踪文件。它们均视为 Existing User Work，夜间任务不得覆盖、删除、恢复或重排。
- 当前本地运行状态：`GET /health` 返回 200；`GET /ready`、前端和数据库状态已有本地证据；当前实时响应头包含 `x-backend-runtime: axum`。
- 运行环境：Rust 1.88、Node v24.18.0、npm 11.16.0、Python 3.14.6、Docker 29.6.1。
- 当前配置是开发环境；生产配置、真实外部服务、长期 soak 和独立人工评审不能由夜间工作假定为已完成。
- 真实浏览器冒烟：使用 README 推荐的 `http://localhost:3000` 登录成功，进入项目列表和项目 8 的笔记、资料、AI 问答、图谱页面，并打开/取消“新建笔记”对话框均正常。使用 `http://127.0.0.1:3000` 时，当前 `.env` 的 API host 为 `localhost:8001`，登录后 `/auth/me` 仍 401；这是 host 别名不一致造成的 cookie 约束，当前不改认证实现。

## Project Architecture

| Area | Actual implementation | Evidence |
|---|---|---|
| Frontend | Next.js 16 + React 19 + TypeScript；Playwright E2E | `frontend/package.json`, `frontend/e2e/` |
| Backend | Rust 1.88 + Axum，单进程提供业务 API | `backend/Cargo.toml`, `backend/src/api/mod.rs`, `README.md` |
| Database | PostgreSQL 16 + pgvector；Rust SQLx 初始化/迁移链路 | `docker-compose.yml`, `backend/src/db.rs`, `backend/sql/` |
| Authentication | Bearer token 与 HttpOnly cookie；登录限流；auth version 使退出/改密后的旧令牌失效 | `backend/src/api/auth.rs`, `backend/src/security.rs` |
| Projects/collaboration | 用户、小组、项目成员、项目角色、独立评价人 | `backend/src/api/users.rs`, `groups.rs`, `projects.rs` |
| Notes | 实验笔记创建、编辑、提交审批、审核、历史与图谱相关处理 | `backend/src/api/notes.rs`, `frontend/src/app/(dashboard)/projects/[id]/` |
| Files/OCR | 项目/笔记资料上传、审核、OCR、人工确认、归档、下载 | `backend/src/api/files.rs`, `ocr.rs`, `frontend/.../data/` |
| RAG | 文本分块、嵌入、词法/向量混合检索、图谱增强、问答、查询日志 | `backend/src/rag.rs`, `backend/src/api/rag.rs` |
| Embedding | 开发/测试默认 `rust-hash-512-v1` 512 维；生产目标为 OpenAI-compatible `BAAI/bge-m3` 1024 维 | `backend/src/embedding.rs`, `README.md` |
| Knowledge graph | 项目级实体/关系抽取、查询与可视化 | `backend/src/knowledge_graph.rs`, `backend/src/api/knowledge_graph.rs`, `frontend/.../kg/` |
| AI Agent | 固定任务型实验总结、周报、阶段报告、图谱概览；生成运行记录与引用审计 | `backend/src/api/agents.rs`, `backend/src/api/agent_runtime.rs`, `frontend/.../ai/` |
| MCP/tools | MCP 路由与工具调用确认/拒绝链路 | `backend/src/api/mcp.rs`, `backend/src/api/agent_runtime.rs` |
| Storage | `SYSTEM_STORAGE_PATH`/容器 `/storage`，与数据库作为同一恢复点管理 | `backend/src/config.rs`, `scripts/restore-system.sh` |
| Testing/evidence | Rust 单元/集成测试、历史 Python pytest、Next.js typecheck/lint/build、Playwright E2E、门禁与证据脚本 | `backend/src/`, `backend/tests/`, `frontend/package.json`, `scripts/` |

## Core User Flows (verified from code)

| Flow | Implemented path | Confidence / gap |
|---|---|---|
| A. 注册/登录 | 本地管理员引导 + `/auth/login`, `/auth/me`, `/auth/logout`; 前端登录页与 `AuthGuard` | 高；普通用户自助注册未在当前 Rust 路由中确认 |
| B. 创建科研项目 | `/projects` POST；项目列表/详情/成员/审核人页面 | 高 |
| C. 创建实验 | 实验以项目笔记/记录形式实现；`/projects/{project_id}/notes` | 高；需通过 E2E 继续确认完整点击路径 |
| D. 记录实验过程 | 笔记表单、详情、状态/审批链；Notes API | 高 |
| E. 上传实验材料 | 项目/笔记文件上传、文件审核、OCR/人工确认、下载 | 高 |
| F. 查询实验历史 | 项目笔记列表、全文搜索、RAG 实验/查询日志 | 高 |
| G. AI 辅助实验记录 | 固定任务 Agent 页面与生成 API；保存运行状态、引用和审计信息 | 高 |
| H. RAG/知识检索 | `/rag/*`、`/api/search*`、知识图谱增强检索；开发环境可用 hash embedding | 高 |
| I. 团队协作 | Groups、项目成员权限、独立评价人、审批与盲评 | 高 |
| J. 权限控制 | 服务端 `CurrentUser`、项目权限函数、角色/能力字段与覆盖测试 | 高；仍需持续关注跨域/并发边界 |

## Existing Evidence

- `docs/system-evidence/local-health-latest.json`：2026-08-10，本地就绪、PostgreSQL/存储/指标通过；明确标示开发环境和未绑定 revision。
- `docs/system-evidence/validation-results.json`：已有 compose 配置、Rust schema、Tesseract、负载 smoke、重启恢复等证据；证据文件属于既有状态，不当作本轮新测量。
- `docs/experiments/agent-quality-real-2026-08-10.json`：5 个 Agent case 自动门禁通过，但 human review 为 pending，且记录了文献引用精度和异常检测的限制。
- `docs/experiments/final-maturity-gate-latest.json`：当前未通过；原因包括非生产配置、缺失独立人工评审冻结、长期 soak/TLS/异地备份/最终证据清单等外部或高成本条件。

## Test Surface

- Rust 测试：位于 `backend/src/` 与 `backend/tests/`，覆盖认证、项目、笔记、文件/OCR、RAG、知识图谱、Agent、审计、配置与安全边界。
- Python pytest：`backend/tests/test_*.py`，部分是历史兼容/数据层测试；不能替代 Rust 生产运行时验证。
- Frontend：`npm run lint`、`npm run typecheck`、`npm run build`、`npm run test:e2e`。
- E2E：`frontend/e2e/system.spec.ts`、`user-journeys.spec.ts`、`real-lab-acceptance.spec.ts`（后两者及 fixtures 在初始化时为未跟踪文件，视为用户工作）。
- 运行脚本：`scripts/run-system-e2e.sh` 会构建 compose、运行 Playwright、重启恢复验证和负载 smoke，成本高且会创建/清理测试容器，夜间仅在任务明确需要时执行。

## Night Constraints

- 不改架构、数据库方案、认证方案、生产配置、真实密钥/账号/数据；不 push、merge、rebase、部署。
- 单任务默认最多改 8 个文件；优先新增测试/文档或局部修复，且避开初始化前已有 diff。
- 每项修改必须有基线、局部测试、diff review、独立审查结论和论文价值说明。
- 若需要用户决策、外部 API key、真实人工评审或生产环境，标记 `NEEDS_OWNER_DECISION`，不擅自推进。
