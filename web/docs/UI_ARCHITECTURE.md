# UI Architecture

The homepage renders `InvestigationDashboard`, a client component that fetches the sandbox investigation from Sherlock Engine. The feature is separated into a dashboard container, presentational investigation components, a reusable connection-status pill, and a typed API client.

```text
page.tsx
  └── InvestigationDashboard
        ├── StatusPill
        ├── IncidentCard
        ├── AffectedAssets
        ├── HypothesisList
        ├── EvidenceList
        └── RecommendationCard
```

`src/lib/investigation.ts` is the only current API boundary. It reads `NEXT_PUBLIC_SHERLOCK_API_URL`, defaults to `http://localhost:8000`, and calls the backend demo endpoint.

The dashboard is intentionally prepared for a graph/timeline addition without including React Flow or making the initial bundle more complex.
