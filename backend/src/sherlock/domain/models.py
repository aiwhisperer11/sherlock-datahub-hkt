from __future__ import annotations

from datetime import datetime
from enum import Enum

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
