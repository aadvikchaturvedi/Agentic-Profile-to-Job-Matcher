# Agentic Profile-to-Job Matcher

## State of the project

- `new.pipeline` (working) — four-stage pipeline: ScraperAgent → ParserAgent → EnrichmentAgent → MatchingAgent. Uses Playwright (headless Chromium) + BeautifulSoup, with LLM fallback for bad DOM. Weighted scoring via YAML (`scoring_weights.yaml`) + sentence-transformers embeddings.
- `new.config.Settings` — Pydantic-settings config class, reads from `.env` with `JOBEXTRACT_` prefix.
- `frontend-next/` — Next.js (App Router) deployed to Vercel. Hooks into `/api/new/*` endpoints.
- Backend runs on FastAPI (port 8000), Ollama on port 11434.

## Commands

```bash
.venv/bin/pip install -r requirements.txt
brew install tesseract
.venv/bin/python3 -m playwright install chromium
ollama serve
.venv/bin/python3 -m mypy backend/ --ignore-missing-imports
.venv/bin/uvicorn app.main:app --reload     # backend (port 8000)
```

## Architecture

- **API**: FastAPI with `/api/new/*` routes (runs, health, WebSocket streaming, resumes) at `backend/app/main.py`.
- **Logging**: Loguru throughout — console colorized + file rotation (`logs/agentic-matcher.log`).
- **Config**: `new.config.Settings` — reads env vars with `JOBEXTRACT_` prefix (`.env`).
- **Pipeline**: `new.pipeline` — scraper → parser → enrichment → matching. Each step retries 2× with exponential backoff. Matching falls back gracefully (no resume → skip, LLM fails → embedding estimate, embedder unavailable → keyword overlap).
- **Scoring weights**: `backend/scoring_weights.yaml` — configurable without code changes.

## Known gaps

- `.env` with placeholder `GROQ_API_KEY` — rotate before production use.
- sentence-transformers model (`all-MiniLM-L6-v2`) downloads on first use (~80 MB); embedding score requires `numpy`.
- No test coverage for `new.pipeline` stages or SSE routes.
