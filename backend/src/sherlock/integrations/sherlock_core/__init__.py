"""Transport contracts and pure adapters for the Sherlock-Core boundary."""

from .client import SherlockCoreClient, SherlockCoreUnavailableError
from .contracts import (
    DataHubInvestigationRequest,
    DataHubInvestigationResponse,
    EvidenceMcpSource,
    EvidenceProvenance,
    EvidenceSourceReference,
    ProviderAttempt,
    SherlockBaselineRequest,
    SherlockEvidence,
    SherlockFollowUpRequest,
)
from .follow_up import prepare_follow_up, reconcile_follow_up_ids
from .normalizer import normalise_datahub_observation
from .selection import select_observation

__all__ = [
    "DataHubInvestigationRequest",
    "DataHubInvestigationResponse",
    "EvidenceMcpSource",
    "EvidenceProvenance",
    "EvidenceSourceReference",
    "ProviderAttempt",
    "SherlockBaselineRequest",
    "SherlockCoreClient",
    "SherlockCoreUnavailableError",
    "SherlockEvidence",
    "SherlockFollowUpRequest",
    "normalise_datahub_observation",
    "prepare_follow_up",
    "reconcile_follow_up_ids",
    "select_observation",
]
