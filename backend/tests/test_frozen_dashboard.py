import asyncio
import json
from types import SimpleNamespace
from urllib.error import URLError

import pytest
from fastapi.testclient import TestClient

from sherlock.api.main import app
from sherlock.connectors.datahub.provider import (
    ORDER_DETAILS_URN,
    DataHubMetadataProvider,
    DataHubProviderError,
    DataHubSettings,
    GraphQLMetadataProvider,
    McpMetadataProvider,
    SnapshotMetadataProvider,
    _extract_mcp_structured_result,
    _normalise_mcp,
)
from sherlock.domain.models import DataHubObservation


class StubSource:
    def __init__(self, observation: DataHubObservation | Exception) -> None:
        self.observation = observation
        self.calls = 0

    def fetch(self) -> DataHubObservation:
        self.calls += 1
        if isinstance(self.observation, Exception):
            raise self.observation
        return self.observation


def snapshot() -> DataHubObservation:
    return SnapshotMetadataProvider().fetch()


def test_mcp_response_maps_to_internal_models() -> None:
    entities = {
        "entities": [
            {
                "urn": ORDER_DETAILS_URN,
                "name": "ORDER_DETAILS",
                "platform": {"name": "snowflake"},
                "structuredProperties": {
                    "properties": [
                        {
                            "structuredProperty": {"definition": {"qualifiedName": "showcase.dataFreshnessSla"}},
                            "values": [{"stringValue": "Daily"}],
                        }
                    ]
                },
            }
        ]
    }
    fields = {"totalFields": 55, "fields": [{"fieldPath": "quantity_on_hand", "nativeDataType": "NUMBER(38,0)"}]}
    upstream = {"upstreams": {"total": 1, "returned": 1, "offset": 0, "hasMore": False, "entities": [{"urn": "urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.order_entry_db.order_entry.inventories,PROD)", "platform": {"name": "dbt"}, "type": "DATASET"}]}}
    downstream = {"downstreams": {"total": 1, "returned": 1, "offset": 0, "hasMore": False, "entities": [{"urn": "urn:li:dataset:(urn:li:dataPlatform:powerbi,b2fd91.report,PROD)", "platform": {"name": "powerbi"}, "type": "DATASET"}]}}

    observed = _normalise_mcp(entities, fields, upstream, downstream)

    assert observed.schema_total == 55
    assert observed.schema_fields[0].field_path == "quantity_on_hand"
    assert observed.structured_properties["showcase.dataFreshnessSla"] == "Daily"
    assert observed.upstream.direction == "upstream"
    assert observed.upstream.hops == 1
    assert observed.upstream.total == 1
    assert observed.downstream.offset == 0
    assert observed.consumers[0].platform == "powerbi"


def test_mcp_rejects_tools_outside_read_allowlist() -> None:
    provider = McpMetadataProvider(DataHubSettings(token="not-printed"))

    with pytest.raises(DataHubProviderError, match="not permitted"):
        asyncio.run(provider._call(SimpleNamespace(), "add_tags", {}))


def test_mcp_extracts_camel_case_structured_content() -> None:
    result = SimpleNamespace(isError=False, structuredContent={"entities": []}, content=[])

    assert _extract_mcp_structured_result(result, "get_entities") == {"entities": []}


def test_mcp_extracts_snake_case_structured_content() -> None:
    result = SimpleNamespace(is_error=False, structured_content={"fields": []}, content=[])

    assert _extract_mcp_structured_result(result, "list_schema_fields") == {"fields": []}


def test_mcp_extracts_json_object_from_text_content() -> None:
    result = SimpleNamespace(isError=False, content=[SimpleNamespace(text=json.dumps({"upstreams": {}}))])

    assert _extract_mcp_structured_result(result, "get_lineage") == {"upstreams": {}}


def test_mcp_extracts_error_without_payload() -> None:
    payload = {"token": "must-not-appear"}
    result = SimpleNamespace(is_error=True, structured_content=payload, content=[])

    with pytest.raises(DataHubProviderError) as error:
        _extract_mcp_structured_result(result, "get_entities")

    assert str(error.value) == "MCP get_entities returned an error"
    assert payload["token"] not in str(error.value)


