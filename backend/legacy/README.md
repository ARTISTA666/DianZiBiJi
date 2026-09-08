# Legacy Python Backend (Dev-Only)

> **This code is NOT used in production.** The production backend is fully implemented in Rust (Axum) under `backend/src/`.

This directory contains the original Python FastAPI implementation, retained for:

1. **Development reference** — The Python code served as the original prototype and contains readable reference implementations of all business logic.
2. **Scripted E2E probes** — Some validation scripts (`scripts/`) reference Python FastAPI utilities.
3. **Test infrastructure** — Python pytest tests (`tests/`) provide an additional layer of verification for data model contracts.

## Structure

| Directory | Contents |
| :--- | :--- |
| `app/` | FastAPI application (routes, models, schemas, services) |
| `tests/` | Python pytest test suite (33 files) |
| `migrations/` | Alembic migration revisions (0001–0016) |
| `scripts/` | DB validation and runtime evidence export scripts |
| `alembic.ini` | Alembic configuration |
| `requirements*.txt` | Python dependency specifications |

## Running Tests

```bash
cd backend/legacy
pip install -r requirements.txt -r requirements-test.txt
python -m pytest tests -q
```

## Migration Note

The production Rust backend bootstraps databases from `backend/sql/0001_initial.sql` and maintains schema versions via `rust_schema_versions`. The Alembic migrations here are historical.
