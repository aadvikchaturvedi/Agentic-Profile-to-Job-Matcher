# Agentic Profile-to-Job Matcher

## State of the project

- `parser_agent` (working) — Ollama-based resume parsing with **regex fallback** (`parser_fallback.py`).
- `fetch_agent` (working) — scrapes LinkedIn, Naukri, Unstop, Glassdoor via **Playwright** (headless Chromium) + `BeautifulSoup`; now uses **fake-useragent**, **proxy cycling**, and **cookie persistence**.
- `scoring_agent` (working) — weighted scoring (50% skills, 30% experience, 20% relevance) via **YAML configurable weights** (`scoring_weights.yaml`) with **sentence-transformers** hybrid.
- `report_agent` (working) — formats `MatchResult` into a structured `AgentResponse` with strengths, gaps, and action plan.
- `orchestrator.py` (working) — wires the full pipeline: resume → parser → scorer → reporter; exposes **progress callbacks** for SSE streaming.
- `frontend/app.py` (new) — **Streamlit** dashboard with file upload, mode selection (text JD or live scrape), SSE progress bar.
- `backend/tests/` has 26 fetch_agent unit tests.

## Commands

```bash
.venv/bin/pip install -r requirements.txt   # install all deps (new: streamlit, slowapi, loguru, sentence-transformers, pyyaml, python-docx, pytesseract, fake-useragent)
brew install tesseract                      # needed for OCR image support
.venv/bin/python3 -m playwright install chromium  # download Playwright browser
ollama serve                                # required before running any agent
.venv/bin/python3 -m mypy backend/ --ignore-missing-imports  # type check
.venv/bin/python3 -m unittest backend/tests/test_fetch_agent.py -v  # 26 tests
.venv/bin/uvicorn app.main:app --reload     # start the FastAPI server (port 8000)
.venv/bin/streamlit run frontend/app.py     # start the Streamlit dashboard (port 8501)
./run.sh                                    # full pipeline: install → mypy → pytest
```

## Architecture

- **API**: FastAPI (`POST /api/match`, `POST /api/match-jobs SSE streaming`) at `backend/app/main.py`. Reads PDF via `FileConverter` (supports .pdf, .docx, .png, .jpg, .txt), extracts text, passes to `MultiAgentOrchestrator`.
- **Rate limiting**: SlowAPI (30 req/min on `/api/match`, 20 req/min on `/api/match-jobs`).
- **Logging**: Loguru throughout — console colorized + file rotation (`logs/agentic-matcher.log`).
- **Chains**:
  - `Match`: resume file + JD text → `FileConverter` → `Parser` (Ollama → fallback) → `ScoringAgent` (YAML weights + embeddings) → `ReportAgent` → `AgentResponse`
  - `Fetch & Match`: resume file + search query → `FileConverter` → `Parser` → `FetchAgent` (scrape + dedup) → `ScoringAgent` (best-of-N) → `ReportAgent` → SSE stream
- **Config**: Pydantic-settings `Settings` class in `app/core/config.py`. Reads from `.env`. New fields: `PROXY_LIST`, `EMBEDDING_MODEL`, `ENABLE_EMBEDDINGS`, `WEIGHTS_PATH`, `COOKIE_FILE`.
- **Models**: Pydantic v2 in `app/models/`. New: `ProgressUpdate` for SSE streaming.
- **Scoring weights**: `backend/scoring_weights.yaml` — modifies weights without code changes.
- **File support**: `backend/app/utils/file_converter.py` — extracts text from PDF (pypdf), DOCX (python-docx), images (pytesseract), and plain text.

## Import convention

All agents use `sys.path.insert(0, ...)` to make `backend/app/` importable. When importing from the FastAPI app (uvicorn), use absolute paths (`from app.models import ...`). When running agents standalone, the sys.path hack handles it.

## Known gaps

- `.env` with placeholder `GROQ_API_KEY` — rotate before production use.
- `fetch_agent` scrapers often get blocked by JS-heavy sites. Playwright + proxy cycling + fake-useragent helps but anti-bot measures can still block.
- sentence-transformers model (`all-MiniLM-L6-v2`) downloads on first use (~80 MB); embedding score requires `numpy`.
- No test coverage for new files (`file_converter.py`, `parser_fallback.py`, `streamlit app`, SSE routes).
