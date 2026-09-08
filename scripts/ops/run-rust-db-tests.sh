#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
compose() {
  bash "$ROOT/scripts/docker-compose-with-revision.sh" \
    -p eln-rust-test-db -f "$ROOT/docker-compose.test-db.yml" "$@"
}

cleanup() {
  compose down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

compose up -d --wait

# 从实际运行的容器发现宿主端口，避免与 docker-compose.test-db.yml 中
# TEST_DB_PORT 覆盖值漂移（历史上曾出现 55432/55433 不一致导致 DB 测试全部超时）。
TEST_DB_PORT_ACTUAL=$(compose port db 5432 2>/dev/null | sed 's/.*://' | head -n1)
TEST_DATABASE_URL=${TEST_DATABASE_URL:-postgresql://eln_test:eln_test_password@127.0.0.1:${TEST_DB_PORT_ACTUAL:-55432}/postgres}

TEST_DATABASE_URL="$TEST_DATABASE_URL" cargo +1.88.0 test \
  --manifest-path "$ROOT/backend/Cargo.toml" \
  --locked --all-targets --no-default-features -- --test-threads=1
