# Sherlock Engine backend

FastAPI backend for Sherlock's evidence sandbox. It exposes the deterministic
demo endpoints `GET /health`, `GET /api/v1/demo/stale-pipeline`, and
`GET /api/v1/demo/frozen-dashboard`. The Frozen Dashboard route creates a
`DataHubMetadataProvider` for each request and builds a deterministic result
while keeping simulated incident input, provider-backed observations, derived
content, and limitations distinct.

## Requirements and installation

Python 3.11 or newer is required. The checked-in `uv.lock` supports the
reproducible local workflow:

```bash
cd backend
uv sync
```

Run the API on port 8000:

```bash
uv run uvicorn sherlock.api.main:app --reload --port 8000
```

## Configuration

Copy `.env.example` only when local configuration is needed. Keep runtime
credentials out of source, fixtures, browser variables, and test output.

| Variable | Purpose |
| --- | --- |
| `SHERLOCK_CORS_ORIGINS` | Comma-separated browser origins; code default: `http://localhost:3000`. |
| `SHERLOCK_METADATA_MODE` | `sandbox` (default), `mcp`, `graphql`, or `auto`. |
| `DATAHUB_GMS_URL` | GMS base URL used by GraphQL and passed to the MCP child; code default: `http://localhost:8080`. |
| `DATAHUB_GMS_TOKEN` | Optional bearer token for GraphQL and required by the MCP provider. |
| `SHERLOCK_DATAHUB_MCP_COMMAND` | Command used to launch the MCP server. |
| `SHERLOCK_DATAHUB_MCP_PACKAGE` | MCP package argument passed to that command. |
| `SHERLOCK_DATAHUB_TIMEOUT_SECONDS` | Timeout for provider requests. |

## Frozen Dashboard provider modes

`sandbox` reads `fixtures/frozen_dashboard_snapshot.json`. Its observation is
labelled `local_snapshot_unverified`, and its resulting evidence is labelled
`snapshot_fixture`. It is a local, non-auditable snapshot; it is neither live
DataHub metadata nor live freshness evidence.

`graphql` sends a read-only request to the configured GMS `/api/graphql`
endpoint and normalises the returned dataset. Its query requests schemas,
ownership, and upstream and downstream lineage. A token is included only when
configured.

`mcp` requires `DATAHUB_GMS_TOKEN`, starts the configured MCP command with
mutation support disabled, and permits only `get_entities`,
`list_schema_fields`, and `get_lineage`. It rejects calls outside that allowlist
and sanitises provider errors before returning them.

`auto` tries MCP, then GraphQL, then the local snapshot. It records sanitized
provider attempts and constructs the response from the first successful
provider. If MCP has no token, that attempt is recorded as `not_configured`
before `auto` continues.

The response field is named `observed_from_datahub` for contract compatibility,
but its name does not establish live provenance. Consumers must use the
selected provider, observation `source`, and evidence provenance: a snapshot
payload remains local and unverified.

## Validation

Run the ordinary backend suite with:

```bash
uv run pytest -v
```

These tests cover the API, sandbox fixture, provider selection and fallback,
MCP and GraphQL adapter normalisation with stubs, read-tool restrictions, and
error sanitisation. They do not demonstrate connectivity to a live DataHub
instance. The separate GraphQL compatibility test is skipped unless
`DATAHUB_LIVE=1` is set; it is the only test intended to contact a local live
GraphQL endpoint.
