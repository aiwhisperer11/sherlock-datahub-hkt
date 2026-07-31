import { readFileSync } from "node:fs";
import path from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { McpSampleBody, errorLabel, loadingLabel } from "../src/features/mcp-sample/mcp-sample-panel";
import { entityTypeFromUrn, fetchMcpSample, type SampleView } from "../src/lib/mcp-sample";

const readyEntity: SampleView = {
  mode: "mcp",
  verified: true,
  entityCount: 1,
  capturedAt: "2026-07-31T16:36:00Z",
  warnings: [],
  entity: {
    urn: "urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.order_entry_db.order_entry.addresses,PROD)",
    type: "DATASET",
    name: "addresses",
    platform: "dbt",
    schemaFields: ["address_id", "zipcode"],
    owners: ["Data Platform Team"],
    glossaryTerms: ["PII"],
    domains: ["Data Platform Team"],
    upstreamUrns: ["urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.order_entry.addresses,PROD)"],
    downstreamUrns: [],
  },
};

describe("MCP sample metadata", () => {
  it("derives an entity type from a urn instead of fabricating one", () => {
    expect(entityTypeFromUrn("urn:li:dataset:(urn:li:dataPlatform:dbt,x,PROD)")).toBe("DATASET");
    expect(entityTypeFromUrn("not-a-urn")).toBe("UNKNOWN");
  });

  it("renders real MCP entity metadata with a verified live badge", () => {
    const html = renderToStaticMarkup(createElement(McpSampleBody, { data: readyEntity }));

    expect(html).toContain("addresses");
    expect(html).toContain("dbt");
    expect(html).toContain("DATASET");
    expect(html).toContain("urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.order_entry_db.order_entry.addresses,PROD)");
    expect(html).toContain("address_id");
    expect(html).toContain("Data Platform Team");
    expect(html).toContain("PII");
    expect(html).toContain("MCP");
    expect(html).toContain("live, verified");
  });

  it("labels snapshot data distinctly and never claims it is live", () => {
    const snapshotData: SampleView = { ...readyEntity, mode: "snapshot", verified: false };

    const html = renderToStaticMarkup(createElement(McpSampleBody, { data: snapshotData }));

    expect(html).toContain("Snapshot");
    expect(html).toContain("demo data, not live");
    expect(html).not.toContain("live, verified");
  });

  it("renders an empty field distinctly, without treating it as an error", () => {
    const data: SampleView = { ...readyEntity, entity: { ...readyEntity.entity!, owners: [], domains: [] } };

    const html = renderToStaticMarkup(createElement(McpSampleBody, { data }));

    expect(html).toContain("None recorded");
    expect(html).toContain("addresses");
  });

  it("renders a distinct empty state when the source returned no entity at all", () => {
    const data: SampleView = { mode: "mcp", verified: true, entityCount: 0, capturedAt: null, warnings: [], entity: null };

    const html = renderToStaticMarkup(createElement(McpSampleBody, { data }));

    expect(html).toContain("No entity was returned");
    expect(html).not.toContain("None recorded");
  });

  it("labels loading and error states per active source", () => {
    expect(loadingLabel("mcp")).toContain("live MCP");
    expect(loadingLabel("snapshot")).toContain("snapshot");
    expect(errorLabel("mcp", "MCP requires DATAHUB_GMS_TOKEN")).toContain("MCP unavailable");
    expect(errorLabel("snapshot", "boom")).toContain("Snapshot unavailable");
  });

  it("calls only the Sherlock backend, with no auth header attached client-side", async () => {
    const payload = {
      source_mode: "mcp",
      source_verified: true,
      entity_count: 1,
      entity: {
        urn: "urn:li:dataset:(x)",
        type: "DATASET",
        name: "x",
        platform: "dbt",
        schema_fields: [],
        owners: [],
        glossary_terms: [],
        domains: [],
        upstream_urns: [],
        downstream_urns: [],
      },
      captured_at: "2026-07-31T16:36:00Z",
      warnings: [],
    };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => payload });
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchMcpSample();

    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/api/v1/metadata/mcp/sample");
    expect(fetchMock.mock.calls[0]).toHaveLength(1);
    expect(result.mode).toBe("mcp");
    expect(result.verified).toBe(true);
  });

  it("surfaces the backend's sanitised error detail without inventing one", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 502, json: async () => ({ detail: "MCP requires DATAHUB_GMS_TOKEN" }) })
    );

    await expect(fetchMcpSample()).rejects.toThrow("MCP requires DATAHUB_GMS_TOKEN");
  });

  it("never references the backend secret token name or an auth header in frontend source", () => {
    const files = ["src/lib/mcp-sample.ts", "src/features/mcp-sample/mcp-sample-panel.tsx", "src/lib/investigation.ts"];
    for (const file of files) {
      const contents = readFileSync(path.resolve(__dirname, "..", file), "utf-8");
      expect(contents).not.toMatch(/DATAHUB_GMS_TOKEN/);
      expect(contents).not.toMatch(/Authorization/i);
      expect(contents).not.toMatch(/Bearer /);
    }
  });
});
