export type Confidence = {
  evidence_coverage: number;
  source_reliability: number;
  consistency: number;
  lineage_proximity: number;
  score: number;
};

export type Investigation = {
  id: string;
  title: string;
  incident: { title: string; description: string; detected_at: string; severity: string };
  assets: { id: string; name: string; platform: string; asset_type: string; freshness_sla_minutes?: number }[];
  evidence: { id: string; summary: string; source: string; reliability: number }[];
  hypotheses: { id: string; statement: string; confidence: Confidence }[];
  conclusion: { summary: string; certainty: string };
  recommended_actions: { id: string; summary: string; priority: string; rationale: string }[];
};

export const apiUrl = (process.env.NEXT_PUBLIC_SHERLOCK_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export async function fetchStalePipeline(): Promise<Investigation> {
  const response = await fetch(`${apiUrl}/api/v1/demo/stale-pipeline`);
  if (!response.ok) throw new Error(`Engine responded with ${response.status}`);
  return response.json() as Promise<Investigation>;
}
