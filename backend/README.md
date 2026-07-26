# Sherlock Engine backend

FastAPI backend for the Sherlock evidence sandbox. It exposes deterministic demo investigations and the Frozen Dashboard investigation. The latter separates simulated incident telemetry, observed DataHub metadata, and conclusions derived by this backend; it does not use an LLM.

## Requirements and installation

Python 3.11 or newer is required.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

`uv sync` / `uv run` is also supported by the checked-in `uv.lock`, but the editable `pip` command above is the direct development installation supported by `pyproject.toml`.

## Configuration

Copy `.env.example` only if local configuration is needed. Do not put credentials in source, fixtures, test output, or browser variables.

```bash
cp .env.example .env
```

| Variable | Purpose |
| --- | --- |
| `SHERLOCK_CORS_ORIGINS` | Comma-separated browser origins; default `http://localhost:3000`. |
| `SHERLOCK_METADATA_MODE` | `sandbox` (default), `mcp`, `graphql`, or `auto`. |
| `DATAHUB_GMS_URL` | DataHub GMS base URL for live MCP/GraphQL modes. |
| `DATAHUB_GMS_TOKEN` | Runtime-only credential used by live MCP/GraphQL modes; leave unset for sandbox. |
| `SHERLOCK_DATAHUB_MCP_COMMAND` | Command used to launch the MCP server. |
| `SHERLOCK_DATAHUB_MCP_PACKAGE` | MCP package argument passed to that command. |
| `SHERLOCK_DATAHUB_TIMEOUT_SECONDS` | Timeout for live metadata requests. |

Run locally on port 8000:

```bash
uvicorn sherlock.api.main:app --reload --port 8000
```

Available endpoints are `GET /health`, `GET /api/v1/demo/stale-pipeline`, and `GET /api/v1/demo/frozen-dashboard`.

## Frozen Dashboard metadata modes

`sandbox` reads `fixtures/frozen_dashboard_snapshot.json`; it requires no network or token and identifies the observation as `snapshot_from_verified_datahub`. It is fixed evidence, not a live freshness signal.

`mcp` queries only the allowlisted read tools `get_entities`, `list_schema_fields`, and `get_lineage`; mutation tools are rejected and the MCP child is given mutation-disabled configuration. `graphql` performs a read-only GMS GraphQL request. Both are live metadata paths and require a configured GMS URL; MCP also requires the runtime token. `auto` attempts MCP, then GraphQL, then the snapshot, recording sanitized provider outcomes. Every Frozen Dashboard response is built from exactly one successful provider.

## Validation

```bash
cd backend
pytest -v
```

The tests cover the API, sandbox fixture, provider selection/fallback, MCP/GraphQL normalization, and sanitization of provider errors. They do not validate a reachable live DataHub instance.
