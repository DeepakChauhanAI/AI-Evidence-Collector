# Panacea InfoSec — AI Evidence Collector

Transparent, configurable system that collects SOC 2 (or any framework) audit
evidence on a schedule. Deterministic collectors do the pulling; an AI / keyword mapper
suggests which collector fits each control (behind `suggest_collector()`).

## Loop
import checklist (CSV from a GRC export) → map a collector to each control →
run manually or on a schedule → evidence written to disk, SHA-256 hashed, listed in the dashboard.

## Run

Backend (sqlite by default; set `DATABASE_URL=postgresql://...` for Postgres):
```
cd backend
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m app.selfcheck          # verify core loop
.venv/Scripts/uvicorn app.main:app --reload    # http://localhost:8000/docs
```

Frontend:
```
cd frontend
npm install
npm run dev                                     # http://localhost:5173 (proxies /api)
```

## Collectors (`backend/app/collectors.py`)
- `http_api` — any HTTP/JSON API (cloud, SaaS, internal endpoint)
- `document` — fetch a document over HTTP (policy PDF, exported report)
- `screenshot` — full-page capture of a web console with no API (needs `playwright install chromium`)

Add a vector = add a function + register it in `REGISTRY`.

## LLM provider (optional)
`suggest_collector()` uses an LLM to map each control to a collector when
`AI_API_KEY` is set, else a deterministic keyword fallback. Any OpenAI-compatible
endpoint works — configure via `AI_API_KEY` / `AI_BASE_URL` / `AI_MODEL`
(see `backend/.env.example`). Mirrors the governance platform's provider pattern.

## Not built yet (add when a control needs it)
- Cloud SDK collectors (boto3 etc.) with live credentials
- Multi-user / per-tenant accounts (current auth is one shared token)
