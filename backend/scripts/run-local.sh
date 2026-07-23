#!/usr/bin/env bash
set -euo pipefail

uvicorn sherlock.api.main:app --reload --port 8000
