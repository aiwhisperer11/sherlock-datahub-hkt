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

## `GET /api/v1/metadata/mcp/sample`

Discovers one real entity from the configured DataHub instance over MCP (`search`, then `get_entities` and `get_lineage`) and returns it normalised. Unlike the Frozen Dashboard demo, it does not target a fixed URN — it searches for whatever entities actually exist.

Requires `SHERLOCK_METADATA_MODE=mcp` and `DATAHUB_GMS_TOKEN`. There is no GraphQL or snapshot fallback: if MCP is not configured, fails, or returns zero entities, the endpoint responds `502` with a sanitised error instead of substituting fixture data.

```json
{
  "source_mode": "mcp",
  "source_verified": true,
  "entity_count": 1,
  "entity": {
    "urn": "...", "type": "...", "name": "...", "platform": "...",
    "schema_fields": [], "owners": [], "glossary_terms": [], "domains": [],
    "upstream_urns": [], "downstream_urns": []
  },
  "captured_at": "2026-07-31T16:36:00Z",
  "warnings": []
}
```

## Planned API

`POST /api/v1/investigations` is a Phase 2 endpoint. It will accept an asset URN and symptom type, and must include whether the returned investigation used live DataHub data or a snapshot fallback.
