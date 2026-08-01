import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from sherlock.api.main import app
from sherlock.connectors.datahub.provider import DataHubMetadataProvider, DataHubProviderError, DataHubSettings
from sherlock.connectors.datahub.writeback import (
    _WRITEBACK_TAG_URN,
    McpWritebackProvider,
    _EntityWritebackState,
    _investigation_marker,
)


def _investigation():
    return DataHubMetadataProvider().load_frozen_dashboard_from_snapshot()


def _provider(monkeypatch: pytest.MonkeyPatch) -> McpWritebackProvider:
    monkeypatch.setattr(DataHubMetadataProvider, "load_frozen_dashboard", lambda self: _investigation())
    return McpWritebackProvider(DataHubSettings(mode="mcp", token="not-printed"))


def test_endpoint_rejects_missing_confirmation() -> None:
    response = TestClient(app).post("/api/v1/investigations/frozen-dashboard/writeback", json={"add_tag": True})

    assert response.status_code == 400


def test_endpoint_does_not_call_mcp_without_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fail_if_called(self, add_tag: bool):
        nonlocal called
        called = True
        raise AssertionError("write() must not run without confirm=true")

    monkeypatch.setattr(McpWritebackProvider, "write", fail_if_called)

    response = TestClient(app).post("/api/v1/investigations/frozen-dashboard/writeback", json={"confirm": False})

    assert response.status_code == 400
    assert called is False


def test_client_cannot_supply_a_target_urn(monkeypatch: pytest.MonkeyPatch) -> None:
    """The public body only has confirm/add_tag; a client-supplied urn field must be ignored."""
    seen_add_tag = {}

    def fake_write(self, add_tag: bool):
        seen_add_tag["value"] = add_tag
        from sherlock.domain.models import WritebackResult

        return WritebackResult(
            urn=self.target_urn, investigation_id="x", description_written=True, tag_added=False,
            verified=True, already_published=False, degraded=False, detail="ok",
        )

    monkeypatch.setattr(McpWritebackProvider, "write", fake_write)

    response = TestClient(app).post(
        "/api/v1/investigations/frozen-dashboard/writeback",
        json={"confirm": True, "add_tag": False, "target_urn": "urn:li:dataset:(urn:li:dataPlatform:evil,x,PROD)"},
    )

    assert response.status_code == 200
    assert response.json()["urn"] != "urn:li:dataset:(urn:li:dataPlatform:evil,x,PROD)"
    assert seen_add_tag["value"] is False


