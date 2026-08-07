# Document publish flow — real, reproducible outputs

These three files are real API responses from this project, captured in one
run against a local DataHub OSS instance (`showcase-ecommerce` datapack) and
the real deployed Sherlock-Core canonical engine
(`https://sherlock-engine.vercel.app`). No secrets, tokens, or credentials
are present in any of them — DataHub's `METADATA_SERVICE_AUTH_ENABLED` was
`false` for this local instance, and no `Authorization` header is ever
included in these response bodies.

Sequence:

1. **`preview.json`** — response of `GET /api/v1/documents/preview`.
   `engine_source` is `"sherlock_core_canonical"`: the real LLM-backed engine
   ran, not the local fallback. `reasoning_consequence.evidence_ids` is
   `["E1","E2","E3","E4"]` — every DataHub-sourced evidence item, including
   `E4` (the `get_lineage` evidence: 12 real upstream dependencies of
   ORDER_DETAILS), was actually cited by the investigation's hypothesis. Note
   what the engine explicitly does *not* say: even with a `PII` glossary term
   in evidence, the statement declines to treat it as a cause — "insufficient
   ... to prioritize a specific operational or governance concern" — per the
   prompt rule that DataHub metadata is governed context, not a demonstrated
   cause, by default.
2. **`publish.json`** — response of `POST /api/v1/documents/publish` with
   `{"preview_hash": "<preview.json's preview_hash>", "approved": true}`.
   `status: "created"` — a real `Document` entity was written to DataHub via
   the `save_document` MCP tool. Took ~12.6s (only the publish-side MCP
   calls: an idempotency check via `search_documents`, then `save_document`
   — it does not re-run MCP context acquisition or the engine call that
   `preview.json` took ~49s for).
3. **`retrieve.json`** — response of
   `GET /api/v1/documents/retrieve?idempotency_key=...&expected_urn=...`.
   `status: "verified"` — an independent read confirming the published
   document's URN, title, and idempotency marker all match what was
   approved.

A second `POST /publish` with the *same* `preview_hash` returns
`{"status": "already_exists"}` instead of creating a duplicate —
`mcp-server-datahub` has no document-delete tool, so this idempotency is
what keeps repeated approvals safe.

See `backend/docs/PUBLISH_APPROVAL_FLOW.md` for the full contract and
`README.md` ("Document Publish Flow") for how to reproduce this yourself.
