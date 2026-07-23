# Sherlock Web

Next.js dashboard for the Sherlock stale-pipeline demo.

## Local run

Requires Node.js 20.9+ and the engine running on port 8000.

```bash
cd sherlock-web
npm install
cp .env.example .env.local
npm run dev
```

Open `http://localhost:3000`. The dashboard calls `GET /api/v1/demo/stale-pipeline` from `NEXT_PUBLIC_SHERLOCK_API_URL` (default: `http://localhost:8000`).

## Validation

```bash
npm run lint
npm test
npm run build
```

The visual graph is deliberately componentized but does not yet include React Flow. Vercel compatibility comes from the standard Next.js build; this repository is not configured or deployed to Vercel.
