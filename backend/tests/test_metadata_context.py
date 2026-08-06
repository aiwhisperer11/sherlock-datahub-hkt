from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from sherlock.api.main import app
from sherlock.connectors.datahub.provider import (
    ORDER_DETAILS_URN,
    DataHubMetadataProvider,
    DataHubProviderError,
    DataHubSettings,
    SnapshotMetadataProvider,
    UnsupportedMetadataUrnError,
)
from sherlock.domain.models import DataHubObservation, MetadataContextResult

UNSUPPORTED_URN = "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.order_entry.inventories,PROD)"


class StubSource:
    def __init__(self, observation: DataHubObservation | Exception) -> None:
        self.observation = observation

    def fetch(self) -> DataHubObservation:
        if isinstance(self.observation, Exception):
            raise self.observation
        return self.observation


def snapshot() -> DataHubObservation:
    return SnapshotMetadataProvider().fetch()


def test_metadata_context_accepts_order_details_urn_and_returns_full_evidence() -> None:
    """The supported-URN path: source, mode, live, and the underlying evidence (schema, PII
    tags, ownership, lineage) must all be present and untouched by this new wrapper."""
    result = DataHubMetadataProvider(
        DataHubSettings(mode="mcp"),
        {"mcp": StubSource(snapshot()), "graphql": StubSource(DataHubProviderError("graphql should not run"))},
    ).load_metadata_context(ORDER_DETAILS_URN)

    assert isinstance(result, MetadataContextResult)
    assert result.entity_urn == ORDER_DETAILS_URN
    assert result.mode == "mcp"
    assert result.source == "mcp"
    assert result.live is True
    assert isinstance(result.retrieved_at, datetime)
    assert result.observation.urn == ORDER_DETAILS_URN
    assert result.observation.schema_fields
    assert "PII" in result.observation.glossary_terms
    assert result.observation.owners
    assert result.observation.upstream.entities
    assert result.observation.downstream.entities
    assert [attempt.provider for attempt in result.provider_attempts] == ["mcp"]


def test_metadata_context_retrieved_at_is_independent_of_observation_captured_at() -> None:
    """retrieved_at marks this request; observation.captured_at marks when the provider
    normalised its evidence. They must be distinct fields, not aliases of each other."""
    result = DataHubMetadataProvider(DataHubSettings(mode="mcp"), {"mcp": StubSource(snapshot())}).load_metadata_context(ORDER_DETAILS_URN)

    assert isinstance(result.retrieved_at, datetime)
    assert isinstance(result.observation.captured_at, datetime)


def test_metadata_context_rejects_unsupported_urn_before_touching_any_provider() -> None:
    provider = DataHubMetadataProvider(DataHubSettings(mode="mcp"), {"mcp": StubSource(DataHubProviderError("must not be called"))})

    with pytest.raises(UnsupportedMetadataUrnError, match="ORDER_DETAILS"):
        provider.load_metadata_context(UNSUPPORTED_URN)


def test_metadata_context_auto_fallback_to_snapshot_is_not_live() -> None:
    result = DataHubMetadataProvider(
        DataHubSettings(mode="auto"),
        {
            "mcp": StubSource(DataHubProviderError("mcp unavailable")),
            "graphql": StubSource(DataHubProviderError("graphql unavailable")),
            "snapshot": StubSource(snapshot()),
        },
    ).load_metadata_context(ORDER_DETAILS_URN)

    assert result.source == "snapshot"
    assert result.live is False


def test_endpoint_returns_200_for_supported_urn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHERLOCK_METADATA_MODE", "sandbox")
    monkeypatch.delenv("DATAHUB_GMS_TOKEN", raising=False)

    response = TestClient(app).get("/api/v1/metadata/context", params={"urn": ORDER_DETAILS_URN})

    assert response.status_code == 200
    body = response.json()
    assert body["entity_urn"] == ORDER_DETAILS_URN
    assert body["source"] == "snapshot"
    assert body["live"] is False
    assert body["observation"]["schema_fields"]


def test_endpoint_returns_400_for_unsupported_urn() -> None:
    response = TestClient(app).get("/api/v1/metadata/context", params={"urn": UNSUPPORTED_URN})

    assert response.status_code == 400
    assert "ORDER_DETAILS" in response.json()["detail"]


def test_endpoint_surfaces_provider_failure_as_502(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_error(self: DataHubMetadataProvider, urn: str) -> MetadataContextResult:
        raise DataHubProviderError("MCP metadata request failed")

    monkeypatch.setattr("sherlock.connectors.datahub.provider.DataHubMetadataProvider.load_metadata_context", raise_error)

    response = TestClient(app).get("/api/v1/metadata/context", params={"urn": ORDER_DETAILS_URN})

    assert response.status_code == 502
    assert response.json()["detail"] == "MCP metadata request failed"
