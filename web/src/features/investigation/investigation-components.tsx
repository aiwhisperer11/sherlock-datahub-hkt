import type { Investigation } from "@/lib/investigation";

export function IncidentCard({ investigation }: { investigation: Investigation }) {
  const { incident } = investigation;
  return <article className="card"><h2>Incident</h2><p><strong>{incident.title}</strong> · {incident.severity}</p><p>{incident.description}</p><p className="muted">Detected {new Date(incident.detected_at).toLocaleString()}</p></article>;
}

export function AffectedAssets({ assets }: Pick<Investigation, "assets">) {
  return <article className="card"><h2>Affected & downstream assets</h2><ul>{assets.map((asset) => <li key={asset.id}><strong>{asset.name}</strong><br /><span className="muted">{asset.platform} · {asset.asset_type} · SLA {asset.freshness_sla_minutes ?? "n/a"} min</span></li>)}</ul></article>;
}

export function HypothesisList({ hypotheses }: Pick<Investigation, "hypotheses">) {
  return <article className="card full"><h2>Hypotheses & confidence</h2><ul>{hypotheses.map((hypothesis) => <li key={hypothesis.id}><strong>{hypothesis.statement}</strong><br /><span className="score">{Math.round(hypothesis.confidence.score * 100)}%</span><span className="muted"> · coverage {hypothesis.confidence.evidence_coverage}, reliability {hypothesis.confidence.source_reliability}, consistency {hypothesis.confidence.consistency}, proximity {hypothesis.confidence.lineage_proximity}</span></li>)}</ul></article>;
}

export function EvidenceList({ evidence }: Pick<Investigation, "evidence">) {
  return <article className="card"><h2>Evidence</h2><ul>{evidence.map((item) => <li key={item.id}>{item.summary}<br /><span className="muted">{item.source} · reliability {item.reliability}</span></li>)}</ul></article>;
}

export function RecommendationCard({ investigation }: { investigation: Investigation }) {
  const action = investigation.recommended_actions[0];
  return <article className="card"><h2>Conclusion & recommendation</h2><p>{investigation.conclusion.summary}</p>{action && <><p className="priority">{action.priority} · {action.summary}</p><p className="muted">{action.rationale}</p></>}</article>;
}
