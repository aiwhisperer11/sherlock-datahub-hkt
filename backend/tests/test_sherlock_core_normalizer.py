from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from sherlock.domain.models import DataHubObservation, LineageEntity, LineagePage, SchemaField
from sherlock.integrations.sherlock_core import DataHubInvestigationRequest, ProviderAttempt, SherlockFollowUpRequest, normalise_datahub_observation, prepare_follow_up, reconcile_follow_up_ids, select_observation
from sherlock.integrations.sherlock_core.contracts import DataHubInvestigationResponse
from sherlock.integrations.sherlock_core.contracts import DataHubEvidenceSourceReference, EvidenceSourceReference, NewEvidence
from sherlock.integrations.sherlock_core.normalizer import build_case_id
from sherlock.integrations.sherlock_core.boundary import CanonicalInvestigationError, validate_unchanged


def observation() -> DataHubObservation:
    return DataHubObservation(
        urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,warehouse.orders,PROD)",
        name="orders",
        platform="snowflake",
        schema_fields=[SchemaField(field_path="z_field", native_data_type="VARCHAR"), SchemaField(field_path="a_field", native_data_type="INTEGER"), SchemaField(field_path="api_token", native_data_type="VARCHAR")],
        structured_properties={"zeta": "last", "alpha": "first", "api_key": "must-not-leak"},
        owners=["team-b", "team-a"],
        tags=["gold", "finance"],
        glossary_terms=["Orders"],
        upstream=LineagePage(direction="upstream", hops=1, offset=0, limit=20, returned=2, entities=[LineageEntity(urn="urn:li:dataset:up-b"), LineageEntity(urn="urn:li:dataset:up-a")]),
        downstream=LineagePage(direction="downstream", hops=1, offset=0, limit=20, returned=0, entities=[]),
        consumers=[],
        source="test",
        captured_at=datetime(2026, 7, 25, 12, 0, tzinfo=UTC),
    )


def request() -> DataHubInvestigationRequest:
    return DataHubInvestigationRequest(asset_urn=observation().urn, incident_id="alert/123", observed_outcome="Dashboard did not update.", expected_behavior="Dashboard should update after the scheduled pipeline run.")


def test_normalizer_is_deterministic_and_preserves_provenance_outside_sherlock_request() -> None:
    first, first_provenance = normalise_datahub_observation(request(), observation(), selected_provider="graphql")
    second, second_provenance = normalise_datahub_observation(request(), observation(), selected_provider="graphql")

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first_provenance.model_dump(mode="json") == second_provenance.model_dump(mode="json")
    assert [item.id for item in first.evidence] == [f"E{index}" for index in range(1, len(first.evidence) + 1)]
    assert first.case_id.endswith(":alert%2F123")
    assert "evidence_sources" not in first.model_dump()
    assert first_provenance.evidence_sources["E1"].provider == "graphql"
    assert all("Metadata captured at 2026-07-25T12:00:00Z." in item.content for item in first.evidence)
    assert all("Metadata only; does not demonstrate execution, data freshness, or root cause." in item.content for item in first.evidence)


def test_normalizer_sorts_metadata_and_excludes_sensitive_properties() -> None:
    baseline, provenance = normalise_datahub_observation(request(), observation(), selected_provider="mcp")
    labels = [item.label for item in baseline.evidence]
    contents = " ".join(item.content for item in baseline.evidence)

    assert labels.index("Schema field a_field") < labels.index("Schema field z_field")
    assert labels.index("DataHub property alpha") < labels.index("DataHub property zeta")
    assert "api_token" not in contents
    assert "must-not-leak" not in contents
    assert provenance.selected_provider == "mcp"
    assert all(source.live for source in provenance.evidence_sources.values())


def test_snapshot_evidence_is_marked_non_live_without_claiming_freshness() -> None:
    baseline, provenance = normalise_datahub_observation(request(), observation(), selected_provider="snapshot")

    assert "This is a non-live snapshot." in baseline.evidence[0].content
    assert provenance.limitations[-1] == "This is a non-live snapshot."
    assert not any(source.live for source in provenance.evidence_sources.values())


def test_sandbox_metadata_mode_is_accepted_and_maps_to_snapshot_selection() -> None:
    request_with_sandbox = DataHubInvestigationRequest(
        asset_urn=observation().urn,
        incident_id="alert/123",
        observed_outcome="Dashboard did not update.",
        expected_behavior="Dashboard should update after the scheduled pipeline run.",
        metadata_mode="sandbox",
    )
    selected, provider, attempts = select_observation(
        request_with_sandbox.metadata_mode,
        {"mcp": observation, "graphql": observation, "snapshot": observation},
    )

    assert selected.urn == observation().urn
    assert provider == "snapshot"
    assert [(item.provider, item.status) for item in attempts] == [("snapshot", "succeeded")]


