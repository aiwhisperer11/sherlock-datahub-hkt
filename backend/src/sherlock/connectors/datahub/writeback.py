from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sherlock.connectors.datahub.provider import (
    ORDER_DETAILS_URN,
    DataHubMetadataProvider,
    DataHubProviderError,
    DataHubSettings,
    _ALLOWED_DOCUMENT_MCP_TOOLS,
    _ALLOWED_MCP_TOOLS,
    _build_stdio_parameters,
    _call_mcp_tool,
    _require_token,
    _run_mcp_fetch,
)
from sherlock.domain.models import (
    DocumentPreview,
    DocumentRetrievalResult,
    DocumentWritebackResult,
    FrozenDashboardResult,
    WritebackResult,
)
from sherlock.integrations.sherlock_core.boundary import CanonicalInvestigationError, validate_unchanged
from sherlock.integrations.sherlock_core.client import SherlockCoreClient, SherlockCoreUnavailableError
from sherlock.investigations.datahub_document_flow import (
    build_baseline_request,
    build_document_preview,
    build_document_preview_from_engine_snapshot,
    derive_reasoning_consequence,
    deterministic_idempotency_key,
    evidence_from_entity,
    evidence_from_lineage,
    to_canonical_evidence,
)

_ALLOWED_WRITEBACK_MCP_TOOLS = {"update_description", "add_tags"}
_WRITEBACK_TAG_URN = "urn:li:tag:sherlock-investigated"


def _investigation_marker(investigation_id: str) -> str:
    """A plain-text, visible marker — DataHub strips HTML comments from descriptions on write,
    so a `<!-- ... -->` marker never survives a round trip and idempotency checks against it
    would always miss, causing duplicate appends on every call. Confirmed empirically."""
    return f"Sherlock investigation `{investigation_id}`"


def _render_summary_markdown(investigation: FrozenDashboardResult) -> str:
    timestamp = datetime.now(UTC).isoformat()
    prime_suspect = investigation.prime_suspect
    return (
        f"**{_investigation_marker(investigation.id)}** — {timestamp}\n"
        f"- Prime suspect: {prime_suspect.label} (`{prime_suspect.hypothesis_id}`)\n"
        f"- Confidence: {prime_suspect.confidence} (provisional)\n"
        f"- Next test: {investigation.final_result.immediate_action}\n"
    )


@dataclass(frozen=True)
class _EntityWritebackState:
    description: str | None
    tag_urns: frozenset[str]


@dataclass(frozen=True)
class _MutationOutcome:
    description_written: bool
    tag_added: bool
    degraded: bool
    detail: str


def _fetch_entity_state(settings: DataHubSettings, urn: str) -> _EntityWritebackState:
    """Read-only lookup of the current description and tags for `urn`. Mutations disabled."""
    return _run_mcp_fetch(_fetch_entity_state_async(settings, urn), settings.timeout_seconds, settings.mcp_command)


async def _fetch_entity_state_async(settings: DataHubSettings, urn: str) -> _EntityWritebackState:
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    parameters = _build_stdio_parameters(settings)
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await _call_mcp_tool(session, "get_entities", {"urns": [urn]}, _ALLOWED_MCP_TOOLS)

    entity_list = result.get("entities", result.get("results", result.get("result", [])))
    if not isinstance(entity_list, list) or not entity_list:
        raise DataHubProviderError("Writeback target entity was not found")
    entity = entity_list[0]
    description = entity.get("editableProperties", {}).get("description")
    tag_entries = entity.get("tags", {}).get("tags", [])
    tag_urns = frozenset(
        item["tag"]["urn"]
        for item in tag_entries
        if isinstance(item, dict) and isinstance(item.get("tag"), dict) and item["tag"].get("urn")
    )
    return _EntityWritebackState(description=description, tag_urns=tag_urns)


def _build_writeback_stdio_parameters(settings: DataHubSettings) -> Any:
    from mcp import StdioServerParameters

    return StdioServerParameters(
        command=settings.mcp_command,
        args=[settings.mcp_package],
        env={
            "DATAHUB_GMS_URL": settings.gms_url,
            # settings.token is None when DATAHUB_GMS_TOKEN is unset — a real,
            # supported configuration against an instance with
            # METADATA_SERVICE_AUTH_ENABLED=false, not an error. No placeholder
            # token is substituted; DataHub itself enforces auth if required.
            "DATAHUB_GMS_TOKEN": settings.token or "",
            "TOOLS_IS_MUTATION_ENABLED": "true",
        },
    )


