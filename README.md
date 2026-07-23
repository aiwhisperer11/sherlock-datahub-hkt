# Sherlock Evidence Sandbox

Sherlock investigates **The Case of the Stale Pipeline**: a NYC Taxi revenue dashboard is stale, and the investigation distinguishes a genuine business event from a silent data-pipeline degradation. It presents the affected assets, evidence, hypotheses, explainable confidence, conclusion, and recommended action.

## Repository layout

```text
sherlock-datahub-hkt/
├── backend/  # FastAPI evidence engine and sandbox fixture
├── web/      # Next.js investigation dashboard
└── docs/     # Documentation shared by the monorepo
```

Each package preserves its own README, setup notes, and package-specific `.gitignore`.

## Requirements

- Python 3.11+
- Node.js 20.9+
- npm
- `uv` for the backend validation workflow

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

Open `http://localhost:3000`. The frontend reads `NEXT_PUBLIC_SHERLOCK_API_URL`, which defaults to `http://localhost:8000`.

## Sandbox status

The current vertical slice uses a deterministic, clearly labelled JSON sandbox fixture. It does not connect to external services and does not use an LLM. DataHub MCP integration is intentionally **not implemented yet**; the backend only contains the interface boundary for a future adapter.

## Validation

```bash
cd backend && uv sync && uv run pytest
cd web && npm ci && npm run lint && npm test && npm run build
```

No commits, remotes, publication, or deployment are configured by this repository setup.
