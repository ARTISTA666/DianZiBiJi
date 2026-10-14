#!/bin/bash
set -euo pipefail
root=/Users/yusong/Downloads/new/full-system
if [[ $# -lt 5 || "$1" != '-p' || "$2" != 'eln-t148-e2e' || "$3" != '-f' || "$4" != "$root/docker-compose.e2e.yml" ]]; then
  echo 'Refusing a compose target outside the owned T148 stack' >&2
  exit 97
fi
shift 4
exec bash "$root/scripts/ops/docker-compose-with-revision.sh" --allow-dirty -p eln-t148-e2e -f "$root/docker-compose.e2e.yml" -f "$root/agent-work/t148-2026-10-12/system/compose.override.yml" "$@"
