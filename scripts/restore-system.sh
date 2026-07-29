#!/bin/sh
set -eu

umask 077

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

if [ "$#" -ne 2 ] || [ "$2" != "--confirm-replace" ]; then
  printf 'Usage: %s BACKUP_DIR --confirm-replace\n' "$0" >&2
  printf '[FAIL] restore replaces the current database and uploaded files.\n' >&2
  exit 2
fi
case "$1" in
  /*) backup=$1 ;;
  *) backup=$ROOT/$1 ;;
esac

for required in manifest.txt database.dump storage.tar.gz; do
  if [ ! -s "$backup/$required" ]; then
    printf '[FAIL] backup file is missing or empty: %s\n' "$backup/$required" >&2
    exit 1
  fi
done

env_value() {
  key=$1
  fallback=$2
  value=$(printenv "$key" 2>/dev/null || true)
  if [ -z "$value" ]; then
    value=$(awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' .env)
  fi
  printf '%s' "${value:-$fallback}"
}

manifest_value() {
  key=$1
  awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "$backup/manifest.txt"
}

sha256_file() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    sha256sum "$1" | awk '{print $1}'
  fi
}

if [ "$(manifest_value manifest_version)" != 1 ]; then
  printf '[FAIL] unsupported backup manifest version.\n' >&2
  exit 1
fi
if [ "$(sha256_file "$backup/database.dump")" != "$(manifest_value database_sha256)" ]; then
  printf '[FAIL] database dump checksum does not match the manifest.\n' >&2
  exit 1
fi
if [ "$(sha256_file "$backup/storage.tar.gz")" != "$(manifest_value storage_sha256)" ]; then
  printf '[FAIL] storage archive checksum does not match the manifest.\n' >&2
  exit 1
fi
if [ ! -f .env ]; then
  printf '[FAIL] .env is missing; refusing to guess database credentials.\n' >&2
  exit 1
fi

database=$(env_value POSTGRES_DB eln)
database_user=$(env_value POSTGRES_USER eln_user)
backend_port=$(env_value BACKEND_PORT 8000)
storage_setting=$(env_value SYSTEM_STORAGE_PATH ./storage)
case "$storage_setting" in
  /*) storage_path=$storage_setting ;;
  *) storage_path=$ROOT/$storage_setting ;;
esac
case "$database" in
  postgres|template0|template1)
    printf '[FAIL] refusing to replace PostgreSQL maintenance database: %s\n' "$database" >&2
    exit 1
    ;;
esac

if [ -n "${RESTORE_PYTHON:-}" ]; then
  restore_python=$RESTORE_PYTHON
elif [ -x "$ROOT/backend/.venv/bin/python" ]; then
  restore_python=$ROOT/backend/.venv/bin/python
else
  restore_python=$(command -v python3 || true)
fi
if [ -z "$restore_python" ]; then
  printf '[FAIL] Python 3 is required to validate the storage archive.\n' >&2
  exit 1
fi

storage_parent=$(dirname -- "$storage_path")
mkdir -p "$storage_parent"
extracted=$(mktemp -d "$storage_parent/.eln-restore.XXXXXX")
restore_started=0
restore_completed=0
rollback=
cleanup() {
  rm -rf "$extracted"
  if [ "$restore_started" -eq 1 ] && [ "$restore_completed" -ne 1 ]; then
    printf '[FAIL] restore stopped after replacement began; application services remain stopped.\n' >&2
    if [ -n "$rollback" ]; then
      printf '[INFO] validated rollback bundle: %s/%s\n' "$ROOT" "$rollback" >&2
    fi
  fi
}
trap cleanup EXIT INT TERM
mkdir "$extracted/storage"
"$restore_python" "$ROOT/scripts/safe_extract_storage.py" \
  "$backup/storage.tar.gz" "$extracted/storage"

if ! docker compose exec -T db pg_isready -U "$database_user" -d "$database" >/dev/null; then
  printf '[FAIL] PostgreSQL is not ready.\n' >&2
  exit 1
fi
if ! docker compose exec -T db pg_restore --list <"$backup/database.dump" >/dev/null; then
  printf '[FAIL] database dump cannot be read by pg_restore.\n' >&2
  exit 1
fi

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
rollback=backups/pre-restore-$timestamp
scripts/backup-system.sh "$rollback"
printf '[OK] pre-restore rollback bundle created: %s/%s\n' "$ROOT" "$rollback"

restore_started=1
docker compose stop frontend backend >/dev/null

docker compose exec -T db dropdb --if-exists --force -U "$database_user" "$database"
docker compose exec -T db createdb -U "$database_user" -O "$database_user" "$database"
docker compose exec -T db pg_restore \
  -U "$database_user" \
  -d "$database" \
  --no-owner \
  --no-acl \
  --exit-on-error <"$backup/database.dump"

previous_storage=$storage_path.pre-restore-$timestamp
if [ -e "$storage_path" ]; then
  mv "$storage_path" "$previous_storage"
fi
mv "$extracted/storage" "$storage_path"

docker compose up -d --no-deps backend >/dev/null
attempts=0
until curl -fsS "http://127.0.0.1:$backend_port/ready" >/dev/null 2>&1; do
  attempts=$((attempts + 1))
  if [ "$attempts" -ge 90 ]; then
    printf '[FAIL] restored backend did not become ready. Keep services stopped and restore %s to roll back.\n' "$rollback" >&2
    docker compose stop backend >/dev/null 2>&1 || true
    exit 1
  fi
  sleep 2
done
docker compose up -d --no-deps frontend >/dev/null

rm -rf "$previous_storage"
restore_completed=1
printf '[OK] restore completed and backend is ready.\n'
printf '[INFO] rollback bundle retained at: %s/%s\n' "$ROOT" "$rollback"
