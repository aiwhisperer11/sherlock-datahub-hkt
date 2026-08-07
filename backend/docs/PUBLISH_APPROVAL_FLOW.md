# Publish/approval flow: DataHub context -> Sherlock evidence -> document

Minimal, wired implementation of:

```
discover -> read governed context -> Sherlock evidence -> observable reasoning
consequence -> preview -> explicit human approval -> save_document -> retrieve
```

No UI, deploy, new mutation types, or endpoint were added — this is the
provider-level flow the spike (`MCP_SAVE_DOCUMENT_SPIKE.md`) said would need
to exist before any of those.

## Flow

```
                    DocumentWritebackProvider.preview(urn)
                    ─────────────────────────────────────
urn ──▶ MCP get_entities (read-only, _ALLOWED_MCP_TOOLS)
             │
             ▼
     evidence_from_entity()          ── pure, no MCP call
     [DataHubEvidence: tool, urn, observed_fact, observed_at, provenance]
             │
             ▼
     derive_reasoning_consequence()  ── pure, cites evidence_ids, sets next_test
             │
             ▼
     deterministic_idempotency_key() ── pure, sha256(urn|consequence.id)[:16]
             │
             ▼
     build_document_preview()        ── pure, renders title/content, includes
                                          persistence_warning
             │
             ▼
        DocumentPreview  ◀── returned to caller. No MCP mutation has happened.


                    ── explicit human approval boundary ──
                    caller must pass approved=True itself


                    DocumentWritebackProvider.publish(preview, approved)
                    ─────────────────────────────────────────────────────
approved=False ──▶ raise DataHubProviderError (no MCP subprocess opened at all)

approved=True
   │
   ▼
MCP search_documents(idempotency_key)  ── read-only, _ALLOWED_DOCUMENT_MCP_TOOLS
   │
   ├─ found  ──▶ DocumentWritebackResult(status="already_exists") ── no write
   │
   └─ not found
        │
        ▼
      MCP save_document(...)  ── mutation, _ALLOWED_DOCUMENT_MCP_TOOLS
        │
        ▼
      DocumentWritebackResult(status="created", urn=...)


                    DocumentWritebackProvider.retrieve(idempotency_key, expected_urn)
                    ──────────────────────────────────────────────────────────────
MCP search_documents(idempotency_key)  ── read-only, independent of publish()
   │
   ├─ not found                        ──▶ DocumentRetrievalResult(status="not_found")
   ├─ found, urn/title/marker mismatch ──▶ DocumentRetrievalResult(status="mismatch")
   └─ found, urn/title/marker match    ──▶ DocumentRetrievalResult(status="verified")
```

Three separate MCP subprocesses across `preview` -> `publish` -> `retrieve`,
never mixed in one — same discipline as the existing `McpWritebackProvider`
(read-only mutations-disabled sessions for reads, one mutations-enabled
session only for the write, and an independent read-only session to verify).

## Evidence that DataHub actually affects reasoning

`derive_reasoning_consequence()` branches on the real evidence content, not
on the URN alone: if a `PII`-tagged glossary term is among the observed
facts, the statement, `next_test`, and cited `evidence_ids` are about PII
governance review; otherwise they are about ownership/escalation. Against
the real local ORDER_DETAILS entity (which does carry a `PII` glossary
term), the live test asserts the PII branch is taken and that the resulting
`next_test` and document content quote the real observed fact, not a
canned string.

`test_reasoning_consequence_cites_real_evidence_ids` (no Docker) is the test
that guarantees this structurally: it asserts `consequence.evidence_ids` is
non-empty and is a subset of the evidence ids actually produced by
`evidence_from_entity()` — a reasoning consequence can never cite evidence
that was not really observed.

## Preview / approval / publish contract

- `preview(urn) -> DocumentPreview`: read-only. Calls `get_entities` only.
  Never calls `save_document`. Returns the exact `title`/`content`/
  `document_type`/`related_assets` that would be published, plus a
  deterministic `idempotency_key` and a `persistence_warning` stating the
  document is permanent and cannot currently be deleted or edited by
  Sherlock (mcp-server-datahub 0.6.0 has no document-delete tool).
- `publish(preview, approved: bool) -> DocumentWritebackResult`: the only
  method that can call `save_document`. `approved` must be passed
  explicitly and be `True`; if not, it raises before opening any MCP
  subprocess — there is no default path that publishes an investigation
  automatically. Even when approved, it first checks the idempotency key via
  `search_documents`; if a document with that key already exists, it returns
  `status="already_exists"` and performs no mutation.
- `retrieve(idempotency_key, expected_urn=None) -> DocumentRetrievalResult`:
  independent read-only re-check after publishing, confirming the URN,
  title, and idempotency marker actually match what was supposed to be
  written — `status="verified"` only when all three agree.

## Test results

No-Docker unit tests (pure functions + mocked MCP), run with the normal
suite:

```
uv run --project backend --frozen pytest -q
106 passed, 7 skipped   # 7 skipped = the two DATAHUB_LIVE-gated files
```

New files: `test_mcp_stdio_parameters.py` (5), `test_datahub_document_flow.py`
(9), `test_document_writeback.py` (9, includes the approval-gate and
idempotency tests) — 21 new tests overall (some existing counts included
above), all passing without Docker.

Live-gated tests against the real local DataHub instance:

```
DATAHUB_LIVE=1 uv run --project backend --frozen pytest \
  backend/tests/test_mcp_save_document_live.py backend/tests/test_graphql_value_entities_live.py -v
7 passed in 92.52s
```

Including `test_missing_token_does_not_crash_against_this_auth_disabled_instance`,
which builds `DataHubSettings(token=None)` and runs a real `preview()` call
against this instance — no placeholder token, proving the `_build_stdio_parameters`
fix works for real, not only under a mock.

## Limitations still pending

- No HTTP endpoint or UI wires this to a human approver yet — `approved`
  is a Python boolean parameter today. Out of scope for this task by
  explicit instruction.
- Documents cannot be deleted or edited by Sherlock once published; this is
  disclosed in `DocumentPreview.persistence_warning`, not solved.
- `preview()` derives reasoning from a single `get_entities` read of one
  URN; it does not yet incorporate lineage, schema, or the elaborate
  Frozen Dashboard investigation machinery — deliberately minimal per this
  task's scope.
- `derive_reasoning_consequence()` currently has two branches (PII present /
  absent). It is a real, evidence-driven decision, but a narrow one; it is
  not a general-purpose reasoning engine.
