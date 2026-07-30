# DataHub Integration

## Current behavior

`DataHubMetadataProvider` supports the Frozen Dashboard demo through three read-only sources:

1. DataHub MCP (`mcp`) using only `get_entities`, `list_schema_fields`, and `get_lineage`.
2. GMS GraphQL (`graphql`) at `${DATAHUB_GMS_URL}/api/graphql`.
3. A local unverified snapshot fixture (`sandbox`).

`auto` tries MCP, GraphQL, then the snapshot. Each attempt is emitted with its provider, status, duration, and sanitized failure reason. Evidence is selected from one provider per response; it is never silently merged.

## Safety

- MCP receives `DATAHUB_GMS_URL` and `DATAHUB_GMS_TOKEN` only in its child-process environment, with `TOOLS_IS_MUTATION_ENABLED=false`.
- GraphQL sends a token only as an Authorization header when one is configured.
- No provider treats `Last Updated` or `Synced` as data freshness.
- The snapshot is `local_snapshot_unverified` with `snapshot_fixture` provenance; it is not live DataHub metadata or freshness evidence.

## Endpoint contract

`GET /api/v1/demo/frozen-dashboard` separates simulated incident input, live `observed_from_datahub` when available, snapshot-backed `snapshot_fixture` evidence when sandbox is selected, `derived_by_sherlock`, `limitations`, `provider_attempts`, and `selected_provider`. MCP without a token is `not_configured`; an attempted MCP error is `failed`.

The initial dashboard symptom is simulated. Metadata evidence can support hypotheses, but the implementation never claims a root cause without operational logs or other confirming evidence.
