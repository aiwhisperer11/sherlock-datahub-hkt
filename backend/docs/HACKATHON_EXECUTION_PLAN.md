# SHERLOCK EVIDENCE SANDBOX — HACKATHON EXECUTION PLAN
**Build with DataHub: The Agent Hackathon**
**Submission Period:** July 23 - August 10, 2026 (19 days)

---

## 1. CONTEXT & SCOPE

### The Case of the Stale Pipeline
**Business Narrative:**
*"The ride-sharing dashboard shows anomalous revenue, but nobody knows if the business collapsed or if the data stopped updating."*

**Investigation Flow:**
1. **Symptom:** Revenue metric hasn't updated in 6 hours (dashboard alert triggered)
2. **Question:** Is this a business crash or a pipeline degradation?
3. **Sherlock's job:** Reconstruct what happened, where it broke, and what's impacted
4. **Output:** Evidence-backed investigation with confidence score and recommended action

### MVP Scope (P0 — Mandatory)
- ✅ Select/receive an asset to investigate (nyc-taxi revenue metric)
- ✅ Read metadata, schema, ownership, lineage from DataHub
- ✅ Identify probable point of degradation (freshness signal)
- ✅ Trace upstream & downstream dependencies
- ✅ Generate 2-4 hypotheses (pipeline failed, data contract broken, schema mismatch)
- ✅ Collect real evidence for each hypothesis
- ✅ Compute explainable confidence score
- ✅ Present conclusion, impact, and recommended action
- ✅ Export investigation as JSON

### P1 (If Time Permits)
- Timeline visualization
- Comparison between two pipeline runs
- Deep links to DataHub assets
- Markdown export

### Out of Scope
- Universal anomaly detection
- Autonomous remediation execution
- Multi-agent orchestration
- Real BYOC connectors
- Specialized graph database
- LLM-only reasoning (evidence must be traceable)

---

## 2. ARCHITECTURE

### System Diagram
```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js)                   │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐   │
│  │ Investigation│  │   Evidence   │  │  Hypothesis     │   │
│  │ Dashboard    │  │   Timeline   │  │  Scorer         │   │
│  └──────────────┘  └──────────────┘  └─────────────────┘   │
└────────────────────────────┬─────────────────────────────────┘
                             │ REST API
┌────────────────────────────▼─────────────────────────────────┐
│                   BACKEND (FastAPI)                           │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐   │
│  │ Investigation│  │   Evidence   │  │  DataHub        │   │
│  │ Engine       │  │   Graph      │  │  Connector      │   │
│  └──────────────┘  └──────────────┘  └─────────────────┘   │
└────────────────────────────┬─────────────────────────────────┘
                             │ MCP Server + Skills
┌────────────────────────────▼─────────────────────────────────┐
│              DATAHUB (Local Quickstart)                      │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  NYC-Taxi Dataset (3-stage pipeline with issues)        │ │
│  │  • Freshness degradation planted                        │ │
│  │  • Lineage: ingestion → transform → dashboard           │ │
│  │  • Metadata: schema, ownership, tags                    │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### Evidence Graph Data Model
```
Incident
  ├─ id: str
  ├─ asset_urn: str (what changed)
  ├─ symptom: str (freshness, schema, lineage)
  ├─ detected_at: datetime
  ├─ observations: [Observation]
  └─ hypotheses: [Hypothesis]

Observation
  ├─ id: str
  ├─ type: "freshness_lag" | "schema_mismatch" | "lineage_break"
  ├─ data: dict
  └─ source: "datahub" | "computed"

Hypothesis
  ├─ id: str
  ├─ title: str (e.g., "Upstream job failed")
  ├─ description: str
  ├─ confidence: float (0.0-1.0)
  ├─ status: "supported" | "weakly_supported" | "inconclusive"
  ├─ supporting_evidence: [Evidence]
  ├─ contradicting_evidence: [Evidence]
  └─ confidence_breakdown:
       ├─ evidence_coverage: float
       ├─ source_reliability: float
       ├─ consistency: float
       └─ lineage_proximity: float

Evidence
  ├─ id: str
  ├─ type: "log" | "metric" | "schema" | "lineage" | "ownership"
  ├─ statement: str (what it shows)
  ├─ source: str (where it came from, e.g., "DataHub.asset.freshness")
  ├─ confidence: float
  └─ link: str (URL to DataHub or external trace)

Conclusion
  ├─ status: "supported" | "weakly_supported" | "inconclusive"
  ├─ root_cause_hypothesis: str | null
  ├─ impacted_assets: [Asset]
  ├─ overall_confidence: float
  ├─ reasoning: str
  └─ recommended_action: str
```

**Scoring Formula (Weighted Average):**
```
confidence = (
    0.35 × evidence_coverage
    + 0.25 × source_reliability
    + 0.25 × consistency
    + 0.15 × lineage_proximity
)

