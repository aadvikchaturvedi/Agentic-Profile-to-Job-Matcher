from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from loguru import logger

from app.api.routes import router, limiter
from app.utils.logging_config import setup_logging
from app.core.shutdown import graceful_shutdown
from new.db import init_db
from new.api.runs import router as new_runs_router
from new.api.health import router as new_health_router
from new.api.ws import router as new_ws_router
from new.api.resumes import router as new_resumes_router


@asynccontextmanager
async def lifespan(application: FastAPI):
    init_db()
    logger.info("New multi-agent job extractor DB initialized")
    yield
    await graceful_shutdown()


setup_logging()

app = FastAPI(
    title="Agentic Profile-to-Job Matcher + Multi-Agent Job Extractor",
    version="1.0.0",
    description="Multi-agent pipeline for resume parsing, job fetching, scoring, and reporting.",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "detail": exc.detail},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.opt(exception=True).error("Unhandled exception", path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"status": "error", "detail": "Internal server error"},
    )


app.include_router(router)
app.include_router(new_runs_router)
app.include_router(new_health_router)
app.include_router(new_ws_router)
app.include_router(new_resumes_router)

logger.info("Application started")
