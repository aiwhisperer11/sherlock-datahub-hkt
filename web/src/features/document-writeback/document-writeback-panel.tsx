"use client";

import React, { useState } from "react";
import { StatusPill } from "@/components/status-pill";
import {
  type DocumentPreview,
  type EngineSource,
  type PublishResult,
  type RetrievalResult,
  previewDocument,
  publishDocument,
  retrieveDocument,
} from "@/lib/document-writeback";

export type FlowState =
  | { status: "idle" }
  | { status: "loading-preview" }
  | { status: "preview-error"; message: string }
  | { status: "reviewing"; preview: DocumentPreview; previewHash: string }
  | { status: "publishing"; preview: DocumentPreview; previewHash: string }
  | { status: "publish-error"; message: string; preview: DocumentPreview; previewHash: string }
  | { status: "verifying"; preview: DocumentPreview; publish: PublishResult }
  | { status: "verified"; preview: DocumentPreview; publish: PublishResult; retrieval: RetrievalResult }
  | { status: "verify-error"; message: string; preview: DocumentPreview; publish: PublishResult };

/** The only state the panel ever starts in. There is no mount-time effect hook
 * anywhere in this file: mounting this component makes zero network calls,
 * mutating or otherwise. */
export const initialFlowState: FlowState = { status: "idle" };

/** Pure — takes no dependency on fetch/publish/preview at all. Cancelling can
 * never reach a network call because this function has no way to make one. */
export function cancelPreview(): FlowState {
  return { status: "idle" };
}

function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : "Unable to reach Sherlock Engine";
}

export function DocumentWritebackPanel() {
  const [state, setState] = useState<FlowState>(initialFlowState);

  async function handleGeneratePreview() {
    setState({ status: "loading-preview" });
    try {
      const { preview, previewHash } = await previewDocument();
      setState({ status: "reviewing", preview, previewHash });
    } catch (reason: unknown) {
      setState({ status: "preview-error", message: errorMessage(reason) });
    }
  }

  function handleCancel() {
    setState(cancelPreview());
  }

  async function handleApprove() {
    if (state.status !== "reviewing") return;
    const { preview, previewHash } = state;
    setState({ status: "publishing", preview, previewHash });
    let publish: PublishResult;
    try {
      publish = await publishDocument(previewHash, true);
    } catch (reason: unknown) {
      setState({ status: "publish-error", message: errorMessage(reason), preview, previewHash });
      return;
    }
    setState({ status: "verifying", preview, publish });
    try {
      const retrieval = await retrieveDocument(publish.idempotencyKey, publish.urn);
      setState({ status: "verified", preview, publish, retrieval });
    } catch (reason: unknown) {
      setState({ status: "verify-error", message: errorMessage(reason), preview, publish });
    }
  }

  return (
    <section className="section document-writeback-section" aria-labelledby="document-writeback-title">
      <p className="section-label">Publish investigation to DataHub</p>
      <h2 id="document-writeback-title">Discover → evidence → reasoning → preview → approval → publish → retrieve</h2>
      <p className="muted">
        Reads ORDER_DETAILS context live over MCP and drafts a document. Nothing is written to DataHub until you review it below and explicitly approve.
        Reading MCP context and, if configured, running the canonical Sherlock-Core engine together can take <strong>50-90 seconds</strong> — that is the
        real cost of a live MCP round trip plus an LLM call, not a stalled request.
      </p>

      {state.status === "idle" && (
        <div className="mode-toggle">
          <button type="button" className="active" onClick={handleGeneratePreview}>
            Generate preview
          </button>
        </div>
      )}

      {state.status === "loading-preview" && <StatusPill state="loading">Reading DataHub context and running Sherlock-Core (typically 50-90s)…</StatusPill>}
      {state.status === "preview-error" && (
        <>
          <StatusPill state="error">Preview unavailable · {state.message}</StatusPill>
          <div className="mode-toggle">
            <button type="button" className="active" onClick={handleGeneratePreview}>
              Try again
            </button>
          </div>
        </>
      )}

      {state.status === "reviewing" && (
        <>
          <DocumentReviewBody preview={state.preview} />
          <p className="muted">
            This exact preview stays approvable for <strong>15 minutes</strong> (server-side cache, cleared on backend restart). After that, Approve &amp;
            publish will fail with a 409 and you&apos;ll need to generate a new preview.
          </p>
          <div className="mode-toggle" role="group" aria-label="Review actions">
            <button type="button" className="active" onClick={handleApprove}>
              Approve &amp; publish
            </button>
            <button type="button" onClick={handleCancel}>
              Cancel
            </button>
          </div>
        </>
      )}

      {state.status === "publishing" && (
        <>
          <DocumentReviewBody preview={state.preview} />
          <StatusPill state="loading">Publishing (approved)…</StatusPill>
        </>
      )}

      {state.status === "publish-error" && (
        <>
          <DocumentReviewBody preview={state.preview} />
          <StatusPill state="error">Publish failed · {state.message}</StatusPill>
          <div className="mode-toggle">
            <button type="button" onClick={handleCancel}>
              Cancel
            </button>
          </div>
        </>
      )}

      {state.status === "verifying" && (
        <>
          <PublishResultBody publish={state.publish} />
          <StatusPill state="loading">Verifying via retrieve…</StatusPill>
        </>
      )}

      {state.status === "verified" && (
        <>
          <PublishResultBody publish={state.publish} />
          <RetrievalResultBody retrieval={state.retrieval} />
        </>
      )}

      {state.status === "verify-error" && (
        <>
          <PublishResultBody publish={state.publish} />
          <StatusPill state="error">Verification failed · {state.message}</StatusPill>
        </>
      )}
    </section>
  );
}

