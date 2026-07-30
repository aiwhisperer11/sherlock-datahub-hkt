# Architecture

This repository is a monorepo. `backend/` owns the FastAPI API, investigation
models, and DataHub provider layer; `web/` owns the browser client. They meet
at the REST contract exposed by the backend. The repository also preserves the
existing Sherlock Core normalisation boundary under
`backend/src/sherlock/integrations/`.

## Implemented path

```text
local snapshot (sandbox) ───────────────┐
GraphQL adapter (schemas, ownership,    │
  upstream/downstream lineage) ─────────┼─> DataHubMetadataProvider
MCP adapter (get_entities,              │             │
  list_schema_fields, get_lineage) ─────┘             v
                                        FrozenDashboardResult
                                                 │
                                                 v
                                      FastAPI API -> Next.js client

SherlockInvestigation 1.0.0 fixture -> existing Sherlock Core normalisation
                                      boundary -> preserved models and tests
```

`GET /api/v1/demo/stale-pipeline` loads the labelled JSON fixture, validates
it into Pydantic models, and returns an `Investigation`.

`GET /api/v1/demo/frozen-dashboard` creates `DataHubMetadataProvider` per
request. In `sandbox` mode it reads the frozen JSON fixture. In `mcp` or
`graphql` mode it uses only that selected adapter. In `auto`, the selection
order is MCP, GraphQL, then snapshot; failed attempts are retained as
sanitised `provider_attempts`, and the first successful provider supplies the
observation used to build the result.

The result carries parallel provenance instead of merging claims:
`simulated_incident_input`, `observed_from_datahub`, and
`derived_by_sherlock`. It also returns limitations, missing evidence, and a
provisional verdict. The Frozen Dashboard fixture is reproducible but is not
live data freshness evidence.

## Provider boundaries

`DataHubMetadataProvider` separates acquisition from interpretation. The
GraphQL adapter sends a read-only query for schemas, ownership, and upstream
and downstream lineage. The MCP adapter is configured with mutation support
disabled and invokes only `get_entities`, `list_schema_fields`, and
`get_lineage`.

The provider normalises a selected source into `DataHubObservation`, then
builds a deterministic `FrozenDashboardResult`. This path does not replace the
preserved Sherlock Core normalisation boundary or its `SherlockInvestigation
1.0.0` fixture and tests.

## Evidence semantics

- A sandbox result comes from a local snapshot labelled
  `local_snapshot_unverified`, with evidence labelled `snapshot_fixture`.
- A local snapshot is not metadata live, and metadata live is not freshness
  live. The snapshot therefore does not establish current DataHub state or a
  current freshness value.
- When GraphQL or MCP succeeds, the selected provider is reflected in the
  response and the normalised observation source; provider attempts retain
  their sanitised statuses.
- Incident symptom and telemetry remain simulated input, separate from the
  selected provider's observation and from Sherlock-derived content.

The `observed_from_datahub` response-field name alone is not proof of a live
query. Provenance must be read from the selected provider, observation source,
and evidence labels.

## DataHub boundary and secrets

The MCP adapter permits only `get_entities`, `list_schema_fields`, and
`get_lineage`; it disables mutations in the child process. GraphQL sends a
read request to the configured GMS URL. `DATAHUB_GMS_TOKEN` is read at runtime
only, is not placed in fixtures or API responses, and provider errors are
reduced to non-credential messages. BYOC means the operator supplies the GMS
URL/token in their own runtime environment; no credential provisioning or
secret storage is implemented here.

## Sandbox versus live

- CORS origins are configured with `SHERLOCK_CORS_ORIGINS`; the code default
  is `http://localhost:3000`.
- FastAPI exposes generated OpenAPI documentation at `/docs`.
- Sandbox is deterministic and needs neither network nor token. MCP and
  GraphQL are live metadata acquisition modes and depend on an available
  configured DataHub instance.
- Neither live path proves warehouse freshness, dbt execution, or BI refresh
  status; those gaps remain explicit in the response.
- The local DataHub service on port 9002 has not been verified; no live MCP or
  GraphQL validation is claimed by this checkpoint.

## Not present in this checkpoint

Sherlock-Core is pre-existing work outside this checkpoint. There is no remote
Sherlock-Core client, endpoint, package dependency, or invocation in this
codebase; consequently the implemented path is not
`DataHub -> FastAPI -> Sherlock-Core -> frontend`.

Likewise, no `SherlockInvestigation` artifact or version `1.0.0` is defined or
consumed. The response contract implemented here is the local Pydantic
`FrozenDashboardResult` model. Any future Sherlock-Core/BYOC contract
integration must be added as a new, separately verified boundary rather than
documented as current behavior.
