import { apiUrl, fetchFrozenDashboard, readErrorDetail, type DataHubObservation } from "./investigation";

export type SampleMode = "mcp" | "snapshot";

/** Mirrors ORDER_DETAILS_URN in sherlock/connectors/datahub/provider.py. The live
 * metadata-context endpoint only supports this URN today — see UnsupportedMetadataUrnError. */
const ORDER_DETAILS_URN = "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.analytics.order_details,PROD)";

/** The provenance the backend actually used to answer, independent of which UI tab was clicked. */
export type MetadataSource = "mcp" | "graphql" | "snapshot";

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
  /** Which tab/fetcher was requested (UI intent) — not a provenance claim. */
  mode: SampleMode;
  /** The backend's real, reported provenance. Never inferred from `mode`: a "mcp" tab request
   * can legitimately come back with source "graphql" or "snapshot" under auto fallback. */
  source: MetadataSource;
  /** True only when source is "mcp" or "graphql". Distinct from any notion of "verified". */
  live: boolean;
  entityCount: number;
  /** From observation.captured_at: when the provider normalised this evidence. */
  capturedAt: string | null;
  /** From the endpoint's top-level retrieved_at: when this HTTP request resolved. Null for the
   * snapshot path, which is served via the frozen-dashboard endpoint and has no request-time field. */
  retrievedAt: string | null;
  warnings: string[];
  entity: SampleEntity | null;
};

type MetadataContextApiResponse = {
  entity_urn: string;
  mode: string;
  source: MetadataSource;
  live: boolean;
  retrieved_at: string;
  observation: DataHubObservation;
  provider_attempts: { provider: string; status: string; duration_ms: number; error?: string | null }[];
};

/** Derives an entity type from a DataHub urn (e.g. "urn:li:dataset:(...)" -> "DATASET"). Never fabricates a type. */
export function entityTypeFromUrn(urn: string): string {
  const match = /^urn:li:([a-zA-Z]+):/.exec(urn);
  return match ? match[1].toUpperCase() : "UNKNOWN";
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
    domains: [], // Not present in DataHubObservation; not fabricated.
    upstreamUrns: observation.upstream.entities.map((entity) => entity.urn),
    downstreamUrns: observation.downstream.entities.map((entity) => entity.urn),
  };
}

/**
 * Live read via GET /api/v1/metadata/context?urn=ORDER_DETAILS_URN. Reports the backend's
 * actual source and live flag — never assumes "mcp" just because this is the live tab; under
 * SHERLOCK_METADATA_MODE=auto the backend may honestly answer from graphql or snapshot instead.
 * No fallback here either: if this fails, the caller switches to Snapshot manually.
 */
export async function fetchLiveMetadataContext(): Promise<SampleView> {
  const response = await fetch(`${apiUrl}/api/v1/metadata/context?urn=${encodeURIComponent(ORDER_DETAILS_URN)}`);
  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail ?? `Engine responded with ${response.status}`);
  }
  const body = (await response.json()) as MetadataContextApiResponse;
  return {
    mode: "mcp",
    source: body.source,
    live: body.live,
    entityCount: 1,
    capturedAt: body.observation.captured_at ?? null,
    retrievedAt: body.retrieved_at,
    warnings: body.observation.warning ? [body.observation.warning] : [],
    entity: toSampleEntity(body.observation),
  };
}

/**
 * Public demo mode: reuses the existing `/api/v1/demo/frozen-dashboard` sandbox endpoint
 * instead of a second snapshot endpoint, so the data model is not duplicated. Always
 * reports source "snapshot" / live=false since this is fixture data, never live DataHub metadata.
 */
export async function fetchSnapshotSample(): Promise<SampleView> {
  const dashboard = await fetchFrozenDashboard();
  const observation = dashboard.observed_from_datahub;
  return {
    mode: "snapshot",
    source: "snapshot",
    live: false,
    entityCount: observation ? 1 : 0,
    capturedAt: observation?.captured_at ?? null,
    retrievedAt: null,
    warnings: observation?.warning ? [observation.warning] : [],
    entity: observation ? toSampleEntity(observation) : null,
  };
}
