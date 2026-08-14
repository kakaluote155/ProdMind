#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$REPO_ROOT"

args=(down --remove-orphans)
if [[ "${1:-}" == "--volumes" ]]; then args+=(--volumes); fi

docker compose "${args[@]}"
if [[ "${1:-}" == "--volumes" ]]; then
  echo "ProdMind demo stopped and local demo volumes removed."
else
  echo "ProdMind demo stopped; local demo volumes were preserved."
fi
