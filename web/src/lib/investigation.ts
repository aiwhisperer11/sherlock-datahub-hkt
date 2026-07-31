export type ConfidenceFactor = { value: number; explanation: string; evidence_ids: string[] };

export type DataHubObservation = {
  urn: string;
  name: string;
  platform: string;
  schema_total?: number | null;
  schema_fields: { field_path: string; native_data_type?: string | null }[];
  structured_properties: Record<string, string | number>;
  owners: string[];
  escalation_contact?: string | null;
  tags: string[];
  glossary_terms: string[];
  upstream: { total?: number | null; returned: number; entities: LineageEntity[] };
  downstream: { total?: number | null; returned: number; entities: LineageEntity[] };
  consumers: LineageEntity[];
  related_assets: { urn: string; name: string; platform: string; structured_properties: Record<string, string | number>; escalation_contact?: string | null }[];
  source: string;
  captured_at?: string | null;
  warning?: string | null;
};

export type LineageEntity = { urn: string; name?: string | null; platform?: string | null; entity_type?: string | null };
export type EvidenceRelationship = "supports" | "contradicts" | "neutral" | "missing";

export type FrozenDashboard = {
  id: string;
  title: string;
  simulated_incident_input: string[];
  simulated_telemetry: { id: string; label: string; value_hours: number; context: string; provenance: "simulated_incident_input" }[];
  observed_from_datahub: DataHubObservation;
  anomalies: { id: string; type: string; title: string; expected: string; observed: string; gap: string; severity: string; provenance: string[]; why_it_matters: string }[];
  initial_hypotheses: { id: string; statement: string; prior_confidence: number; evidence_needed: string[]; status: string }[];
  evidence: { id: string; statement: string; provenance: "simulated_incident_input" | "observed_from_datahub" | "snapshot_fixture" | "derived_by_sherlock"; source_reference?: string | null; reliability: number; limitations: string[] }[];
  hypothesis_matrix: { hypothesis_id: string; evidence_id: string; relationship: EvidenceRelationship; weight: number; rationale: string }[];
  confidence_update: { hypothesis_id: string; prior_confidence: number; factors: ConfidenceFactor[]; final_confidence: number; explanation: string }[];
  prime_suspect: { hypothesis_id: string; label: string; status: "provisional"; confidence: number; why_selected: string; strongest_supporting_evidence: string; strongest_counterevidence: string; what_would_change_the_verdict: string };
  wald: { id: string; question: string; missing_evidence: string; why_it_may_be_invisible: string; hypotheses_affected: string[]; information_value: "high" | "medium" | "low"; acquisition_action: string; could_change_prime_suspect: boolean }[];
  final_result: { verdict: string; verdict_status: "provisional"; confidence: number; affected_assets: string[]; business_impact: string; immediate_action: string; owner_to_contact: string; confirmation_needed: string; guardrail: string };
  derived_by_sherlock: unknown[];
  limitations: string[];
  provider_attempts: { provider: string; status: "succeeded" | "failed" | "not_configured"; duration_ms: number; error?: string | null }[];
  selected_provider: string;
  conclusion: string;
  recommended_action: string;
};

export const apiUrl = (process.env.NEXT_PUBLIC_SHERLOCK_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

/** Reads a FastAPI-style `{ detail }` error body, if the backend sent one. Never throws. */
export async function readErrorDetail(response: Response): Promise<string | null> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === "string" ? body.detail : null;
  } catch {
    return null;
  }
}

export async function fetchFrozenDashboard(): Promise<FrozenDashboard> {
  const response = await fetch(`${apiUrl}/api/v1/demo/frozen-dashboard`);
  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail ?? `Engine responded with ${response.status}`);
  }
  return response.json() as Promise<FrozenDashboard>;
}
