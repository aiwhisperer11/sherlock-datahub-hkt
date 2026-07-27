"""Pure follow-up preparation and provenance reconciliation."""
from __future__ import annotations

from typing import Any

from .contracts import DataHubEvidenceSourceReference, FollowUpProvenance, NewEvidence, SherlockFollowUpRequest


def prepare_follow_up(previous_snapshot: dict[str, Any], new_evidence: list[NewEvidence], sources: list[DataHubEvidenceSourceReference]) -> tuple[SherlockFollowUpRequest, FollowUpProvenance]:
    if len(new_evidence) != len(sources):
        raise ValueError("every new evidence item requires one source reference")
    return SherlockFollowUpRequest(previous_snapshot=previous_snapshot, new_evidence=new_evidence), FollowUpProvenance(pending_evidence_sources=sources)


def reconcile_follow_up_ids(previous_snapshot: dict[str, Any], returned_snapshot: dict[str, Any], provenance: FollowUpProvenance) -> dict[str, DataHubEvidenceSourceReference]:
    """Map only newly assigned canonical E-ids; neither snapshot is changed."""
    previous_ids = {item["id"] for item in previous_snapshot.get("case", {}).get("evidence", []) if isinstance(item, dict) and isinstance(item.get("id"), str)}
    returned_ids = [item["id"] for item in returned_snapshot.get("case", {}).get("evidence", []) if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"] not in previous_ids]
    if len(returned_ids) != len(provenance.pending_evidence_sources):
        raise ValueError("returned Sherlock evidence cannot be reconciled safely")
    return dict(zip(returned_ids, provenance.pending_evidence_sources, strict=True))
