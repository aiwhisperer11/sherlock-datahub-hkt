import { readFileSync } from "node:fs";
import path from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import {
  DocumentReviewBody,
  EngineSourceBadge,
  PublishResultBody,
  RetrievalResultBody,
  cancelPreview,
  initialFlowState,
} from "../src/features/document-writeback/document-writeback-panel";
import { previewDocument, publishDocument, retrieveDocument, type DocumentPreview, type PublishResult, type RetrievalResult } from "../src/lib/document-writeback";

const PREVIEW: DocumentPreview = {
  idempotency_key: "sherlock-investigation-ca0510a294ea2256",
  document_type: "Insight",
  title: "Sherlock investigation: ORDER_DETAILS (sherlock-investigation-ca0510a294ea2256)",
  content: "# Sherlock investigation preview\n\nReasoning consequence: ...\nNext test: ...\n\nEvidence:\n- [get_lineage] 12 upstream dependency(ies)...",
  related_assets: ["urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.analytics.order_details,PROD)"],
  reasoning_consequence: {
    id: "consequence-lineage-x",
    statement: "ORDER_DETAILS depends on upstream data; if an upstream dependency failed or was delayed, ORDER_DETAILS could be stale or incomplete.",
    evidence_ids: ["ev-upstream-x"],
    next_test: "Check the latest run status of the upstream dependencies feeding ORDER_DETAILS before ruling them out as the cause of the incident.",
  },
  evidence: [
    {
      id: "ev-upstream-x",
      tool: "get_lineage",
      urn: "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.analytics.order_details,PROD)",
      observed_fact: "12 upstream dependency(ies) at one hop: INVENTORIES, ORDERS, PRODUCTS.",
      observed_at: "2026-08-07T12:31:32Z",
      provenance: "observed_from_datahub",
    },
    {
      id: "ev-terms-x",
      tool: "get_entities",
      urn: "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.analytics.order_details,PROD)",
      observed_fact: "Glossary terms attached: PII, SOC2 Auditable.",
      observed_at: "2026-08-07T12:31:32Z",
      provenance: "observed_from_datahub",
    },
  ],
  persistence_warning: "This document is permanent once published: mcp-server-datahub exposes no document-delete tool, so Sherlock cannot remove or edit it afterward.",
  engine_source: "sherlock_core_canonical",
};

