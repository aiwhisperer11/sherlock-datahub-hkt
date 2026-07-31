"use client";

import React, { useEffect, useState } from "react";
import { StatusPill } from "@/components/status-pill";
import { fetchMcpSample, fetchSnapshotSample, type SampleMode, type SampleView } from "@/lib/mcp-sample";

type LoadState = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; data: SampleView };

const FETCHERS: Record<SampleMode, () => Promise<SampleView>> = {
  mcp: fetchMcpSample,
  snapshot: fetchSnapshotSample,
};

const MODE_LABEL: Record<SampleMode, string> = { mcp: "MCP (live)", snapshot: "Snapshot (demo)" };

export function loadingLabel(mode: SampleMode): string {
  return `Fetching ${mode === "mcp" ? "live MCP" : "snapshot"} metadata…`;
}

export function errorLabel(mode: SampleMode, message: string): string {
  return `${mode === "mcp" ? "MCP unavailable" : "Snapshot unavailable"} · ${message}`;
}

export function McpSamplePanel() {
  const [mode, setMode] = useState<SampleMode>("mcp");
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    FETCHERS[mode]()
      .then((data) => {
        if (!cancelled) setState({ status: "ready", data });
      })
      .catch((reason: unknown) => {
        if (!cancelled) setState({ status: "error", message: reason instanceof Error ? reason.message : "Unable to reach Sherlock Engine" });
      });
    return () => {
      cancelled = true;
    };
  }, [mode]);

  return (
    <section className="section mcp-sample-section" aria-labelledby="mcp-sample-title">
      <div className="mcp-sample-head">
        <div>
          <p className="section-label">Live metadata sample</p>
          <h2 id="mcp-sample-title">One real DataHub entity via MCP</h2>
        </div>
        <div className="mode-toggle" role="tablist" aria-label="Metadata source">
          {(Object.keys(MODE_LABEL) as SampleMode[]).map((candidate) => (
            <button
              key={candidate}
              type="button"
              role="tab"
              aria-selected={mode === candidate}
              className={mode === candidate ? "active" : ""}
              onClick={() => setMode(candidate)}
            >
              {MODE_LABEL[candidate]}
            </button>
          ))}
        </div>
      </div>
      <p className="muted mcp-sample-hint">
        {mode === "mcp"
          ? "Fetches one real entity from your local DataHub instance over MCP. No fallback: if this fails, switch to Snapshot manually."
          : "Reuses the reproducible Frozen Dashboard demo fixture — not a live MCP call. Safe to view without a local DataHub instance."}
      </p>

      {state.status === "loading" && <StatusPill state="loading">{loadingLabel(mode)}</StatusPill>}
      {state.status === "error" && <StatusPill state="error">{errorLabel(mode, state.message)}</StatusPill>}
      {state.status === "ready" && <McpSampleBody data={state.data} />}
    </section>
  );
}

export function McpSampleBody({ data }: { data: SampleView }) {
  if (!data.entity || data.entityCount === 0) {
    return (
      <div className="empty-state-block" aria-label="No entity available">
        <SourceBadge mode={data.mode} verified={data.verified} />
        <p className="muted">No entity was returned by this source.</p>
      </div>
    );
  }

  const { entity } = data;
  return (
    <div className="mcp-sample-body">
      <div className="mcp-sample-meta">
        <SourceBadge mode={data.mode} verified={data.verified} />
        {data.capturedAt && <span className="captured-at">Captured {new Date(data.capturedAt).toLocaleString()}</span>}
      </div>
      <div className="mcp-entity-heading">
        <h3>{entity.name}</h3>
        <p className="muted">
          {entity.platform} · {entity.type}
        </p>
        <p className="urn">{entity.urn}</p>
      </div>
      <div className="mcp-field-grid">
        <FieldList label="Schema fields" items={entity.schemaFields} />
        <FieldList label="Owners" items={entity.owners} />
        <FieldList label="Glossary terms" items={entity.glossaryTerms} />
        <FieldList label="Domain" items={entity.domains} />
        <FieldList label="Upstream lineage" items={entity.upstreamUrns} />
        <FieldList label="Downstream lineage" items={entity.downstreamUrns} />
      </div>
      {data.warnings.length > 0 && (
        <ul className="warning-list">
          {data.warnings.map((warning) => (
            <li className="warning" key={warning}>
              {warning}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FieldList({ label, items }: { label: string; items: string[] }) {
  return (
    <div className="mcp-field">
      <h3>{label}</h3>
      {items.length === 0 ? (
        <p className="muted empty-state">None recorded</p>
      ) : (
        <ul>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SourceBadge({ mode, verified }: { mode: SampleMode; verified: boolean }) {
  if (mode === "mcp") {
    return <span className={`source-badge mcp ${verified ? "verified" : "unverified"}`}>MCP · {verified ? "live, verified" : "not verified"}</span>;
  }
  return <span className="source-badge snapshot">Snapshot · demo data, not live</span>;
}
