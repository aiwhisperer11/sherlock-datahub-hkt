import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from sherlock.connectors.datahub import DataHubMetadataProvider, DataHubProviderError, McpSampleProvider
from sherlock.connectors.datahub.writeback import McpWritebackProvider
from sherlock.connectors.sandbox import SandboxMetadataProvider
from sherlock.domain.models import FrozenDashboardResult, Investigation, McpSampleResult, WritebackResult

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

provider = SandboxMetadataProvider()


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


@app.post("/api/v1/investigations/frozen-dashboard/writeback", response_model=WritebackResult)
def frozen_dashboard_writeback(request: WritebackRequest) -> WritebackResult:
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Writeback requires confirm=true")
    try:
        return McpWritebackProvider().write(add_tag=request.add_tag)
    except DataHubProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
