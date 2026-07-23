"use client";

import { useEffect, useState } from "react";
import { StatusPill } from "@/components/status-pill";
import { fetchStalePipeline, type Investigation } from "@/lib/investigation";
import { AffectedAssets, EvidenceList, HypothesisList, IncidentCard, RecommendationCard } from "./investigation-components";

export function InvestigationDashboard() {
  const [investigation, setInvestigation] = useState<Investigation>();
  const [error, setError] = useState<string>();

  useEffect(() => {
    fetchStalePipeline().then(setInvestigation).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : "Unable to reach Sherlock Engine");
    });
  }, []);

  return (
    <main>
      <p className="eyebrow">Sherlock · DataHub Agent</p>
      <h1>The Case of the Stale Pipeline</h1>
      <p className="muted">An explainable investigation of silent freshness degradation.</p>
      {!investigation && !error && <StatusPill state="loading">Connecting to Sherlock Engine…</StatusPill>}
      {investigation && <StatusPill state="success">Backend connected · sandbox investigation loaded</StatusPill>}
      {error && <StatusPill state="error">Backend unavailable · {error}</StatusPill>}
      {investigation && <section className="grid" aria-label="Investigation details">
        <IncidentCard investigation={investigation} />
        <AffectedAssets assets={investigation.assets} />
        <HypothesisList hypotheses={investigation.hypotheses} />
        <EvidenceList evidence={investigation.evidence} />
        <RecommendationCard investigation={investigation} />
      </section>}
    </main>
  );
}
