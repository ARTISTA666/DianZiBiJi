#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

if [ ! -f .env ]; then
  cp .env.example .env
  printf '[INFO] Created .env from .env.example.\n'
fi

sh scripts/check-macos.sh
docker compose up -d --build

env_value() {
  key=$1
  fallback=$2
  value=$(awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' .env)
  printf '%s' "${value:-$fallback}"
}

wait_for_url() {
  url=$1
  name=$2
  attempts=0
  until curl -fsS "$url" >/dev/null 2>&1; do
    attempts=$((attempts + 1))
    if [ "$attempts" -ge 90 ]; then
      docker compose logs --tail=120 "$name"
      printf '[FAIL] %s did not become ready: %s\n' "$name" "$url" >&2
      exit 1
    fi
    sleep 2
  done
  printf '[OK] %s is ready: %s\n' "$name" "$url"
}

backend_port=$(env_value BACKEND_PORT 8001)
frontend_port=$(env_value FRONTEND_PORT 3000)
wait_for_url "http://127.0.0.1:$backend_port/ready" backend
wait_for_url "http://127.0.0.1:$frontend_port" frontend

# 等待后端就绪（Rust 后端内置数据库初始化）
echo "等待后端服务就绪..."
for i in $(seq 1 30); do
  if docker compose exec -T backend curl -fsS http://localhost:8000/ready >/dev/null 2>&1; then
    echo "后端服务已就绪"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "警告：后端服务在 30 秒内未就绪，继续启动..."
  fi
  sleep 1
done

languages=$(docker compose exec -T backend tesseract --list-langs 2>/dev/null)
for language in $(env_value OCR_LANGUAGES chi_sim+eng | tr '+' ' '); do
  if ! printf '%s\n' "$languages" | grep -qx "$language"; then
    printf '[FAIL] Tesseract language is missing: %s\n' "$language" >&2
    exit 1
  fi
done
printf '[OK] configured Tesseract languages are installed\n'

printf '\nSystem is ready.\nFrontend: http://localhost:%s\nBackend:  http://localhost:%s\n' "$frontend_port" "$backend_port"