final_confidence = confidence × (1 - contradiction_ratio)

Status mapping:
- final_confidence >= 0.7 → "supported"
- 0.4 <= final_confidence < 0.7 → "weakly_supported"
- final_confidence < 0.4 → "inconclusive"
```

**Critical Rule:** Sherlock does NOT invent certainty. If evidence is insufficient, conclude "inconclusive".

### Integration Points with DataHub

| Layer | DataHub Component | Sherlock Use |
|-------|-------------------|--------------|
| Metadata | MCP Server | Read asset, schema, ownership, tags |
| Lineage | MCP Server | Trace upstream/downstream dependencies |
| Freshness | MCP Server / Skills | Detect staleness signals |
| Quality | Skills | Identify data contract violations |
| Evidence | REST API | Link back to asset detail pages |

---

## 3. FOLDER STRUCTURE

### Workspace: `DATAHUB` (existing)
```
DATAHUB/
├── sherlock-datahub-backend/     # Backend repository (Python) — NEW
│   ├── .git/
│   ├── README.md
│   ├── pyproject.toml        # Single source of truth for dependencies
│   ├── uv.lock              # Lock file for reproducible builds
│   ├── .gitignore
│   ├── .env.example
│   │
│   ├── src/
│   │   └── sherlock/
│   │       ├── __init__.py
│   │       ├── main.py                    # FastAPI entry point
│   │       │
│   │       ├── models/
│   │       │   ├── __init__.py
│   │       │   ├── evidence.py            # Evidence Graph data classes
│   │       │   ├── incident.py            # Incident model
│   │       │   ├── hypothesis.py          # Hypothesis model
│   │       │   └── conclusion.py          # Conclusion model
│   │       │
│   │       ├── engine/
│   │       │   ├── __init__.py
│   │       │   ├── investigator.py        # Main investigation orchestrator
│   │       │   ├── lineage_tracer.py      # Upstream/downstream tracing
│   │       │   ├── hypothesis_generator.py # Generate hypotheses
│   │       │   ├── evidence_collector.py  # Collect & score evidence
│   │       │   └── confidence_scorer.py   # Compute confidence score
│   │       │
│   │       ├── datahub/
│   │       │   ├── __init__.py
│   │       │   ├── mcp_client.py          # MCP Server connector
│   │       │   ├── asset_reader.py        # Read asset metadata
│   │       │   ├── lineage_reader.py      # Read lineage graphs
│   │       │   └── freshness_reader.py    # Read freshness signals
│   │       │
│   │       ├── api/
│   │       │   ├── __init__.py
│   │       │   ├── routes.py              # FastAPI endpoints
│   │       │   ├── schemas.py             # Request/response DTOs
│   │       │   └── middleware.py          # CORS, logging, etc.
│   │       │
│   │       └── config/
│   │           ├── __init__.py
│   │           ├── settings.py            # Environment config
│   │           └── constants.py           # Hardcoded defaults
│   │
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_investigator.py
│   │   ├── test_evidence_collector.py
│   │   └── test_datahub_integration.py
│   │
│   ├── datasets/
│   │   └── nyc-taxi-seed.json            # Preloaded sample incident
│   │
│   └── docs/
│       ├── ARCHITECTURE.md
│       ├── DATAHUB_INTEGRATION.md
│       ├── SETUP.md
│       ├── API_ENDPOINTS.md
│       └── SCORING.md
│
│
├── sherlock-datahub-web/           # Frontend repository (Next.js) — EXISTING
│   ├── .git/
│   ├── README.md
│   ├── package.json
│   ├── next.config.js
│   ├── tsconfig.json
│   ├── .gitignore
│   │
│   ├── public/
│   │   └── favicon.ico
│   │
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx                   # Home / investigation input
│   │   │   ├── investigations/
│   │   │   │   └── [id]/
│   │   │   │       └── page.tsx           # Investigation detail view
│   │   │   ├── api/
│   │   │   │   └── proxy/
│   │   │   │       └── route.ts           # Optional: proxy to backend
│   │   │   ├── layout.tsx                 # Root layout
│   │   │   └── globals.css
│   │   │
│   │   ├── components/
│   │   │   ├── DashboardLayout.tsx
│   │   │   ├── InvestigationForm.tsx      # Input: select asset
│   │   │   ├── EvidenceTimeline.tsx       # Timeline of evidence
│   │   │   ├── HypothesisCard.tsx         # Single hypothesis display
│   │   │   ├── HypothesisScorer.tsx       # Score visualizer
│   │   │   ├── ConclusionPanel.tsx        # Final recommendation
│   │   │   ├── DataHubLink.tsx            # Deep link to asset
│   │   │   └── ExportButton.tsx           # JSON/Markdown export
│   │   │
│   │   ├── hooks/
│   │   │   ├── useInvestigation.ts        # Fetch & poll investigation
│   │   │   ├── useDataHub.ts              # Asset search (optional)
│   │   │   └── useLocalStorage.ts         # Persist form state
│   │   │
│   │   ├── types/
│   │   │   ├── incident.ts
│   │   │   ├── evidence.ts
│   │   │   ├── hypothesis.ts
│   │   │   └── api.ts
│   │   │
│   │   ├── lib/
│   │   │   ├── api-client.ts              # Backend API wrapper
│   │   │   ├── formatters.ts              # Display helpers
│   │   │   └── constants.ts
│   │   │
│   │   ├── styles/
│   │   │   ├── globals.css
│   │   │   └── Investigation.module.css
│   │   │
│   │   └── context/
│   │       └── InvestigationContext.tsx   # Global state (optional)
│   │
│   ├── docs/
│   │   ├── UI_ARCHITECTURE.md
│   │   ├── SETUP.md
│   │   └── DEPLOYMENT.md
│   │
│   ├── public/snapshots/
│   │   └── demo-incident.json             # Snapshot demo data
│   │
│   ├── .env.example
│   └── vercel.json                        # Vercel config
│
│
└── DATAHUB_WORKSPACE.code-workspace      # Workspace file


