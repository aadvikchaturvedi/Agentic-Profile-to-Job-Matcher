import json
import csv
import io
import os
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import Session, select, desc

from new.db import engine
from new.models import Run, Job, RunEvent, JobMatch, RunCreate


def _format_domain(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname:
        return parsed.hostname
    if parsed.scheme == "file":
        return os.path.basename(parsed.path) or "local file"
    return url

from new.pipeline import Pipeline
from new.tasks import task_manager
from new.event_bridge import make_ws_callback

router = APIRouter(prefix="/api/new/runs", tags=["new-runs"])


@router.post("", response_model=dict)
async def create_run(body: RunCreate):
    try:
        parsed = urlparse(body.url)
        if not parsed.scheme or (not parsed.netloc and parsed.scheme != "file"):
            raise HTTPException(status_code=400, detail="Invalid URL")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid URL")

    with Session(engine) as session:
        filters_str = body.filters if isinstance(body.filters, str) else json.dumps(body.filters)
        run = Run(
            url=body.url,
            max_pages=body.max_pages,
            filters=filters_str,
            status="pending",
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id

    pipeline = Pipeline()
    pipeline.on_event(make_ws_callback(run_id))
    task_manager.start_run(run_id, pipeline)

    return {"run_id": run_id, "status": "pending", "url": body.url}


@router.get("", response_model=list[dict])
async def list_runs():
    with Session(engine) as session:
        runs = session.exec(
            select(Run).order_by(desc(Run.created_at)).limit(50)
        ).all()

    result = []
    for r in runs:
        domain = _format_domain(r.url)
        latest_event = None
        with Session(engine) as s:
            events = s.exec(
                select(RunEvent)
                .where(RunEvent.run_id == r.id)
                .order_by(desc(RunEvent.timestamp))
                .limit(1)
            ).first()
            if events:
                latest_event = events.message

        result.append({
            "id": r.id,
            "url": r.url,
            "domain": domain,
            "status": r.status,
            "duration_ms": r.duration_ms,
            "job_count": r.job_count,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "latest_event": latest_event,
        })
    return result


@router.get("/{run_id}", response_model=dict)
async def get_run(run_id: str, include_match: bool = Query(False)):
    with Session(engine) as session:
        run = session.get(Run, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        jobs = session.exec(
            select(Job).where(Job.run_id == run_id)
        ).all()

        events = session.exec(
            select(RunEvent)
            .where(RunEvent.run_id == run_id)
            .order_by(RunEvent.timestamp)
        ).all()

        job_matches = {}
        if include_match:
            matches = session.exec(
                select(JobMatch).where(
                    JobMatch.job_id.in_([j.id for j in jobs])
                )
            ).all()
            for m in matches:
                job_matches[m.job_id] = {
                    "match_score": m.match_score,
                    "matched_skills": json.loads(m.matched_skills) if m.matched_skills else [],
                    "missing_skills": json.loads(m.missing_skills) if m.missing_skills else [],
                    "improvement_notes": m.improvement_notes,
                    "llm_scored": m.llm_scored,
                }

    domain = _format_domain(run.url)

    return {
        "id": run.id,
        "url": run.url,
        "domain": domain,
        "max_pages": run.max_pages,
        "filters": run.filters,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "duration_ms": run.duration_ms,
        "job_count": run.job_count,
        "error": run.error,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "jobs": [
            {
                "id": j.id,
                "title": j.title,
                "company": j.company,
                "location_type": j.location_type,
                "location_raw": j.location_raw,
                "salary_min": j.salary_min,
                "salary_max": j.salary_max,
                "currency": j.currency,
                "tech_stack": json.loads(j.tech_stack) if j.tech_stack else [],
                "confidence": j.confidence,
                "source_url": j.source_url,
                "match": job_matches.get(j.id),
            }
            for j in jobs
        ],
        "events": [
            {
                "id": e.id,
                "agent": e.agent,
                "status": e.status,
                "message": e.message,
                "timestamp": e.timestamp.isoformat(),
            }
            for e in events
        ],
    }


@router.post("/{run_id}/pause")
async def pause_run(run_id: str):
    if task_manager.pause_run(run_id):
        return {"status": "paused"}
    raise HTTPException(status_code=404, detail="Run not found or not running")


@router.post("/{run_id}/resume")
async def resume_run(run_id: str):
    if task_manager.resume_run(run_id):
        return {"status": "resumed"}
    raise HTTPException(status_code=404, detail="Run not found or not paused")


@router.post("/{run_id}/stop")
async def stop_run(run_id: str):
    if task_manager.stop_run(run_id):
        return {"status": "stopped"}
    raise HTTPException(status_code=404, detail="Run not found or not running")


@router.get("/{run_id}/export")
async def export_run(run_id: str, format: str = Query("json", pattern="^(csv|json)$")):
    with Session(engine) as session:
        run = session.get(Run, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        jobs = session.exec(
            select(Job).where(Job.run_id == run_id)
        ).all()

    if format == "json":
        data = [
            {
                "title": j.title,
                "company": j.company,
                "location_type": j.location_type,
                "location_raw": j.location_raw,
                "salary_min": j.salary_min,
                "salary_max": j.salary_max,
                "currency": j.currency,
                "tech_stack": json.loads(j.tech_stack) if j.tech_stack else [],
                "confidence": j.confidence,
                "source_url": j.source_url,
            }
            for j in jobs
        ]
        return data

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "title", "company", "location_type", "location_raw",
        "salary_min", "salary_max", "currency", "tech_stack",
        "confidence", "source_url",
    ])
    for j in jobs:
        writer.writerow([
            j.title, j.company, j.location_type, j.location_raw or "",
            j.salary_min or "", j.salary_max or "", j.currency or "",
            json.dumps(json.loads(j.tech_stack)) if j.tech_stack else "[]",
            j.confidence, j.source_url,
        ])
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=jobs_{run_id}.csv"},
    )
