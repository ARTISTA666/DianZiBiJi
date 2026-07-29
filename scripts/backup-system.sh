#!/bin/sh
set -eu

umask 077

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

if [ ! -f .env ]; then
  printf '[FAIL] .env is missing; refusing to guess database credentials.\n' >&2
  exit 1
fi

env_value() {
  key=$1
  fallback=$2
  value=$(printenv "$key" 2>/dev/null || true)
  if [ -z "$value" ]; then
    value=$(awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' .env)
  fi
  printf '%s' "${value:-$fallback}"
}

sha256_file() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    sha256sum "$1" | awk '{print $1}'
  fi
}

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
requested=${1:-backups/eln-$timestamp}
case "$requested" in
  /*) output=$requested ;;
  *) output=$ROOT/$requested ;;
esac
temporary=$output.tmp.$$
stopped_services=
completed=0

cleanup() {
  if [ -n "$stopped_services" ]; then
    docker compose start $stopped_services >/dev/null 2>&1 || true
  fi
  if [ "$completed" -ne 1 ]; then
    rm -rf "$temporary"
  fi
}
trap cleanup EXIT INT TERM

if [ -e "$output" ] || [ -e "$temporary" ]; then
  printf '[FAIL] backup path already exists: %s\n' "$output" >&2
  exit 1
fi

mkdir -p "$(dirname -- "$output")"
mkdir -m 700 "$temporary"
database=$(env_value POSTGRES_DB eln)
database_user=$(env_value POSTGRES_USER eln_user)
app_revision=$(env_value APP_REVISION unversioned)
storage_setting=$(env_value SYSTEM_STORAGE_PATH ./storage)
case "$storage_setting" in
  /*) storage_path=$storage_setting ;;
  *) storage_path=$ROOT/$storage_setting ;;
esac
mkdir -p "$storage_path"

if ! docker compose exec -T db pg_isready -U "$database_user" -d "$database" >/dev/null; then
  printf '[FAIL] PostgreSQL is not ready; no backup was created.\n' >&2
  exit 1
fi

running_services=$(docker compose ps --status running --services)
if printf '%s\n' "$running_services" | grep -qx backend; then
  stopped_services=backend
fi
if printf '%s\n' "$running_services" | grep -qx frontend; then
  stopped_services="$stopped_services frontend"
fi
if [ -n "$stopped_services" ]; then
  # This deployment uses one application writer. Briefly stopping it makes the
  # database dump and uploaded-file archive one consistent recovery point.
  docker compose stop $stopped_services >/dev/null
fi

docker compose exec -T db pg_dump \
  -U "$database_user" \
  -d "$database" \
  --format=custom \
  --no-owner \
  --no-acl >"$temporary/database.dump"
tar -C "$storage_path" -czf "$temporary/storage.tar.gz" .

database_sha256=$(sha256_file "$temporary/database.dump")
storage_sha256=$(sha256_file "$temporary/storage.tar.gz")
cat >"$temporary/manifest.txt" <<EOF
manifest_version=1
created_at=$timestamp
app_revision=$app_revision
database=$database
database_sha256=$database_sha256
storage_sha256=$storage_sha256
EOF

mv "$temporary" "$output"
if [ -n "$stopped_services" ]; then
  docker compose start $stopped_services >/dev/null
  stopped_services=
fi
completed=1
printf '[OK] system backup created: %s\n' "$output"
