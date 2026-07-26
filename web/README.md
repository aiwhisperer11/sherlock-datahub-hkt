# Sherlock Web

Next.js frontend for the Frozen Dashboard investigation. It fetches the backend response and visibly renders evidence provenance, provider attempts, limitations, confidence, and uncertainty.

## Requirements and installation

Node.js 20.9 or newer and npm are required. A committed `package-lock.json` is present, so use the reproducible install command:

```bash
cd web
npm ci
```

## Configuration and local run

The only browser-facing configuration used by the code is `NEXT_PUBLIC_SHERLOCK_API_URL`. It defaults to `http://localhost:8000`; it must point at the FastAPI backend and must not contain a secret.

```bash
cp .env.example .env.local
npm run dev
```

Open `http://localhost:3000`. Start the backend separately with `uvicorn sherlock.api.main:app --port 8000`; the page calls `GET /api/v1/demo/frozen-dashboard`. If the API origin differs, add the frontend origin to the backend's `SHERLOCK_CORS_ORIGINS`.

## Validation

```bash
npm run build
```

Additional repository scripts are `npm run lint` and `npm test`. The frontend has no direct DataHub, MCP, GraphQL, or credential access; it receives the sanitized investigation response from FastAPI.
