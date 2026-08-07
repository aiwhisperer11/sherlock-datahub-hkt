"""No-Docker unit tests for DocumentWritebackProvider: preview/publish/retrieve,
with MCP mocked exactly like test_writeback.py mocks McpWritebackProvider."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from sherlock.connectors.datahub.provider import DataHubProviderError, DataHubSettings
from sherlock.connectors.datahub.writeback import DocumentWritebackProvider
from sherlock.domain.models import DataHubEvidence, DocumentPreview, ReasoningConsequence

URN = "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.analytics.order_details,PROD)"


def _pii_entity_response() -> SimpleNamespace:
    return SimpleNamespace(
        isError=False,
        structuredContent={
            "result": [
                {
                    "urn": URN,
                    "name": "ORDER_DETAILS",
                    "ownership": {"owners": [{"owner": {"properties": {"displayName": "Data Platform Team"}}}]},
                    "glossaryTerms": {"terms": [{"term": {"properties": {"name": "PII"}}}]},
                }
            ]
        },
        content=[],
    )


def _upstream_lineage_response() -> SimpleNamespace:
    return SimpleNamespace(
        isError=False,
        structuredContent={"upstreams": {"entities": [{"entity": {"name": "INVENTORIES", "urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,x,PROD)"}}]}},
        content=[],
    )


def _empty_lineage_response() -> SimpleNamespace:
    return SimpleNamespace(isError=False, structuredContent={"upstreams": {"entities": []}}, content=[])


def _search_hit(title: str, urn: str) -> SimpleNamespace:
    return SimpleNamespace(
        isError=False,
        structuredContent={"searchResults": [{"entity": {"urn": urn, "info": {"title": title}}}]},
        content=[],
    )


def _search_empty() -> SimpleNamespace:
    return SimpleNamespace(isError=False, structuredContent={"searchResults": []}, content=[])


def _save_success(urn: str) -> SimpleNamespace:
    return SimpleNamespace(isError=False, structuredContent={"success": True, "urn": urn, "message": "created"}, content=[])


class ScriptedSession:
    def __init__(self, responses: dict[str, list[SimpleNamespace]]) -> None:
        self._responses = {name: list(values) for name, values in responses.items()}
        self.calls: list[str] = []

    async def initialize(self) -> None:
        return None

    async def call_tool(self, name: str, arguments: dict[str, object]):
        self.calls.append(name)
        queue = self._responses.get(name)
        if not queue:
            raise AssertionError(f"unexpected/extra call to {name}")
        return queue.pop(0)


class _FakeStdioClient:
    async def __aenter__(self):
        return (None, None)

    async def __aexit__(self, *exc):
        return False


def _patch_mcp(monkeypatch: pytest.MonkeyPatch, session: ScriptedSession) -> None:
    class FakeClientSession:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr("mcp.client.stdio.stdio_client", lambda parameters: _FakeStdioClient())
    monkeypatch.setattr("mcp.ClientSession", FakeClientSession)


def _preview() -> DocumentPreview:
    consequence = ReasoningConsequence(
        id="consequence-lineage-x", statement="stub statement", evidence_ids=["ev-upstream-x"], next_test="stub next test"
    )
    evidence = [DataHubEvidence(id="ev-upstream-x", tool="get_lineage", urn=URN, observed_fact="stub fact", observed_at=datetime.now(UTC))]
    return DocumentPreview(
        idempotency_key="sherlock-investigation-deadbeefcafebabe",
        document_type="Insight",
        title="Sherlock investigation: ORDER_DETAILS (sherlock-investigation-deadbeefcafebabe)",
        content="preview content",
        related_assets=[URN],
        reasoning_consequence=consequence,
        evidence=evidence,
    )


def test_preview_reads_entity_and_lineage_and_derives_evidence_and_reasoning(monkeypatch: pytest.MonkeyPatch) -> None:
    session = ScriptedSession({"get_entities": [_pii_entity_response()], "get_lineage": [_upstream_lineage_response()]})
    _patch_mcp(monkeypatch, session)
    provider = DocumentWritebackProvider(DataHubSettings(mode="mcp", token="x"))

    preview = provider.preview(URN)

    assert session.calls == ["get_entities", "get_lineage"]
    assert preview.evidence
    # PII is real evidence (present in the content for context) but must never
    # drive the reasoning consequence — lineage does, since it is the
    # incident-relevant signal here.
    assert "PII" in preview.content
    assert preview.reasoning_consequence.id.startswith("consequence-lineage-")
    assert "PII" not in preview.reasoning_consequence.statement
    assert preview.related_assets == [URN]
    assert preview.idempotency_key in preview.title


def test_preview_falls_back_to_ownership_reasoning_without_lineage(monkeypatch: pytest.MonkeyPatch) -> None:
    session = ScriptedSession({"get_entities": [_pii_entity_response()], "get_lineage": [_empty_lineage_response()]})
    _patch_mcp(monkeypatch, session)
    provider = DocumentWritebackProvider(DataHubSettings(mode="mcp", token="x"))

    preview = provider.preview(URN)

    assert session.calls == ["get_entities", "get_lineage"]
    assert preview.reasoning_consequence.id.startswith("consequence-ownership-")


def test_publish_without_approval_raises_and_never_touches_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("must not open an MCP subprocess without approval")

    monkeypatch.setattr("mcp.client.stdio.stdio_client", fail_if_called)
    provider = DocumentWritebackProvider(DataHubSettings(mode="mcp", token="x"))

    with pytest.raises(DataHubProviderError, match="approval"):
        provider.publish(_preview(), approved=False)


def test_publish_creates_when_nothing_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    preview = _preview()
    session = ScriptedSession(
        {
            "search_documents": [_search_empty()],
            "save_document": [_save_success("urn:li:document:shared-new-1")],
        }
    )
    _patch_mcp(monkeypatch, session)
    provider = DocumentWritebackProvider(DataHubSettings(mode="mcp", token="x"))

    result = provider.publish(preview, approved=True)

    assert session.calls == ["search_documents", "save_document"]
    assert result.status == "created"
    assert result.urn == "urn:li:document:shared-new-1"
    assert result.idempotency_key == preview.idempotency_key


def test_publish_is_idempotent_and_never_calls_save_document_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    preview = _preview()
    session = ScriptedSession({"search_documents": [_search_hit(preview.title, "urn:li:document:shared-existing-1")]})
    _patch_mcp(monkeypatch, session)
    provider = DocumentWritebackProvider(DataHubSettings(mode="mcp", token="x"))

    result = provider.publish(preview, approved=True)

    assert session.calls == ["search_documents"]  # save_document never called
    assert result.status == "already_exists"
    assert result.urn == "urn:li:document:shared-existing-1"


def test_retrieve_verified_when_urn_title_and_marker_match(monkeypatch: pytest.MonkeyPatch) -> None:
    preview = _preview()
    session = ScriptedSession({"search_documents": [_search_hit(preview.title, "urn:li:document:shared-existing-1")]})
    _patch_mcp(monkeypatch, session)
    provider = DocumentWritebackProvider(DataHubSettings(mode="mcp", token="x"))

    result = provider.retrieve(preview.idempotency_key, expected_urn="urn:li:document:shared-existing-1")

    assert result.status == "verified"
    assert result.urn == "urn:li:document:shared-existing-1"
    assert preview.idempotency_key in result.title


def test_retrieve_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    session = ScriptedSession({"search_documents": [_search_empty()]})
    _patch_mcp(monkeypatch, session)
    provider = DocumentWritebackProvider(DataHubSettings(mode="mcp", token="x"))

    result = provider.retrieve("sherlock-investigation-doesnotexist")

    assert result.status == "not_found"
    assert result.urn is None


def test_retrieve_mismatch_when_urn_does_not_match_expected(monkeypatch: pytest.MonkeyPatch) -> None:
    preview = _preview()
    session = ScriptedSession({"search_documents": [_search_hit(preview.title, "urn:li:document:shared-unexpected")]})
    _patch_mcp(monkeypatch, session)
    provider = DocumentWritebackProvider(DataHubSettings(mode="mcp", token="x"))

    result = provider.retrieve(preview.idempotency_key, expected_urn="urn:li:document:shared-existing-1")

    assert result.status == "mismatch"


def test_mutation_subprocess_rejects_document_tools_outside_allowlist() -> None:
    import asyncio

    from sherlock.connectors.datahub.provider import _call_mcp_tool
    from sherlock.connectors.datahub.provider import _ALLOWED_DOCUMENT_MCP_TOOLS

    with pytest.raises(DataHubProviderError, match="not permitted"):
        asyncio.run(_call_mcp_tool(SimpleNamespace(), "remove_owners", {}, _ALLOWED_DOCUMENT_MCP_TOOLS))


def test_preview_timeout_is_sanitised_not_a_hang(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test for the reproduced failure: GET /api/v1/documents/preview
    returned a 502 timeout under normal load against a real local Quickstart
    instance because get_entities + get_lineage share one session/timeout
    budget. This proves the failure path itself is correct — a short timeout
    still surfaces the sanitised DataHubProviderError, never hangs, never
    raises the raw asyncio/anyio exception to the caller."""
    provider = DocumentWritebackProvider(DataHubSettings(mode="mcp", token="not-printed", timeout_seconds=0.001))

    async def never_returns(urn: str) -> tuple[dict, dict]:
        await asyncio.sleep(1)
        return {}, {}

    monkeypatch.setattr(provider, "_fetch_context", never_returns)

    with pytest.raises(DataHubProviderError, match="timed out"):
        provider.preview(URN)


