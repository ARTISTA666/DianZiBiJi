#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

failures=0

ok() { printf '[OK] %s\n' "$1"; }
warn() { printf '[WARN] %s\n' "$1"; }
fail() { printf '[FAIL] %s\n' "$1" >&2; failures=$((failures + 1)); }

env_value() {
  key=$1
  fallback=$2
  value=$(awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' .env 2>/dev/null || true)
  printf '%s' "${value:-$fallback}"
}

project_owns_port() {
  port=$1
  for container in $(docker compose ps -q 2>/dev/null); do
    if docker port "$container" 2>/dev/null | grep -q ":$port"; then
      return 0
    fi
  done
  return 1
}

check_port() {
  name=$1
  port=$2
  if ! lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    ok "$name port $port is available"
  elif project_owns_port "$port"; then
    ok "$name port $port is already used by this project"
  else
    fail "$name port $port is occupied by another process"
  fi
}

if [ "$(uname -s)" = "Darwin" ]; then
  ok "macOS $(sw_vers -productVersion) ($(uname -m))"
else
  fail "this check is intended for macOS"
fi

if ! command -v docker >/dev/null 2>&1; then
  fail "Docker is not installed"
elif ! docker info >/dev/null 2>&1; then
  fail "Docker Desktop is not running"
else
  ok "Docker daemon is available"
fi

if docker compose version >/dev/null 2>&1; then
  ok "Docker Compose is available"
else
  fail "Docker Compose is unavailable"
fi

if [ ! -f .env ]; then
  fail ".env is missing; copy .env.example first"
else
  ok ".env exists"
  app_env=$(env_value APP_ENV development)
  secret_key=$(env_value SECRET_KEY change-me-in-production)
  bootstrap_password=$(env_value BOOTSTRAP_ADMIN_PASSWORD admin123)
  postgres_password=$(env_value POSTGRES_PASSWORD eln_password)
  deepseek_api_key=$(env_value DEEPSEEK_API_KEY '')
  app_revision=$(env_value APP_REVISION unversioned)
  seed_demo_data=$(env_value SEED_DEMO_DATA false)
  if [ "$app_env" = production ]; then
    if [ "$secret_key" = change-me-in-production ] || [ "${#secret_key}" -lt 32 ]; then
      fail "production SECRET_KEY must be changed and contain at least 32 characters"
    fi
    if [ "$bootstrap_password" = admin123 ] || [ "${#bootstrap_password}" -lt 12 ]; then
      fail "production BOOTSTRAP_ADMIN_PASSWORD must be changed and contain at least 12 characters"
    fi
    if [ "$postgres_password" = eln_password ] || [ "${#postgres_password}" -lt 12 ]; then
      fail "production POSTGRES_PASSWORD must be changed and contain at least 12 characters"
    fi
    if [ -z "$deepseek_api_key" ]; then
      fail "production DEEPSEEK_API_KEY is empty"
    fi
    if [ "$app_revision" = unversioned ] || [ -z "$app_revision" ]; then
      fail "production APP_REVISION must identify the deployed release"
    fi
    if [ "$seed_demo_data" != false ]; then
      fail "production SEED_DEMO_DATA must be false"
    fi
  elif [ -z "$deepseek_api_key" ]; then
    warn "DEEPSEEK_API_KEY is empty; non-AI features work, but generation requests will fail clearly"
  else
    ok "DEEPSEEK_API_KEY is configured"
  fi
  if [ "$app_env" != production ] && [ "$secret_key" = "change-me-in-production" ]; then
    warn "SECRET_KEY still uses the development default"
  elif [ "$app_env" != production ]; then
    ok "SECRET_KEY has been changed"
  fi
fi

if docker compose config --quiet >/dev/null 2>&1; then
  ok "Docker Compose configuration is valid"
else
  fail "Docker Compose configuration is invalid"
fi

check_port backend "$(env_value BACKEND_PORT 8000)"
check_port frontend "$(env_value FRONTEND_PORT 3000)"

backend_port=$(env_value BACKEND_PORT 8000)
frontend_port=$(env_value FRONTEND_PORT 3000)
api_base_url=$(env_value NEXT_PUBLIC_API_BASE_URL "http://localhost:$backend_port")
case "$api_base_url" in
  "http://localhost:$backend_port"|"http://127.0.0.1:$backend_port")
    ok "frontend API URL matches backend port $backend_port"
    ;;
  *)
    fail "NEXT_PUBLIC_API_BASE_URL does not match backend port $backend_port"
    ;;
esac

cors_origins=$(env_value CORS_ORIGINS "http://localhost:3000,http://127.0.0.1:3000")
case ",$cors_origins," in
  *",http://localhost:$frontend_port,"*|*",http://127.0.0.1:$frontend_port,"*)
    ok "CORS origins include frontend port $frontend_port"
    ;;
  *)
    fail "CORS_ORIGINS does not include frontend port $frontend_port"
    ;;
esac

if [ "$failures" -ne 0 ]; then
  printf '\n%d check(s) failed.\n' "$failures" >&2
  exit 1
fi

printf '\nmacOS environment check passed.\n'