**Key Principles:**
- Each repo is independent: separate git, dependencies, deployments
- Backend is purely API (no frontend assets)
- Frontend consumes backend via REST only
- No shared monorepo dependencies
- Clear separation of concerns
```

---

## 4. TIMELINE & PHASES

### PHASE 1: Technical Spike & Setup (July 23-26 | 4 days)

**Goal:** Validate that DataHub local works, dataset loads, and Sherlock can query it.

**Daily Breakdown:**

**Day 1 (July 23) — Infrastructure Setup**
- [ ] Clone existing `sherlock-datahub-web` repo and install dependencies
- [ ] Create `sherlock-datahub-backend` repo locally (Python project skeleton)
- [ ] Spin up DataHub locally using [official Quickstart Guide](https://docs.datahub.com/docs/quickstart)
- [ ] Load `nyc-taxi` dataset into DataHub: `datahub datapack load nyc-taxi`
- [ ] Verify DataHub UI is accessible at **http://localhost:9002**
- [ ] Verify frontend runs: `npm run dev` should work on http://localhost:3000
- [ ] Document all connection strings in `.env.example` files

**Deliverable:** Both repos ready + DataHub running locally
**Validation:** `datahub cli` commands work; UI at 9002; Frontend runs at 3000; nyc-taxi tables visible

---

**Day 2 (July 24) — MCP Server Inspection & Asset Reading**
- [ ] Install `mcp-server-datahub` in `sherlock-datahub-backend` (Python >= 3.11 required)
- [ ] **GATE: Inspect MCP Server capabilities**
  - [ ] List available tools in MCP Server
  - [ ] Verify which freshness, assertions, incidents, and lineage signals are exposed
  - [ ] Document findings in `docs/DATAHUB_INTEGRATION.md`
  - [ ] If expected signals are missing, plan workarounds (computed signals, mock data)
- [ ] Write `src/sherlock/datahub/mcp_client.py` (basic MCP connector)
- [ ] Implement `src/sherlock/datahub/asset_reader.py` to fetch asset metadata
- [ ] Discover and fetch a **real NYC-taxi asset URN** from running DataHub instance
- [ ] Verify we can read: schema, ownership, tags, last_modified

**Deliverable:** Working MCP client that reads one asset
**Validation:** Print real asset metadata to console; confirm schema & ownership resolve. Document which MCP signals are actually available.

---

**Day 3 (July 25) — Lineage Tracing**
- [ ] Implement `src/sherlock/datahub/lineage_reader.py`
- [ ] Trace upstream dependencies (what feeds into the revenue metric)
- [ ] Trace downstream dependencies (what consumes the revenue metric)
- [ ] Store results in structured dict: `{upstream: [...], downstream: [...]}`
- [ ] Verify we get 3-level lineage from NYC-taxi (ingest → transform → metric)

**Deliverable:** Lineage graph for one asset
**Validation:** Console output shows full 3-level chain with asset names

---

**Day 4 (July 26) — Freshness & Evidence Signals**
- [ ] Implement `src/sherlock/datahub/freshness_reader.py`
- [ ] Query freshness metadata from DataHub (last run, last row, SLA)
- [ ] Build sample incident JSON with planted freshness issue (e.g., "no update for 6h")
- [ ] Write `src/sherlock/models/evidence.py` basic data classes
- [ ] **SPIKE VALIDATION TEST:** Run a Python script that:
  - Reads an asset
  - Gets lineage
  - Detects freshness issue
  - Outputs JSON structure

**Deliverable:** End-to-end spike working (no UI, no API yet)
**Validation:**
```bash
python -m sherlock.spike \
  --asset-urn "urn:li:dataset:..." \
  --output investigation.json
