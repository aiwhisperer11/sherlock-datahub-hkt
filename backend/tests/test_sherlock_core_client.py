"""No-Docker unit tests for SherlockCoreClient: the real (new) HTTP transport
to the canonical Sherlock-Core engine. Mocks the transport (urlopen), never
the reasoning — there is no reasoning to mock here, only a network call."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from sherlock.integrations.sherlock_core.client import SherlockCoreClient, SherlockCoreUnavailableError
from sherlock.integrations.sherlock_core.contracts import EvidenceMcpSource, SherlockBaselineRequest, SherlockEvidence


def _baseline() -> SherlockBaselineRequest:
    return SherlockBaselineRequest(
        case_id="datahub-document:x",
        case_title="t",
        domain="d",
        observed_outcome="o",
        expected_behavior="e",
        evidence=[
            SherlockEvidence(
                id="E1",
                label="DataHub get_lineage",
                content="fact",
                source=EvidenceMcpSource(tool="get_lineage", entity_urn="urn:li:dataset:(x,y,PROD)", retrieved_at=datetime(2026, 8, 7, tzinfo=UTC)),
            )
        ],
    )


def test_unconfigured_client_raises_without_a_network_call(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*_a, **_kw):
        raise AssertionError("must not open a connection when unconfigured")

    monkeypatch.setattr("sherlock.integrations.sherlock_core.client.urlopen", fail_if_called)
    client = SherlockCoreClient(base_url=None)

    assert client.configured is False
    with pytest.raises(SherlockCoreUnavailableError, match="not configured"):
        client.run_baseline_investigation(_baseline())


def test_from_environment_reads_sherlock_core_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHERLOCK_CORE_URL", raising=False)
    unconfigured = SherlockCoreClient.from_environment()
    assert unconfigured.configured is False

    monkeypatch.setenv("SHERLOCK_CORE_URL", "http://localhost:3001")
    configured = SherlockCoreClient.from_environment()
    assert configured.configured is True
    assert configured.base_url == "http://localhost:3001"


def test_default_timeout_is_90_seconds() -> None:
    """Regression test: a real 4-evidence-item baseline against the deployed
    engine (https://sherlock-engine.vercel.app) took long enough to exceed a
    30s budget and raise TimeoutError — not a code defect, an insufficient
    default for how much reasoning work the LLM does per evidence item."""
    assert SherlockCoreClient(base_url="http://x").timeout_seconds == 90.0


def test_timeout_env_var_still_overrides_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHERLOCK_CORE_TIMEOUT_SECONDS", "10")
    client = SherlockCoreClient.from_environment()
    assert client.timeout_seconds == 10.0


def test_successful_response_is_parsed_and_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    posted = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"schema_version": "1.0.0", "hypotheses": []}).encode()

    def fake_urlopen(request, timeout):
        posted["url"] = request.full_url
        posted["body"] = json.loads(request.data)
        posted["headers"] = dict(request.header_items())
        posted["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("sherlock.integrations.sherlock_core.client.urlopen", fake_urlopen)
    client = SherlockCoreClient(base_url="http://localhost:3001", timeout_seconds=12.0)

    result = client.run_baseline_investigation(_baseline())

    assert result == {"schema_version": "1.0.0", "hypotheses": []}
    assert posted["url"] == "http://localhost:3001/api/investigate"
    assert posted["body"]["evidence"][0]["source"]["tool"] == "get_lineage"
    assert posted["timeout"] == 12.0


def test_connection_failure_raises_sanitised_unavailable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from urllib.error import URLError

    def fake_urlopen(request, timeout):
        raise URLError("Connection refused")

    monkeypatch.setattr("sherlock.integrations.sherlock_core.client.urlopen", fake_urlopen)
    client = SherlockCoreClient(base_url="http://localhost:3001")

    with pytest.raises(SherlockCoreUnavailableError, match="Sherlock-Core investigation request failed"):
        client.run_baseline_investigation(_baseline())


def test_non_json_response_raises_unavailable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"not json"

    monkeypatch.setattr("sherlock.integrations.sherlock_core.client.urlopen", lambda request, timeout: FakeResponse())
    client = SherlockCoreClient(base_url="http://localhost:3001")

    with pytest.raises(SherlockCoreUnavailableError):
        client.run_baseline_investigation(_baseline())
