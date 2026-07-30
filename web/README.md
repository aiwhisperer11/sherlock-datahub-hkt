# Sherlock Web

Next.js client for the Frozen Dashboard response. It fetches
`GET /api/v1/demo/frozen-dashboard` from `NEXT_PUBLIC_SHERLOCK_API_URL`
(default `http://localhost:8000`), then represents the payload, selected
provider, evidence provenance, simulated inputs, derived hypotheses, and
limitations. It visibly renders evidence provenance, provider attempts,
limitations, confidence, and uncertainty. The frontend does not perform the
investigation or establish the provenance of the returned evidence.

## Requirements and installation

Node.js 20.9+ and the backend are required. A committed `package-lock.json` is
present, so use the reproducible install command:

```bash
cd web
npm ci
cp .env.example .env.local
npm run dev
```

## Configuration and local run

The only browser-facing configuration used by the code is
`NEXT_PUBLIC_SHERLOCK_API_URL`. It defaults to `http://localhost:8000`; it
must point at the FastAPI backend and must not contain a secret.

Open `http://localhost:3000`. Start the backend separately with
`uv run uvicorn sherlock.api.main:app --reload --port 8000`; the page calls
`GET /api/v1/demo/frozen-dashboard`. If the API origin differs, add the
frontend origin to the backend's `SHERLOCK_CORS_ORIGINS`.

## Available scripts

`package.json` provides the following scripts:

```bash
npm run dev
npm run lint
npm test
npm run build
```

There is no `start` script, so this README documents the supported
development, validation, and build scripts only. The frontend has no direct
DataHub, MCP, GraphQL, or credential access; it receives the sanitized
investigation response from FastAPI.
