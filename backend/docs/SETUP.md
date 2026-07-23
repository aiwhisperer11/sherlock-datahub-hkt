# Backend Setup

Requires Python 3.11 or newer.

```bash
cd sherlock-datahub-backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
uvicorn sherlock.api.main:app --reload --port 8000
```

Run tests with `pytest`. The interactive OpenAPI documentation is at `http://localhost:8000/docs`.

For local web access, set `SHERLOCK_CORS_ORIGINS=http://localhost:3000`. The sandbox fixture is self-contained and does not require DataHub services or credentials.
