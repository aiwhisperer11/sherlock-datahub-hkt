import React from "react";
import type { EvidenceRelationship, FrozenDashboard } from "@/lib/investigation";

const percentage = (value: number) => `${Math.round(value * 100)}%`;

export function AnomalyPanel({ anomalies }: Pick<FrozenDashboard, "anomalies">) {
  return <section className="section anomaly-section" aria-labelledby="anomalies-title">
    <p className="section-label">01 · Anomaly</p><h2 id="anomalies-title">Expectation violated</h2>
    <div className="anomaly-list">{anomalies.map((anomaly) => <article className="anomaly" key={anomaly.id}>
      <div><span className="type-badge">{anomaly.type.replaceAll("_", " ")}</span><span className={`severity ${anomaly.severity}`}>{anomaly.severity}</span></div>
      <h3>{anomaly.title}</h3><div className="expected-observed"><p><strong>Expected</strong>{anomaly.expected}</p><p><strong>Observed</strong>{anomaly.observed}</p><p className="gap"><strong>Gap</strong>{anomaly.gap}</p></div>
      <p className="muted">{anomaly.why_it_matters}</p>
    </article>)}</div>
  </section>;
}

export function InitialHypotheses({ hypotheses }: { hypotheses: FrozenDashboard["initial_hypotheses"] }) {
  return <section className="section" aria-labelledby="hypotheses-title"><p className="section-label">02 · Initial hypotheses</p><h2 id="hypotheses-title">What could explain the gap?</h2>
    <div className="hypothesis-list">{hypotheses.map((hypothesis) => <article key={hypothesis.id} className="hypothesis-row"><span className="hypothesis-id">{hypothesis.id}</span><div><h3>{hypothesis.statement}</h3><p className="muted">Need next: {hypothesis.evidence_needed.join(" · ")}</p></div><div className="prior"><span>Prior</span><strong>{percentage(hypothesis.prior_confidence)}</strong><small>{hypothesis.status}</small></div></article>)}</div>
  </section>;
}

export function EvidenceBoard({ evidence, matrix }: { evidence: FrozenDashboard["evidence"]; matrix: FrozenDashboard["hypothesis_matrix"] }) {
  const relationshipFor = (evidenceId: string): EvidenceRelationship[] => [...new Set(matrix.filter((entry) => entry.evidence_id === evidenceId).map((entry) => entry.relationship))];
  return <section className="section evidence-section" aria-labelledby="evidence-title"><p className="section-label">03 · Investigation / evidence board</p><h2 id="evidence-title">What we know, and where it came from</h2>
    <div className="evidence-list">{evidence.map((item) => <article className="evidence-item" key={item.id}><div className="evidence-meta"><span className={`provenance ${item.provenance}`}>{item.provenance.replaceAll("_", " ")}</span>{relationshipFor(item.id).map((relationship) => <span className={`relationship ${relationship}`} key={relationship}>{relationship}</span>)}</div><p><strong>{item.id}</strong> · {item.statement}</p><p className="muted">Reliability {percentage(item.reliability)} · {item.limitations[0]}</p></article>)}</div>
  </section>;
}

export function HypothesisMatrix({ hypotheses, matrix, updates }: { hypotheses: FrozenDashboard["initial_hypotheses"]; matrix: FrozenDashboard["hypothesis_matrix"]; updates: FrozenDashboard["confidence_update"] }) {
  const count = (id: string, relationship: EvidenceRelationship) => matrix.filter((entry) => entry.hypothesis_id === id && entry.relationship === relationship).length;
  return <section className="section matrix-section" aria-labelledby="matrix-title"><p className="section-label">04 · Hypothesis matrix</p><h2 id="matrix-title">Evidence-based confidence update</h2><p className="muted">This is a reproducible evidence score, not a Bayesian probability.</p>
    <div className="matrix-table" role="table" aria-label="Hypothesis evidence matrix"><div className="matrix-head" role="row"><span>Hypothesis</span><span>Supports</span><span>Contradicts</span><span>Missing</span><span>Prior → current</span></div>{hypotheses.map((hypothesis) => {
      const update = updates.find((item) => item.hypothesis_id === hypothesis.id);
      return <div className="matrix-row" role="row" key={hypothesis.id}><span><strong>{hypothesis.id}</strong></span><span>{count(hypothesis.id, "supports")}</span><span>{count(hypothesis.id, "contradicts")}</span><span>{count(hypothesis.id, "missing")}</span><span>{update ? `${percentage(update.prior_confidence)} → ${percentage(update.final_confidence)}` : "Not scored"}</span></div>;
    })}</div>
    <div className="confidence-notes">{updates.map((update) => <p key={update.hypothesis_id}><strong>{update.hypothesis_id}</strong> · {update.explanation}</p>)}</div>
  </section>;
}

