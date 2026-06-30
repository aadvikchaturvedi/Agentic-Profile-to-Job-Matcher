import time
import psutil
from fastapi import APIRouter

router = APIRouter(tags=["new-health"])

_start_time = time.time()


@router.get("/api/new/health")
async def health_check():
    uptime_seconds = time.time() - _start_time
    cpu_percent = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    return {
        "status": "ok",
        "uptime_seconds": round(uptime_seconds, 1),
        "cpu_percent": cpu_percent,
        "memory_percent": mem.percent,
        "memory_available_mb": round(mem.available / (1024 * 1024), 1),
        "version": "1.0.0",
    }


@router.get("/api/new/health/live")
async def live_check():
    return {"status": "ok"}
