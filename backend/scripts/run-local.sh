#!/usr/bin/env bash
set -euo pipefail

backend_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$backend_dir"

uvicorn_args=(uvicorn sherlock.api.main:app --reload --port 8000)
if [[ -f .env ]]; then
  uvicorn_args+=(--env-file .env)
fi

exec uv run "${uvicorn_args[@]}"
