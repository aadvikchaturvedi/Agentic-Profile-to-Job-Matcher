# Pre-Deployment Audit + Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the multi-agent job extractor for Fly.io (backend) + Vercel (frontend) deployment by fixing all issues enumerated in the 12-section audit checklist.

**Architecture:** FastAPI backend with a four-stage agent pipeline (Scraper → Parser → Enrichment → Matching), SQLite persistence, WebSocket live stream, Next.js frontend. The plan keeps the existing architecture and only fixes correctness, deployment, and observability gaps.

**Tech Stack:** Python 3.11, FastAPI, SQLModel/SQLAlchemy, Loguru, Playwright, httpx, Next.js 14+ (App Router), TypeScript, Tailwind.

---

## Chunk 1: Core Backend Foundation — LLMClient, Config, Health Endpoint

**Files:**
- Modify: `backend/new/llm_client.py`
- Modify: `backend/new/config.py`
- Modify: `backend/new/api/health.py`

**Complexity:** `simple`

### 1.1 LLMClient fixes (`backend/new/llm_client.py`)

Current state is mostly correct, but `parse_json()` regex is greedy and may not find the outermost `{`/`}` reliably.

Required changes:
- Keep `__init__`, `_headers`, `complete`, `health_check`, and `parse_json` signatures.
- `complete()`: log raw response at DEBUG level (already done). Ensure timeout is `httpx.AsyncClient(timeout=60.0)`.
- `parse_json()`:
  - Strip markdown fences first (use non-greedy regex, or split on ```).
  - Find outermost `{` and `}` in the cleaned text and slice between them.
  - Raise `ValueError` with first 300 chars of raw output if no JSON object found.
  - Never raise bare `json.JSONDecodeError`.
- `health_check()`: hit `{base_url}/v1/models`, return True/False, never raise, log pass/fail clearly.

Acceptance criteria:
- `python -c "from new.llm_client import LLMClient; c=LLMClient('http://localhost:11434','mistral'); print(c.parse_json('{\"a\":1}'))"` returns `{'a': 1}`.
- `c.parse_json('```json\n{\"a\":1}\n```')` returns `{'a': 1}`.
- `c.parse_json('not json')` raises `ValueError` containing first 300 chars.

### 1.2 Config fixes (`backend/new/config.py`)

Current state has fields but missing `validation_alias` for `llm_base_url` and `llm_model`, and `model_config` already uses `extra="ignore"` (good).

Required changes:
- Add `validation_alias="JOBEXTRACT_LLM_BASE_URL"` to `llm_base_url`.
- Add `validation_alias="JOBEXTRACT_LLM_MODEL"` to `llm_model`.
- Keep `groq_api_key` with `validation_alias="GROQ_API_KEY"`.
- Keep `extra="ignore"`.
- Ensure `env_file=".env"` path is relative to uvicorn launch directory (already set).

Acceptance criteria:
- `JOBEXTRACT_LLM_MODEL=foo python -c "from new.config import settings; print(settings.llm_model)"` outputs `foo`.
- `GROQ_API_KEY=bar python -c "from new.config import settings; print(settings.groq_api_key)"` outputs `bar`.

### 1.3 Health endpoint (`backend/new/api/health.py`)

Current state returns system stats but not LLM/db reachability.

Required changes:
- Keep existing system stats.
- Instantiate `LLMClient(settings.llm_base_url, settings.llm_model, settings.groq_api_key)`.
- Add `llm_reachable = await llm.health_check()`.
- Add `db_reachable` by attempting a simple DB query (e.g., `select 1` via `Session(engine)`).
- Return JSON shape:
  ```json
  {
    "status": "ok",
    "llm_reachable": true,
    "llm_model": "llama3.2",
    "db_reachable": true,
    ...existing fields...
  }
  ```

Acceptance criteria:
- `GET /api/new/health` returns `llm_reachable` boolean and `llm_model` string.
- `llm_reachable` is `True` when Ollama is up and `False` when it is not (never 500).

---

## Chunk 2: Agent Fixes — Scraper, Parser, Enrichment, Matching

**Files:**
- Modify: `backend/new/agents/scraper.py`
- Modify: `backend/new/agents/parser.py`
- Modify: `backend/new/agents/enrichment.py`
- Modify: `backend/new/agents/matching.py` (verify only, minimal changes if needed)

**Complexity:** `simple` (heuristic changes, no concurrency)

### 2.1 Scraper (`backend/new/agents/scraper.py`)

Required changes:
- Keep `headless=True` (uses `settings.playwright_headless`).
- User agent is already realistic.
- Change `page.goto(url, wait_until="networkidle", timeout=30000)` to `wait_until="domcontentloaded"`.
- Increase timeout to at least 30000ms (already 30s) and catch `playwright.async_api.TimeoutError` and other errors.
- Log full error detail (URL + error message) and emit `failed` event, returning `{"pages": [], "error": ...}` without raising.
- Pagination already uses `max_pages - 1` cap; ensure `max_pages` is respected and cannot loop infinitely (already capped).

Acceptance criteria:
- `_scrape_page` uses `wait_until="domcontentloaded"`.
- Timeout errors are caught and emitted as `failed` events.
- `run()` returns `{"pages": [], "error": ...}` on timeout.

### 2.2 Parser (`backend/new/agents/parser.py`)

Current state calls LLM as a fallback and uses bare `json.loads`. The spec allows flagging this and confirming the LLM call uses `LLMClient.parse_json()`.

Required changes:
- Handle empty/None HTML input gracefully (return empty jobs, emit `completed` with 0 jobs).
- In `_parse_with_llm`, replace `json.loads(cleaned)` with `LLMClient.parse_json(raw)`.
- If parsing fails, return empty list.

Acceptance criteria:
- `ParserAgent.run({"pages": []})` returns `{"jobs": [], "total": 0}`.
- LLM fallback path uses `LLMClient.parse_json()`.

### 2.3 Enrichment (`backend/new/agents/enrichment.py`)

Required changes:
- `_normalize_salary`: ensure missing/None salary returns `(None, None, None)` without raising (already does).
- `_extract_tech_stack`: ensure empty text returns empty list without raising (already does).
- `_compute_confidence`: clamp result to `0.0–1.0` float, never None, never outside range (already clamps via `min(score, 1.0)`; verify no None path).

Acceptance criteria:
- Empty jobs returns `{"enriched_jobs": [], "total": 0}`.
- All `confidence` values are floats between 0.0 and 1.0.

### 2.4 Matching (`backend/new/agents/matching.py`)

Current state already imports from `new.llm_client` and uses `LLMClient.parse_json()`. Verify and keep.

Required changes (if any):
- Ensure fallback path (embedding-only estimate) is triggered only on actual exception (already the case).
- Ensure `match_score` is float 1.0–10.0 or null, never string, never outside range.
- Ensure `matched_skills` and `missing_skills` default to `[]`, never None.
- Ensure no active resume skips cleanly (already implemented).

Acceptance criteria:
- No active resume returns `{"matches": [], "total": 0, "skipped": True}`.
- LLM fallback produces numeric `match_score`.
- All `matched_skills`/`missing_skills` are lists.

---

## Chunk 3: Pipeline Orchestration + WebSocket + main.py

**Files:**
- Modify: `backend/new/pipeline.py`
- Modify: `backend/new/api/ws.py`
- Modify: `backend/app/main.py`

**Complexity:** `complex` (background task lifecycle, exception handling, async queues)

### 3.1 Pipeline (`backend/new/pipeline.py`)

Required changes:
- `execute()` already logs entry. Add per-agent stage logs using exact format:
  ```python
  logger.info(f"[PIPELINE] starting {agent.__class__.__name__} run_id={run_id}")
  ```
  before each `await self._retry_agent(...)`.
- Background task strong reference is already retained in `new/tasks.py` via `task_manager._tasks`. Verify `task_manager` is used.
- LLM health check is already inside MatchingAgent (only before Matching stage), so it does not block Scraper/Parser/Enrichment.
- Wrap entire `execute()` body in try/except that catches all exceptions, logs full traceback, updates DB run status to `failed`, and emits `failed` WebSocket event (already present; verify it catches everything).
- Agent stage isolation: currently one big try around all stages. Refactor so each stage has its own try/except. If a stage fails, subsequent stages should still run where possible:
  - Scraper fails → no pages → parser gets empty pages → returns empty jobs → enrichment gets empty jobs → matching gets empty jobs.
  - Parser fails → enrichment still runs on parsed jobs (or empty).
  - Enrichment fails → matching still runs on raw jobs (or empty).
  - If Scraper succeeds but Parser fails, mark run as `partial` not `failed`.

Acceptance criteria:
- Logs contain `[PIPELINE] execute() ENTERED` and `[PIPELINE] starting ScraperAgent`, etc.
- Background task is retained in `task_manager._tasks`.
- Uncaught exception in any stage updates DB to `failed` and emits `failed` event.
- Partial failures result in status `partial`.

### 3.2 WebSocket (`backend/new/api/ws.py`)

Required changes:
- On connect, replay existing events from DB (already implemented).
- On disconnect, cleanly remove connection without raising (already implemented).
- If run is already `completed` or `failed` when WebSocket connects, send final status event immediately and close cleanly.
- Connection manager already iterates with error handling; ensure one failed send does not drop others (already implemented with `dead` set).

Acceptance criteria:
- Reconnecting mid-run replays historical events.
- Connecting to a completed run receives a `complete` event and closes cleanly.

### 3.3 main.py (`backend/app/main.py`)

Required changes:
- Confirm only `new.*` routers mounted (already true).
- CORS: change `allow_origins=["*"]` to include both `http://localhost:3000` and a production Vercel URL from env:
  ```python
  origins = [
      "http://localhost:3000",
      os.getenv("FRONTEND_URL", ""),
  ]
  app.add_middleware(
      CORSMiddleware,
      allow_origins=origins,
      ...
  )
  ```
- Confirm `init_db()` called inside lifespan context manager (already true).
- Confirm no `slowapi`/rate limiter imports remain (already true).

Acceptance criteria:
- `os.environ.get("FRONTEND_URL")` is read for CORS.
- Only `new.*` routers are imported.

---

## Chunk 4: API Endpoints — runs.py, resumes.py

**Files:**
- Modify: `backend/new/api/runs.py`
- Modify: `backend/new/api/resumes.py`

**Complexity:** `simple`

### 4.1 runs.py

Current state is mostly correct. Verify and keep:
- `POST /api/new/runs` returns run_id immediately and starts pipeline in background via `task_manager.start_run` (already true).
- `GET /api/new/runs` sorted by `created_at` desc (already true).
- `GET /api/new/runs/{run_id}?include_match=true` returns empty `jobs: []` while in progress (already true).
- `POST /api/new/runs/{run_id}/stop` cancels task. Current `task_manager.stop_run` only sets `_stop_requested`. Optionally also cancel the asyncio.Task via `task.cancel()`.

Required changes:
- In `task_manager.stop_run`, after `pipeline.request_stop()`, also cancel the stored `asyncio.Task` and update DB status to `stopped`.

Acceptance criteria:
- Stop endpoint cancels background task and sets DB status to `stopped`.

### 4.2 resumes.py

Current state is mostly correct.

Required changes:
- `GET /api/new/resumes/active` already uses `response_model=Optional[dict]` and returns null (verify).
- `POST /api/new/resumes` already handles non-PDF by attempting decode and returns 400 if no text; add explicit content-type check returning 400 for obviously non-text/non-PDF uploads if needed.
- Confirm resume `raw_text` is never included in WebSocket events (events use pipeline messages, not resume payload).

Acceptance criteria:
- Active resume empty returns `null`.
- Non-PDF upload returns 400 with clear message.
- No WS event contains `raw_text`.

---

## Chunk 5: Database + Deployment Files

**Files:**
- Modify: `backend/new/db.py`
- Verify: `backend/new/models.py`
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Create: `fly.toml`

**Complexity:** `simple`

### 5.1 Database (`backend/new/db.py`)

Current state: `database_url` comes from `settings.database_url`, which is env-configurable via `JOBEXTRACT_DATABASE_URL` (because env_prefix is `JOBEXTRACT_`).

Required changes:
- Confirm SQLite path is configurable via env var (already true because `database_url` uses `settings.database_url`).
- Ensure default is sensible for local dev (already `./backend/new/job_extract.db`).
- `init_db()` is called in lifespan (already true).
- Verify models in `backend/new/models.py` have `table=True` and correct FKs (already true).

Acceptance criteria:
- `JOBEXTRACT_DATABASE_URL=sqlite:////data/jobextract.db` is respected.
- All models have `table=True`.

### 5.2 Dockerfile

Current state has `python3 -m playwright install chromium` and `python3 -m playwright install-deps chromium` as separate commands, plus apt installs tesseract. The spec requires:

```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y wget gnupg ca-certificates
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps chromium
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Required changes:
- Match the exact spec shape while keeping the existing working directory/scoring weights copy if needed.
- Replace `python3 -m playwright install chromium && python3 -m playwright install-deps chromium` with `playwright install --with-deps chromium`.
- Keep `--no-cache-dir`.

Acceptance criteria:
- Dockerfile contains `playwright install --with-deps chromium`.

### 5.3 docker-compose.yml

Current state has only `ollama` and `api` services (good) but wrong env vars.

Required changes:
- Match the exact spec:
  ```yaml
  services:
    ollama:
      image: ollama/ollama
      ports:
        - "11434:11434"
      volumes:
        - ollama_data:/root/.ollama
      restart: unless-stopped

    api:
      build:
        context: ./backend
        dockerfile: Dockerfile
      ports:
        - "8000:8000"
      environment:
        - JOBEXTRACT_LLM_BASE_URL=http://ollama:11434
        - JOBEXTRACT_LLM_MODEL=mistral
        - GROQ_API_KEY=
        - DATABASE_URL=sqlite:////data/jobextract.db
        - FRONTEND_URL=https://your-app.vercel.app
      volumes:
        - sqlite_data:/data
      depends_on:
        - ollama
      restart: unless-stopped

  volumes:
    ollama_data:
    sqlite_data:
  ```

Acceptance criteria:
- Only `ollama` and `api` services.
- Env vars match spec.

### 5.4 fly.toml

Create if missing with exact spec:

```toml
app = "job-extract-api"
primary_region = "sin"   # Singapore — closest to Delhi

[build]
  dockerfile = "backend/Dockerfile"

[env]
  PORT = "8000"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true

[[mounts]]
  source = "sqlite_data"
  destination = "/data"

[[vm]]
  memory = "1gb"
  cpu_kind = "shared"
  cpus = 1
```

Acceptance criteria:
- `fly.toml` exists at repo root with above content.

---

## Chunk 6: Frontend Empty States + Build

**Files:**
- Verify: `frontend-next/.env.local`
- Verify: `frontend-next/src/lib/api.ts`
- Verify: `frontend-next/src/hooks/useRunSocket.ts`
- Modify: `frontend-next/src/components/ResultsGrid.tsx` (empty states)
- Modify: `frontend-next/src/components/AgentLiveStream.tsx` (failed state)
- Run: `cd frontend-next && npm run build`

**Complexity:** `simple`

### 6.1 Environment / WebSocket verification

Required changes:
- Confirm `.env.local` has `NEXT_PUBLIC_API_URL=http://localhost:8000`.
- Confirm `api.ts` line 1 uses `process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"`.
- Confirm `useRunSocket.ts` derives `wss://` from `https://` via `API_BASE.replace(/^http/, "ws")`.

### 6.2 Empty states

Required changes:
- `ResultsGrid`: when no resume uploaded, show message "Upload a resume to see match scores" instead of dashes (banner already exists; verify).
- Run in progress: results grid shows jobs as they come in or a clear loading state (already shows jobs list; verify).
- Run failed: `AgentLiveStream` should show clear error message in the agent monitor, not frozen "Waiting...". Update `AgentTrack` to display failed status prominently and show `error` event message.
- Zero jobs found: show "No jobs found for this URL" instead of empty table.

Acceptance criteria:
- No-resume banner text matches spec.
- Failed run shows error in AgentLiveStream.
- Zero jobs shows "No jobs found for this URL".

### 6.3 Build

Acceptance criteria:
- `npm run build` completes with zero errors (warnings acceptable).

---

## Chunk 7: Final Smoke Test & Checklist

**Files:** All

**Complexity:** `complex` (end-to-end, requires running services)

### 7.1 Smoke test steps

1. Start backend: `cd backend && ../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000` — no import errors, `init_db` completes.
2. Health check: `curl http://localhost:8000/api/new/health` returns real status with `llm_reachable`.
3. Full pipeline run via frontend at `localhost:3000` with URL `https://remoteok.com/remote-dev-jobs`, max pages 2. Logs must include:
   - `[PIPELINE] execute() ENTERED`
   - `[PIPELINE] starting ScraperAgent`
   - `[PIPELINE] starting ParserAgent`
   - `[PIPELINE] starting EnrichmentAgent`
   - `[PIPELINE] starting MatchingAgent`
   - `[LLMClient] raw response: {"match_score":...`
4. UI shows at least one job with numeric match_score, matched_skills badges, missing_skills badges, and improvement_notes.
5. Frontend build passes.

### 7.2 Final checklist

- `backend/new/llm_client.py` fully implemented, not empty.
- `LLMClient` instantiated with `api_key=settings.groq_api_key` everywhere.
- `new/config.py` has `llm_base_url`, `llm_model`, `groq_api_key` with correct aliases.
- No pydantic `extra="forbid"` crashing on unknown env vars.
- `app/core/config.py` confirmed deleted.
- Scraper uses `domcontentloaded`, realistic user_agent, 30s+ timeout, caught errors.
- Parser handles empty HTML without raising; LLM fallback uses `LLMClient.parse_json()`.
- Enrichment handles missing salary/tech_stack without raising.
- Matching imports from `new.llm_client`, uses `parse_json()`, fallback only on real exception.
- Pipeline `execute()` has entry log + per-stage logs + full traceback catch.
- LLM health check only before Matching stage.
- Background task has retained strong reference.
- WebSocket replays history on reconnect, handles disconnect cleanly, closes completed/failed runs.
- `GET /api/new/resumes/active` returns null not 404 when empty.
- `GET /api/new/health` returns real `llm_reachable` status.
- SQLite path is env-configurable.
- CORS allows both localhost:3000 and production Vercel URL via env var.
- Dockerfile has `playwright install --with-deps chromium`.
- docker-compose.yml has only `ollama` + `api` services.
- `fly.toml` created with persistent volume mount at `/data`.
- `npm run build` passes with zero errors.
- Full smoke test passes end to end.
- No API keys or secrets committed to git.
- `.gitignore` covers `.env`, `.env.local`, `*.env`.

---

## Execution Notes

- Backend fixes are mostly independent of frontend changes, except the CORS env var.
- Docker/deployment files are independent of code fixes.
- Smoke test must be run after all code fixes are complete and the backend can boot.
- If the user cannot provide a running Ollama instance for the smoke test, the health check should still return `llm_reachable: false` without crashing.
