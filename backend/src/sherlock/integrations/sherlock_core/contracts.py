"""DataHub-owned transport models for the future Sherlock-Core boundary.

These models deliberately do not validate, alter, or duplicate the canonical
``SherlockInvestigation`` schema.  Sherlock-Core remains its sole producer.
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator
from .boundary import validate_unchanged


MetadataMode = Literal["auto", "mcp", "graphql", "snapshot", "sandbox"]
EvidenceProvider = Literal["mcp", "graphql", "snapshot"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DataHubInvestigationRequest(_StrictModel):
    asset_urn: str = Field(min_length=1, max_length=2048)
    incident_id: str = Field(min_length=1, max_length=512)
    observed_outcome: str = Field(min_length=1, max_length=10_000)
    expected_behavior: str = Field(min_length=1, max_length=10_000)
    user_hypotheses: list[str] = Field(default_factory=list, max_length=50)
    metadata_mode: MetadataMode = "auto"

    @field_validator("asset_urn", "incident_id", "observed_outcome", "expected_behavior", "user_hypotheses", mode="after")
    @classmethod
    def reject_control_characters(cls, value: str | list[str]) -> str | list[str]:
        values = value if isinstance(value, list) else [value]
        if any(any(character in item for character in ("\x00", "\r", "\n")) for item in values):
            raise ValueError("control characters are not permitted")
        return value


class EvidenceMcpSource(_StrictModel):
    """Optional machine provenance for evidence acquired over DataHub MCP.

    Mirrors the `source` object added to the canonical schema's evidence
    item (`schemas/sherlock-investigation-1.0.0.schema.json`). Absent for
    user-provided or legacy evidence — this must never be required.
    """

    type: Literal["datahub_mcp"] = "datahub_mcp"
    tool: str = Field(min_length=1, max_length=128)
    entity_urn: str = Field(min_length=1, max_length=2048)
    retrieved_at: datetime


class SherlockEvidence(_StrictModel):
    id: str = Field(pattern=r"^E[1-9][0-9]*$")
    label: str = Field(min_length=1, max_length=256)
    content: str = Field(min_length=1, max_length=10_000)
    source: EvidenceMcpSource | None = None


class DataHubEvidenceSourceReference(_StrictModel):
    asset_urn: str
    provider: EvidenceProvider
    query_or_aspect: str
    captured_at: datetime
    limitations: list[str]


class NormalizedEvidence(_StrictModel):
    """Internal evidence; its source reference never crosses into Sherlock."""
    id: str = Field(pattern=r"^E[1-9][0-9]*$")
    label: str
    content: str
    source_reference: DataHubEvidenceSourceReference


class SherlockBaselineRequest(_StrictModel):
    case_id: str = Field(min_length=1, max_length=4096)
    case_title: str = Field(min_length=1, max_length=512)
    domain: str = Field(min_length=1, max_length=256)
    observed_outcome: str
    expected_behavior: str
    evidence: list[SherlockEvidence] = Field(min_length=1)
    user_hypotheses: list[str] = Field(default_factory=list)


class EvidenceSourceReference(DataHubEvidenceSourceReference):
    """Backward-compatible alias with explicit liveness for response provenance."""
    live: bool

    @computed_field(return_type=str)
    @property
    def source_reference(self) -> str:
        return self.query_or_aspect


class EvidenceProvenance(_StrictModel):
    selected_provider: EvidenceProvider
    captured_at: datetime
    asset_urn: str
    limitations: list[str]
    evidence_sources: dict[str, EvidenceSourceReference]


class ProviderAttempt(_StrictModel):
    provider: EvidenceProvider
    status: Literal["succeeded", "failed"]
    error_code: str | None = Field(default=None, max_length=128)
    message: str | None = Field(default=None, max_length=512)

    @field_validator("error_code", "message")
    @classmethod
    def reject_control_characters(cls, value: str | None) -> str | None:
        if value is not None and any(character in value for character in ("\x00", "\r", "\n")):
            raise ValueError("control characters are not permitted")
        return value

    @field_validator("message")
    @classmethod
    def redact_credential_values(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return re.sub(
            r"(?i)\b(bearer|token|password|secret|api[_ -]?key)\b\s*[:=]?\s*[^\s,;]+",
            r"\1 [redacted]",
            value,
        )


class DataHubInvestigationResponse(_StrictModel):
    # This is intentionally opaque at this gate: no local fork of the
    # canonical SherlockInvestigation schema and no response remapping.
    investigation: dict[str, Any]
    evidence_provenance: EvidenceProvenance
    provider_attempts: list[ProviderAttempt]

    @field_validator("investigation")
    @classmethod
    def validate_canonical_investigation(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_unchanged(value)


class NewEvidence(_StrictModel):
    label: str = Field(min_length=1, max_length=256)
    content: str = Field(min_length=1, max_length=10_000)


class SherlockFollowUpRequest(_StrictModel):
    # Preserve the complete canonical snapshot exactly; Sherlock-Core assigns
    # IDs to new evidence during the follow-up request.
    previous_snapshot: dict[str, Any]
    new_evidence: list[NewEvidence] = Field(min_length=1)


class FollowUpProvenance(_StrictModel):
    """Parallel, pending provenance; keyed by position until Sherlock assigns E-ids."""
    pending_evidence_sources: list[DataHubEvidenceSourceReference]