def test_already_published_skips_mutation_entirely(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(monkeypatch)
    investigation = _investigation()
    state = _EntityWritebackState(description=_investigation_marker(investigation.id), tag_urns=frozenset({_WRITEBACK_TAG_URN}))
    monkeypatch.setattr("sherlock.connectors.datahub.writeback._fetch_entity_state", lambda settings, urn: state)

    def fail_if_called(self, *args, **kwargs):
        raise AssertionError("_mutate must not run when already published")

    monkeypatch.setattr(McpWritebackProvider, "_mutate", fail_if_called)

    result = provider.write(add_tag=True)

    assert result.already_published is True
    assert result.description_written is False
    assert result.tag_added is False
    assert result.verified is True


def test_partial_gap_only_adds_missing_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Description already published, tag missing, add_tag=True: only add_tags should run."""
    provider = _provider(monkeypatch)
    investigation = _investigation()
    before = _EntityWritebackState(description=_investigation_marker(investigation.id), tag_urns=frozenset())
    after = _EntityWritebackState(description=_investigation_marker(investigation.id), tag_urns=frozenset({_WRITEBACK_TAG_URN}))
    states = iter([before, after])
    monkeypatch.setattr("sherlock.connectors.datahub.writeback._fetch_entity_state", lambda settings, urn: next(states))

    calls: list[str] = []

    class Session:
        async def call_tool(self, name: str, arguments: dict[str, object]):
            calls.append(name)
            return SimpleNamespace(isError=False, structuredContent={"success": True}, content=[])

        async def initialize(self) -> None:
            return None

        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(name="update_description"), SimpleNamespace(name="add_tags")])

    class FakeStdioClient:
        async def __aenter__(self):
            return (None, None)

        async def __aexit__(self, *exc):
            return False

    class FakeClientSession:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return Session()

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr("mcp.client.stdio.stdio_client", lambda parameters: FakeStdioClient())
    monkeypatch.setattr("mcp.ClientSession", FakeClientSession)

    result = provider.write(add_tag=True)

    assert calls == ["add_tags"]
    assert result.description_written is False
    assert result.tag_added is True
    assert result.already_published is False
    assert result.verified is True


def test_degraded_when_update_description_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(monkeypatch)
    investigation = _investigation()
    before = _EntityWritebackState(description=None, tag_urns=frozenset())
    after = _EntityWritebackState(description=None, tag_urns=frozenset({_WRITEBACK_TAG_URN}))
    states = iter([before, after])
    monkeypatch.setattr("sherlock.connectors.datahub.writeback._fetch_entity_state", lambda settings, urn: next(states))

    calls: list[str] = []

    class Session:
        async def call_tool(self, name: str, arguments: dict[str, object]):
            calls.append(name)
            return SimpleNamespace(isError=False, structuredContent={"success": True}, content=[])

        async def initialize(self) -> None:
            return None

        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(name="add_tags")])  # no update_description

    class FakeStdioClient:
        async def __aenter__(self):
            return (None, None)

        async def __aexit__(self, *exc):
            return False

    class FakeClientSession:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return Session()

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr("mcp.client.stdio.stdio_client", lambda parameters: FakeStdioClient())
    monkeypatch.setattr("mcp.ClientSession", FakeClientSession)

    result = provider.write(add_tag=True)

    assert calls == ["add_tags"]
    assert result.description_written is False
    assert result.tag_added is True
    assert result.degraded is True
    assert investigation.id  # sanity: fixture built correctly


def test_partial_failure_keeps_the_successful_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reproduces the real failure observed against live DataHub: update_description succeeds,
    add_tags fails (tag URN did not exist yet). The endpoint must report the partial success,
    not raise and discard it — the description write already happened, it cannot be un-done
    by an exception."""
    provider = _provider(monkeypatch)
    investigation = _investigation()
    before = _EntityWritebackState(description=None, tag_urns=frozenset())
    after = _EntityWritebackState(description=_investigation_marker(investigation.id), tag_urns=frozenset())
    states = iter([before, after])
    monkeypatch.setattr("sherlock.connectors.datahub.writeback._fetch_entity_state", lambda settings, urn: next(states))

    class Session:
        async def call_tool(self, name: str, arguments: dict[str, object]):
            if name == "add_tags":
                raise RuntimeError("Error add tags: Urn does not exist.")
            return SimpleNamespace(isError=False, structuredContent={"success": True}, content=[])

        async def initialize(self) -> None:
            return None

        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(name="update_description"), SimpleNamespace(name="add_tags")])

    class FakeStdioClient:
        async def __aenter__(self):
            return (None, None)

        async def __aexit__(self, *exc):
            return False

    class FakeClientSession:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return Session()

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr("mcp.client.stdio.stdio_client", lambda parameters: FakeStdioClient())
    monkeypatch.setattr("mcp.ClientSession", FakeClientSession)

    result = provider.write(add_tag=True)

    assert result.description_written is True
    assert result.tag_added is False
    assert result.degraded is True
    assert result.already_published is False
    assert "add_tags" in result.detail


def test_fails_explicitly_when_no_mutation_tool_is_available(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(monkeypatch)
    before = _EntityWritebackState(description=None, tag_urns=frozenset())
    monkeypatch.setattr("sherlock.connectors.datahub.writeback._fetch_entity_state", lambda settings, urn: before)

    class Session:
        async def initialize(self) -> None:
            return None

        async def list_tools(self):
            return SimpleNamespace(tools=[])  # neither tool available

    class FakeStdioClient:
        async def __aenter__(self):
            return (None, None)

        async def __aexit__(self, *exc):
            return False

    class FakeClientSession:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return Session()

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr("mcp.client.stdio.stdio_client", lambda parameters: FakeStdioClient())
    monkeypatch.setattr("mcp.ClientSession", FakeClientSession)

    with pytest.raises(DataHubProviderError, match="no compatible mutation tool"):
        provider.write(add_tag=False)


def test_mutation_subprocess_rejects_tools_outside_writeback_allowlist() -> None:
    provider = McpWritebackProvider(DataHubSettings(mode="mcp", token="not-printed"))

    with pytest.raises(DataHubProviderError, match="not permitted"):
        asyncio.run(provider._call(SimpleNamespace(), "remove_owners", {}))


def test_marker_is_stable_for_the_same_investigation_id() -> None:
    assert _investigation_marker("investigation-frozen-dashboard") == _investigation_marker("investigation-frozen-dashboard")
    assert _investigation_marker("a") != _investigation_marker("b")
