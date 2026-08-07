# MCP save_document Spike — GO

Date: 2026-08-07. Scope: verify `discover -> read governed context -> save_document -> retrieve`
against a real local DataHub instance, and determine how the Sherlock backend
should call it. No UI, hosting, video, or extra features were touched.

## Environment actually used

- DataHub GMS: `v1.5.0.6` (commit `d0fce948555c06b3083479d40e8fa270d156c71f`), from `GET /config`.
- DataHub frontend image: `acryldata/datahub-frontend-react:v1.5.0.6`.
- DataHub CLI (client): `1.6.0.15`.
- `mcp-server-datahub`: `0.6.0` (resolved by `uvx mcp-server-datahub@latest`).
- `mcp` Python client library: `1.28.1` (backend pins `mcp>=1.0,<2.0`; already satisfied).
- Catalog: local `showcase-ecommerce` datapack (same one referenced in the hackathon resources), already loaded from a prior session — this is why `ORDER_DETAILS` and 18 pre-existing `Document` entities were present before this spike touched anything.
- `METADATA_SERVICE_AUTH_ENABLED=false` on this local instance (matches what the top-level README already discloses about the earlier local setup) — not exposed to the internet, host-only.

## Commands executed

```bash
# Docker Desktop was not running at session start; started it, then:
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

# First quickstart attempt regressed the MySQL port (see Blockers below):
datahub docker quickstart --no-pull-images --dump-logs-on-failure

# Fix: restore the working port mapping, then bring the stack up directly
# (docker compose auto-loads /home/work/.datahub/quickstart/.env):
docker rm datahub-mysql-1 datahub-datahub-gms-quickstart-1 \
  datahub-frontend-quickstart-1 datahub-datahub-actions-quickstart-1 \
  datahub-system-update-quickstart-1
# edited docker-compose.yml: mysql published port 3306 -> 3307
cd /home/work/.datahub/quickstart
docker compose -f docker-compose.yml -p datahub --profile quickstart up -d

curl --fail http://localhost:8080/config
curl --fail -d '{"query":"{ __typename }"}' -H 'Content-Type: application/json' http://localhost:8080/api/graphql

# Version check
uv tool run --from mcp-server-datahub@latest python -c \
  "import importlib.metadata; print(importlib.metadata.version('mcp-server-datahub'))"

# Live MCP round trip (reproducible test)
cd sherlock-datahub-hkt/backend
DATAHUB_LIVE=1 DATAHUB_GMS_TOKEN=<non-empty local placeholder> \
  uv run --frozen pytest tests/test_mcp_save_document_live.py -v
```

## MCP tools actually discovered (live `list_tools()`, not documentation)

Without mutations (8 tools — this is the default; matches what
`McpMetadataProvider`/`McpSampleProvider` already assume in `provider.py`):

```
get_dataset_queries, get_entities, get_lineage, get_lineage_paths_between,
grep_documents, list_schema_fields, search, search_documents
```

With `TOOLS_IS_MUTATION_ENABLED=true` (20 tools):

```
add_owners, add_structured_properties, add_tags, add_terms,
get_dataset_queries, get_entities, get_lineage, get_lineage_paths_between,
grep_documents, list_schema_fields, remove_domains, remove_owners,
remove_structured_properties, remove_tags, remove_terms, save_document,
search, search_documents, set_domains, update_description
```

Two things worth flagging that were not obvious from documentation:

- `search_documents` and `grep_documents` are **read-only** tools, available
  even with mutations disabled. Retrieval does not require write access.
- There is **no delete/remove-document tool** in this tool set. Once
  `save_document` succeeds, nothing over MCP can remove it.

## Evidence: read

`get_entities(["urn:li:dataset:(...,order_details,PROD)"])`, mutations
disabled, returned the real entity: name `ORDER_DETAILS`, platform
`snowflake`, 3 owners (technical owner + 2 data stewards), a `PII` glossary
term, and governance tags. This is real governed context from DataHub, not a
fixture — same shape `McpMetadataProvider._normalise_mcp` already parses.

