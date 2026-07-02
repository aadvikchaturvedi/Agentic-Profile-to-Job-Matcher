import time
import logging
import psutil
from fastapi import APIRouter
from sqlalchemy import text
from sqlmodel import Session

from new.config import settings
from new.db import engine
from new.llm_client import LLMClient

logger = logging.getLogger(__name__)

router = APIRouter(tags=["new-health"])

_start_time = time.time()


def _check_db() -> bool:
    """Run a trivial query to confirm the database is reachable."""
    try:
        with Session(engine) as session:
            session.exec(text("SELECT 1")).first()
        return True
    except Exception as e:
        logger.error(f"[Health] DB health check failed: {e}")
        return False


@router.get("/api/new/health")
async def health_check():
    uptime_seconds = time.time() - _start_time
    cpu_percent = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()

    llm = LLMClient(
        settings.llm_base_url, settings.llm_model, settings.groq_api_key
    )
    llm_reachable = await llm.health_check()
    db_reachable = _check_db()

    return {
        "status": "ok",
        "llm_reachable": llm_reachable,
        "llm_model": settings.llm_model,
        "db_reachable": db_reachable,
        "uptime_seconds": round(uptime_seconds, 1),
        "cpu_percent": cpu_percent,
        "memory_percent": mem.percent,
        "memory_available_mb": round(mem.available / (1024 * 1024), 1),
        "version": "1.0.0",
    }


@router.get("/api/new/health/live")
async def live_check():
    return {"status": "ok"}
