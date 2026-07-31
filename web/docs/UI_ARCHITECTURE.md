# UI Architecture

The homepage renders `InvestigationDashboard`, a client component that fetches the Frozen Dashboard investigation from Sherlock Engine. It keeps the simulated symptom, DataHub observations, and Sherlock-derived hypotheses visibly separate. The feature is separated into a dashboard container, presentational investigation components, a reusable connection-status pill, and a typed API client.

```text
page.tsx
  └── InvestigationDashboard
        ├── StatusPill
        ├── InvestigationSummary
        ├── DataHubEvidence
        ├── HypothesisList
        ├── ProviderAttempts
        ├── Limitations
        └── McpSamplePanel
              ├── StatusPill
              └── McpSampleBody (SourceBadge, FieldList × 6)
```

`src/lib/investigation.ts` reads `NEXT_PUBLIC_SHERLOCK_API_URL`, defaults to `http://localhost:8000`, and calls `/api/v1/demo/frozen-dashboard`.

`McpSamplePanel` (`src/features/mcp-sample/`) shows one real DataHub entity. It has two explicit, user-selected modes with no silent fallback between them:

- **MCP (live)** calls `src/lib/mcp-sample.ts`'s `fetchMcpSample()` against `GET /api/v1/metadata/mcp/sample`. Requires the backend to be running with `SHERLOCK_METADATA_MODE=mcp` and a real DataHub; on failure it shows an error state naming the sanitised backend detail, never a fabricated snapshot.
- **Snapshot (demo)** calls `fetchSnapshotSample()`, which reuses the existing `/api/v1/demo/frozen-dashboard` sandbox response instead of a second backend endpoint, and maps its `observed_from_datahub` into the same display shape. Always reports `verified: false` and is visibly labelled "Snapshot · demo data, not live".

Both paths only ever call the Sherlock backend (never GraphQL, never DataHub directly), so `DATAHUB_GMS_TOKEN` never reaches the browser.

The dashboard is intentionally prepared for a graph/timeline addition without including React Flow or making the initial bundle more complex.
