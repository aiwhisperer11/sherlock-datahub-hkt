# Sherlock for DataHub

Sherlock is a hackathon prototype for investigating metadata-driven incidents
without pretending that metadata alone proves execution state or root cause.
The current vertical slice focuses on two demo cases:

- `GET /api/v1/demo/stale-pipeline`: deterministic sandbox-only investigation.
- `GET /api/v1/demo/frozen-dashboard`: deterministic investigation that can use
  a local snapshot or read-only DataHub metadata adapters.

The problem it tries to solve is practical: when a dashboard looks stale or a
governance signal looks contradictory, teams need a structured investigation
artifact that keeps these things separate:

- simulated incident input;
- metadata observed from DataHub or from a labelled local snapshot;
- Sherlock-derived hypotheses and limitations;
- what still has to be checked outside DataHub before claiming root cause.

## Current architecture

Implemented runtime path for the Frozen Dashboard endpoint:

```text
DataHub GMS
  -> GraphQL adapter (read-only) or MCP adapter (read-only)
  -> Sherlock backend (FastAPI)
  -> frontend (Next.js)
```

Additional preserved integration boundary in this repository:

```text
DataHub observation
  -> Sherlock Core normalization boundary
  -> SherlockInvestigation 1.0.0 schema validation/tests
```

That preserved Sherlock Core boundary exists under
`backend/src/sherlock/integrations/sherlock_core/`, but it is not the runtime
path used by `GET /api/v1/demo/frozen-dashboard` today.

Repository layout:

```text
sherlock-datahub-hkt/
├── backend/  # FastAPI API, metadata providers, fixtures, tests
├── web/      # Next.js frontend
└── docs/     # project docs and spike artifacts
```

## What Is Implemented

Backend endpoints implemented now:

- `GET /health`
- `GET /api/v1/demo/stale-pipeline`
- `GET /api/v1/demo/frozen-dashboard`
- FastAPI OpenAPI docs at `/docs`

Metadata modes supported by code in `backend/src/sherlock/connectors/datahub/provider.py`:

- `sandbox`
- `mcp`
- `graphql`
- `auto`

Behavior by mode:

- `sandbox`: reads `backend/fixtures/frozen_dashboard_snapshot.json`
- `mcp`: read-only MCP child process; requires `DATAHUB_GMS_TOKEN`
- `graphql`: read-only request to `${DATAHUB_GMS_URL}/api/graphql`
- `auto`: tries `mcp -> graphql -> snapshot`

The backend never silently merges providers in one response. It records
`provider_attempts` and builds the result from the first successful provider.

## Frozen Dashboard Status

The Frozen Dashboard demo is real code and test-covered, but the default demo
path is still a deterministic local snapshot.

Snapshot source and provenance:

- file: `backend/fixtures/frozen_dashboard_snapshot.json`
- observation `source`: `local_snapshot_unverified`
- `captured_at`: `2026-07-24T00:00:00Z`
- warning in fixture: original capture is not auditable against the current
  DataHub response

What that means:

- it is not live DataHub metadata;
- it is not live freshness evidence;
- it is not proof that a pipeline, dbt job, warehouse table, or BI refresh ran;
- it is suitable for a reproducible demo and tests only.

## Governance Terms Case

This repository now contains a two-iteration Governance Terms investigation in
`backend/fixtures/investigations/governance_terms/`.

- `iteration_1.json`: records the contradiction and competing explanations
- `iteration_2.json`: reuses previously captured evidence to narrow the case
  without claiming one global root cause
- `manifest.json`: records schema version, validation status, SHA-256 digests,
  and confirms `mutation_performed=false`, `ingestion_performed=false`,
  `root_cause_proven=false`

Important limits of these fixtures:

- they are Sherlock investigation snapshots derived from previously captured
  live metadata;
- they are not raw MCP responses;
- they do not by themselves prove an MCP execution;
- no mutation or ingestion was performed to create them.

## DataHub MCP Integration Status

The MCP integration was validated end-to-end against a real DataHub instance,
separately from the public demo scenario:

