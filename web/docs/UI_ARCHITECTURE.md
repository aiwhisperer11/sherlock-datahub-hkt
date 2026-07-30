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
        └── Limitations
```

`src/lib/investigation.ts` is the only current API boundary. It reads `NEXT_PUBLIC_SHERLOCK_API_URL`, defaults to `http://localhost:8000`, and calls `/api/v1/demo/frozen-dashboard`.

The dashboard is intentionally prepared for a graph/timeline addition without including React Flow or making the initial bundle more complex.