class McpWritebackProvider:
    """Publishes a live-MCP-sourced Frozen Dashboard investigation back to DataHub.

    Three separate MCP subprocesses, never mixed:
      1. read-only (mutations disabled) — sources the investigation via a real MCP read,
         and checks whether it was already published (idempotency).
      2. write (mutations enabled, allowlist limited to update_description/add_tags) —
         only opened when something is actually missing.
      3. read-only (mutations disabled) — verifies the write by reading the entity back.

    The target URN is always ORDER_DETAILS_URN; callers cannot supply a URN.
    """

    def __init__(self, settings: DataHubSettings | None = None) -> None:
        self.settings = settings or DataHubSettings.from_environment()
        self.target_urn = ORDER_DETAILS_URN

    def write(self, add_tag: bool) -> WritebackResult:
        _require_token(self.settings)

        investigation = DataHubMetadataProvider(DataHubSettings.from_environment_forced_to_mode("mcp")).load_frozen_dashboard()
        marker = _investigation_marker(investigation.id)

        before = _fetch_entity_state(self.settings, self.target_urn)
        description_already_present = marker in (before.description or "")
        tag_already_present = _WRITEBACK_TAG_URN in before.tag_urns

        if description_already_present and (not add_tag or tag_already_present):
            return WritebackResult(
                urn=self.target_urn,
                investigation_id=investigation.id,
                description_written=False,
                tag_added=False,
                verified=True,
                already_published=True,
                degraded=False,
                detail="Investigation already published to this entity; no mutation performed.",
            )

        summary = _render_summary_markdown(investigation)
        outcome = _run_mcp_fetch(
            self._mutate(summary, add_tag, description_already_present, tag_already_present),
            self.settings.timeout_seconds,
            self.settings.mcp_command,
        )

        after = _fetch_entity_state(self.settings, self.target_urn)
        verified = marker in (after.description or "") and (not add_tag or _WRITEBACK_TAG_URN in after.tag_urns)

        return WritebackResult(
            urn=self.target_urn,
            investigation_id=investigation.id,
            description_written=outcome.description_written,
            tag_added=outcome.tag_added,
            verified=verified,
            already_published=False,
            degraded=outcome.degraded,
            detail=outcome.detail,
        )

    async def _mutate(
        self,
        summary: str,
        add_tag: bool,
        description_already_present: bool,
        tag_already_present: bool,
    ) -> _MutationOutcome:
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        parameters = _build_writeback_stdio_parameters(self.settings)
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                listed_names = {tool.name for tool in listed.tools}

                has_update_description = "update_description" in listed_names
                has_add_tags = "add_tags" in listed_names

                description_written = False
                tag_added = False
                degraded = False
                description_failed = False
                tag_failed = False

                # Each mutation is isolated: a failure in one must not discard a success already
                # committed to DataHub by the other, and must not raise past a partial result.
                if not description_already_present:
                    if has_update_description:
                        try:
                            await self._call(session, "update_description", {"entity_urn": self.target_urn, "operation": "append", "description": summary})
                            description_written = True
                        except Exception:
                            degraded = True
                            description_failed = True
                    else:
                        degraded = True

                if add_tag and not tag_already_present:
                    if has_add_tags:
                        try:
                            await self._call(session, "add_tags", {"tag_urns": [_WRITEBACK_TAG_URN], "entity_urns": [self.target_urn]})
                            tag_added = True
                        except Exception:
                            degraded = True
                            tag_failed = True
                    else:
                        degraded = True

        nothing_accomplished = (
            not description_written
            and not tag_added
            and not description_already_present
            and not (tag_already_present and add_tag)
        )
        if nothing_accomplished:
            if description_failed:
                raise DataHubProviderError("update_description failed and no other content could be published")
            if tag_failed:
                raise DataHubProviderError("add_tags failed (the tag URN may not exist yet in DataHub) and no other content could be published")
            raise DataHubProviderError("Writeback could not publish any content: no compatible mutation tool is available")

        detail_parts: list[str] = []
        if description_written:
            detail_parts.append("Published update_description.")
        elif description_already_present:
            detail_parts.append("Description already published.")
        elif description_failed:
            detail_parts.append("update_description failed; summary was not published.")
        elif not has_update_description:
            detail_parts.append("update_description unavailable (degraded).")

        if add_tag:
            if tag_added:
                detail_parts.append("Published add_tags.")
            elif tag_already_present:
                detail_parts.append("Tag already present.")
            elif tag_failed:
                detail_parts.append("add_tags failed — the tag URN may not exist yet in DataHub; create it once, then retry.")
            elif not has_add_tags:
                detail_parts.append("add_tags unavailable (degraded).")

        return _MutationOutcome(description_written=description_written, tag_added=tag_added, degraded=degraded, detail=" ".join(detail_parts))

    async def _call(self, session: Any, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return await _call_mcp_tool(session, tool_name, arguments, _ALLOWED_WRITEBACK_MCP_TOOLS)


class DocumentWritebackProvider:
    """discover -> evidence -> reasoning -> preview -> (human approval) -> save_document -> retrieve.

    Three separate concerns, never mixed in one method:
      - preview() only reads (get_entities, general read allowlist) and derives
        evidence/reasoning/content through pure functions. It never calls
        save_document and therefore never mutates DataHub.
      - publish() is the only method that can call save_document, restricted to
        `_ALLOWED_DOCUMENT_MCP_TOOLS`, and only runs the mutation when the
        caller passes `approved=True` explicitly — there is no default that
        publishes an investigation automatically. It first checks
        `preview.idempotency_key` via the read-only `search_documents`, so a
        retried call finds the existing document instead of creating a
        duplicate (mcp-server-datahub has no document-delete tool: duplicates
        would be permanent).
      - retrieve() independently re-reads by idempotency key and confirms the
        URN, title, and idempotency marker actually match.
    """

    def __init__(self, settings: DataHubSettings | None = None, engine_client: SherlockCoreClient | None = None) -> None:
        self.settings = settings or DataHubSettings.from_environment()
        self.engine_client = engine_client or SherlockCoreClient.from_environment()

    def preview(self, urn: str) -> DocumentPreview:
        """discover -> evidence -> [canonical Sherlock-Core engine] -> preview.

        The canonical engine is the primary path: DataHub evidence is
        converted to canonical SherlockEvidence (with `source` provenance)
        and submitted to Sherlock-Core's real investigation engine. Only when
        the engine is not configured (`SHERLOCK_CORE_URL` unset), unreachable,
        or its snapshot does not actually cite any DataHub evidence, this
        falls back to derive_reasoning_consequence() — always disclosed via
        `DocumentPreview.engine_source`, never presented as the canonical
        engine's conclusion.
        """
        entity, upstream = _run_mcp_fetch(self._fetch_context(urn), self.settings.timeout_seconds, self.settings.mcp_command)
        observed_at = datetime.now(UTC)
        evidence = evidence_from_entity("get_entities", urn, entity, observed_at) + evidence_from_lineage("get_lineage", urn, upstream, observed_at)

        canonical_evidence = to_canonical_evidence(evidence)
        engine_preview = self._try_canonical_engine(urn, evidence, canonical_evidence)
        if engine_preview is not None:
            return engine_preview

        consequence = derive_reasoning_consequence(urn, evidence)
        idempotency_key = deterministic_idempotency_key(urn, consequence.id)
        fallback = build_document_preview(urn, evidence, consequence, idempotency_key)
        disclosure = (
            "[Sherlock-Core canonical engine unavailable for this preview; the "
            "reasoning below is a local fallback, not the canonical engine's "
            "conclusion.]\n\n"
        )
        return fallback.model_copy(update={"content": disclosure + fallback.content, "engine_source": "local_fallback"})

    def _try_canonical_engine(
        self, urn: str, evidence: list[Any], canonical_evidence: list[Any]
    ) -> DocumentPreview | None:
        if not self.engine_client.configured:
            return None
        baseline = build_baseline_request(urn, canonical_evidence)
        try:
            raw_snapshot = self.engine_client.run_baseline_investigation(baseline)
            snapshot = validate_unchanged(raw_snapshot)
        except (SherlockCoreUnavailableError, CanonicalInvestigationError):
            return None
        idempotency_key = deterministic_idempotency_key(urn, str(snapshot.get("meta", {}).get("case_id", urn)))
        return build_document_preview_from_engine_snapshot(urn, evidence, canonical_evidence, snapshot, idempotency_key)

    async def _fetch_context(self, urn: str) -> tuple[dict[str, Any], dict[str, Any]]:
        """One read-only session, two calls: get_entities (name/owners/glossary) and
        get_lineage upstream (incident-relevant dependency signal). Kept in one
        session so preview() opens exactly one MCP subprocess, not two."""
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        parameters = _build_stdio_parameters(self.settings, mutation_enabled=False)
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                entity_result = await _call_mcp_tool(session, "get_entities", {"urns": [urn]}, _ALLOWED_MCP_TOOLS)
                upstream_result = await _call_mcp_tool(
                    session,
                    "get_lineage",
                    {"urn": urn, "column": None, "query": "*", "upstream": True, "max_hops": 1, "max_results": 20, "offset": 0},
                    _ALLOWED_MCP_TOOLS,
                )
        entity_list = entity_result.get("result", entity_result.get("entities", entity_result.get("results", [])))
        if not isinstance(entity_list, list) or not entity_list or not isinstance(entity_list[0], dict):
            raise DataHubProviderError("Preview target entity was not found")
        return entity_list[0], upstream_result

    def publish(self, preview: DocumentPreview, approved: bool) -> DocumentWritebackResult:
        if not approved:
            raise DataHubProviderError("Publishing a Sherlock investigation document requires explicit human approval")

        existing = _run_mcp_fetch(self._find_by_key(preview.idempotency_key), self.settings.timeout_seconds, self.settings.mcp_command)
        if existing is not None:
            return DocumentWritebackResult(
                status="already_exists",
                urn=str(existing.get("urn")),
                idempotency_key=preview.idempotency_key,
                document_type=preview.document_type,
                title=preview.title,
                detail="A document with this idempotency key is already published; no mutation performed.",
            )

        saved = _run_mcp_fetch(self._save(preview), self.settings.timeout_seconds, self.settings.mcp_command)
        urn = saved.get("urn")
        if not saved.get("success") or not urn:
            raise DataHubProviderError("save_document did not report success")
        return DocumentWritebackResult(
            status="created",
            urn=str(urn),
            idempotency_key=preview.idempotency_key,
            document_type=preview.document_type,
            title=preview.title,
            detail=str(saved.get("message") or "Document created."),
        )

    async def _save(self, preview: DocumentPreview) -> dict[str, Any]:
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        parameters = _build_stdio_parameters(self.settings, mutation_enabled=True)
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await _call_mcp_tool(
                    session,
                    "save_document",
                    {
                        "document_type": preview.document_type,
                        "title": preview.title,
                        "content": preview.content,
                        "related_assets": preview.related_assets,
                    },
                    _ALLOWED_DOCUMENT_MCP_TOOLS,
                )

    async def _find_by_key(self, idempotency_key: str) -> dict[str, Any] | None:
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        parameters = _build_stdio_parameters(self.settings, mutation_enabled=False)
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await _call_mcp_tool(session, "search_documents", {"query": idempotency_key}, _ALLOWED_DOCUMENT_MCP_TOOLS)
        for hit in result.get("searchResults", []):
            entity = hit.get("entity") if isinstance(hit, dict) else None
            if not isinstance(entity, dict):
                continue
            title = entity.get("info", {}).get("title", "")
            if idempotency_key in title:
                return entity
        return None

    def retrieve(self, idempotency_key: str, expected_urn: str | None = None) -> DocumentRetrievalResult:
        """Independently re-read by idempotency key and confirm URN/title/marker."""
        entity = _run_mcp_fetch(self._find_by_key(idempotency_key), self.settings.timeout_seconds, self.settings.mcp_command)
        if entity is None:
            return DocumentRetrievalResult(
                status="not_found", urn=None, title=None, idempotency_key=idempotency_key, detail="search_documents found no document with this idempotency key."
            )
        urn = entity.get("urn")
        title = entity.get("info", {}).get("title")
        marker_present = isinstance(title, str) and idempotency_key in title
        urn_matches = expected_urn is None or urn == expected_urn
        if marker_present and urn_matches and urn:
            return DocumentRetrievalResult(
                status="verified", urn=str(urn), title=title, idempotency_key=idempotency_key, detail="URN, title, and idempotency marker all matched."
            )
        return DocumentRetrievalResult(
            status="mismatch",
            urn=str(urn) if urn else None,
            title=title,
            idempotency_key=idempotency_key,
            detail="Document found but URN or title did not match what was expected.",
        )