export function PrimeSuspectPanel({ suspect }: { suspect: FrozenDashboard["prime_suspect"] }) {
  return <section className="prime-suspect" aria-labelledby="prime-title"><p className="section-label">05 · Prime suspect</p><div className="prime-heading"><div><h2 id="prime-title">{suspect.label}</h2><span className="provisional">Provisional · {percentage(suspect.confidence)} confidence</span></div><span className="suspect-id">{suspect.hypothesis_id}</span></div>
    <p>{suspect.why_selected}</p><div className="prime-grid"><p><strong>Strongest support</strong>{suspect.strongest_supporting_evidence}</p><p><strong>Counterevidence</strong>{suspect.strongest_counterevidence}</p><p><strong>Changes the verdict</strong>{suspect.what_would_change_the_verdict}</p></div>
  </section>;
}

export function WaldPanel({ items }: { items: FrozenDashboard["wald"] }) {
  return <section className="section wald-section" aria-labelledby="wald-title"><p className="section-label">06 · WALD — The Missing Evidence</p><h2 id="wald-title">What could change the verdict?</h2><p className="muted">Named for Abraham Wald: seek the evidence that may be absent from the data that survived into view, and prioritize what would most change the case.</p>
    <ol className="wald-list">{items.map((item) => <li key={item.id}><div><span className={`information ${item.information_value}`}>{item.information_value} information value</span><h3>{item.question}</h3><p><strong>Missing:</strong> {item.missing_evidence}</p><p className="muted">Why invisible: {item.why_it_may_be_invisible}</p><p><strong>Acquire:</strong> {item.acquisition_action}</p></div><span className="affected">{item.hypotheses_affected.join(", ")}{item.could_change_prime_suspect ? " · can change Prime Suspect" : ""}</span></li>)}</ol>
  </section>;
}

export function FinalResultPanel({ result }: { result: FrozenDashboard["final_result"] }) {
  return <section className="final-result" aria-labelledby="result-title"><p className="section-label">07 · Final result</p><h2 id="result-title">{result.verdict}</h2><span className="provisional">{result.verdict_status} · {percentage(result.confidence)} confidence</span><div className="result-grid"><p><strong>Business impact</strong>{result.business_impact}</p><p><strong>Immediate action</strong>{result.immediate_action}</p><p><strong>Owner to contact</strong>{result.owner_to_contact}</p><p><strong>Confirmation needed</strong>{result.confirmation_needed}</p></div><p className="guardrail">{result.guardrail}</p></section>;
}

export function AuditTrail({ investigation }: { investigation: FrozenDashboard }) {
  const observation = investigation.observed_from_datahub;
  return <section className="section audit-section" aria-labelledby="audit-title"><p className="section-label">08 · Evidence provenance / guardrails</p><h2 id="audit-title">Technical audit trail</h2><div className="audit-grid"><article><h3>Selected provider</h3><p><strong>{investigation.selected_provider}</strong> · {observation.source}</p><p className="muted">ORDER_DETAILS · {observation.platform} · {observation.schema_total} columns · SLA {String(observation.structured_properties["showcase.dataFreshnessSla"] ?? "not recorded")}</p><p className="muted">Escalation: {observation.escalation_contact ?? "not recorded"} · {observation.upstream.total ?? observation.upstream.returned} upstream / {observation.downstream.total ?? observation.downstream.returned} downstream at one hop</p></article><article><h3>Provider attempts</h3><ul>{investigation.provider_attempts.map((attempt) => <li key={`${attempt.provider}-${attempt.status}`}><strong>{attempt.provider}</strong> · {attempt.status === "not_configured" ? "not configured (optional)" : attempt.status} · {attempt.duration_ms} ms{attempt.error ? ` · ${attempt.error}` : ""}</li>)}</ul></article><article><h3>Observed companion asset</h3>{observation.related_assets.map((asset) => <p key={asset.urn}><strong>{asset.name}</strong> · {asset.platform} · SLA {String(asset.structured_properties["showcase.dataFreshnessSla"] ?? "not recorded")} · quality {String(asset.structured_properties["showcase.dataQualityScore"] ?? "not recorded")} · escalation {asset.escalation_contact ?? "not recorded"}</p>)}</article></div>{observation.warning && <p className="warning">{observation.warning}</p>}<ul className="guardrails">{investigation.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul></section>;
}

export function InvestigationNarrative({ investigation }: { investigation: FrozenDashboard }) {
  return <><AnomalyPanel anomalies={investigation.anomalies} /><InitialHypotheses hypotheses={investigation.initial_hypotheses} /><EvidenceBoard evidence={investigation.evidence} matrix={investigation.hypothesis_matrix} /><HypothesisMatrix hypotheses={investigation.initial_hypotheses} matrix={investigation.hypothesis_matrix} updates={investigation.confidence_update} /><PrimeSuspectPanel suspect={investigation.prime_suspect} /><WaldPanel items={investigation.wald} /><FinalResultPanel result={investigation.final_result} /><AuditTrail investigation={investigation} /></>;
}
