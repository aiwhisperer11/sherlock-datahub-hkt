from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, computed_field


class RelationshipType(str, Enum):
    AFFECTS = "AFFECTS"
    UPSTREAM_OF = "UPSTREAM_OF"
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    EXPLAINS = "EXPLAINS"
    RECOMMENDS = "RECOMMENDS"


class Relationship(BaseModel):
    source_id: str
    relationship: RelationshipType
    target_id: str


class Incident(BaseModel):
    id: str
    title: str
    description: str
    detected_at: datetime
    severity: str


class Asset(BaseModel):
    id: str
    name: str
    platform: str
    asset_type: str
    freshness_sla_minutes: int | None = None


class Observation(BaseModel):
    id: str
    observed_at: datetime
    source: str
    summary: str


class Evidence(BaseModel):
    id: str
    observation_id: str
    source: str
    summary: str
    observed_at: datetime
    reliability: float = Field(ge=0, le=1)


class ConfidenceComponents(BaseModel):
    evidence_coverage: float = Field(ge=0, le=1)
    source_reliability: float = Field(ge=0, le=1)
    consistency: float = Field(ge=0, le=1)
    lineage_proximity: float = Field(ge=0, le=1)

    @computed_field(return_type=float)
    @property
    def score(self) -> float:
        """Confidence is explicit rather than a black-box score."""
        return round(
            self.evidence_coverage
            * self.source_reliability
            * self.consistency
            * self.lineage_proximity,
            3,
        )


class Hypothesis(BaseModel):
    id: str
    statement: str
    confidence: ConfidenceComponents


class RecommendedAction(BaseModel):
    id: str
    summary: str
    priority: str
    rationale: str


class Conclusion(BaseModel):
    id: str
    summary: str
    certainty: str


class Investigation(BaseModel):
    id: str
    title: str
    incident: Incident
    assets: list[Asset]
    observations: list[Observation]
    evidence: list[Evidence]
    hypotheses: list[Hypothesis]
    conclusion: Conclusion
    recommended_actions: list[RecommendedAction]
    relationships: list[Relationship]


class ProviderAttempt(BaseModel):
    provider: str
    status: Literal["succeeded", "failed", "not_configured"]
    duration_ms: int = Field(ge=0)
    error: str | None = None


class SchemaField(BaseModel):
    field_path: str
    native_data_type: str | None = None
    description: str | None = None


class LineageEntity(BaseModel):
    urn: str
    name: str | None = None
    platform: str | None = None
    entity_type: str | None = None
    relationship_type: str | None = None


class LineagePage(BaseModel):
    direction: str
    hops: int = Field(ge=1)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
    total: int | None = Field(default=None, ge=0)
    returned: int = Field(ge=0)
    has_more: bool | None = None
    entities: list[LineageEntity]


class ObservedDataHubAsset(BaseModel):
    urn: str
    name: str
    platform: str
    structured_properties: dict[str, str | float]
    escalation_contact: str | None = None


class DataHubObservation(BaseModel):
    urn: str
    name: str
    platform: str
    schema_total: int | None = Field(default=None, ge=0)
    schema_fields: list[SchemaField]
    structured_properties: dict[str, str | float]
    owners: list[str]
    escalation_contact: str | None = None
    tags: list[str]
    glossary_terms: list[str]
    upstream: LineagePage
    downstream: LineagePage
    consumers: list[LineageEntity]
    related_assets: list[ObservedDataHubAsset] = Field(default_factory=list)
    source: str
    captured_at: datetime
    warning: str | None = None


class McpSampleEntity(BaseModel):
    urn: str
    type: str
    name: str
    platform: str
    schema_fields: list[str]
    owners: list[str]
    glossary_terms: list[str]
    domains: list[str]
    upstream_urns: list[str]
    downstream_urns: list[str]


class McpSampleResult(BaseModel):
    source_mode: Literal["mcp"] = "mcp"
    source_verified: bool
    entity_count: int = Field(ge=0)
    entity: McpSampleEntity
    captured_at: datetime
    warnings: list[str]


