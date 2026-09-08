# AGENTS.md

面向编码代理的最小路由指导：本仓库包含三套运行时（Rust 后端、legacy Python、Next.js 前端），修改前先确认目标运行时，改完只跑对应检查。

## 专家团队路由

| 任务类型 | 路由到 | 说明 |
| --- | --- | --- |
| 需求分析、用户故事、验收标准、科研场景建模 | `product-manager` | 产品与需求 Agent，只读调研，不写代码 |
| 架构设计、模块边界、接口审核、ADR、技术债 | `architect` | 系统架构 Agent，只读分析，不写代码 |
| Rust 后端 API、数据库迁移、权限校验、业务规则 | `backend-engineer` | 后端开发 Agent，改 `backend/src/` |
| Next.js 前端页面、组件、状态管理、E2E 锚点 | `frontend-engineer` | 前端开发 Agent，改 `frontend/src/` |
| RAG、向量检索、Agent 工具、MCP、AI 降级 | `ai-engineer` | 数据与 AI Agent，改 AI/数据层 |
| 测试验证、E2E、回归、Docker、安全检查 | `qa-engineer` | QA + DevOps 安全 Agent，只读验证 |
| 代码审查、安全审计、契约一致性、回归风险 | `code-reviewer` | 代码审查 Agent，只读评审 |

## 关键架构约束

- **生产后端是 Rust（Axum）**：`backend/src/`，工具链固定 Rust 1.88.0（`backend/rust-toolchain.toml`）。所有后端功能改动都应落在 Rust 代码中。
- **Python 是 legacy / dev-only**：`backend/legacy/app/` 的 FastAPI 代码仅作开发参考与脚本化 E2E 探针，不参与生产服务运行；`scripts/` 下的 Python 仅用于离线数据处理和证据校验（按功能域分组在 `scripts/gates/`、`scripts/freeze/`、`scripts/experiments/`、`scripts/data/`、`scripts/render/`、`scripts/ops/`、`scripts/audit/` 子目录中）。不要把新后端功能写进 Python。
- **前端**：`frontend/`，Next.js + TypeScript，API 类型由 `backend/openapi.json` 生成（`npm run generate:api`），生成结果必须提交。
- **启动方式为 Docker Compose**：`cp .env.example .env && bash scripts/ops/docker-compose-with-revision.sh up -d --build`。Compose 构建生产镜像，不挂载源码；代码变更后需重新构建镜像。后端 http://localhost:8001（`/health`、`/ready`），前端 http://localhost:3000。
- **核心业务优先**：任何 AI 功能都不能替代核心业务闭环。基础系统未稳定前，不得将资源投入炫技型 AI 功能。

## 各运行时本地测试命令

Rust 后端（集成测试使用隔离的 pgvector/pg16 测试库）：

```bash
./scripts/ops/run-rust-db-tests.sh
cd backend
cargo fmt --all --check
cargo clippy --locked --all-targets --all-features -- -D warnings
```

Python（legacy 后端测试 + 仓库脚本测试；默认使用 SQLite，避免把历史 FastAPI 夹具误当成生产 PostgreSQL 验证）：

```bash
cd backend/legacy && python -m pytest tests -q
python -m pytest -q scripts/*/test_*.py          # 在仓库根目录执行
```

前端：

```bash
cd frontend
npm run lint
npm run typecheck
npm run build
```

系统级 E2E（隔离生产栈，较慢，仅在跨端改动时运行）：

```bash
scripts/ops/run-system-e2e.sh
```

## 变更 → 检查路由

| 修改位置 | 必跑检查 |
| --- | --- |
| `backend/src/`、`backend/Cargo.toml`、`backend/legacy/tests/` | Rust：`cargo fmt --check` + `cargo clippy -- -D warnings` + `cargo test -- --test-threads=1` |
| `backend/src/`（改了 API 结构） | 上述 Rust 检查 + 更新 `backend/openapi.json` + 前端 `npm run generate:api` 并提交 `src/lib/api-schema.d.ts` |
| `backend/legacy/app/`（legacy Python） | `cd backend/legacy && python -m pytest tests -q` |
| `backend/legacy/migrations/`、`backend/sql/` | Rust 测试（集成测试覆盖 schema） |
| `frontend/src/` | `npm run lint` + `npm run typecheck` + `npm run build` |
| `scripts/**/*.py` | `python -m pytest -q scripts/*/test_*.py` |
| `docker-compose*.yml`、`backend/Dockerfile`、`frontend/Dockerfile` | `bash scripts/ops/docker-compose-with-revision.sh config --quiet` + `bash scripts/ops/docker-compose-with-revision.sh build` |
| `deploy/nginx.conf.template` | `backend/.venv/bin/python scripts/gates/check_reverse_proxy_config.py` |

CI（`.github/workflows/ci.yml`）以相同分组运行 backend-python、backend-rust、frontend、system-e2e 四个 job；本地至少跑通与改动对应的分组再提交。

## 并线协作约定（多 Agent 并行推进论文）

本仓库由多个 AI agent 并线推进论文（当前：证据线 ZCode、文字线 GPT），遵守以下规则：

- **域分区**：文字线只做纯语言/叙事修改，**不动任何数字、证据句、公式、引文编号**，不碰 `backend/`、`reviews/`、`docs/system-evidence/`、`agent-work/`；证据线负责对照代码与证据的机制性修改、测试、实验与评审。跨线需求写入状态文件协商，不得自行跨线。
- **单写者窗口**：`docs/毕业论文重构稿.md` 任意时刻只有一个 agent 持窗修改。开工前必读 `docs/并线协作状态.md` 确认当前持窗方；窗口内小步提交，收工必须更新状态文件并释放窗口。
- **提交纪律**：commit message 标注归属（`[文字线]`/`[证据线]`），一次提交只含一类改动；论文每处修改须可经 `git diff` 审计，修改前先对照 `reviews/round-0N/baseline-thesis-snapshot.md` 类基线。
- **互审**：每轮合并后由证据线的 `/thesis-review` 对对方改动区域做快速复审，重点核查技术含义与数字未被破坏。
- **大文件不入库**：`data/real/`（129MB 数据集）、`agent-work/` 实验工作区（44MB DRAFT 材料，仅 `thesis-agents/` 等文本资产入库）、编译产物 PDF 保持本地，不提交。