def test_evidence_source_reference_serializes_backward_compatible_source_reference() -> None:
    reference = EvidenceSourceReference(
        asset_urn=observation().urn,
        provider="snapshot",
        query_or_aspect="schema:a_field",
        captured_at=observation().captured_at,
        limitations=["Metadata only"],
        live=False,
    )

    dumped = reference.model_dump(mode="json")
    assert dumped["query_or_aspect"] == "schema:a_field"
    assert dumped["source_reference"] == "schema:a_field"


def test_normalizer_rejects_mismatched_asset() -> None:
    invalid_request = request().model_copy(update={"asset_urn": "urn:li:dataset:other"})

    with pytest.raises(ValueError, match="must match"):
        normalise_datahub_observation(invalid_request, observation(), selected_provider="mcp")


def test_transport_contracts_reject_unsafe_identifiers_and_follow_up_does_not_assign_ids() -> None:
    with pytest.raises(ValueError, match="control characters"):
        DataHubInvestigationRequest(asset_urn="urn:li:dataset:bad\nvalue", incident_id="i", observed_outcome="o", expected_behavior="e")

    follow_up = SherlockFollowUpRequest(previous_snapshot={"schema_version": "1.0.0", "unknown": {"kept": True}}, new_evidence=[{"label": "Run log", "content": "Pipeline completed."}])
    assert follow_up.previous_snapshot["unknown"] == {"kept": True}
    assert "id" not in follow_up.new_evidence[0].model_dump()
    assert build_case_id("urn:li:dataset:ok", "path/segment") == "datahub:urn:li:dataset:ok:path%2Fsegment"


def test_provider_attempt_redacts_credential_values() -> None:
    attempt = ProviderAttempt(provider="graphql", status="failed", message="request failed: Bearer token-that-must-not-leak")

    assert attempt.message == "request failed: Bearer [redacted]"


def test_provider_selection_is_exclusive_and_fallback_is_explicit() -> None:
    selected, provider, attempts = select_observation("auto", {"mcp": lambda: (_ for _ in ()).throw(RuntimeError("token top-secret failed")), "graphql": observation, "snapshot": observation})

    assert selected.urn == observation().urn
    assert provider == "graphql"
    assert [(item.provider, item.status) for item in attempts] == [("mcp", "failed"), ("graphql", "succeeded")]
    assert "top-secret" not in attempts[0].message


def test_follow_up_preserves_snapshot_and_reconciles_only_returned_ids() -> None:
    source = DataHubEvidenceSourceReference(asset_urn=observation().urn, provider="mcp", query_or_aspect="run-log", captured_at=observation().captured_at, limitations=["Metadata only"])
    previous = {"case": {"evidence": [{"id": "E1"}]}, "unknown": {"unchanged": True}}
    follow_up, pending = prepare_follow_up(previous, [NewEvidence(label="Run log", content="Completed")], [source])
    mapping = reconcile_follow_up_ids(previous, {"case": {"evidence": [{"id": "E1"}, {"id": "E2"}]}}, pending)

    assert follow_up.previous_snapshot == previous
    assert "id" not in follow_up.new_evidence[0].model_dump()
    assert mapping == {"E2": source}


def test_invalid_sherlock_response_is_rejected_without_remapping() -> None:
    valid = json.loads((Path(__file__).parent / "fixtures" / "sherlock-investigation-1.0.0.json").read_text())
    _, provenance = normalise_datahub_observation(request(), observation(), selected_provider="mcp")
    response = DataHubInvestigationResponse(investigation=valid, evidence_provenance=provenance, provider_attempts=[])
    assert response.investigation == valid

    for invalid in (
        {key: value for key, value in valid.items() if key != "case"},
        {**valid, "unexpected": True},
        {**valid, "schema_version": "wrong"},
    ):
        with pytest.raises(ValueError):
            DataHubInvestigationResponse(investigation=invalid, evidence_provenance=provenance, provider_attempts=[])

    with pytest.raises(CanonicalInvestigationError, match="schema_version"):
        validate_unchanged({"schema_version": "wrong"})
    with pytest.raises(ValueError, match="schema_version"):
        DataHubInvestigationResponse(investigation={"schema_version": "wrong"}, evidence_provenance=provenance, provider_attempts=[])
