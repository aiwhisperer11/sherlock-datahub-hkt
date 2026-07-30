# Sherlock Evidence Sandbox

Sherlock investigates **The Case of the Frozen Dashboard** through a FastAPI
backend and a Next.js dashboard. The backend keeps simulated incident input,
provider provenance, deterministic hypotheses, limitations, and recommended
next actions separate in the response consumed by the frontend.

For the Frozen Dashboard, the default `sandbox` path reads a deterministic
local JSON snapshot. That snapshot is labelled `local_snapshot_unverified`: it
is not live DataHub metadata and it is not live freshness evidence. When a
live provider is selected, read-only GraphQL and MCP adapters can retrieve and
normalise DataHub schemas, ownership, and lineage. In `auto` mode the backend
tries MCP, then GraphQL, then the local snapshot, and returns the provider
attempts alongside the selected result.
Sherlock investigates **The Case of the Frozen Dashboard**: a dashboard has missed its expected update, and the investigation keeps the simulated alert, observed DataHub metadata, derived hypotheses, limitations, and recommendation distinct.

## Repository layout

```text
sherlock-datahub-hkt/
├── backend/  # FastAPI API, providers, fixtures, and tests
├── web/      # Next.js client for the Frozen Dashboard response
└── docs/     # Cross-cutting documentation index and supporting material
```

See the package READMEs for focused setup and behaviour, and
[`docs/README.md`](docs/README.md) for the documentation index.

## Requirements

- Python 3.11+
- Node.js 20.9+
- npm
- `uv` for the backend workflow

## Run locally

Start the backend on port **8000**:

```bash
cd backend
uv sync
uv run uvicorn sherlock.api.main:app --reload --port 8000
```

In a second terminal, start the web app on port **3000**:

```bash
cd web
npm ci
cp .env.example .env.local
npm run dev
```

Open `http://localhost:3000`. The frontend reads
`NEXT_PUBLIC_SHERLOCK_API_URL`, whose code default is
`http://localhost:8000`.
Open `http://localhost:3000`. The frontend reads `NEXT_PUBLIC_SHERLOCK_API_URL`, which defaults to `http://localhost:8000`.

## DataHub evidence modes

The default vertical slice uses a deterministic, clearly labelled JSON snapshot from verified DataHub evidence and does not use an LLM. The Frozen Dashboard endpoint also supports read-only DataHub MCP and GMS GraphQL providers. In `auto` mode it tries MCP, GraphQL, then the snapshot; each provider attempt is returned in the response. Snapshot evidence is explicitly marked as non-live freshness evidence.

## Validation

```bash
cd backend && uv sync && uv run pytest
cd web && npm ci && npm run lint && npm test && npm run build
```
