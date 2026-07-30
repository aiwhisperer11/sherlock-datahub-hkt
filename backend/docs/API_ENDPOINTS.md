# API Endpoints

Base URL for local development: `http://localhost:8000`.

## `GET /health`

Returns service availability.

```json
{ "status": "ok" }
```

## `GET /api/v1/demo/stale-pipeline`

Returns the deterministic sandbox investigation for **The Case of the Stale Pipeline**. It is demo data, not a live DataHub result.

The response contains `incident`, `assets`, `observations`, `evidence`, `hypotheses`, `conclusion`, `recommended_actions`, and typed `relationships`. Every hypothesis includes the individual confidence components and the computed `score`.

## `GET /api/v1/demo/frozen-dashboard`

Returns the Frozen Dashboard investigation. Its response deliberately separates `simulated_incident_input`, `observed_from_datahub`, `derived_by_sherlock`, `limitations`, `provider_attempts`, and `selected_provider`.

`SHERLOCK_METADATA_MODE=sandbox` is the default and reads the local unverified snapshot fixture. Its evidence is `snapshot_fixture`, not live DataHub metadata or freshness. Real read-only `mcp` and `graphql` use `observed_from_datahub`; `auto` tries MCP, GraphQL, then the snapshot. MCP without a token is `not_configured`; attempted MCP errors are `failed`.
The endpoint does not assert a root cause without operational evidence such as execution logs or live freshness signals.

## Planned API

`POST /api/v1/investigations` is a Phase 2 endpoint. It will accept an asset URN and symptom type, and must include whether the returned investigation used live DataHub data or a snapshot fallback.