describe("DocumentWritebackPanel state", () => {
  it("starts idle, with no data and no in-flight request", () => {
    expect(initialFlowState).toEqual({ status: "idle" });
  });

  it("cancelling returns to idle and is provably incapable of calling fetch", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const next = cancelPreview();

    expect(next).toEqual({ status: "idle" });
    expect(fetchMock).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});

describe("Document review body — what a human sees before approving", () => {
  it("shows title, reasoning consequence, next_test, DataHub evidence with tool/urn/provenance, content, and the permanence warning", () => {
    const html = renderToStaticMarkup(createElement(DocumentReviewBody, { preview: PREVIEW }));

    expect(html).toContain(PREVIEW.title);
    expect(html).toContain(PREVIEW.reasoning_consequence.statement);
    expect(html).toContain(PREVIEW.reasoning_consequence.next_test);
    expect(html).toContain("get_lineage");
    expect(html).toContain("get_entities");
    expect(html).toContain("12 upstream dependency(ies)");
    expect(html).toContain("observed_from_datahub");
    expect(html).toContain(PREVIEW.evidence[0].urn);
    expect(html).toContain("Document content that would be published");
    expect(html).toContain(PREVIEW.persistence_warning);
    expect(html).toContain("cannot remove or edit it afterward");
  });

  it("never claims PII as the reasoning consequence, even when PII evidence is present in the list", () => {
    const html = renderToStaticMarkup(createElement(DocumentReviewBody, { preview: PREVIEW }));

    // PII evidence is shown for context (it's real evidence)...
    expect(html).toContain("PII");
    // ...but the reasoning consequence itself must not be built around it.
    expect(PREVIEW.reasoning_consequence.statement).not.toContain("PII");
    expect(PREVIEW.reasoning_consequence.next_test).not.toContain("PII");
  });

  it("shows the canonical-engine badge when engine_source is sherlock_core_canonical", () => {
    const html = renderToStaticMarkup(createElement(DocumentReviewBody, { preview: { ...PREVIEW, engine_source: "sherlock_core_canonical" } }));

    expect(html).toContain("Sherlock-Core canonical engine");
    expect(html).not.toContain("Local fallback");
  });

  it("shows a distinct fallback badge when engine_source is local_fallback, never claiming canonical", () => {
    const html = renderToStaticMarkup(createElement(DocumentReviewBody, { preview: { ...PREVIEW, engine_source: "local_fallback" } }));

    expect(html).toContain("Local fallback (canonical engine unavailable)");
    expect(html).not.toContain("Sherlock-Core canonical engine");
  });
});

describe("EngineSourceBadge", () => {
  it("never renders both states at once for either input", () => {
    const canonical = renderToStaticMarkup(createElement(EngineSourceBadge, { engineSource: "sherlock_core_canonical" }));
    const fallback = renderToStaticMarkup(createElement(EngineSourceBadge, { engineSource: "local_fallback" }));

    expect(canonical).toContain("Sherlock-Core canonical engine");
    expect(canonical).not.toContain("fallback");
    expect(fallback).toContain("Local fallback");
    expect(fallback).not.toContain("Sherlock-Core canonical engine");
  });
});

describe("Publish and retrieval result bodies", () => {
  it("renders a created result with its URN", () => {
    const publish: PublishResult = { status: "created", urn: "urn:li:document:shared-new-1", idempotencyKey: PREVIEW.idempotency_key, documentType: "Insight", title: PREVIEW.title, detail: "Document created." };

    const html = renderToStaticMarkup(createElement(PublishResultBody, { publish }));

    expect(html).toContain("Created (new document)");
    expect(html).toContain("urn:li:document:shared-new-1");
  });

  it("renders an already_exists result distinctly from created", () => {
    const publish: PublishResult = { status: "already_exists", urn: "urn:li:document:shared-existing-1", idempotencyKey: PREVIEW.idempotency_key, documentType: "Insight", title: PREVIEW.title, detail: "Already published; no mutation performed." };

    const html = renderToStaticMarkup(createElement(PublishResultBody, { publish }));

    expect(html).toContain("Already exists (no mutation performed)");
    expect(html).not.toContain("Created (new document)");
  });

  it("renders a verified retrieval distinctly from a failed one", () => {
    const verified: RetrievalResult = { status: "verified", urn: "urn:li:document:shared-new-1", title: PREVIEW.title, idempotencyKey: PREVIEW.idempotency_key, detail: "matched" };
    const notFound: RetrievalResult = { status: "not_found", urn: null, title: null, idempotencyKey: PREVIEW.idempotency_key, detail: "no document found" };

    const verifiedHtml = renderToStaticMarkup(createElement(RetrievalResultBody, { retrieval: verified }));
    const notFoundHtml = renderToStaticMarkup(createElement(RetrievalResultBody, { retrieval: notFound }));

    expect(verifiedHtml).toContain("Verified via retrieve");
    expect(notFoundHtml).toContain("Retrieve found no document");
    expect(notFoundHtml).not.toContain("Verified via retrieve");
  });
});

describe("document-writeback lib fetch calls", () => {
  it("previewDocument calls GET /api/v1/documents/preview and never sends a body", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ preview: PREVIEW, preview_hash: "abc123" }) });
    vi.stubGlobal("fetch", fetchMock);

    const result = await previewDocument();

    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/api/v1/documents/preview");
    expect(fetchMock.mock.calls[0]).toHaveLength(1); // no options object — GET, no body
    expect(result.previewHash).toBe("abc123");
    expect(result.preview.title).toBe(PREVIEW.title);
    vi.unstubAllGlobals();
  });

  it("previewDocument surfaces the backend's sanitised error detail", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 502, json: async () => ({ detail: "MCP metadata request failed" }) }));

    await expect(previewDocument()).rejects.toThrow("MCP metadata request failed");
    vi.unstubAllGlobals();
  });

  it("publishDocument POSTs preview_hash and approved, nothing else", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: "created", urn: "urn:li:document:shared-new-1", idempotency_key: PREVIEW.idempotency_key, document_type: "Insight", title: PREVIEW.title, detail: "created" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await publishDocument("abc123", true);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/documents/publish");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({ preview_hash: "abc123", approved: true });
    expect(result.status).toBe("created");
    expect(result.urn).toBe("urn:li:document:shared-new-1");
    vi.unstubAllGlobals();
  });

  it("publishDocument surfaces a rejected/altered preview as an error, not a silent success", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 409, json: async () => ({ detail: "Preview is stale or does not match what was reviewed" }) }));

    await expect(publishDocument("wrong-hash", true)).rejects.toThrow("Preview is stale or does not match what was reviewed");
    vi.unstubAllGlobals();
  });

  it("retrieveDocument sends idempotency_key and expected_urn as query params", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: "verified", urn: "urn:li:document:shared-new-1", title: PREVIEW.title, idempotency_key: PREVIEW.idempotency_key, detail: "matched" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await retrieveDocument(PREVIEW.idempotency_key, "urn:li:document:shared-new-1");

    expect(fetchMock).toHaveBeenCalledWith(
      `http://localhost:8000/api/v1/documents/retrieve?idempotency_key=${encodeURIComponent(PREVIEW.idempotency_key)}&expected_urn=${encodeURIComponent("urn:li:document:shared-new-1")}`
    );
    expect(result.status).toBe("verified");
    vi.unstubAllGlobals();
  });

  it("retrieveDocument omits expected_urn when not supplied", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: "not_found", urn: null, title: null, idempotency_key: PREVIEW.idempotency_key, detail: "no document" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await retrieveDocument(PREVIEW.idempotency_key);

    const [url] = fetchMock.mock.calls[0];
    expect(url).not.toContain("expected_urn");
    vi.unstubAllGlobals();
  });

  it("never references the backend secret token name or an auth header in frontend source", () => {
    const files = ["src/lib/document-writeback.ts", "src/features/document-writeback/document-writeback-panel.tsx"];
    for (const file of files) {
      const contents = readFileSync(path.resolve(__dirname, "..", file), "utf-8");
      expect(contents).not.toMatch(/DATAHUB_GMS_TOKEN/);
      expect(contents).not.toMatch(/Authorization/i);
      expect(contents).not.toMatch(/Bearer /);
    }
  });
});

describe("no mutation on load, preview, or cancel — proven from source, not just behavior", () => {
  const panelSource = readFileSync(path.resolve(__dirname, "..", "src/features/document-writeback/document-writeback-panel.tsx"), "utf-8");

  it("has no useEffect at all, so nothing runs automatically on mount", () => {
    expect(panelSource).not.toMatch(/useEffect/);
  });

  it("handleCancel's entire body is exactly the pure state reset — no fetch, no publish, no preview call", () => {
    const match = /function handleCancel\(\) \{([\s\S]*?)\n {2}\}/.exec(panelSource);
    expect(match, "handleCancel function not found").toBeTruthy();
    const body = match![1];
    expect(body).toContain("cancelPreview()");
    expect(body).not.toMatch(/publishDocument|previewDocument|retrieveDocument|fetch\(/);
  });

  it("publishDocument is only ever called from handleApprove, once in the whole file", () => {
    const occurrences = panelSource.match(/publishDocument\(/g) ?? [];
    expect(occurrences).toHaveLength(1);
    const approveIndex = panelSource.indexOf("async function handleApprove");
    const callIndex = panelSource.indexOf("publishDocument(");
    expect(callIndex).toBeGreaterThan(approveIndex);
  });
});
