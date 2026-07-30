# Sherlock Web

Next.js client for the Frozen Dashboard response. It fetches
`GET /api/v1/demo/frozen-dashboard` from `NEXT_PUBLIC_SHERLOCK_API_URL`
(default `http://localhost:8000`), then represents the payload, selected
provider, evidence provenance, simulated inputs, derived hypotheses, and
limitations. The frontend does not perform the investigation or establish the
provenance of the returned evidence.

## Local run

Node.js 20.9+ and the backend are required. From the repository root:

```bash
cd web
npm ci
cp .env.example .env.local
npm run dev
```

Open `http://localhost:3000`.

## Available scripts

`package.json` provides the following scripts:

```bash
npm run dev
npm run lint
npm test
npm run build
```

There is no `start` script, so this README documents the supported development,
validation, and build scripts only.
