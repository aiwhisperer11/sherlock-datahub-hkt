from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sherlock.connectors.datahub.provider import (
    ORDER_DETAILS_URN,
    DataHubMetadataProvider,
    DataHubProviderError,
    DataHubSettings,
    _ALLOWED_MCP_TOOLS,
    _build_stdio_parameters,
    _call_mcp_tool,
    _require_token,
    _run_mcp_fetch,
)
from sherlock.domain.models import FrozenDashboardResult, WritebackResult

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
            "DATAHUB_GMS_TOKEN": settings.token,
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
