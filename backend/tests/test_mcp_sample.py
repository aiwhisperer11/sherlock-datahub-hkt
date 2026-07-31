import asyncio
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from sherlock.api.main import app
from sherlock.connectors.datahub.provider import (
    DataHubProviderError,
    DataHubSettings,
    McpSampleProvider,
    _normalise_mcp_sample,
)
from sherlock.domain.models import McpSampleEntity, McpSampleResult


def _real_shaped_entity(urn: str) -> dict[str, object]:
    """Shaped like the real mcp-server-datahub get_entities response observed against local GMS."""
    return {
        "result": [
            {
                "urn": urn,
                "name": "addresses",
                "platform": {"urn": "urn:li:dataPlatform:dbt", "name": "dbt"},
                "properties": {"name": "addresses", "description": "Customer addresses"},
                "ownership": {"owners": [{"owner": {"urn": "urn:li:corpGroup:x", "properties": {"displayName": "Data Platform Team"}}}]},
                "glossaryTerms": {"terms": [{"term": {"properties": {"name": "PII"}}}]},
                "domain": {"domain": {"urn": "urn:li:domain:x", "properties": {"name": "Data Platform Team"}}},
                "schemaMetadata": {"fields": [{"fieldPath": "address_id", "nativeDataType": "NUMBER"}, {"fieldPath": "zipcode", "nativeDataType": "NUMBER"}]},
            }
        ]
    }


def test_mcp_entity_normalises_to_sample_model() -> None:
    urn = "urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.order_entry_db.order_entry.addresses,PROD)"
    upstream = {"upstreams": {"searchResults": [{"entity": {"urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.order_entry.addresses,PROD)"}}]}}
    downstream = {"downstreams": {"searchResults": [{"entity": {"urn": "urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.order_entry_db.analytics.order_details,PROD)"}}]}}

    result = _normalise_mcp_sample(_real_shaped_entity(urn), upstream, downstream)

    assert isinstance(result, McpSampleResult)
    assert result.source_mode == "mcp"
    assert result.source_verified is True
    assert result.entity_count == 1
    assert result.entity.urn == urn
    assert result.entity.type == "DATASET"
    assert result.entity.name == "addresses"
    assert result.entity.platform == "dbt"
    assert result.entity.schema_fields == ["address_id", "zipcode"]
    assert result.entity.owners == ["Data Platform Team"]
    assert result.entity.glossary_terms == ["PII"]
    assert result.entity.domains == ["Data Platform Team"]
    assert result.entity.upstream_urns == ["urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.order_entry.addresses,PROD)"]
    assert result.entity.downstream_urns == ["urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.order_entry_db.analytics.order_details,PROD)"]
    assert result.warnings == []
    assert isinstance(result.captured_at, datetime)


def test_zero_entities_produces_explicit_error() -> None:
    provider = McpSampleProvider(DataHubSettings(mode="mcp", token="not-printed"))

    class ZeroResultSession:
        async def call_tool(self, _name: str, _arguments: dict[str, object]) -> object:
            class _Result:
                structuredContent = {"total": 0, "searchResults": []}
                content: list[object] = []
                isError = False

            return _Result()

    with pytest.raises(DataHubProviderError, match="zero entities"):
        asyncio.run(provider._discover(ZeroResultSession()))


def test_mcp_failure_does_not_fall_back_silently(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = McpSampleProvider(DataHubSettings(mode="mcp", token="not-printed"))

    async def broken_fetch() -> McpSampleResult:
        raise RuntimeError("transport exploded")

    monkeypatch.setattr(provider, "_fetch", broken_fetch)

    with pytest.raises(DataHubProviderError, match="MCP metadata request failed"):
        provider.fetch_sample()


def test_missing_token_is_explicit_and_does_not_run_mcp() -> None:
    provider = McpSampleProvider(DataHubSettings(mode="mcp", token=None))

    with pytest.raises(DataHubProviderError, match="DATAHUB_GMS_TOKEN"):
        provider.fetch_sample()


def test_mcp_sample_failure_is_sanitised(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "token-that-must-not-appear"
    provider = McpSampleProvider(DataHubSettings(mode="mcp", token=token))

    async def leaky_fetch() -> McpSampleResult:
        raise RuntimeError(token)

    monkeypatch.setattr(provider, "_fetch", leaky_fetch)

    with pytest.raises(DataHubProviderError) as error:
        provider.fetch_sample()

    assert token not in str(error.value)


def test_endpoint_returns_mcp_source_mode_and_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    sample = McpSampleResult(
        source_mode="mcp",
        source_verified=True,
        entity_count=1,
        entity=McpSampleEntity(
            urn="urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.order_entry_db.order_entry.addresses,PROD)",
            type="DATASET",
            name="addresses",
            platform="dbt",
            schema_fields=["address_id"],
            owners=["Data Platform Team"],
            glossary_terms=["PII"],
            domains=["Data Platform Team"],
            upstream_urns=[],
            downstream_urns=["urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.order_entry_db.analytics.order_details,PROD)"],
        ),
        captured_at=datetime.now(UTC),
        warnings=[],
    )
    monkeypatch.setattr("sherlock.connectors.datahub.provider.McpSampleProvider.fetch_sample", lambda self: sample)

    response = TestClient(app).get("/api/v1/metadata/mcp/sample")

    assert response.status_code == 200
    body = response.json()
    assert body["source_mode"] == "mcp"
    assert body["source_verified"] is True
    assert body["entity_count"] == 1
    assert body["entity"]["urn"] == sample.entity.urn
    assert body["captured_at"]


def test_endpoint_surfaces_explicit_error_without_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_error(self: McpSampleProvider) -> McpSampleResult:
        raise DataHubProviderError("MCP search returned zero entities")

    monkeypatch.setattr("sherlock.connectors.datahub.provider.McpSampleProvider.fetch_sample", raise_error)

    response = TestClient(app).get("/api/v1/metadata/mcp/sample")

    assert response.status_code == 502
    assert response.json()["detail"] == "MCP search returned zero entities"
