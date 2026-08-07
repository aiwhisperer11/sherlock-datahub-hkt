"use client";

import { useEffect, useState } from "react";
import { StatusPill } from "@/components/status-pill";
import { DocumentWritebackPanel } from "@/features/document-writeback/document-writeback-panel";
import { McpSamplePanel } from "@/features/mcp-sample/mcp-sample-panel";
import { fetchFrozenDashboard, type FrozenDashboard } from "@/lib/investigation";
import { InvestigationNarrative } from "./investigation-components";

export function InvestigationDashboard() {
  const [investigation, setInvestigation] = useState<FrozenDashboard>();
  const [error, setError] = useState<string>();

  useEffect(() => {
    fetchFrozenDashboard().then(setInvestigation).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : "Unable to reach Sherlock Engine");
    });
  }, []);

  return (
    <main>
      <header className="case-header">
        <p className="eyebrow">Sherlock · DataHub Agent</p>
        <div className="case-title"><div><h1>The Case of the Frozen Dashboard</h1><p className="muted">Expected → Observed → Gap → Hypotheses → Evidence needed → Confidence update</p></div><div className="case-badges"><span className="scenario">Simulated incident scenario</span>{investigation && <span className="severity high">High severity</span>}</div></div>
      </header>
      {!investigation && !error && <StatusPill state="loading">Connecting to Sherlock Engine…</StatusPill>}
      {investigation && <StatusPill state="success">Backend connected · {investigation.selected_provider} provider selected · provisional investigation</StatusPill>}
      {error && <StatusPill state="error">Backend unavailable · {error}</StatusPill>}
      <McpSamplePanel />
      <DocumentWritebackPanel />
      {investigation && <div className="investigation-flow" aria-label="Frozen dashboard investigation"><InvestigationNarrative investigation={investigation} /></div>}
    </main>
  );
}
