import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from sherlock.connectors.datahub import DataHubMetadataProvider, DataHubProviderError, McpSampleProvider
from sherlock.connectors.sandbox import SandboxMetadataProvider
from sherlock.domain.models import FrozenDashboardResult, Investigation, McpSampleResult

app = FastAPI(title="Sherlock Engine", version="0.1.0")

origins = [origin.strip() for origin in os.getenv("SHERLOCK_CORS_ORIGINS", "http://localhost:3000").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

provider = SandboxMetadataProvider()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/demo/stale-pipeline", response_model=Investigation)
def stale_pipeline_demo() -> Investigation:
    return provider.load_stale_pipeline_demo()


@app.get("/api/v1/demo/frozen-dashboard", response_model=FrozenDashboardResult)
def frozen_dashboard_demo() -> FrozenDashboardResult:
    return DataHubMetadataProvider().load_frozen_dashboard()


@app.get("/api/v1/metadata/mcp/sample", response_model=McpSampleResult)
def mcp_sample() -> McpSampleResult:
    try:
        return McpSampleProvider().fetch_sample()
    except DataHubProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
