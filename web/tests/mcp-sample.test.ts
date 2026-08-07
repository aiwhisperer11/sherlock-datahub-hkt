import { readFileSync } from "node:fs";
import path from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { McpSampleBody, errorLabel, loadingLabel } from "../src/features/mcp-sample/mcp-sample-panel";
import { entityTypeFromUrn, fetchLiveMetadataContext, type SampleView } from "../src/lib/mcp-sample";

const readyEntity: SampleView = {
  mode: "mcp",
  source: "mcp",
  live: true,
  entityCount: 1,
  capturedAt: "2026-07-31T16:36:00Z",
  retrievedAt: "2026-08-06T16:09:38Z",
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

  it("renders real MCP entity metadata with a live MCP badge", () => {
    const html = renderToStaticMarkup(createElement(McpSampleBody, { data: readyEntity }));

    expect(html).toContain("addresses");
    expect(html).toContain("dbt");
    expect(html).toContain("DATASET");
    expect(html).toContain("urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.order_entry_db.order_entry.addresses,PROD)");
    expect(html).toContain("address_id");
    expect(html).toContain("Data Platform Team");
    expect(html).toContain("PII");
    expect(html).toContain("MCP · Live");
  });

  it("labels a graphql-sourced response as GraphQL, never as MCP, even on the mcp tab", () => {
    const graphqlData: SampleView = { ...readyEntity, mode: "mcp", source: "graphql", live: true };

    const html = renderToStaticMarkup(createElement(McpSampleBody, { data: graphqlData }));

    expect(html).toContain("GraphQL · Live");
    expect(html).not.toContain("MCP · Live");
  });

  it("labels snapshot data distinctly and never claims it is live, even on the mcp tab", () => {
    const snapshotData: SampleView = { ...readyEntity, mode: "mcp", source: "snapshot", live: false };

    const html = renderToStaticMarkup(createElement(McpSampleBody, { data: snapshotData }));

    expect(html).toContain("Snapshot · Frozen (not live)");
    expect(html).not.toContain("MCP · Live");
    expect(html).not.toContain("GraphQL · Live");
  });

  it("renders an empty field distinctly, without treating it as an error", () => {
    const data: SampleView = { ...readyEntity, entity: { ...readyEntity.entity!, owners: [], domains: [] } };

    const html = renderToStaticMarkup(createElement(McpSampleBody, { data }));

    expect(html).toContain("None recorded");
    expect(html).toContain("addresses");
  });

  it("renders a distinct empty state when the source returned no entity at all", () => {
    const data: SampleView = { mode: "mcp", source: "mcp", live: true, entityCount: 0, capturedAt: null, retrievedAt: null, warnings: [], entity: null };

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

  it("calls the URN-parametrised metadata-context endpoint, with no auth header attached client-side", async () => {
    const payload = {
      entity_urn: "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.analytics.order_details,PROD)",
      mode: "mcp",
      source: "mcp",
      live: true,
      retrieved_at: "2026-08-06T16:09:38Z",
      observation: {
        urn: "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.analytics.order_details,PROD)",
        name: "ORDER_DETAILS",
        platform: "snowflake",
        schema_fields: [{ field_path: "order_id", native_data_type: "NUMBER(38,0)" }],
        structured_properties: {},
        owners: ["David Kim"],
        tags: [],
        glossary_terms: ["PII"],
        upstream: { total: 0, returned: 0, entities: [] },
        downstream: { total: 0, returned: 0, entities: [] },
        consumers: [],
        related_assets: [],
        source: "mcp",
        captured_at: "2026-07-31T16:36:00Z",
        warning: null,
      },
      provider_attempts: [{ provider: "mcp", status: "succeeded", duration_ms: 900 }],
    };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => payload });
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchLiveMetadataContext();

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/metadata/context?urn=urn%3Ali%3Adataset%3A(urn%3Ali%3AdataPlatform%3Asnowflake%2Cb2fd91.order_entry_db.analytics.order_details%2CPROD)"
    );
    expect(fetchMock.mock.calls[0]).toHaveLength(1);
    expect(result.source).toBe("mcp");
    expect(result.live).toBe(true);
    expect(result.retrievedAt).toBe("2026-08-06T16:09:38Z");
    expect(result.capturedAt).toBe("2026-07-31T16:36:00Z");
  });

  it("surfaces the backend's sanitised error detail without inventing one", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 502, json: async () => ({ detail: "MCP metadata request failed" }) })
    );

    await expect(fetchLiveMetadataContext()).rejects.toThrow("MCP metadata request failed");
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