class SimulatedTelemetry(BaseModel):
    id: str
    label: str
    value_hours: int = Field(ge=0)
    context: str
    provenance: Literal["simulated_incident_input"] = "simulated_incident_input"


class Anomaly(BaseModel):
    id: str
    type: Literal["unexpected_change", "missing_update", "cross_layer_contradiction", "stage_inconsistency"]
    title: str
    expected: str
    observed: str
    gap: str
    severity: Literal["low", "medium", "high", "critical"]
    provenance: list[str]
    why_it_matters: str


class InitialHypothesis(BaseModel):
    id: str
    statement: str
    prior_confidence: float = Field(ge=0, le=1)
    evidence_needed: list[str]
    status: Literal["open", "deprioritized"]


class InvestigationEvidence(BaseModel):
    id: str
    statement: str
    provenance: Literal["simulated_incident_input", "observed_from_datahub", "snapshot_fixture", "derived_by_sherlock"]
    source_reference: str | None = None
    reliability: float = Field(ge=0, le=1)
    observed_at: datetime | None = None
    limitations: list[str]


class HypothesisMatrixEntry(BaseModel):
    hypothesis_id: str
    evidence_id: str
    relationship: Literal["supports", "contradicts", "neutral", "missing"]
    weight: float = Field(ge=0, le=1)
    rationale: str


class ConfidenceUpdate(BaseModel):
    hypothesis_id: str
    prior_confidence: float = Field(ge=0, le=1)
    factors: list["ConfidenceFactor"]
    final_confidence: float = Field(ge=0, le=1)
    explanation: str


class PrimeSuspect(BaseModel):
    hypothesis_id: str
    label: str
    status: Literal["provisional"]
    confidence: float = Field(ge=0, le=1)
    why_selected: str
    strongest_supporting_evidence: str
    strongest_counterevidence: str
    what_would_change_the_verdict: str


class WaldMissingEvidence(BaseModel):
    id: str
    question: str
    missing_evidence: str
    why_it_may_be_invisible: str
    hypotheses_affected: list[str]
    information_value: Literal["high", "medium", "low"]
    acquisition_action: str
    could_change_prime_suspect: bool


class FinalResult(BaseModel):
    verdict: str
    verdict_status: Literal["provisional"]
    confidence: float = Field(ge=0, le=1)
    affected_assets: list[str]
    business_impact: str
    immediate_action: str
    owner_to_contact: str
    confirmation_needed: str
    guardrail: str


class ConfidenceFactor(BaseModel):
    value: float = Field(ge=0, le=1)
    explanation: str
    evidence_ids: list[str]


class ExplainableConfidence(BaseModel):
    evidence_coverage: ConfidenceFactor
    source_reliability: ConfidenceFactor
    consistency: ConfidenceFactor
    lineage_proximity: ConfidenceFactor

    @computed_field(return_type=float)
    @property
    def score(self) -> float:
        return round(
            self.evidence_coverage.value
            * self.source_reliability.value
            * self.consistency.value
            * self.lineage_proximity.value,
            3,
        )


class FrozenDashboardHypothesis(BaseModel):
    id: str
    statement: str
    confidence: ExplainableConfidence


class FrozenDashboardResult(BaseModel):
    id: str
    title: str
    simulated_incident_input: list[str]
    observed_from_datahub: DataHubObservation
    simulated_telemetry: list[SimulatedTelemetry]
    anomalies: list[Anomaly]
    initial_hypotheses: list[InitialHypothesis]
    evidence: list[InvestigationEvidence]
    hypothesis_matrix: list[HypothesisMatrixEntry]
    confidence_update: list[ConfidenceUpdate]
    prime_suspect: PrimeSuspect
    wald: list[WaldMissingEvidence]
    final_result: FinalResult
    derived_by_sherlock: list[FrozenDashboardHypothesis]
    limitations: list[str]
    provider_attempts: list[ProviderAttempt]
    selected_provider: str
    conclusion: str
    recommended_action: str
