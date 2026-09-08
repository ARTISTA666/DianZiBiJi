# Backend — Rust (Axum)

Production backend for the Electronic Lab Notebook system, implemented in Rust 1.88 with the Axum web framework.

## Quick Start

```bash
# Run via Docker Compose (recommended)
cp .env.example .env
bash scripts/docker-compose-with-revision.sh up -d --build

# Health check
curl http://localhost:8001/health
curl http://localhost:8001/ready
```

## Project Structure

| Path | Description |
| :--- | :--- |
| `src/` | Production Rust source code |
| `src/api/` | HTTP route handlers (Axum) |
| `src/rag/` | RAG retrieval engine (hybrid search + KG-RAG) |
| `src/models/` | Data structures and Serde schemas |
| `sql/` | Bootstrap SQL schema (`0001_initial.sql`) |
| `openapi.json` | OpenAPI 3.1 specification (source of truth for API contract) |
| `legacy/` | Archived Python FastAPI code (dev reference only) |

## Development

```bash
# Format check
cargo fmt --all --check

# Lint
cargo clippy --locked --all-targets --all-features -- -D warnings

# Run tests (requires PostgreSQL with pgvector)
./scripts/run-rust-db-tests.sh

# Or run tests directly
cargo test --locked --all-targets --all-features -- --test-threads=1
```

## API Contract

The OpenAPI specification is at `openapi.json`. When API routes change:

1. Update `openapi.json`
2. Run `cd ../frontend && npm run generate:api`
3. Commit the updated `frontend/src/lib/api-schema.d.ts`
