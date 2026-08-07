import { apiUrl, readErrorDetail } from "./investigation";

export type DataHubEvidence = {
  id: string;
  tool: string;
  urn: string;
  observed_fact: string;
  observed_at: string;
  provenance: "observed_from_datahub";
};

export type ReasoningConsequence = {
  id: string;
  statement: string;
  evidence_ids: string[];
  next_test: string;
};

/** Which source produced reasoning_consequence/content — never inferred, always
 * reported by the backend, so the UI never presents a local fallback as the
 * canonical Sherlock-Core engine's conclusion. */
export type EngineSource = "sherlock_core_canonical" | "local_fallback";

export type DocumentPreview = {
  idempotency_key: string;
  document_type: string;
  title: string;
  content: string;
  related_assets: string[];
  reasoning_consequence: ReasoningConsequence;
  evidence: DataHubEvidence[];
  persistence_warning: string;
  engine_source: EngineSource;
};

export type PreviewResponse = { preview: DocumentPreview; previewHash: string };

export type PublishStatus = "created" | "already_exists";
export type PublishResult = {
  status: PublishStatus;
  urn: string;
  idempotencyKey: string;
  documentType: string;
  title: string;
  detail: string;
};

export type RetrievalStatus = "verified" | "not_found" | "mismatch";
export type RetrievalResult = {
  status: RetrievalStatus;
  urn: string | null;
  title: string | null;
  idempotencyKey: string;
  detail: string;
};

type PreviewApiResponse = { preview: DocumentPreview; preview_hash: string };
type PublishApiResponse = { status: PublishStatus; urn: string; idempotency_key: string; document_type: string; title: string; detail: string };
type RetrievalApiResponse = { status: RetrievalStatus; urn: string | null; title: string | null; idempotency_key: string; detail: string };

/** Read-only: GET /api/v1/documents/preview. Never mutates DataHub. */
export async function previewDocument(): Promise<PreviewResponse> {
  const response = await fetch(`${apiUrl}/api/v1/documents/preview`);
  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail ?? `Engine responded with ${response.status}`);
  }
  const body = (await response.json()) as PreviewApiResponse;
  return { preview: body.preview, previewHash: body.preview_hash };
}

/**
 * The only function in this file that can mutate DataHub. Callers must have
 * already obtained previewHash from previewDocument() and gotten explicit
 * human approval before calling this — there is no default/automatic call
 * site for it anywhere in this module or in the panel component.
 */
export async function publishDocument(previewHash: string, approved: boolean): Promise<PublishResult> {
  const response = await fetch(`${apiUrl}/api/v1/documents/publish`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ preview_hash: previewHash, approved }),
  });
  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail ?? `Engine responded with ${response.status}`);
  }
  const body = (await response.json()) as PublishApiResponse;
  return { status: body.status, urn: body.urn, idempotencyKey: body.idempotency_key, documentType: body.document_type, title: body.title, detail: body.detail };
}

/** Read-only: GET /api/v1/documents/retrieve. Independent re-check after publishing. */
export async function retrieveDocument(idempotencyKey: string, expectedUrn?: string): Promise<RetrievalResult> {
  const params = new URLSearchParams({ idempotency_key: idempotencyKey });
  if (expectedUrn) params.set("expected_urn", expectedUrn);
  const response = await fetch(`${apiUrl}/api/v1/documents/retrieve?${params.toString()}`);
  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail ?? `Engine responded with ${response.status}`);
  }
  const body = (await response.json()) as RetrievalApiResponse;
  return { status: body.status, urn: body.urn, title: body.title, idempotencyKey: body.idempotency_key, detail: body.detail };
}
