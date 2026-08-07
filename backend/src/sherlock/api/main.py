import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from sherlock.connectors.datahub import DataHubMetadataProvider, DataHubProviderError, McpSampleProvider, UnsupportedMetadataUrnError
from sherlock.connectors.datahub.provider import ORDER_DETAILS_URN
from sherlock.connectors.datahub.writeback import DocumentWritebackProvider, McpWritebackProvider
from sherlock.connectors.sandbox import SandboxMetadataProvider
from sherlock.domain.models import (
    DocumentPreview,
    DocumentRetrievalResult,
    DocumentWritebackResult,
    FrozenDashboardResult,
    Investigation,
    McpSampleResult,
    MetadataContextResult,
    WritebackResult,
)
from sherlock.api.preview_cache import PreviewCache

app = FastAPI(title="Sherlock Engine", version="0.1.0")

origins = [origin.strip() for origin in os.getenv("SHERLOCK_CORS_ORIGINS", "http://localhost:3000").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class WritebackRequest(BaseModel):
    confirm: bool = False
    add_tag: bool = False


class DocumentPreviewResponse(BaseModel):
    preview: DocumentPreview
    preview_hash: str


class DocumentPublishRequest(BaseModel):
    preview_hash: str
    approved: bool = False


provider = SandboxMetadataProvider()
_document_preview_cache = PreviewCache()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/demo/stale-pipeline", response_model=Investigation)
def stale_pipeline_demo() -> Investigation:
    return provider.load_stale_pipeline_demo()


@app.get("/api/v1/demo/frozen-dashboard", response_model=FrozenDashboardResult)
def frozen_dashboard_demo() -> FrozenDashboardResult:
    return DataHubMetadataProvider().load_frozen_dashboard_from_snapshot()


@app.get("/api/v1/metadata/mcp/sample", response_model=McpSampleResult)
def mcp_sample() -> McpSampleResult:
    try:
        return McpSampleProvider().fetch_sample()
    except DataHubProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.get("/api/v1/metadata/context", response_model=MetadataContextResult)
def metadata_context(urn: str) -> MetadataContextResult:
    try:
        return DataHubMetadataProvider().load_metadata_context(urn)
    except UnsupportedMetadataUrnError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except DataHubProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.post("/api/v1/investigations/frozen-dashboard/writeback", response_model=WritebackResult)
def frozen_dashboard_writeback(request: WritebackRequest) -> WritebackResult:
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Writeback requires confirm=true")
    try:
        return McpWritebackProvider().write(add_tag=request.add_tag)
    except DataHubProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.get("/api/v1/documents/preview", response_model=DocumentPreviewResponse)
def document_preview() -> DocumentPreviewResponse:
    """Read-only: get_entities + get_lineage over MCP, then either the real
    Sherlock-Core canonical engine (if SHERLOCK_CORE_URL is configured) or a
    local fallback. Never calls save_document — this is what the human
    reviews before approving. The target is always ORDER_DETAILS_URN,
    matching McpWritebackProvider: callers cannot supply an arbitrary urn.

    The exact returned preview is cached server-side, keyed by its own
    content hash (see sherlock.api.preview_cache) — POST /publish looks it
    up by that hash and publishes it verbatim. It never regenerates a
    preview to check against, because the canonical engine is a live LLM
    call: two calls with identical DataHub evidence return different wording
    (confirmed against https://sherlock-engine.vercel.app), so comparing a
    freshly regenerated preview's hash against what the human approved would
    almost always — and incorrectly — read as "stale."
    """
    try:
        preview = DocumentWritebackProvider().preview(ORDER_DETAILS_URN)
    except DataHubProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    preview_hash = _document_preview_cache.put(preview)
    return DocumentPreviewResponse(preview=preview, preview_hash=preview_hash)


@app.post("/api/v1/documents/publish", response_model=DocumentWritebackResult)
def document_publish(request: DocumentPublishRequest) -> DocumentWritebackResult:
    """The only endpoint that can call save_document, and only when both:
    (a) approved=true was passed explicitly, and (b) preview_hash resolves to
    a still-cached, still-verified preview. This never re-runs MCP context
    acquisition or the Sherlock-Core engine — it looks up the exact preview
    object the human reviewed and publishes that, unmodified. The client
    never supplies title/content directly — there is no request field for
    them — so altered content has no channel to reach save_document, and an
    unknown, tampered, or expired preview_hash is rejected with 409 rather
    than silently published. A cache miss also happens, by design, for any
    preview_hash issued before the backend last restarted: the cache is
    purely in-memory and is not persisted.
    """
    if not request.approved:
        raise HTTPException(status_code=400, detail="Publishing requires explicit human approval (approved=true)")
    cached_preview = _document_preview_cache.get_verified(request.preview_hash)
    if cached_preview is None:
        raise HTTPException(
            status_code=409,
            detail="Preview not found, expired, or altered; generate a new preview and approve again",
        )
    try:
        return DocumentWritebackProvider().publish(cached_preview, approved=True)
    except DataHubProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.get("/api/v1/documents/retrieve", response_model=DocumentRetrievalResult)
def document_retrieve(idempotency_key: str, expected_urn: str | None = None) -> DocumentRetrievalResult:
    """Independent read-only re-check via search_documents; never calls save_document."""
    try:
        return DocumentWritebackProvider().retrieve(idempotency_key, expected_urn=expected_urn)
    except DataHubProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