## Evidence: save

`save_document` input schema (required: `document_type`, `title`, `content`;
optional: `urn`, `topics`, `related_documents`, `related_assets`).
`document_type` is an enum: `Insight | Decision | FAQ | Analysis | Summary |
Recommendation | Note | Context`.

Call:
```json
{"document_type": "Note", "title": "Sherlock MCP spike (...)",
 "content": "...", "related_assets": ["urn:li:dataset:(...,order_details,PROD)"]}
```
Result:
```json
{"success": true, "urn": "urn:li:document:shared-e183c7a5-96f0-44e8-8055-f843f6362635",
 "message": "Successfully created document: ...", "author": "__datahub_system"}
```

## Evidence: retrieve

`get_entities([<document urn>])` only returns the bare `urn` for `Document`
entities — its generic entity expansion does not cover Document-specific
aspects. The tool that actually works for retrieval is `search_documents`:

```json
{"start": 0, "count": 10, "total": 1,
 "searchResults": [{"entity": {"urn": "urn:li:document:shared-e183c7a5-...",
   "subType": "Note",
   "info": {"title": "Sherlock MCP spike (sherlock-mcp-save-document-live-test-marker)",
     "created": {"actor": {"urn": "urn:li:corpuser:__ingestion"}}}}}]}
```
Title and urn match what was saved. This required waiting a few seconds for
Kafka-based search indexing to catch up — an immediate `search_documents`
call right after `save_document` returned `total=0` once.

This is a real save -> real retrieve round trip through official MCP tools,
not a single isolated call: it is captured as an idempotent, repeatable
automated test (see below), run twice with the second run correctly finding
the already-saved document instead of duplicating it.

## How the Sherlock backend should invoke this

Same pattern already used by `McpMetadataProvider` (read) and
`McpWritebackProvider` (write), in `backend/src/sherlock/connectors/datahub/`:
a dedicated `stdio_client` + `ClientSession` per phase, tool-name allowlisted
via `_call_mcp_tool`, read phases with `TOOLS_IS_MUTATION_ENABLED=false` and
the save phase with it `=true`, never mixed in one subprocess. Concretely,
this is a new capability parallel to writeback, not a change to the existing
`update_description`/`add_tags` writeback path.

## Files that would need to change to wire this in (not done — spike only)

- `backend/src/sherlock/connectors/datahub/provider.py`: add
  `_ALLOWED_DOCUMENT_MCP_TOOLS = {"search_documents", "save_document"}`; fix
  `_build_stdio_parameters`/`_build_writeback_stdio_parameters` to coerce a
  `None` token to `""` instead of raising a `pydantic` `ValidationError` (see
  Blockers) so the same code path works against an auth-disabled local
  instance without a placeholder env var.
- `backend/src/sherlock/connectors/datahub/writeback.py`: add a
  `DocumentWritebackProvider` alongside `McpWritebackProvider`, reusing
  `_fetch_entity_state`-style idempotency (search by a stable marker before
  saving — mirrors what `test_mcp_save_document_live.py` already does).
- `backend/src/sherlock/domain/models.py`: a `DocumentWritebackResult` model
  (urn, document_type, title, verified, already_published).
- `backend/src/sherlock/api/main.py`: a new endpoint, e.g.
  `POST /api/v1/investigations/{id}/publish-document`, gated on the human
  approval step called for in the target flow — it must not auto-publish.
- `backend/tests/test_mcp_save_document_live.py`: already added by this
  spike; extend once the provider/writeback code above exists so the live
  test also exercises the wired path, not just raw MCP calls.
- Out of scope per this spike's instructions, listed only for later: the
  `web/src/features/investigation/` approval UI, and hosting/deploy docs.

## Real blockers hit (and their resolutions)

1. **Docker Desktop was not running** at the start of this session (WSL
   `docker` command unavailable). Resolved by starting Docker Desktop from
   WSL (`powershell.exe -Command "Start-Process 'Docker Desktop.exe'"`) and
   polling until the daemon responded (~90s).
