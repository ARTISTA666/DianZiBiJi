#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
allow_dirty=0
if [ "${1:-}" = "--allow-dirty" ]; then
  allow_dirty=1
  shift
fi

app_env="${APP_ENV:-}"
if [ -z "$app_env" ] && [ -f "$ROOT_DIR/.env" ]; then
  app_env="$(awk -F= '$1 == "APP_ENV" {sub(/^[^=]*=/, ""); print; exit}' "$ROOT_DIR/.env")"
fi
app_env="${app_env:-development}"
if [ "$allow_dirty" -eq 1 ] && [ "$app_env" = "production" ]; then
  echo "--allow-dirty is available only for non-production development runs" >&2
  exit 1
fi

revision="$(git -C "$ROOT_DIR" rev-parse --verify HEAD^{commit})"
case "$revision" in
  ''|*[!0-9a-f]*)
    echo "git HEAD is not a hexadecimal revision" >&2
    exit 1
    ;;
esac
if [ "${#revision}" -ne 40 ] && [ "${#revision}" -ne 64 ]; then
  echo "git HEAD is not a full revision" >&2
  exit 1
fi

if [ "$allow_dirty" -eq 0 ]; then
  if ! git -C "$ROOT_DIR" diff --quiet || ! git -C "$ROOT_DIR" diff --cached --quiet; then
    echo "tracked checkout changes detected; use a clean checkout for build/evidence" >&2
    exit 1
  fi
  disallowed_untracked=0
  while IFS= read -r status_line; do
    [ -n "$status_line" ] || continue
    path="${status_line#?? }"
    case "$path" in
      data/real/*|agent-work/*)
        ;;
      *)
        disallowed_untracked=1
        ;;
    esac
  done <<EOF
$(git -C "$ROOT_DIR" status --porcelain=v1 --untracked-files=all | awk 'substr($0, 1, 2) == "??"')
EOF
  if [ "$disallowed_untracked" -ne 0 ]; then
    echo "untracked non-research files detected; build/evidence requires a clean checkout" >&2
    exit 1
  fi
fi

cd "$ROOT_DIR"
exec env BUILD_REVISION="$revision" docker compose "$@"
