# Sherlock Engine

FastAPI backend for Sherlock's evidence-driven investigations. This first slice runs entirely on a clearly labelled JSON sandbox fixture; it does not contact DataHub or use an LLM.

## Local run

Requires Python 3.11+.

```bash
cd sherlock-engine
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
uvicorn sherlock.api.main:app --reload --port 8000
```

The API is available at `http://localhost:8000`, with docs at `/docs`.

## Validation

```bash
pytest
```

Endpoints:

- `GET /health`
- `GET /api/v1/demo/stale-pipeline`

`SHERLOCK_CORS_ORIGINS` configures local browser origins and defaults to `http://localhost:3000`.

## Current boundaries

`DataHubMetadataProvider` is intentionally only an interface skeleton. Wiring the DataHub MCP client, authentication, persistence beyond fixture files, and LLM reasoning are explicitly out of scope for this scaffold.
