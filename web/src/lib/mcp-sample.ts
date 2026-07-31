import { apiUrl, fetchFrozenDashboard, readErrorDetail, type DataHubObservation } from "./investigation";

export type SampleMode = "mcp" | "snapshot";

export type SampleEntity = {
  urn: string;
  type: string;
  name: string;
  platform: string;
  schemaFields: string[];
  owners: string[];
  glossaryTerms: string[];
  domains: string[];
  upstreamUrns: string[];
  downstreamUrns: string[];
};

export type SampleView = {
  mode: SampleMode;
  verified: boolean;
  entityCount: number;
  capturedAt: string | null;
  warnings: string[];
  entity: SampleEntity | null;
};

type McpSampleApiResponse = {
  source_mode: "mcp";
  source_verified: boolean;
  entity_count: number;
  entity: {
    urn: string;
    type: string;
    name: string;
    platform: string;
    schema_fields: string[];
    owners: string[];
    glossary_terms: string[];
    domains: string[];
    upstream_urns: string[];
    downstream_urns: string[];
  } | null;
  captured_at?: string | null;
  warnings: string[];
};

/** Derives an entity type from a DataHub urn (e.g. "urn:li:dataset:(...)" -> "DATASET"). Never fabricates a type. */
export function entityTypeFromUrn(urn: string): string {
  const match = /^urn:li:([a-zA-Z]+):/.exec(urn);
  return match ? match[1].toUpperCase() : "UNKNOWN";
}

/** Live read-only MCP sample. Never falls back to snapshot or GraphQL on failure. */
export async function fetchMcpSample(): Promise<SampleView> {
  const response = await fetch(`${apiUrl}/api/v1/metadata/mcp/sample`);
  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail ?? `Engine responded with ${response.status}`);
  }
  const body = (await response.json()) as McpSampleApiResponse;
  return {
    mode: "mcp",
    verified: body.source_verified,
    entityCount: body.entity_count,
    capturedAt: body.captured_at ?? null,
    warnings: body.warnings,
    entity:
      body.entity_count > 0 && body.entity
        ? {
            urn: body.entity.urn,
            type: body.entity.type,
            name: body.entity.name,
            platform: body.entity.platform,
            schemaFields: body.entity.schema_fields,
            owners: body.entity.owners,
            glossaryTerms: body.entity.glossary_terms,
            domains: body.entity.domains,
            upstreamUrns: body.entity.upstream_urns,
            downstreamUrns: body.entity.downstream_urns,
          }
        : null,
  };
}

function toSampleEntity(observation: DataHubObservation): SampleEntity {
  return {
    urn: observation.urn,
    type: entityTypeFromUrn(observation.urn),
    name: observation.name,
    platform: observation.platform,
    schemaFields: observation.schema_fields.map((field) => field.field_path),
    owners: observation.owners,
    glossaryTerms: observation.glossary_terms,
    domains: [], // Not present in the snapshot fixture or its DataHubObservation model; not fabricated.
    upstreamUrns: observation.upstream.entities.map((entity) => entity.urn),
    downstreamUrns: observation.downstream.entities.map((entity) => entity.urn),
  };
}

/**
 * Public demo mode: reuses the existing `/api/v1/demo/frozen-dashboard` sandbox endpoint
 * instead of a second snapshot endpoint, so the data model is not duplicated. Always
 * reports verified=false since this is fixture data, never live DataHub metadata.
 */
export async function fetchSnapshotSample(): Promise<SampleView> {
  const dashboard = await fetchFrozenDashboard();
  const observation = dashboard.observed_from_datahub;
  return {
    mode: "snapshot",
    verified: false,
    entityCount: observation ? 1 : 0,
    capturedAt: observation?.captured_at ?? null,
    warnings: observation?.warning ? [observation.warning] : [],
    entity: observation ? toSampleEntity(observation) : null,
  };
}
