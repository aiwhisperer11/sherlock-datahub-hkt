# Architecture

## Implemented path

```text
DataHub metadata / sanitized snapshot
             |
             v
FastAPI DataHubMetadataProvider -> FrozenDashboardResult -> Next.js frontend
```

`GET /api/v1/demo/frozen-dashboard` creates `DataHubMetadataProvider` for each request. In `sandbox` mode it loads the frozen JSON fixture. In `mcp` or `graphql` mode it retrieves live metadata through the corresponding read-only adapter. In `auto`, the selection order is MCP, GraphQL, snapshot. The first successful source is the only provider used to construct that investigation; previous failures are retained as sanitized `provider_attempts`.

The result carries parallel provenance instead of merging claims: `simulated_incident_input`, `observed_from_datahub`, and `derived_by_sherlock`. It also returns limitations, missing evidence, and a provisional verdict. The Frozen Dashboard fixture is therefore reproducible but is not live data freshness evidence.

## DataHub boundary and secrets

The MCP adapter permits only `get_entities`, `list_schema_fields`, and `get_lineage`; it disables mutations in the child process. GraphQL sends a read request to the configured GMS URL. `DATAHUB_GMS_TOKEN` is read at runtime only, is not placed in fixtures or API responses, and provider errors are reduced to non-credential messages. BYOC means the operator supplies the GMS URL/token in their own runtime environment; no credential provisioning or secret storage is implemented here.

## Sandbox versus live

Sandbox is deterministic and needs neither network nor token. MCP and GraphQL are live metadata acquisition modes and depend on an available configured DataHub instance. Neither live path proves warehouse freshness, dbt execution, or BI refresh status; those gaps remain explicit in the response.

The local DataHub service on port 9002 has not been verified; no live MCP or GraphQL validation is claimed by this checkpoint.

## Not present in this checkpoint

Sherlock-Core is pre-existing work outside this checkpoint. There is no remote Sherlock-Core client, endpoint, package dependency, or invocation in this codebase; consequently the implemented path is not `DataHub -> FastAPI -> Sherlock-Core -> frontend`.

Likewise, no `SherlockInvestigation` artifact or version `1.0.0` is defined or consumed. The response contract implemented here is the local Pydantic `FrozenDashboardResult` model. Any future Sherlock-Core/BYOC contract integration must be added as a new, separately verified boundary rather than documented as current behavior.
