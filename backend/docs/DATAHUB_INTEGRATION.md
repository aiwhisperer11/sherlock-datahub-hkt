# DataHub Integration

## Current behavior

`DataHubMetadataProvider` supports the Frozen Dashboard demo through three read-only sources:

1. DataHub MCP (`mcp`) using only `get_entities`, `list_schema_fields`, and `get_lineage`.
2. GMS GraphQL (`graphql`) at `${DATAHUB_GMS_URL}/api/graphql`.
3. A sanitized verified snapshot (`sandbox`).

`auto` tries MCP, GraphQL, then the snapshot. Each attempt is emitted with its provider, status, duration, and sanitized failure reason. Evidence is selected from one provider per response; it is never silently merged.

## Safety

- MCP receives `DATAHUB_GMS_URL` and `DATAHUB_GMS_TOKEN` only in its child-process environment, with `TOOLS_IS_MUTATION_ENABLED=false`.
- GraphQL sends a token only as an Authorization header when one is configured.
- No provider treats `Last Updated` or `Synced` as data freshness.
- The snapshot is explicitly labelled `snapshot_from_verified_datahub` and is not live freshness evidence.

## Endpoint contract

`GET /api/v1/demo/frozen-dashboard` separates `simulated_incident_input`, `observed_from_datahub`, `derived_by_sherlock`, `limitations`, `provider_attempts`, and `selected_provider`.

The initial dashboard symptom is simulated. Metadata evidence can support hypotheses, but the implementation never claims a root cause without operational logs or other confirming evidence.
