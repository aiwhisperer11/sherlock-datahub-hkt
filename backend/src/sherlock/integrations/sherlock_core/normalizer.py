"""Pure conversion from observed DataHub metadata into Sherlock input."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from sherlock.domain.models import DataHubObservation, LineageEntity

from .contracts import (
    DataHubEvidenceSourceReference,
    DataHubInvestigationRequest,
    EvidenceProvenance,
    EvidenceProvider,
    EvidenceSourceReference,
    NormalizedEvidence,
    SherlockBaselineRequest,
    SherlockEvidence,
)

_SENSITIVE_NAME_PARTS = ("secret", "token", "password", "api_key", "apikey", "authorization", "cookie")
_METADATA_LIMITATION = "Metadata only; does not demonstrate execution, data freshness, or root cause."
_SNAPSHOT_LIMITATION = "This is a non-live snapshot."


def build_case_id(asset_urn: str, incident_id: str) -> str:
    """Build a stable ID while percent-encoding unsafe delimiters/control input."""
    return f"datahub:{quote(asset_urn, safe=':(),._-')}:{quote(incident_id, safe=':(),._-')}"


def normalise_datahub_observation(
    request: DataHubInvestigationRequest,
    observation: DataHubObservation,
    *,
    selected_provider: EvidenceProvider,
) -> tuple[SherlockBaselineRequest, EvidenceProvenance]:
    """Create deterministic, provenance-separated evidence for Sherlock-Core.

    The function performs no I/O and never interprets metadata as a cause or a
    data-freshness signal.  One call accepts one provider only.
    """
    if observation.urn != request.asset_urn:
        raise ValueError("observation URN must match the requested asset URN")

    captured_at = observation.captured_at
    limitations = [_METADATA_LIMITATION]
    live = selected_provider not in {"snapshot", "sandbox"}
    if not live:
        limitations.append(_SNAPSHOT_LIMITATION)

    entries: list[tuple[str, str, str]] = []
    entries.append(("asset", f"DataHub asset {observation.name}", _asset_content(observation)))

    for field in sorted(observation.schema_fields, key=lambda item: item.field_path):
        if _is_sensitive(field.field_path):
            continue
        data_type = f" ({field.native_data_type})" if field.native_data_type else ""
        entries.append((f"schema:{field.field_path}", f"Schema field {field.field_path}", f"Schema field {field.field_path}{data_type}."))

    if observation.owners:
        entries.append(("ownership", "DataHub ownership", f"Recorded owners: {', '.join(sorted(observation.owners))}."))
    if observation.tags:
        entries.append(("tags", "DataHub tags", f"Recorded tags: {', '.join(sorted(observation.tags))}."))
    if observation.glossary_terms:
        entries.append(("glossary", "DataHub glossary terms", f"Recorded glossary terms: {', '.join(sorted(observation.glossary_terms))}."))

    for key, value in sorted(observation.structured_properties.items()):
        if _is_sensitive(key):
            continue
        entries.append((f"property:{key}", f"DataHub property {key}", f"Recorded property {key}: {_compact(str(value))}."))

    for direction, entities in (("upstream", observation.upstream.entities), ("downstream", observation.downstream.entities)):
        for entity in sorted(entities, key=lambda item: item.urn):
            entries.append((f"lineage:{direction}:{entity.urn}", f"{direction.title()} lineage", _lineage_content(direction, entity)))

    normalized: list[NormalizedEvidence] = []
    sources: dict[str, EvidenceSourceReference] = {}
    for index, (reference, label, content) in enumerate(entries, start=1):
        evidence_id = f"E{index}"
        source = DataHubEvidenceSourceReference(provider=selected_provider, asset_urn=request.asset_urn, query_or_aspect=reference, captured_at=captured_at, limitations=limitations)
        normalized.append(NormalizedEvidence(id=evidence_id, label=_compact(label, 256), content=f"{_compact(content)} Metadata captured at {_timestamp(captured_at)}. {limitations[0]}" + (f" {_SNAPSHOT_LIMITATION}" if not live else ""), source_reference=source))
        sources[evidence_id] = EvidenceSourceReference(
            provider=selected_provider,
            asset_urn=request.asset_urn,
            query_or_aspect=reference,
            captured_at=captured_at,
            live=live,
            limitations=limitations,
        )

    baseline = SherlockBaselineRequest(
        case_id=build_case_id(request.asset_urn, request.incident_id),
        case_title=f"DataHub investigation: {_compact(observation.name, 200)} ({_compact(request.incident_id, 200)})",
        domain="DataHub metadata investigation",
        observed_outcome=request.observed_outcome,
        expected_behavior=request.expected_behavior,
        evidence=[SherlockEvidence(id=item.id, label=item.label, content=item.content) for item in normalized],
        user_hypotheses=request.user_hypotheses,
    )
    provenance = EvidenceProvenance(
        selected_provider=selected_provider,
        captured_at=captured_at,
        asset_urn=request.asset_urn,
        limitations=limitations,
        evidence_sources=sources,
    )
    return baseline, provenance


def _asset_content(observation: DataHubObservation) -> str:
    return f"Asset name: {observation.name}; platform: {observation.platform}; URN: {observation.urn}."


def _lineage_content(direction: str, entity: LineageEntity) -> str:
    details = [f"{direction.title()} lineage asset URN: {entity.urn}"]
    if entity.name:
        details.append(f"name: {entity.name}")
    if entity.platform:
        details.append(f"platform: {entity.platform}")
    return "; ".join(details) + "."


def _timestamp(captured_at: datetime) -> str:
    return captured_at.isoformat().replace("+00:00", "Z")


def _is_sensitive(name: str) -> bool:
    lowered = name.lower().replace("-", "_")
    return any(part in lowered for part in _SENSITIVE_NAME_PARTS)


def _compact(value: str, limit: int = 1000) -> str:
    return " ".join(value.replace("\x00", "").split())[:limit]