def test_preview_timeout_never_leaks_the_token_into_the_log(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    token = "token-that-must-not-appear"
    provider = DocumentWritebackProvider(DataHubSettings(mode="mcp", token=token, timeout_seconds=0.001))

    async def never_returns(urn: str) -> tuple[dict, dict]:
        await asyncio.sleep(1)
        return {}, {}

    monkeypatch.setattr(provider, "_fetch_context", never_returns)

    caplog.set_level(logging.ERROR, logger="sherlock.connectors.datahub.provider")
    with pytest.raises(DataHubProviderError):
        provider.preview(URN)

    assert token not in caplog.text


# --- Canonical Sherlock-Core engine wiring ----------------------------------

from sherlock.integrations.sherlock_core.client import SherlockCoreUnavailableError  # noqa: E402


class _FakeEngineClient:
    def __init__(self, configured: bool, snapshot: dict | None = None, raises: Exception | None = None) -> None:
        self._configured = configured
        self._snapshot = snapshot
        self._raises = raises
        self.received_request = None

    @property
    def configured(self) -> bool:
        return self._configured

    def run_baseline_investigation(self, request):
        self.received_request = request
        if self._raises is not None:
            raise self._raises
        return self._snapshot


def _schema_valid_snapshot_with_no_evidence_links() -> dict:
    """A real, fully schema-valid snapshot (the fixture also used by
    test_sherlock_core_normalizer.py), stripped of every evidence_id
    reference it originally carried (from its own, unrelated checkout/TLS
    case) so tests can attach exactly the citations they mean to test,
    without an accidental collision with this unrelated fixture's own E1-E4."""
    import json
    from pathlib import Path

    snapshot = json.loads((Path(__file__).parent / "fixtures" / "sherlock-investigation-1.0.0.json").read_text())
    for hypothesis in snapshot["hypotheses"]:
        hypothesis["supported_by"] = []
        hypothesis["contradicted_by"] = []
        hypothesis["expected_but_absent_ids"] = []
    for entries in snapshot["expectation_matrix"].values():
        for entry in entries:
            entry["evidence_ids"] = []
    snapshot["next_test"]["description"] = "Generic next step with no evidence id."
    return snapshot


def _snapshot_citing_first_lineage_evidence() -> dict:
    """Same schema-valid snapshot, with its leading hypothesis's supported_by
    pointed at "E4" — the id to_canonical_evidence assigns the lineage fact
    in this test file's fixtures (3 entity facts + 1 lineage fact)."""
    snapshot = _schema_valid_snapshot_with_no_evidence_links()
    snapshot["hypotheses"][0]["supported_by"] = [{"evidence_id": "E4", "reason": "DataHub lineage links the two datasets"}]
    snapshot["prime_suspect"]["hypothesis_id"] = snapshot["hypotheses"][0]["id"]
    snapshot["hypotheses"][0]["statement"] = "ORDER_DETAILS depends on upstream data; a delayed dependency is a candidate, not a proven cause."
    return snapshot


def test_preview_uses_canonical_engine_when_configured_and_cited(monkeypatch: pytest.MonkeyPatch) -> None:
    session = ScriptedSession({"get_entities": [_pii_entity_response()], "get_lineage": [_upstream_lineage_response()]})
    _patch_mcp(monkeypatch, session)
    engine = _FakeEngineClient(configured=True, snapshot=_snapshot_citing_first_lineage_evidence())
    provider = DocumentWritebackProvider(DataHubSettings(mode="mcp", token="x"), engine_client=engine)

    preview = provider.preview(URN)

    assert preview.engine_source == "sherlock_core_canonical"
    assert engine.received_request is not None  # the engine really received a request, not just the publish flow
    assert engine.received_request.evidence  # canonical evidence, with source, was sent
    assert engine.received_request.evidence[0].source is not None
    assert "E4" in preview.reasoning_consequence.evidence_ids


def test_preview_falls_back_when_engine_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    session = ScriptedSession({"get_entities": [_pii_entity_response()], "get_lineage": [_upstream_lineage_response()]})
    _patch_mcp(monkeypatch, session)
    engine = _FakeEngineClient(configured=False)
    provider = DocumentWritebackProvider(DataHubSettings(mode="mcp", token="x"), engine_client=engine)

    preview = provider.preview(URN)

    assert preview.engine_source == "local_fallback"
    assert engine.received_request is None  # never called when not configured
    assert "canonical engine unavailable" in preview.content.lower()


def test_preview_falls_back_when_engine_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    session = ScriptedSession({"get_entities": [_pii_entity_response()], "get_lineage": [_upstream_lineage_response()]})
    _patch_mcp(monkeypatch, session)
    engine = _FakeEngineClient(configured=True, raises=SherlockCoreUnavailableError("connection refused"))
    provider = DocumentWritebackProvider(DataHubSettings(mode="mcp", token="x"), engine_client=engine)

    preview = provider.preview(URN)

    assert preview.engine_source == "local_fallback"
    assert engine.received_request is not None  # it was attempted


def test_preview_falls_back_when_engine_response_cites_no_datahub_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    session = ScriptedSession({"get_entities": [_pii_entity_response()], "get_lineage": [_upstream_lineage_response()]})
    _patch_mcp(monkeypatch, session)
    uncited_snapshot = _schema_valid_snapshot_with_no_evidence_links()
    uncited_snapshot["hypotheses"][0]["supported_by"] = [{"evidence_id": "E999", "reason": "not one of ours"}]
    engine = _FakeEngineClient(configured=True, snapshot=uncited_snapshot)
    provider = DocumentWritebackProvider(DataHubSettings(mode="mcp", token="x"), engine_client=engine)

    preview = provider.preview(URN)

    assert preview.engine_source == "local_fallback"
