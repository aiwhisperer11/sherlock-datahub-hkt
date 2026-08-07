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

## For judges: quick start

No live public demo is required to evaluate this project (per the hackathon
rules and confirmed directly by the DataHub team in `#agent-hackathon`: judges
are not required to test a live instance, and "let judges spin up DataHub
locally using your README instructions" is an explicitly accepted path). This
is the fastest way to see the real thing working:

**Real requirements and timing (measured, not estimated):**

- **Docker** (Desktop or Engine) and **~8 GB RAM free** for the DataHub
  Quickstart stack (GMS, frontend, MySQL, Kafka, OpenSearch). Below that, it
  still runs but slows down noticeably (we saw this directly during
  development — see "Limitations").
- **First-time `datahub docker quickstart`**: 5-10 minutes (image pulls +
  every service reaching healthy). A second run reusing the same containers
  is under a minute.
- **`GET /api/v1/documents/preview`**: 15-50 seconds — one MCP session doing
  `get_entities` + `get_lineage`, plus, if `SHERLOCK_CORE_URL` is set, a real
  LLM call on top (**50-90 seconds total** in that case — this is a live MCP
  round trip and an LLM call, not a stalled request).
- **`POST /api/v1/documents/publish`**: ~10-15 seconds (its own MCP calls
  only — it never re-runs the context read or the engine; see "Document
  Publish Flow").

```bash
# 1. Start DataHub OSS locally (needs Docker, ~8GB RAM free)
pip install --user acryl-datahub   # or: uv tool install acryl-datahub
datahub docker quickstart
datahub datapack load showcase-ecommerce   # richer lineage/glossary/ownership data

# 2. Backend
cd backend
uv sync
uv run uvicorn sherlock.api.main:app --reload --port 8000

# 3. Frontend (second terminal)
cd web
npm ci
cp .env.example .env.local   # NEXT_PUBLIC_SHERLOCK_API_URL=http://localhost:8000
npm run dev
```

Open `http://localhost:3000`, scroll to **"Publish investigation to DataHub"**,
click **Generate preview** — this reads ORDER_DETAILS live over MCP
(`get_entities` + `get_lineage`), and the reasoning shown is either the real
canonical Sherlock-Core engine's output (if you set `SHERLOCK_CORE_URL`, see
below) or a clearly-labelled local fallback. Review the evidence, click
**Approve & publish**, then watch it retrieve and verify. Nothing is written
to DataHub until you explicitly approve it.

If `datahub docker quickstart` fails with a MySQL port error, see
"DataHub GMS: Start Or Verify Locally" below — it's a known Docker
Desktop/WSL2 issue with a documented fix, not a bug in this repository.

## Current architecture

Implemented runtime path for the Frozen Dashboard endpoint:

```text
DataHub GMS
  -> GraphQL adapter (read-only) or MCP adapter (read-only)
  -> Sherlock backend (FastAPI)
  -> frontend (Next.js)
```

Implemented runtime path for the document publish flow (see "Document Publish
Flow" below) — this is the part of the repository that actually wires DataHub
into the canonical Sherlock-Core investigation engine, not a normalization
boundary sitting unused:

```text
DataHub MCP (get_entities + get_lineage, one session)
  -> DataHubEvidence (tool, urn, observed fact, timestamp, provenance)
  -> canonical SherlockEvidence (with source.datahub_mcp) via to_canonical_evidence()
  -> Sherlock-Core canonical engine (real HTTP call, SHERLOCK_CORE_URL)
       - configured + evidence cited by a hypothesis/matrix/next_test -> engine_source="sherlock_core_canonical"
       - not configured / unreachable / nothing cited -> derive_reasoning_consequence() local fallback, always disclosed
  -> DocumentPreview (server-side cached by content hash)
  -> human review + explicit approval
  -> save_document (MCP, mutation) -> retrieve (MCP, verified)
```

The `backend/src/sherlock/integrations/sherlock_core/` package is the
boundary that makes this real: `contracts.py`/`client.py` talk to the actual
deployed engine (`https://github.com/aiwhisperer11/sherlock-engine`, an
LLM-backed investigation engine — see its own README for how it reasons), not
a mock. `backend/docs/PUBLISH_APPROVAL_FLOW.md` has the full contract;
`backend/docs/MCP_SAVE_DOCUMENT_SPIKE.md` has the original technical spike
that proved DataHub's `save_document`/`search_documents` MCP tools work.

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
- `GET /api/v1/metadata/mcp/sample` and `GET /api/v1/metadata/context?urn=...`
- `POST /api/v1/investigations/frozen-dashboard/writeback`
- `GET /api/v1/documents/preview`, `POST /api/v1/documents/publish`,
  `GET /api/v1/documents/retrieve` — see "Document Publish Flow" below
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

## Document Publish Flow

This is the project's main vertical slice: DataHub metadata really reaches
the canonical Sherlock-Core investigation engine, and a real, cited
conclusion can be published back to DataHub as a `Document`, with a human
approval gate in between. Full contract in
`backend/docs/PUBLISH_APPROVAL_FLOW.md`.

- `GET /api/v1/documents/preview` — read-only. Reads ORDER_DETAILS via
  `get_entities` + `get_lineage` in one MCP session, converts the facts into
  canonical evidence (`E1..En`, each carrying `source: {type: "datahub_mcp",
  tool, entity_urn, retrieved_at}`), and — if `SHERLOCK_CORE_URL` is
  configured — submits them to the real Sherlock-Core engine. The returned
  preview is cached server-side, keyed by its own content hash.
- `POST /api/v1/documents/publish` — takes only `{preview_hash, approved}`.
  There is no request field for title/content/evidence: a client cannot
  inject them. It looks up the exact cached preview by hash (never
  regenerates it — the engine is a live LLM and non-deterministic in
  wording, confirmed empirically) and publishes that, verbatim, only when
  `approved: true`. Unknown, tampered, or expired (15 min TTL, in-memory —
  a backend restart clears it) hashes get `409`. Deterministic
  `idempotency_key` means republishing the same investigation returns
  `already_exists`, never a duplicate document.
- `GET /api/v1/documents/retrieve` — independent read-only re-check via
  `search_documents`; confirms URN, title, and idempotency marker match.

Real evidence this actually works, captured against a local DataHub
instance and the deployed engine at `https://sherlock-engine.vercel.app`:

```text
GET /preview  -> engine_source="sherlock_core_canonical"
                 evidence_ids cited: [E1, E2, E3, E4]  (E4 = get_lineage: 12 upstream deps)
                 statement: "The supplied DataHub context is insufficient to
                 prioritize a specific operational or governance concern..."
POST /publish -> {"status": "created", "urn": "urn:li:document:shared-..."}  (12.6s)
GET /retrieve -> {"status": "verified", ...}
POST /publish (same hash again) -> {"status": "already_exists"}
```

The prompt (packaged in the Sherlock-Core repository) includes a rule added
for this integration: DataHub metadata — lineage, ownership, glossary/PII
classifications, schema — is governed *context*, not a demonstrated cause,
by default. The real engine output above reflects that: it explicitly
declines to elevate lineage or the PII glossary term to a cause without
further evidence.

`mcp-server-datahub` has no document-delete tool: anything actually
published this way is permanent. `DocumentPreview.persistence_warning`
discloses this before approval.

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

The MCP integration has been validated end-to-end against a real, local
DataHub instance repeatedly, including the full document publish flow above
against the real deployed Sherlock-Core engine. Read-only tools and the
`save_document` mutation were both exercised; see
`backend/docs/MCP_SAVE_DOCUMENT_SPIKE.md` for the original spike evidence
(exact tool lists discovered with and without mutations enabled) and
`backend/docs/PUBLISH_APPROVAL_FLOW.md` for the wired contract.

**Public demo hosting is intentionally not the delivery mechanism here.**
Per the official rules ("Judges are not required to test the Project and may
choose to judge based solely on the text description, images, and video")
and confirmed directly by the DataHub team in `#agent-hackathon`: deploying
only the frontend/backend and letting a judge run DataHub locally via this
README is an explicitly accepted path, and standing up a permanent public
DataHub host is optional. The deployed backend (if any) therefore runs
without `SHERLOCK_CORE_URL`/a live `DATAHUB_GMS_URL` by default, and every
endpoint above degrades honestly rather than breaking: `/documents/preview`
falls back to local reasoning with `engine_source="local_fallback"` clearly
disclosed, and `/demo/frozen-dashboard` stays snapshot-backed. Nothing in
the UI ever silently presents a fallback as the live/canonical result.

## Required Environment Variables

Backend:

```bash
SHERLOCK_METADATA_MODE=mcp
DATAHUB_GMS_URL=<GMS base URL>
DATAHUB_GMS_TOKEN=
# Optional: the canonical Sherlock-Core engine (see "Document Publish Flow").
# Unset means the document-publish flow always uses the local fallback.
SHERLOCK_CORE_URL=
```

Frontend:

```bash
NEXT_PUBLIC_SHERLOCK_API_URL=http://localhost:8000
```

Also available in `backend/.env.example`:

- `SHERLOCK_CORS_ORIGINS`
- `SHERLOCK_DATAHUB_MCP_COMMAND`
- `SHERLOCK_DATAHUB_MCP_PACKAGE`
- `SHERLOCK_DATAHUB_TIMEOUT_SECONDS` (default 30s)
- `SHERLOCK_CORE_TIMEOUT_SECONDS` (default 90s — a real Sherlock-Core call
  with DataHub evidence takes noticeably longer than a trivial one)

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

If you need to start a local DataHub stack, use the official CLI:

```bash
datahub docker quickstart
datahub datapack load showcase-ecommerce   # optional but recommended: real
                                            # lineage, owners, glossary/PII
                                            # terms for ORDER_DETAILS
```

**Known Docker Desktop / WSL2 issue:** `docs/spike/DATAHUB_SPIKE.md` recorded
Quickstart failing with `ports are not available: exposing port TCP
0.0.0.0:3306 -> ... /forwards/expose returned unexpected status: 500` when
MySQL tries to publish port 3306. This is Docker Desktop's WSL2
port-forwarding layer, not a bug in DataHub or this repository — it does not
happen on plain Linux Docker Engine (e.g. a cloud VM). Fix, verified working:

```bash
# Only if the plain command above fails with the 3306 error:
datahub docker quickstart --mysql-port 3307
```

If a previously-created container is already stuck bound to 3306 (Quickstart
was run once before without the override), remove it first so it gets
recreated with the new port:

```bash
docker rm -f datahub-mysql-1
datahub docker quickstart --mysql-port 3307
```

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

Optional live tests (skipped unless `DATAHUB_LIVE=1` is set and a local GMS
instance is reachable):

```bash
cd backend
DATAHUB_LIVE=1 uv run --frozen pytest \
  tests/test_graphql_value_entities_live.py \
  tests/test_mcp_save_document_live.py -v
```

To also exercise the real canonical engine in that live run, additionally
export `SHERLOCK_CORE_URL=https://sherlock-engine.vercel.app` (or your own
deployment) first.

## Limitations And Pending Work

- The Frozen Dashboard demo (the older, first vertical slice) still defaults
  to a local snapshot, not a live catalog query — that endpoint is
  deliberately unaffected by any DataHub/engine configuration, for
  reproducibility. The Document Publish Flow is the part of this repository
  that is genuinely live end-to-end when configured.
- `PreviewCache` is in-memory only, per backend process: it is not shared
  across multiple backend instances/workers, and a restart clears it (by
  design — see "Document Publish Flow").
- The canonical Sherlock-Core engine is a live LLM call: wording differs
  between calls even for identical DataHub evidence (confirmed empirically).
  `idempotency_key` is deterministic regardless, so this does not create
  duplicate published documents, but two `GET /preview` calls in a row will
  show the human different phrasing of the same underlying evidence.
- `mcp-server-datahub` has no document-delete tool. Anything published is
  permanent; there is no edit or history UI for previously published
  documents.
- There is no implemented ingestion workflow (writing new DataHub datasets),
  only the `Document`-writeback path described above and the older,
  narrower `update_description`/`add_tags` writeback in
  `backend/src/sherlock/connectors/datahub/writeback.py::McpWritebackProvider`.
- The frontend is a consumer of backend responses; it does not talk to
  DataHub or Sherlock-Core directly.
- A real headless-browser click-through with screenshots was attempted but
  could not be completed in this development sandbox (missing system shared
  libraries, no root access to install them); the flow above was instead
  verified with real HTTP calls against the running app end-to-end,
  including against the real deployed engine.

## Exclusions

This README intentionally avoids:

- tokens or credentials;
- real `.env` contents;
- undocumented claims about successful live MCP validation;
