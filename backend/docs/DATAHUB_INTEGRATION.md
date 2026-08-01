# DataHub Integration

## Current behavior

`GET /api/v1/demo/frozen-dashboard` always uses `DataHubMetadataProvider.load_frozen_dashboard_from_snapshot()`, which always reads the local snapshot fixture (`SnapshotMetadataProvider`). It does not read `SHERLOCK_METADATA_MODE` and cannot select MCP or GraphQL. This is deliberate: the endpoint backs the frontend's deterministic "Snapshot (demo)" investigation and must keep working regardless of how live metadata acquisition is configured elsewhere.

`DataHubMetadataProvider.load_frozen_dashboard()` (mode-driven: `sandbox`/`mcp`/`graphql`/`auto`, trying MCP then GraphQL then the snapshot) still exists and is unit-tested, but no HTTP endpoint currently calls it. It is retained for any future operator-configurable live mode, not wired to the API today.

`GET /api/v1/metadata/mcp/sample` always uses `McpSampleProvider`, which is unconditionally MCP-only — it only requires `DATAHUB_GMS_TOKEN`, and does not read `SHERLOCK_METADATA_MODE` either.

`SHERLOCK_METADATA_MODE` therefore has no effect on either live HTTP endpoint. The two features were previously coupled to this single env var — setting it to enable one silently broke the other. See the incident this fixed: a demo deploy where `SHERLOCK_METADATA_MODE` was set for the MCP sample panel, which made `/api/v1/demo/frozen-dashboard` raise `Unsupported SHERLOCK_METADATA_MODE` and return 500.

## Safety

- MCP receives `DATAHUB_GMS_URL` and `DATAHUB_GMS_TOKEN` only in its child-process environment, with `TOOLS_IS_MUTATION_ENABLED=false`.
- GraphQL sends a token only as an Authorization header when one is configured.
- No provider treats `Last Updated` or `Synced` as data freshness.
- The snapshot is `local_snapshot_unverified` with `snapshot_fixture` provenance; it is not live DataHub metadata or freshness evidence.

## Endpoint contract

`GET /api/v1/demo/frozen-dashboard` separates simulated incident input from `observed_from_datahub` (always `snapshot_fixture` provenance today), `derived_by_sherlock`, `limitations`, `provider_attempts`, and `selected_provider` (always `"snapshot"`).

The initial dashboard symptom is simulated. Metadata evidence can support hypotheses, but the implementation never claims a root cause without operational logs or other confirming evidence.

## MCP sample endpoint

`McpSampleProvider` (`GET /api/v1/metadata/mcp/sample`) is a separate, generic read path: it does not target a fixed URN. It calls the MCP `search` tool with a broad query, prefers the first `DATASET` result, then fetches that entity plus one-hop lineage via `get_entities`/`get_lineage`. It never falls back to GraphQL or a snapshot fixture — a missing token, an MCP failure, or a zero-entity search all raise an explicit, sanitised `DataHubProviderError`.
