#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
COMPOSE="docker compose -p eln-e2e -f $ROOT/docker-compose.e2e.yml"
OUTPUT="$ROOT/output/playwright"

mkdir -p "$OUTPUT"

if [ -n "${E2E_PYTHON:-}" ]; then
  E2E_PYTHON_BIN=$E2E_PYTHON
elif [ -x "$ROOT/backend/.venv/bin/python" ]; then
  E2E_PYTHON_BIN=$ROOT/backend/.venv/bin/python
else
  E2E_PYTHON_BIN=$(command -v python3 || true)
fi
if [ -z "$E2E_PYTHON_BIN" ]; then
  echo "Python 3 is required for restart and load probes" >&2
  exit 1
fi

cleanup() {
  $COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

$COMPOSE up -d --build

wait_for_url() {
  url=$1
  name=$2
  attempts=0
  until curl -fsS "$url" >/dev/null 2>&1; do
    attempts=$((attempts + 1))
    if [ "$attempts" -ge 90 ]; then
      $COMPOSE logs --no-color >"$OUTPUT/compose.log"
      echo "$name did not become ready: $url" >&2
      return 1
    fi
    sleep 2
  done
}

wait_for_url http://127.0.0.1:18000/ready backend
wait_for_url http://127.0.0.1:13000 frontend

cd "$ROOT/frontend"
# Bundled Chromium is the reproducible default. A system browser can still be
# selected explicitly, for example E2E_BROWSER_CHANNEL=chrome.
if [ -z "${E2E_BROWSER_CHANNEL:-}" ]; then
  npx playwright install chromium
fi
if ! npm run test:e2e; then
  $COMPOSE logs --no-color >"$OUTPUT/compose.log"
  exit 1
fi

"$E2E_PYTHON_BIN" "$ROOT/scripts/validate_experiment_restart.py" \
  --api-base http://127.0.0.1:18000 \
  --compose-file "$ROOT/docker-compose.e2e.yml" \
  --compose-project eln-e2e \
  --username admin \
  --password admin123 \
  --output "$OUTPUT/restart-recovery.json"

"$E2E_PYTHON_BIN" "$ROOT/scripts/load_smoke.py" \
  --api-base http://127.0.0.1:18000 \
  --username admin \
  --password admin123 \
  --requests 90 \
  --concurrency 10 \
  --output "$OUTPUT/load-smoke.json"
