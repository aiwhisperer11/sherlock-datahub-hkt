# API Endpoints

Base URL for local development: `http://localhost:8000`.

## `GET /health`

Returns service availability.

```json
{ "status": "ok" }
```

## `GET /api/v1/demo/stale-pipeline`

Returns the deterministic sandbox investigation for **The Case of the Stale Pipeline**. It is demo data, not a live DataHub result.

The response contains `incident`, `assets`, `observations`, `evidence`, `hypotheses`, `conclusion`, `recommended_actions`, and typed `relationships`. Every hypothesis includes the individual confidence components and the computed `score`.

## Planned API

`POST /api/v1/investigations` is a Phase 2 endpoint. It will accept an asset URN and symptom type, and must include whether the returned investigation used live DataHub data or a snapshot fallback.
