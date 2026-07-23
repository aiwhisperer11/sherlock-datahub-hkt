# Frontend Setup

Requires Node.js 20.9 or newer and Sherlock Engine on port 8000.

```bash
cd sherlock-datahub-web
npm install
cp .env.example .env.local
npm run dev
```

Open `http://localhost:3000`. `NEXT_PUBLIC_SHERLOCK_API_URL` must point to the backend base URL without a trailing slash.

Validate with:

```bash
npm run lint
npm test
npm run build
```