/** Never lets a local fallback read as the canonical engine's conclusion. */
export function EngineSourceBadge({ engineSource }: { engineSource: EngineSource }) {
  if (engineSource === "sherlock_core_canonical") {
    return <span className="source-badge mcp verified">Sherlock-Core canonical engine</span>;
  }
  return <span className="source-badge snapshot">Local fallback (canonical engine unavailable)</span>;
}

export function DocumentReviewBody({ preview }: { preview: DocumentPreview }) {
  return (
    <div className="document-review-body" aria-label="Document preview, not yet published">
      <div className="mcp-entity-heading">
        <h3>{preview.title}</h3>
        <p className="muted">{preview.document_type}</p>
        <EngineSourceBadge engineSource={preview.engine_source} />
      </div>

      <p>
        <strong>Reasoning consequence:</strong> {preview.reasoning_consequence.statement}
      </p>
      <p>
        <strong>Next test:</strong> {preview.reasoning_consequence.next_test}
      </p>

      <h3>DataHub evidence ({preview.evidence.length})</h3>
      <div className="evidence-list">
        {preview.evidence.map((item) => (
          <div className="evidence-item" key={item.id}>
            <div className="evidence-meta">
              <span className="provenance observed_from_datahub">{item.provenance}</span>
              <span className="muted">{item.tool}</span>
            </div>
            <p>{item.observed_fact}</p>
            <p className="muted urn">{item.urn}</p>
            <p className="muted">Observed {new Date(item.observed_at).toLocaleString()}</p>
          </div>
        ))}
      </div>

      <h3>Document content that would be published</h3>
      <pre className="document-content-preview">{preview.content}</pre>

      <p className="warning">{preview.persistence_warning}</p>
    </div>
  );
}

export function PublishResultBody({ publish }: { publish: PublishResult }) {
  return (
    <div className="publish-result-body" aria-label="Publish result">
      <p>
        <strong>Status:</strong> {publish.status === "created" ? "Created (new document)" : "Already exists (no mutation performed)"}
      </p>
      <p className="urn">
        <strong>URN:</strong> {publish.urn}
      </p>
      <p className="muted">{publish.detail}</p>
    </div>
  );
}

export function RetrievalResultBody({ retrieval }: { retrieval: RetrievalResult }) {
  if (retrieval.status === "verified") {
    return (
      <div className="retrieval-result-body" aria-label="Retrieval verification">
        <StatusPill state="success">Verified via retrieve · URN, title, and idempotency marker matched</StatusPill>
        <p className="urn">{retrieval.urn}</p>
      </div>
    );
  }
  return (
    <div className="retrieval-result-body" aria-label="Retrieval verification">
      <StatusPill state="error">
        {retrieval.status === "not_found" ? "Retrieve found no document" : "Retrieve found a mismatch"} · {retrieval.detail}
      </StatusPill>
    </div>
  );
}
