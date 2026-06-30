# Multi-Agent Job Extractor

A production-ready job extraction pipeline with a Python FastAPI backend (multi-agent orchestration) and a Next.js frontend. The four-agent pipeline scrapes, parses, enriches, and matches job listings from any URL, streaming real-time progress via WebSocket.

## Architecture

```
User → Next.js (React Query) → FastAPI → Pipeline
                                           → ScraperAgent → ParserAgent → EnrichmentAgent → MatchingAgent
                                        ↘ SQLite (sqlmodel) ↙
                                        ↘ WebSocket (/ws/new/runs/{id}) → UI live stream
                                        ↘ Redis (optional) → rate limiting + work queue
```

### Agents

| Agent | Responsibility |
|---|---|
| **ScraperAgent** | Navigates target URL(s) via Playwright (headless Chromium), paginates, extracts raw HTML. Per-domain token-bucket rate limiter (1 req/sec default). |
| **ParserAgent** | Applies CSS/DOM heuristics (`BeautifulSoup`) to find repeating job-card structures. Falls back to LLM-assisted extraction when heuristics find <2 results. |
| **EnrichmentAgent** | Normalizes tech-stack keywords against a 50+ term taxonomy, infers remote/hybrid/onsite from text, parses salary ranges, computes confidence (0–1). |
| **MatchingAgent** | Two-stage scoring: (1) embedding pre-filter (sentence-transformers with LRU cache, fallback to keyword overlap), (2) LLM scoring on top N jobs. Requires an uploaded resume. |

### Pipeline resilience

- Each agent step retries up to 2× with exponential backoff before marking the run `failed`
- If Enrichment fails, Parser's raw output is still persisted with low confidence
- MatchingAgent gracefully falls back: no resume → skip, LLM fails per-job → embedding estimate, embedder unavailable → keyword overlap
- Single-run gate ensures only one pipeline runs at a time (no overlapping extractions)
- Optional Redis-backed work queue for FIFO pipeline execution

## Requirements

- Python 3.11+
- Node.js 18+
- [Playwright Chromium](https://playwright.dev/docs/browsers) (`playwright install chromium`)
- (Optional) Redis 7+ for distributed rate limiting and pipeline queue
- (Optional) [Ollama](https://ollama.ai) for LLM-assisted parsing and job matching

## Setup

### Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

cd backend
PYTHONPATH=. ../.venv/bin/uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend-next
npm install
npm run dev
```

Open http://localhost:3000

### Redis (optional)

Enable Redis for distributed rate limiting and pipeline queue:

```bash
# Set env vars
export JOBEXTRACT_REDIS_URL=redis://localhost:6379/0
export JOBEXTRACT_REDIS_ENABLED=true
```

## Usage

1. **Upload a resume** in the sidebar (PDF or .txt) to enable AI job matching
2. Click **New Extraction**, enter a URL, optionally set max pages
3. Watch the agent live stream (Scraper → Parser → Enrichment → Matching) update in real time
4. Browse extracted jobs in the results grid — search, filter by location type
5. With a resume active: click any row to see matched/missing skills, sort by match score, filter "Strong matches only"
6. Export results as JSON or CSV

### Test with the sample fixture

```bash
cd backend && PYTHONPATH=. ../.venv/bin/python3 -c "
from new.db import init_db; init_db()
from new.pipeline import Pipeline
import asyncio
asyncio.run(Pipeline().execute('test-run-id'))
"
```

Or via the frontend using `file:///absolute/path/to/backend/new/sample_jobs.html`.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/new/health` | Backend health (CPU, memory, uptime) |
| `POST` | `/api/new/resumes` | Upload resume (PDF/txt) → returns parsed profile |
| `GET` | `/api/new/resumes/active` | Currently active resume profile |
| `DELETE` | `/api/new/resumes/{id}` | Remove resume |
| `POST` | `/api/new/runs` | Start extraction `{url, max_pages}` |
| `GET` | `/api/new/runs` | List runs |
| `GET` | `/api/new/runs/{id}?include_match=true` | Run detail + jobs + match scores |
| `POST` | `/api/new/runs/{id}/pause` | Pause running extraction |
| `POST` | `/api/new/runs/{id}/resume` | Resume paused extraction |
| `POST` | `/api/new/runs/{id}/stop` | Stop extraction |
| `GET` | `/api/new/runs/{id}/export?format=csv\|json` | Export results |
| `WS` | `/ws/new/runs/{id}` | WebSocket event stream |

## Redis Features

When enabled (`JOBEXTRACT_REDIS_ENABLED=true`):

- **Distributed rate limiting**: Sliding-window rate limiter for LLM API calls (configurable via `JOBEXTRACT_LLM_RATE_PER_MINUTE` and `JOBEXTRACT_LLM_BURST_SIZE`)
- **Pipeline work queue**: FIFO queue via Redis lists prevents overlapping extraction runs; workers process one run at a time
- **Token usage tracking**: Cumulative LLM token counts persisted in Redis, survives restarts

Falls back gracefully to in-memory implementations when Redis is unavailable.

## Caching

- **EmbeddingCache**: LRU cache (max 2048 entries) stores computed sentence embeddings keyed by text hash — avoids recomputing embeddings for duplicate or overlapping job descriptions
- **@lru_cache on keyword overlap**: Cached Jaccard similarity for token-set comparisons (max 4096 entries)
- Results are process-local; Redis caching of job results is planned

## Tech Stack

- **Backend**: FastAPI, SQLModel/SQLite, Playwright, BeautifulSoup, sentence-transformers, Pydantic v2
- **Frontend**: Next.js 15 (App Router), React 19, TanStack Query, Tailwind CSS v4, Lucide React
- **LLM**: Abstracted behind `LLMClient` — defaults to Ollama, swappable via env vars
- **Cache/MQ**: Redis 7+, `functools.lru_cache`, custom LRU cache
