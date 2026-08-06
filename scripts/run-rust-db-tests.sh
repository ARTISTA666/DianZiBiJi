#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
COMPOSE="docker compose -p eln-rust-test-db -f $ROOT/docker-compose.test-db.yml"
TEST_DATABASE_URL=${TEST_DATABASE_URL:-postgresql://eln_test:eln_test_password@127.0.0.1:55432/postgres}

cleanup() {
  $COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

$COMPOSE up -d --wait
TEST_DATABASE_URL="$TEST_DATABASE_URL" cargo +1.88.0 test \
  --manifest-path "$ROOT/backend/Cargo.toml" \
  --locked --all-targets --no-default-features -- --test-threads=1
