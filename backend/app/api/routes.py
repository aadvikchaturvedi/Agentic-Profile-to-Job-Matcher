import asyncio
import json
import sys
from typing import List, Optional
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from loguru import logger

from app.models import AgentResponse, ProgressUpdate
from app.agents.orchestrator import MultiAgentOrchestrator
from app.utils.file_converter import FileConverter, FileConverterError

router = APIRouter(tags=["Match"])
orchestrator = MultiAgentOrchestrator()
limiter = Limiter(key_func=get_remote_address)


@router.get("/health", tags=["System"], summary="Health check endpoint")
async def health():
    return {"status": "ok", "version": "0.4.0"}


@router.post("/api/match", summary="Match resume to job description", response_model=AgentResponse)
@limiter.limit("30/minute")
async def match(
    request: Request,
    resume: UploadFile = File(...),
    job_description: str = Form(...),
) -> AgentResponse:
    logger.info("POST /api/match", filename=resume.filename)
    try:
        resume_bytes = await resume.read()
        resume_text = FileConverter.extract_text(resume_bytes, resume.filename or "resume.pdf")
    except FileConverterError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("File conversion failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Could not read file: {str(e)[:200]}")

    result = orchestrator.run(resume_text, job_description)
    return result


@router.post("/api/match-jobs", summary="Fetch and match resume against scraped jobs")
@limiter.limit("20/minute")
async def match_jobs(request: Request, resume: UploadFile = File(...), search_query: str = Form(...), location: str = Form("")):
    """
    Streaming SSE endpoint: parse resume, scrape jobs, score, report.
    Returns a Server-Sent Events stream with ProgressUpdate events,
    ending with a 'complete' event carrying the final AgentResponse.
    """
    logger.info("POST /api/match-jobs", filename=resume.filename, query=search_query)

    try:
        resume_bytes = await resume.read()
        resume_text = FileConverter.extract_text(resume_bytes, resume.filename or "resume.pdf")
    except FileConverterError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("File conversion failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Could not read file: {str(e)[:200]}")

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()

        def on_progress(p: ProgressUpdate):
            queue.put_nowait(p)

        async def run_pipeline():
            try:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: orchestrator.run_with_fetch(
                        resume_text, search_query, location=location, on_progress=on_progress
                    ),
                )
                await queue.put(None)
                return result
            except Exception as e:
                logger.error("Pipeline failed", error=str(e))
                await queue.put(
                    ProgressUpdate(step="error", message=f"Pipeline error: {str(e)[:200]}", percent=100)
                )
                await queue.put(None)
                return None

        pipeline_task = asyncio.create_task(run_pipeline())

        while True:
            try:
                ev = await asyncio.wait_for(queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                if pipeline_task.done():
                    break
                continue

            if ev is None:
                break
            yield f"data: {json.dumps(ev.model_dump())}\n\n"

        result = await pipeline_task
        if result:
            yield f"event: complete\ndata: {json.dumps(result.model_dump())}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
