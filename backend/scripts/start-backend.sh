#!/bin/sh
# ---------------------------------------------------------------------------
# LEGACY SCRIPT — no longer used in the production Docker image.
#
# The backend runtime has been fully migrated to Rust (Axum).
# Database schema initialization is now performed by the Rust binary itself
# via sqlx migrations (see `initialize_database` in src/db.rs and
# sql/0001_initial.sql).  The Dockerfile ENTRYPOINT runs `eln-backend`
# directly; this script is NOT invoked during container startup.
#
# Retained for local development reference only.  Safe to remove once the
# Python FastAPI code in backend/app/ is archived.
# ---------------------------------------------------------------------------
set -eu

alembic upgrade head
exec "$@"