- Result: HTTP 200, 20.2s round trip, `source_mode=mcp`, `source_verified=true`.
- Read-only tools only; no mutation performed during this validation.
- This validation is independent of the Frozen Dashboard scenario, which uses
  a labelled snapshot fixture for reproducibility (see "Frozen Dashboard
  Status" above).

The MCP path currently depends on a local DataHub instance and a temporary
tunnel. It is not permanently available in the public demo; the public
demo's Frozen Dashboard endpoint is always snapshot-backed for this reason.
The MCP tab in the UI is an optional, separately-verified capability, not the
source of the incident scenario.

### Live metadata-context endpoint validation

`GET /api/v1/metadata/context?urn=ORDER_DETAILS_URN` was validated live
against the deployed Render backend, connected to a local DataHub Quickstart
instance through a temporary Cloudflare quick tunnel pointed at local GMS.
Result: `source=mcp`, `live=true`, 55 schema fields, PII-tagged glossary
terms, 12 upstream / 14 downstream lineage entities returned.

The tunnel was intentionally closed immediately after capturing this
evidence, and is not part of the public demo's standing infrastructure. The
local DataHub instance behind it runs with
`METADATA_SERVICE_AUTH_ENABLED=false` — leaving that tunnel open would
expose an unauthenticated DataHub instance to the public internet for as
long as it stayed up, which is a real security/availability risk, not a
hypothetical one. As a result, `SHERLOCK_METADATA_MODE=mcp` on the deployed
backend will fail (no reachable `DATAHUB_GMS_URL`) until a new tunnel is
opened for a future verification window. The "MCP (live)" panel correctly
reports this as unavailable rather than silently falling back to the
snapshot.

## Required Environment Variables

Backend:

```bash
SHERLOCK_METADATA_MODE=mcp
DATAHUB_GMS_URL=<GMS base URL>
DATAHUB_GMS_TOKEN=
```

Frontend:

```bash
NEXT_PUBLIC_SHERLOCK_API_URL=http://localhost:8000
```

Also available in `backend/.env.example`:

- `SHERLOCK_CORS_ORIGINS`
- `SHERLOCK_DATAHUB_MCP_COMMAND`
- `SHERLOCK_DATAHUB_MCP_PACKAGE`
- `SHERLOCK_DATAHUB_TIMEOUT_SECONDS`

Do not commit real `.env` files, tokens, or credentials.

## Installation

Requirements:

- Python 3.11+
- `uv`
- Node.js 20.9+
- `npm`

Backend install:

```bash
cd backend
uv sync
```

Frontend install:

```bash
cd web
npm ci
cp .env.example .env.local
```

## Local Run

Start the backend:

```bash
cd backend
uv run uvicorn sherlock.api.main:app --reload --port 8000
```

Start the frontend in a second terminal:

```bash
cd web
npm run dev
```

Open `http://localhost:3000`.

## DataHub GMS: Start Or Verify Locally

The code expects local GMS at:

```text
http://localhost:8080
```

Basic verification:

```bash
curl --fail http://localhost:8080/
```

GraphQL reachability check:

```bash
curl --fail \
  -H 'Content-Type: application/json' \
  -d '{"query":"{ __typename }"}' \
  http://localhost:8080/api/graphql
```

If you need to start a local DataHub stack, the repository spike work used the
official CLI quickstart path documented at the time of the spike:

```bash
datahub docker quickstart
```

But note the checked-in spike result in `docs/spike/DATAHUB_SPIKE.md`: the
local Quickstart was blocked by Docker port-publication issues, so this
repository does not claim that local GMS startup is already solved here.

## Validation Commands

Backend tests:

```bash
cd backend
uv run pytest -v
```

Frontend lint:

```bash
cd web
npm run lint
```

Frontend tests:

```bash
cd web
npm test
```

Frontend build:

```bash
cd web
npm run build
```

Optional live GraphQL compatibility test:

```bash
DATAHUB_LIVE=1 uv run --project backend --frozen pytest \
  backend/tests/test_graphql_value_entities_live.py -q
```

That optional test is skipped unless `DATAHUB_LIVE=1` is set and a local GMS
instance is reachable.

## Limitations And Pending Work

- The main demo still defaults to a local snapshot, not a live catalog query.
- The repository does not prove live metadata, live freshness, or root cause.
- A read-only-verified, opt-in mutation (writeback) path exists in
  `backend/src/sherlock/connectors/datahub/writeback.py`; it is not exposed
  in the public UI and was not exercised as part of the Frozen Dashboard
  scenario.
- There is no implemented ingestion workflow.
- A real end-to-end MCP read successfully returned a DataHub entity with
  `source_mode=mcp` and `source_verified=true`. The validation depends on a
  local DataHub instance and a temporary tunnel, so the MCP path is not
  permanently available in the public demo.
- Local DataHub quickstart was previously blocked by Docker port issues.
- The frontend is a consumer of backend responses; it does not talk to DataHub
  directly.
- The runtime Frozen Dashboard path does not yet invoke the preserved Sherlock
  Core normalization boundary.

## Exclusions

This README intentionally avoids:

- tokens or credentials;
- real `.env` contents;
- undocumented claims about successful live MCP validation;
