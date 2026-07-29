# AGENTS.md

面向编码代理的最小路由指导：本仓库包含三套运行时（Rust 后端、legacy Python、Next.js 前端），修改前先确认目标运行时，改完只跑对应检查。

## 关键架构约束

- **生产后端是 Rust（Axum）**：`backend/src/`，工具链固定 Rust 1.88.0（`backend/rust-toolchain.toml`）。所有后端功能改动都应落在 Rust 代码中。
- **Python 是 legacy / dev-only**：`backend/app/` 的 FastAPI 代码仅作开发参考与脚本化 E2E 探针，不参与生产服务运行；`scripts/` 下的 Python 仅用于离线数据处理和证据校验。不要把新后端功能写进 Python。
- **前端**：`frontend/`，Next.js + TypeScript，API 类型由 `backend/openapi.json` 生成（`npm run generate:api`），生成结果必须提交。
- **启动方式为 Docker Compose**：`cp .env.example .env && docker compose up -d --build`。Compose 构建生产镜像，不挂载源码；代码变更后需重新构建镜像。后端 http://localhost:8001（`/health`、`/ready`），前端 http://localhost:3000。

## 各运行时本地测试命令

Rust 后端（集成测试需要 PostgreSQL，`TEST_DATABASE_URL` 指向 pgvector/pg16；测试共享 schema，保持串行）：

```bash
cd backend
cargo fmt --all --check
cargo clippy --locked --all-targets --all-features -- -D warnings
cargo test --locked --all-targets --all-features -- --test-threads=1
```

Python（legacy 后端测试 + 仓库脚本测试）：

```bash
cd backend && python -m pytest tests -q        # 需要 TEST_DATABASE_URL
python -m pytest -q scripts/test_*.py          # 在仓库根目录执行
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
scripts/run-system-e2e.sh
```

## 变更 → 检查路由

| 修改位置 | 必跑检查 |
| --- | --- |
| `backend/src/`、`backend/Cargo.toml`、`backend/tests/` | Rust：`cargo fmt --check` + `cargo clippy -- -D warnings` + `cargo test -- --test-threads=1` |
| `backend/src/`（改了 API 结构） | 上述 Rust 检查 + 更新 `backend/openapi.json` + 前端 `npm run generate:api` 并提交 `src/lib/api-schema.d.ts` |
| `backend/app/`（legacy Python） | `cd backend && python -m pytest tests -q` |
| `backend/migrations/`、`backend/sql/` | Rust 测试（集成测试覆盖 schema） |
| `frontend/src/` | `npm run lint` + `npm run typecheck` + `npm run build` |
| `scripts/*.py` | `python -m pytest -q scripts/test_*.py` |
| `docker-compose*.yml`、`backend/Dockerfile`、`frontend/Dockerfile` | `docker compose config --quiet` + `docker compose build` |
| `deploy/nginx.conf.template` | `backend/.venv/bin/python scripts/check_reverse_proxy_config.py` |

CI（`.github/workflows/ci.yml`）以相同分组运行 backend-python、backend-rust、frontend、system-e2e 四个 job；本地至少跑通与改动对应的分组再提交。