```
Produces valid JSON with asset, lineage, freshness signal, and empty hypotheses array.

**Phase 1 Success Criteria:**
- ✅ DataHub local + nyc-taxi dataset loaded
- ✅ Sherlock can read asset metadata via MCP
- ✅ Sherlock can trace 3-level lineage
- ✅ Sherlock detects freshness degradation
- ✅ Spike script produces structured JSON output
- ✅ Both repos have clean, documented structure
- ✅ All `.env.example` files are documented

---

### PHASE 2: Evidence Engine MVP (July 27 - Aug 2 | 7 days)

**Goal:** Build the core investigation engine that generates hypotheses, collects evidence, and scores confidence.

**Daily Breakdown:**

**Day 5 (July 27) — Hypothesis Generator**
- [ ] Implement `src/sherlock/engine/hypothesis_generator.py`
- [ ] For a freshness issue, generate 4 template hypotheses:
  1. "Upstream ingestion job failed"
  2. "Transformation pipeline crashed"
  3. "Data contract broken (schema mismatch)"
  4. "Dashboard is displaying stale cache"
- [ ] Link each hypothesis to lineage nodes (which assets support/contradict it)
- [ ] Store hypotheses in `Hypothesis` data model

**Deliverable:** Hypothesis generator module
**Validation:**
```python
hypotheses = generate_hypotheses(
  asset=asset_metadata,
  lineage=lineage_graph,
  symptom="freshness_lag"
)
assert len(hypotheses) >= 2
assert all(h.title for h in hypotheses)
```

---

**Day 6 (July 28) — Evidence Collector**
- [ ] Implement `src/sherlock/engine/evidence_collector.py`
- [ ] For each hypothesis, determine what evidence would support/contradict it
- [ ] Evidence types:
  - **Lineage:** upstream asset X was modified recently (supports "ingestion job ran")
  - **Freshness:** asset Y has no updates in 6h (supports "pipeline failed")
  - **Schema:** dataset Z's schema matches current contract (contradicts "schema mismatch")
  - **Ownership:** asset owner is on-call (metadata context)
- [ ] Collect evidence from DataHub for each hypothesis
- [ ] Compute per-evidence confidence (0.0-1.0 based on freshness proximity)

**Deliverable:** Evidence collector module
**Validation:**
```python
evidence_map = collect_evidence(
  hypotheses=hypotheses,
  asset=asset_metadata,
  lineage=lineage_graph
)
assert evidence_map["hypothesis_1"]["supporting"] > 0
assert evidence_map["hypothesis_1"]["contradicting"] >= 0
```

---

**Day 7 (July 29) — Confidence Scorer**
- [ ] Implement `src/sherlock/engine/confidence_scorer.py`
- [ ] Score formula:
  ```
  confidence = (
      evidence_coverage
      × source_reliability
      × consistency
      × lineage_proximity
  )
  ```
  - **evidence_coverage:** ratio of supporting vs total evidence
  - **source_reliability:** 0.9 for DataHub, 0.7 for inferred
  - **consistency:** do multiple evidence types agree?
  - **lineage_proximity:** how close is evidence to the failing asset?
- [ ] Rank hypotheses by confidence
- [ ] Mark top hypothesis as "root cause"

**Deliverable:** Confidence scorer module
**Validation:**
```python
hypotheses_scored = score_hypotheses(
  hypotheses=hypotheses,
  evidence_map=evidence_map
)
assert all(h.status in ["supported", "weakly_supported", "inconclusive"] for h in hypotheses_scored)
# Sherlock does NOT invent certainty: inconclusive is a valid conclusion
```

---

**Day 8 (July 30) — Investigation Orchestrator**
- [ ] Implement `src/sherlock/engine/investigator.py` (main class)
- [ ] Wire together: asset reader → lineage tracer → hypothesis generator → evidence collector → confidence scorer
- [ ] Accept input: `{asset_urn, symptom_type}`
- [ ] Output: full `Incident` object with conclusions
- [ ] Build recommendation logic: if top hypothesis is "pipeline failed", recommend "check logs" + link

**Deliverable:** End-to-end investigation engine
**Validation:**
```python
investigator = Investigator()
incident = investigator.investigate(
  asset_urn="...",
  symptom="freshness_lag"
)
assert incident.conclusion.status in ["supported", "weakly_supported", "inconclusive"]
# root_cause_hypothesis may be null if status is inconclusive (this is OK)
assert len(incident.hypotheses) >= 2
assert incident.conclusion.recommended_action is not None
```

---

**Day 9 (July 31) — FastAPI Skeleton & Endpoints**
- [ ] Initialize FastAPI in `src/sherlock/main.py`
- [ ] Add health check endpoint: `GET /health`
- [ ] Add investigation endpoint: `POST /investigations` (accepts asset_urn, symptom)
- [ ] Response: returns `Incident` JSON
- [ ] Add CORS middleware for frontend
- [ ] Document endpoints in `docs/API_ENDPOINTS.md`

**Deliverable:** Working FastAPI server
**Validation:**
```bash
uvicorn src.sherlock.main:app --reload
# Test: curl http://localhost:8000/health
# Test: curl -X POST http://localhost:8000/investigations \
#   -H "Content-Type: application/json" \
#   -d '{"asset_urn":"...", "symptom":"freshness_lag"}'
```

---

**Day 10 (Aug 1) — Integration Test & Snapshot Demo Setup**
- [ ] Create `datasets/nyc-taxi-seed.json` with precomputed investigation result (generated from live DataHub)
- [ ] Build controlled fallback: if DataHub connection fails, log error and serve snapshot
- [ ] Snapshot response includes `"is_snapshot": true, "snapshot_timestamp": "...", "note": "Using pre-recorded investigation"`
- [ ] Write integration test: `tests/test_investigator.py`
- [ ] **Decision point:** Does live DataHub connection work reliably?
  - YES: Keep live mode as default (attempt live, fallback to snapshot if error)
  - NO: Use snapshot mode as primary, document why
- [ ] Document decision in `docs/ARCHITECTURE.md` with reasoning

**Deliverable:** Tested, working backend (live or snapshot, both transparent)
**Validation:**
```bash
pytest tests/
# All tests pass
# Backend serves demo incident with valid JSON structure
# Snapshot fallback clearly labels itself (no silent deception)
```

---

**Day 11 (Aug 2) — FastAPI Polish & Error Handling**
- [ ] Add request validation (Pydantic schemas)
- [ ] Add error handling: invalid asset URN, DataHub timeout, etc.
- [ ] Return structured error responses
- [ ] Add logging (request ID, timestamps, debug output)
- [ ] Ensure `pyproject.toml` has all dependencies pinned with versions
- [ ] Write `SETUP.md` for backend (how to install, run locally, deploy)

**Deliverable:** Demo-ready, tested FastAPI service
**Validation:**
```bash
# Errors are handled gracefully
# Logs show request flow
# pyproject.toml dependencies are complete and pinned
```

**Phase 2 Success Criteria:**
- ✅ Investigation engine works end-to-end
- ✅ FastAPI server running locally on port 8000
- ✅ API endpoints return valid JSON
- ✅ Precomputed fallback works (for demo resilience)
- ✅ All core logic is tested
- ✅ Backend documentation is complete

---

### PHASE 3: Frontend UI & Full Integration (Aug 3-6 | 4 days)

**Goal:** Build React/Next.js frontend that consumes backend API and displays investigation results.

**Daily Breakdown:**

**Day 12 (Aug 3) — Next.js Setup & Layout**
- [ ] Initialize Next.js with TypeScript in `sherlock-web`
- [ ] Create base layout: `src/components/DashboardLayout.tsx`
- [ ] Set up global styles (CSS modules or Tailwind)
- [ ] Create home page: `src/pages/index.tsx` (investigation input form)
- [ ] Add environment config: `.env.local` pointing to backend (http://localhost:8000)

**Deliverable:** Functional Next.js app skeleton
**Validation:**
```bash
cd sherlock-web
npm run dev
# http://localhost:3000 loads without errors
```

---

**Day 13 (Aug 4) — Investigation Form & API Client**
- [ ] Build `src/components/InvestigationForm.tsx` (input asset URN or search)
- [ ] Implement `src/lib/api-client.ts` (REST wrapper for backend)
- [ ] Create `src/hooks/useInvestigation.ts` (fetch + polling logic)
- [ ] Add form submission: calls backend POST `/investigations`
- [ ] Display loading state while backend processes
- [ ] Route to detail page on success: `/investigation/[id]`

**Deliverable:** Form that calls backend and navigates to results
**Validation:**
```bash
# User enters asset URN
# Form submits to http://localhost:8000/investigations
# Backend returns incident JSON
# Page redirects to /investigation/123
```

---

**Day 14 (Aug 5) — Evidence Display & Hypothesis Scorer**
- [ ] Build `src/components/HypothesisCard.tsx` (single hypothesis card)
- [ ] Build `src/components/HypothesisScorer.tsx` (confidence bar + breakdown)
- [ ] Build `src/components/EvidenceTimeline.tsx` (list of supporting/contradicting evidence)
- [ ] Create detail page: `src/pages/investigation/[id].tsx`
- [ ] Display all hypotheses ranked by confidence
- [ ] Show evidence breakdown (which evidence supports which hypothesis)

**Deliverable:** Hypothesis visualization
**Validation:**
```bash
# Investigation page loads
# Shows 2-4 hypotheses
# Each hypothesis shows confidence score
# Evidence is linked and explained
```

---

**Day 15 (Aug 6) — Conclusion Panel & Export**
- [ ] Build `src/components/ConclusionPanel.tsx` (final recommendation)
- [ ] Build `src/components/DataHubLink.tsx` (deep link to asset in DataHub)
- [ ] Implement export: JSON button (`ExportButton.tsx`)
- [ ] Optional: Markdown export
- [ ] Style for presentation (colors, typography, spacing)
- [ ] Test responsive design (desktop primary, mobile secondary)

**Deliverable:** Complete investigation view
**Validation:**
```bash
# Investigation page is fully styled and readable
# Export buttons work
# Links to DataHub are clickable
# Page looks professional in 3-minute demo
```

**Phase 3 Success Criteria:**
- ✅ Next.js frontend running locally on port 3000
- ✅ Form accepts asset input
- ✅ Investigation detail page shows all components
- ✅ Evidence, hypotheses, and conclusion are clear
- ✅ Export functionality works
- ✅ Links to DataHub are functional
- ✅ Ready for demo video

---

### PHASE 4: Demo, Docs & Submission (Aug 7-10 | 4 days)

**Goal:** Record demo video, finalize documentation, and submit to Devpost.

**Daily Breakdown:**

**Day 16 (Aug 7) — Demo Script & Recording Setup**
- [ ] Write demo script (< 3 minutes):
  - Intro (15s): "The Case of the Stale Pipeline"
  - Problem (30s): Dashboard shows revenue anomaly, unknown cause
  - Investigation (90s): Input asset, show investigation flow, highlight evidence
  - Conclusion (30s): Root cause identified, recommended action, impact
  - Close (15s): Recap value + mention production extensibility
- [ ] Set up recording environment:
  - Zoom / OBS recording
  - Highlight important UI elements
  - Display backend logs/API calls if helpful
- [ ] Do dry runs (practice script, timing)

**Deliverable:** Demo script + recording setup
**Validation:** Script is < 3 min, covers all key points

---

**Day 17 (Aug 8) — Record, Edit & YouTube Upload**
- [ ] Record demo (2-3 takes until polished)
- [ ] Edit: trim, add captions if needed, ensure clarity
- [ ] Upload to YouTube (unlisted or public)
- [ ] Get video URL for Devpost submission

**Deliverable:** Polished demo video on YouTube
**Validation:** Video is < 3 min, shows functionality, uploaded & accessible

---

**Day 18 (Aug 9) — Final Documentation & Submission**
- [ ] Finalize `sherlock-datahub-backend/README.md` (setup, architecture, endpoints)
- [ ] Finalize `sherlock-datahub-web/README.md` (setup, components, deployment)
- [ ] Write `SUBMISSION_TEXT.md` for Devpost:
  - Project description (2-3 sentences)
  - Features & functionality (bullet points)
  - Technologies (stack recap)
  - How to run (step-by-step for judges)
  - Future extensibility (BYOC, multi-agent, etc.)
- [ ] Ensure repos are public with Apache 2.0 license files
- [ ] Create `examples/` folder with sample outputs (investigation JSON, screenshots)
- [ ] Double-check all submission requirements:
  - ✅ Public repos with Apache 2.0 license
  - ✅ YouTube video link
  - ✅ Working demo link (Vercel for frontend)
  - ✅ Clear setup instructions in README
  - ✅ Text description
  - ✅ Sample outputs (JSON examples)
- [ ] Fill Devpost submission form

**Deliverable:** Complete submission on Devpost
**Validation:** All fields filled, links work, video is accessible

---

**Day 19 (Aug 10) — Buffer & Final Corrections**
- [ ] Buffer day for:
  - Fixing last-minute bugs
  - Re-recording demo if needed
  - Polishing UI if time allows
  - Testing full workflow one more time
- [ ] **Backup plan:** If issues arise, switch to precomputed demo (JSON fallback)
- [ ] Final git push to both repos
- [ ] Confirm Devpost submission went through

**Deliverable:** Submitted & verified
**Validation:** Devpost shows submission as received before 5:00 PM ET Aug 10

---

## 5. SUCCESS CRITERIA BY PHASE

### Phase 1 (End of Day 26 July)
- [ ] DataHub local running with nyc-taxi dataset
- [ ] Sherlock can read an asset, lineage, and freshness signal via MCP
- [ ] Spike script produces valid JSON output
- [ ] Both repos have clean structure and `.env.example` files

### Phase 2 (End of Day 2 Aug)
- [ ] FastAPI server running on port 8000
- [ ] POST `/investigations` endpoint works
- [ ] Investigation engine generates 2-4 hypotheses with evidence
- [ ] Confidence scores are computed and ranked
- [ ] Backend is tested and documented
- [ ] Precomputed fallback mode works

### Phase 3 (End of Day 6 Aug)
- [ ] Next.js frontend running on port 3000
- [ ] Investigation form accepts input and calls backend
- [ ] Detail page displays all investigation components beautifully
- [ ] Export functionality works
- [ ] Links to DataHub are functional
- [ ] Page is ready for 3-minute demo video

### Phase 4 (End of Day 10 Aug)
- [ ] Demo video recorded and uploaded to YouTube (< 3 min)
- [ ] Devpost submission complete with all required fields
- [ ] Both repos are public with Apache 2.0 licenses
- [ ] Setup instructions are clear and tested
- [ ] Sample outputs are in `examples/` folder

---

## 6. FIRST STEPS (TODAY)

### Immediate Actions (Before Day 1):

**Prerequisites:**
- GitHub username: `aiwhisperer11`
- Backend repo (to create): `sherlock-datahub-backend`
- Frontend repo (exists): `sherlock-datahub-web`

---

1. **Clone existing `sherlock-datahub-web` frontend repo**
   ```bash
   cd /path/to/DATAHUB/
   git clone https://github.com/aiwhisperer11/sherlock-datahub-web.git
   cd sherlock-datahub-web
   npm install
   # Verify: npm run dev (should run on http://localhost:3000)
   ```

2. **Create new `sherlock-datahub-backend` repo locally**
   ```bash
   cd /path/to/DATAHUB/
   mkdir sherlock-datahub-backend
   cd sherlock-datahub-backend
   git init
   # Git config respects system/global identity — do NOT override here

   # Create initial structure
   mkdir -p src/sherlock/{models,engine,datahub,api,config} tests datasets docs
   touch README.md pyproject.toml uv.lock .gitignore .env.example

   # Create pyproject.toml with Python >= 3.11 requirement
   cat > pyproject.toml << 'EOF'
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "sherlock-datahub-backend"
version = "0.1.0"
description = "Sherlock: Evidence-based investigation engine for DataHub"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.104.0",
    "pydantic>=2.0.0",
    "uvicorn>=0.24.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
]
EOF

   echo "__pycache__/" >> .gitignore
   echo ".venv/" >> .gitignore
   echo ".env" >> .gitignore

   git add .
   git commit -m "chore: scaffold Sherlock DataHub backend project"
   git branch -M main
   git remote add origin https://github.com/aiwhisperer11/sherlock-datahub-backend.git
   # Do NOT push yet — verify locally first
   ```

3. **Open workspace in VS Code**
   - Open `/path/to/DATAHUB/` as folder in VS Code
   - Install extensions: Python, Pylance, ESLint, Prettier
   - Verify both repos are visible in Explorer panel

4. **Start DataHub locally using official Quickstart**
   ```bash
   # Follow official guide: https://docs.datahub.com/docs/quickstart
   # This will spin up DataHub with all required services

   # Verify DataHub is running at http://localhost:9002

   # Load NYC-taxi dataset
   datahub datapack load nyc-taxi

   # Verify in DataHub UI: http://localhost:9002
   # You should see Tables, Pipelines, and Dashboards from NYC-taxi
   ```

5. **Set up VS Code workspace**
   ```bash
   cd /path/to/DATAHUB/
   cat > DATAHUB_WORKSPACE.code-workspace << 'EOF'
{
  "folders": [
    {
      "path": "sherlock-datahub-backend",
      "name": "Backend"
    },
    {
      "path": "sherlock-datahub-web",
      "name": "Frontend"
    }
  ],
  "settings": {
    "python.linting.enabled": true,
    "python.linting.pylintEnabled": true,
    "[python]": {
      "editor.defaultFormatter": "ms-python.python",
      "editor.formatOnSave": true
    }
  }
}
EOF
   ```
   - Open workspace: `code DATAHUB_WORKSPACE.code-workspace`
   - Install extensions: Python, Pylance, ESLint, Prettier
   - Verify both repos visible in Explorer panel

### Commit Strategy
- **All commits during hackathon** use real timestamps (July 23 - Aug 10)
- **No [BASELINE] prefix** — everything is built during the hackathon
- Use conventional commit prefixes: `chore:`, `feat:`, `fix:`, `docs:`, `test:`
- Phase tags are for clarity in documentation, not commit prefixes

---

## 7. COMMIT & BRANCHING STRATEGY

### Branches (Simplified for 19-day sprint)
- **main:** Always stable. Receives PRs only when Phase gates pass.
- **feat/..., fix/..., docs/...:** Short-lived feature branches
- Each person/component pair works on one branch
- Code review: PR to main before merging
- **No permanent dev branch** — reduces administrative overhead

### Commit Messages
```
type(scope): brief description

