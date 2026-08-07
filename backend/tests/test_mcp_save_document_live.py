"""Live DataHub MCP round trip through the wired DocumentWritebackProvider:
discover -> read governed context -> evidence -> reasoning -> preview ->
(approval) -> save_document -> retrieve. This exercises the real integration
in sherlock.connectors.datahub.writeback, not raw MCP calls — the Docker-free
unit tests in test_document_writeback.py cover the same contract with MCP
mocked; this file proves it against a real local DataHub instance.

See backend/docs/MCP_SAVE_DOCUMENT_SPIKE.md for how this was first verified,
and PUBLISH_APPROVAL_FLOW.md for the preview/approval/publish contract.

Run on demand with:
DATAHUB_LIVE=1 uv run --project backend --frozen pytest \
  backend/tests/test_mcp_save_document_live.py -q
"""

from __future__ import annotations

import asyncio
import os

import pytest

from sherlock.connectors.datahub.provider import DataHubSettings, _build_stdio_parameters
from sherlock.connectors.datahub.writeback import DocumentWritebackProvider

pytestmark = pytest.mark.skipif(
    os.getenv("DATAHUB_LIVE") != "1",
    reason="requires local DataHub MCP; set DATAHUB_LIVE=1 to run",
)

ORDER_DETAILS_URN = "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.analytics.order_details,PROD)"

_READ_TOOLS = {"get_entities", "list_schema_fields", "get_lineage", "search", "search_documents", "get_dataset_queries", "get_lineage_paths_between", "grep_documents"}
_WRITE_TOOLS = _READ_TOOLS | {
    "add_owners",
    "add_structured_properties",
    "add_tags",
    "add_terms",
    "remove_domains",
    "remove_owners",
    "remove_structured_properties",
    "remove_tags",
    "remove_terms",
    "save_document",
    "set_domains",
    "update_description",
}


def _settings() -> DataHubSettings:
    return DataHubSettings.from_environment_forced_to_mode("mcp")


async def _list_tool_names(mutation_enabled: bool) -> set[str]:
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    parameters = _build_stdio_parameters(_settings(), mutation_enabled=mutation_enabled)
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            return {tool.name for tool in listed.tools}


def test_read_only_tools_are_discovered_without_mutations() -> None:
    names = asyncio.run(_list_tool_names(mutation_enabled=False))
    assert names == _READ_TOOLS
    assert "save_document" not in names


def test_mutation_tools_including_save_document_are_discovered_when_enabled() -> None:
    names = asyncio.run(_list_tool_names(mutation_enabled=True))
    assert names == _WRITE_TOOLS
    assert "save_document" in names


def test_missing_token_does_not_crash_against_this_auth_disabled_instance() -> None:
    """This local instance runs METADATA_SERVICE_AUTH_ENABLED=false. Building MCP
    parameters with no token configured at all must still work end-to-end."""
    settings = DataHubSettings(mode="mcp", gms_url=_settings().gms_url, token=None)
    provider = DocumentWritebackProvider(settings)

    preview = provider.preview(ORDER_DETAILS_URN)

    assert preview.evidence


def test_preview_reads_real_order_details_and_derives_evidence() -> None:
    provider = DocumentWritebackProvider(_settings())

    preview = provider.preview(ORDER_DETAILS_URN)

    assert preview.related_assets == [ORDER_DETAILS_URN]
    assert preview.evidence
    assert preview.reasoning_consequence.id
    assert ORDER_DETAILS_URN in preview.content
    assert "no document-delete tool" in preview.persistence_warning
    # Against real ORDER_DETAILS in the showcase-ecommerce catalog, upstream
    # lineage exists, so it must drive the consequence — never PII, even though
    # ORDER_DETAILS also carries a real PII glossary term.
    assert preview.reasoning_consequence.id.startswith("consequence-lineage-")
    assert "PII" not in preview.reasoning_consequence.statement
    assert "PII" not in preview.reasoning_consequence.next_test


def test_publish_requires_explicit_approval_against_the_live_server() -> None:
    from sherlock.connectors.datahub.provider import DataHubProviderError

    provider = DocumentWritebackProvider(_settings())
    preview = provider.preview(ORDER_DETAILS_URN)

    with pytest.raises(DataHubProviderError, match="approval"):
        provider.publish(preview, approved=False)


def test_publish_then_retrieve_round_trips_through_real_mcp() -> None:
    """The end-to-end contract: preview (read) -> publish (approved, idempotent
    mutation) -> retrieve (read) all against real DataHub. Deterministic
    idempotency means reruns land on already_exists, not a new document."""
    provider = DocumentWritebackProvider(_settings())

    preview = provider.preview(ORDER_DETAILS_URN)
    publish_result = provider.publish(preview, approved=True)

    assert publish_result.status in {"created", "already_exists"}
    assert publish_result.urn.startswith("urn:li:document:")
    assert publish_result.idempotency_key == preview.idempotency_key

    retrieval = provider.retrieve(preview.idempotency_key, expected_urn=publish_result.urn)

    assert retrieval.status == "verified"
    assert retrieval.urn == publish_result.urn
    assert preview.idempotency_key in retrieval.title