2. **MySQL port-publish regression**: a bare `datahub docker quickstart`
   regenerated `/home/work/.datahub/quickstart/docker-compose.yml` and reset
   the MySQL published port from `3307` back to the default `3306`, which
   Docker Desktop's WSL2 port-forwarding layer refuses with `ports are not
   available ... /forwards/expose returned unexpected status: 500` — the
   exact failure already documented in `docs/spike/DATAHUB_SPIKE.md` from
   the original spike. Root cause this time: the CLI does not preserve a
   previously-working manual edit to the generated compose file. Fixed by
   editing the port back to `3307` and bringing the stack up with
   `docker compose ... up -d` directly against that file (which auto-loads
   the project's `.env`), instead of relying on the CLI to regenerate it.
3. **`_build_stdio_parameters` rejects a `None` token**: `DataHubSettings.token`
   is `None` when `DATAHUB_GMS_TOKEN` is unset or empty, but
   `StdioServerParameters.env` requires `dict[str, str]`, so constructing it
   raises a `pydantic.ValidationError` before any MCP call happens. Against
   this auth-disabled local instance, a non-empty placeholder token had to
   be passed even though DataHub does not check it. Not a blocker for the
   deployed backend (which always has a real token), but a real rough edge
   for local reproduction — worth the one-line fix noted above.
4. **`grep_documents` is not full-catalog search** — it requires a list of
   document `urns` plus a `pattern`; it greps inside specific already-known
   documents, it does not discover them. `search_documents` is the tool for
   discovery/retrieval by keyword; this was not obvious from the tool name
   alone and cost one failed call to learn.
5. **No document delete/remove tool exists** in `mcp-server-datahub 0.6.0`.
   Every `save_document` call that actually executes is permanent from
   MCP's perspective. The reproducible test avoids pollution by checking
   `search_documents` for a fixed marker before saving, but any future
   wired feature needs the same idempotency discipline — there is no cleanup
   API to fall back on.

None of these blocked the flow; all were resolved within this spike.

## Reproducible test

`backend/tests/test_mcp_save_document_live.py`, gated by `DATAHUB_LIVE=1`
(same convention as `test_graphql_value_entities_live.py`), 4 tests:

1. `list_tools()` without mutations equals the exact 8-tool set above.
2. `list_tools()` with mutations equals the exact 20-tool set above,
   including `save_document`.
3. `get_entities` reads real `ORDER_DETAILS` data.
4. `save_document` then `search_documents` round-trips a marker document,
   idempotently (a second run finds the existing document instead of
   creating a duplicate — verified by running it twice: 41s first run
   including the save, 12.68s second run finding the existing document).

```bash
DATAHUB_LIVE=1 DATAHUB_GMS_TOKEN=<local placeholder, no real auth needed> \
  uv run --project backend --frozen pytest backend/tests/test_mcp_save_document_live.py -v
```

Full suite after adding this file: `85 passed, 5 skipped` (5 skipped =
the two `DATAHUB_LIVE` live-test files, unless `DATAHUB_LIVE=1` is set).

No secrets were committed: `DATAHUB_GMS_TOKEN` is read from the environment
at test time only; this local instance has auth disabled, so the value used
was a placeholder string, never a real credential.

## Verdict: GO

`discover -> read governed context -> save_document -> retrieve` was
verified end-to-end against a real local DataHub `v1.5.0.6` instance through
`mcp-server-datahub 0.6.0`, using the exact `mcp` client call pattern
(`stdio_client` + `ClientSession` + tool allowlisting) already live in
`sherlock/connectors/datahub/provider.py` and `writeback.py` — not a
one-off manual call. It is captured as an idempotent, automated pytest suite
that a CI job or operator can rerun on demand, the same way the existing
live GraphQL check already works. What remains is integration wiring
(provider/writeback/endpoint code listed above) plus the human-approval step
the target flow requires — not technical feasibility of MCP
read/save/retrieve itself, which this spike closes out.