@pytest.mark.parametrize("text", ["not-json", "42", "[]"])
def test_mcp_rejects_non_object_text_content(text: str) -> None:
    result = SimpleNamespace(isError=False, content=[SimpleNamespace(text=text)])

    with pytest.raises(DataHubProviderError, match="no structured result"):
        _extract_mcp_structured_result(result, "get_entities")


def test_mcp_rejects_empty_content() -> None:
    result = SimpleNamespace(isError=False, content=[])

    with pytest.raises(DataHubProviderError, match="no structured result"):
        _extract_mcp_structured_result(result, "get_entities")


def test_mcp_rejects_ambiguous_text_blocks_without_payload() -> None:
    payload = {"entities": [{"urn": "first"}]}
    result = SimpleNamespace(
        isError=False,
        content=[SimpleNamespace(text=json.dumps(payload)), SimpleNamespace(text=json.dumps({"entities": [{"urn": "second"}]}))],
    )

    with pytest.raises(DataHubProviderError) as error:
        _extract_mcp_structured_result(result, "get_entities")

    assert str(error.value) == "MCP get_entities returned ambiguous structured results"
    assert "first" not in str(error.value)


def test_mcp_timeout_is_sanitised(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = McpMetadataProvider(DataHubSettings(token="not-printed", timeout_seconds=0.001))

    async def never_returns() -> DataHubObservation:
        await asyncio.sleep(1)
        return snapshot()

    monkeypatch.setattr(provider, "_fetch", never_returns)

    with pytest.raises(DataHubProviderError, match="timed out"):
        provider.fetch()


def test_graphql_error_does_not_leak_token(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "token-that-must-not-appear"

    def fail_request(*_args: object, **_kwargs: object) -> None:
        raise URLError(token)

    monkeypatch.setattr("sherlock.connectors.datahub.provider.urlopen", fail_request)

    with pytest.raises(DataHubProviderError) as error:
        GraphQLMetadataProvider(DataHubSettings(token=token)).fetch()

    assert token not in str(error.value)


def test_auto_uses_mcp_without_fallback() -> None:
    mcp = StubSource(snapshot())
    graphql = StubSource(DataHubProviderError("graphql should not run"))
    result = DataHubMetadataProvider(DataHubSettings(mode="auto"), {"mcp": mcp, "graphql": graphql, "snapshot": StubSource(snapshot())}).load_frozen_dashboard()

    assert result.selected_provider == "mcp"
    assert mcp.calls == 1
    assert graphql.calls == 0
    assert [attempt.provider for attempt in result.provider_attempts] == ["mcp"]


def test_auto_falls_back_to_graphql() -> None:
    result = DataHubMetadataProvider(
        DataHubSettings(mode="auto"),
        {"mcp": StubSource(DataHubProviderError("mcp unavailable")), "graphql": StubSource(snapshot()), "snapshot": StubSource(snapshot())},
    ).load_frozen_dashboard()

    assert result.selected_provider == "graphql"
    assert [(attempt.provider, attempt.status) for attempt in result.provider_attempts] == [("mcp", "failed"), ("graphql", "succeeded")]


def test_auto_falls_back_to_snapshot_and_records_attempts() -> None:
    result = DataHubMetadataProvider(
        DataHubSettings(mode="auto"),
        {"mcp": StubSource(DataHubProviderError("mcp unavailable")), "graphql": StubSource(DataHubProviderError("graphql unavailable")), "snapshot": StubSource(snapshot())},
    ).load_frozen_dashboard()

    assert result.selected_provider == "snapshot"
    assert [attempt.status for attempt in result.provider_attempts] == ["failed", "failed", "succeeded"]


def test_result_separates_simulated_observed_and_derived() -> None:
    result = DataHubMetadataProvider(DataHubSettings(mode="sandbox"), {"snapshot": StubSource(snapshot())}).load_frozen_dashboard()

    assert result.simulated_incident_input[0].startswith("SIMULATED INCIDENT INPUT:")
    assert all(item.provenance == "simulated_incident_input" for item in result.simulated_telemetry)
    assert result.observed_from_datahub.source == "snapshot_from_verified_datahub"
    assert any(item.provenance == "observed_from_datahub" for item in result.evidence)
    assert any(item.provenance == "derived_by_sherlock" for item in result.evidence)
    assert "not demonstrated" in result.conclusion


def test_scores_are_reproducible_explainable_and_different() -> None:
    result = DataHubMetadataProvider(DataHubSettings(mode="sandbox"), {"snapshot": StubSource(snapshot())}).load_frozen_dashboard()
    updates = result.confidence_update

    assert [update.final_confidence for update in updates] == [0.617, 0.169, 0.129]
    assert len({update.final_confidence for update in updates}) == 3
    assert all(update.factors and update.explanation for update in updates)


def test_anomalies_express_expected_observed_and_gap() -> None:
    result = DataHubMetadataProvider(DataHubSettings(mode="sandbox"), {"snapshot": StubSource(snapshot())}).load_frozen_dashboard()

    missing_update, cross_layer = result.anomalies
    assert missing_update.type == "missing_update"
    assert "24 hours" in missing_update.expected
    assert "31 hours" in missing_update.observed
    assert "7 hours" in missing_update.gap
    assert cross_layer.type == "cross_layer_contradiction"
    assert "26-hour" in cross_layer.gap


def test_matrix_wald_prime_suspect_and_final_result_remain_provisional() -> None:
    result = DataHubMetadataProvider(DataHubSettings(mode="sandbox"), {"snapshot": StubSource(snapshot())}).load_frozen_dashboard()

    assert {entry.relationship for entry in result.hypothesis_matrix} >= {"supports", "contradicts", "missing"}
    assert result.prime_suspect.hypothesis_id == "H1"
    assert result.prime_suspect.status == "provisional"
    assert result.final_result.verdict_status == "provisional"
    assert "before declaring root cause" in result.final_result.verdict
    assert [item.information_value for item in result.wald] == ["high", "high", "high", "medium", "medium"]
    assert result.wald[0].could_change_prime_suspect


def test_snapshot_exposes_related_inventory_metadata_as_observed_evidence() -> None:
    result = DataHubMetadataProvider(DataHubSettings(mode="sandbox"), {"snapshot": StubSource(snapshot())}).load_frozen_dashboard()

    inventory = result.observed_from_datahub.related_assets[0]
    assert inventory.name == "INVENTORIES"
    assert inventory.structured_properties["showcase.dataFreshnessSla"] == "Weekly"
    assert any(item.id == "E9" and item.provenance == "observed_from_datahub" for item in result.evidence)


def test_snapshot_preserves_lineage_query_limits() -> None:
    observed = snapshot()

    assert observed.upstream.direction == "upstream"
    assert observed.upstream.hops == 1
    assert observed.upstream.total == 12
    assert observed.upstream.limit == 20
    assert observed.downstream.offset == 0


def test_existing_endpoint_remains_compatible() -> None:
    response = TestClient(app).get("/api/v1/demo/stale-pipeline")

    assert response.status_code == 200
    assert response.json()["title"] == "The Case of the Stale Pipeline"


def test_frozen_dashboard_sandbox_requires_no_network_or_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHERLOCK_METADATA_MODE", "sandbox")
    monkeypatch.delenv("DATAHUB_GMS_TOKEN", raising=False)

    response = TestClient(app).get("/api/v1/demo/frozen-dashboard")

    assert response.status_code == 200
    assert response.json()["selected_provider"] == "snapshot"
    assert response.json()["provider_attempts"][0]["provider"] == "snapshot"


def test_mcp_result_content_without_an_object_is_sanitised() -> None:
    provider = McpMetadataProvider(DataHubSettings(token="not-printed"))

    class Session:
        async def call_tool(self, _name: str, _arguments: dict[str, object]) -> SimpleNamespace:
            return SimpleNamespace(isError=False, content=[SimpleNamespace(text="not-json")])

    with pytest.raises(DataHubProviderError, match="no structured result"):
        asyncio.run(provider._call(Session(), "get_entities", {"urns": [ORDER_DETAILS_URN]}))
