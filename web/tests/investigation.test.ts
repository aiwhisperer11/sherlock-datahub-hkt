import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { InvestigationNarrative } from "../src/features/investigation/investigation-components";
import { apiUrl, fetchFrozenDashboard, type FrozenDashboard } from "../src/lib/investigation";

const investigation = {
  id: "investigation-frozen-dashboard", title: "The Case of the Frozen Dashboard", simulated_incident_input: ["SIMULATED INCIDENT INPUT: dashboard missed update"],
  simulated_telemetry: [], observed_from_datahub: { urn: "urn:order", name: "ORDER_DETAILS", platform: "snowflake", schema_total: 55, schema_fields: [], structured_properties: { showcase_dataFreshnessSla: "Daily" }, owners: [], tags: [], glossary_terms: [], upstream: { returned: 1, entities: [] }, downstream: { returned: 1, entities: [] }, consumers: [], related_assets: [], source: "local_snapshot_unverified" },
  anomalies: [{ id: "A1", type: "missing_update", title: "Dashboard missed its expected update", expected: "24 hours", observed: "31 hours", gap: "7 hours", severity: "high", provenance: [], why_it_matters: "Investigation starts here." }],
  initial_hypotheses: [{ id: "H1", statement: "dbt transformation delayed", prior_confidence: .45, evidence_needed: ["dbt logs"], status: "open" }],
  evidence: [{ id: "E1", statement: "Simulated dashboard is stale", provenance: "simulated_incident_input", reliability: .65, limitations: ["Synthetic telemetry"] }],
  hypothesis_matrix: [{ hypothesis_id: "H1", evidence_id: "E1", relationship: "supports", weight: .8, rationale: "Supports H1" }, { hypothesis_id: "H1", evidence_id: "logs", relationship: "missing", weight: 1, rationale: "Need logs" }],
  confidence_update: [{ hypothesis_id: "H1", prior_confidence: .45, factors: [], final_confidence: .617, explanation: "Evidence update." }],
  prime_suspect: { hypothesis_id: "H1", label: "The dbt transformation producing ORDER_DETAILS", status: "provisional", confidence: .617, why_selected: "Stage gap", strongest_supporting_evidence: "ORDER_DETAILS stale", strongest_counterevidence: "No logs", what_would_change_the_verdict: "Successful dbt run" },
  wald: [{ id: "W1", question: "Did dbt complete?", missing_evidence: "dbt logs", why_it_may_be_invisible: "Outside DataHub", hypotheses_affected: ["H1"], information_value: "high", acquisition_action: "Inspect job", could_change_prime_suspect: true }],
  final_result: { verdict: "dbt is the Prime Suspect", verdict_status: "provisional", confidence: .617, affected_assets: ["ORDER_DETAILS"], business_impact: "Stale dashboard", immediate_action: "Inspect dbt", owner_to_contact: "Ian Chen", confirmation_needed: "Logs", guardrail: "Not a confirmed root cause." },
  derived_by_sherlock: [], limitations: ["No logs"], provider_attempts: [{ provider: "mcp", status: "not_configured", duration_ms: 0, error: "MCP requires DATAHUB_GMS_TOKEN" }, { provider: "snapshot", status: "succeeded", duration_ms: 0 }], selected_provider: "snapshot", conclusion: "Provisional", recommended_action: "Inspect dbt",
} satisfies FrozenDashboard;

describe("Sherlock Engine client", () => {
  it("uses the local engine URL by default", () => {
    expect(apiUrl).toBe("http://localhost:8000");
  });

  it("returns the frozen-dashboard investigation response", async () => {
    const payload = { id: "investigation-frozen-dashboard", title: "The Case of the Frozen Dashboard" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => payload }));

    await expect(fetchFrozenDashboard()).resolves.toEqual(payload);
    expect(fetch).toHaveBeenCalledWith("http://localhost:8000/api/v1/demo/frozen-dashboard");
  });

  it("renders the Sherlock investigation narrative rather than equal confidence cards", () => {
    const screen = renderToStaticMarkup(createElement(InvestigationNarrative, { investigation }));

    expect(screen).toContain("Expectation violated");
    expect(screen).toContain("Initial hypotheses");
    expect(screen).toContain("Hypothesis matrix");
    expect(screen).toContain("Prime suspect");
    expect(screen).toContain("WALD — The Missing Evidence");
    expect(screen).toContain("Final result");
    expect(screen).toContain("Technical audit trail");
    expect(screen).toContain("62%");
    expect(screen).toContain("not configured (optional)");
    expect(screen).not.toContain("40%");
  });
});