Longer explanation if needed.

Relates to: Day-N or Phase-M
```

### Examples
```
feat(datahub): implement MCP client for asset reading
feat(engine): add hypothesis generator with 4 templates
feat(frontend): build investigation detail page with evidence timeline
docs: update README with setup instructions
test(investigator): add confidence scoring tests
```

---

## 8. DEPLOYMENT CHECKLIST

### Before Aug 10:

**Backend (sherlock-datahub-backend)**
- [ ] All tests pass: `pytest tests/`
- [ ] Linting clean (if configured): `pylint src/` or similar
- [ ] Dependencies locked: `uv.lock` is current
- [ ] `pyproject.toml` specifies Python >= 3.11 and all dependencies
- [ ] Deployment service configured (Railway / Render / precomputed mode)
- [ ] Environment variables documented in `.env.example`
- [ ] No `requirements.txt` (single source of truth: `pyproject.toml`)

**Frontend (sherlock-datahub-web)**
- [ ] All tests pass: `npm test`
- [ ] Build succeeds: `npm run build`
- [ ] No console errors in dev mode
- [ ] Vercel config set up: `vercel.json`
- [ ] Environment variables in `.env.local` + `.env.example`
- [ ] Deployed to Vercel (preview URL shared)

**Submission**
- [ ] Apache 2.0 LICENSE files in both repos
- [ ] README files complete and tested
- [ ] Video URL on YouTube
- [ ] Working Vercel URL
- [ ] Devpost form filled completely
- [ ] All links verified (work for judges)

---

## 9. RISK MITIGATION

| Risk | Probability | Mitigation |
|------|-------------|-----------|
| DataHub MCP connection unstable | Medium | Precomputed fallback mode (Day 10) |
| Next.js build issues with Vercel | Low | Test build locally before Day 15 |
| Hypothesis generator too simplistic | Medium | Expand templates on Day 5; test thoroughly |
| Demo video exceeds 3 minutes | Low | Time script strictly; do multiple takes |
| Judges can't run backend locally | Low | Precomputed mode is backup; Vercel frontend works without backend |
| Scope creep (P1 features added too early) | High | **Protect Phase 1-3 strictly; P1 features only if Phase 3 done by Aug 6** |

---

## 10. COMMUNICATION & STANDUPS

### Daily Standup (10 min, end of day)
- What was completed today?
- What's the blockers (if any)?
- What's tomorrow's priority?
- Any help needed?

### Phase Gate Reviews
- End of each phase: 15 min review
- Validate success criteria
- Adjust timeline if needed
- Document decisions

---

## APPENDIX: Key Links

**Project Repositories:**
- **Backend (sherlock-datahub-backend):** https://github.com/aiwhisperer11/sherlock-datahub-backend
- **Frontend (sherlock-datahub-web):** https://github.com/aiwhisperer11/sherlock-datahub-web

**External Resources:**
- **DataHub Docs:** https://docs.datahub.com/
- **Hackathon Rules:** (See HACKATHON_RULES.md)
- **MCP Server:** https://github.com/acryldata/mcp-server-datahub
- **NYC-Taxi Dataset:** https://github.com/datahub-project/static-assets/tree/main/datasets/nyc-taxi
- **Devpost:** https://datahub.devpost.com/
- **DataHub Slack:** https://join.slack.com/t/datahubspace/shared_invite/zt-3rxzw3uww-7F2k5mDpjKXIGLskiQPwLQ

---

**Document Version:** 1.2
**Last Updated:** July 23, 2026
**Status:** Ready for Execution ✅
**Next Review:** End of Phase 1 (July 26)

---

**Changes Applied (v1.0 → v1.1 → v1.2):**
- ✅ Python >= 3.11 (was 3.9)
- ✅ DataHub port 9002 (was 3000)
- ✅ Quickstart official (no docker-compose in backend)
- ✅ Next.js App Router (src/app/ instead of src/pages/)
- ✅ pyproject.toml + uv.lock (eliminated requirements.txt)
- ✅ No git config overrides (respect team identity)
- ✅ No hardcoded URNs (discover real ones from DataHub)
- ✅ MCP inspection gate (Day 2)
- ✅ Weighted average scoring (0.35/0.25/0.25/0.15) with contradiction penalty
- ✅ Three status options: supported / weakly_supported / inconclusive
- ✅ Transparent snapshot fallback (labeled, not silent)
- ✅ Simplified branching (main + feat/fix/docs, no dev)
- ✅ Conventional commits (chore:, feat:, fix:, docs:, test:)
- ✅ Demo-ready, tested (not "production-ready")
- ✅ Real GitHub URLs (aiwhisperer11/sherlock-datahub-backend, aiwhisperer11/sherlock-datahub-web)
- ✅ FIRST STEPS with real commands and repos

**Approval:** Developer Senior ✓ | Product Manager ✓