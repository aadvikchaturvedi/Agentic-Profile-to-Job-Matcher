"""
End-to-end test for the Multi-Agent Job Extractor.

Tests the full pipeline: ScraperAgent → ParserAgent → EnrichmentAgent → persistence.
Uses a local file:// URL pointing at the sample HTML fixture, so no network is needed.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from new.db import init_db, engine
from new.models import Run, Job, RunEvent
from new.pipeline import Pipeline
from sqlmodel import Session, select


SAMPLE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "sample_jobs.html")
)
SAMPLE_URL = f"file://{SAMPLE_PATH}"


async def test_pipeline():
    init_db()

    # Create a run in the DB
    with Session(engine) as session:
        run = Run(url=SAMPLE_URL, max_pages=1, status="pending")
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id

    print(f"Run ID: {run_id}")
    print(f"URL: {SAMPLE_URL}")
    print()

    # Collect events for verification
    events = []

    async def event_collector(agent, status, message):
        events.append({"agent": agent, "status": status, "message": message})
        print(f"  [{agent:>12}] {status:>10}: {message}")

    # Run pipeline
    pipeline = Pipeline()
    pipeline.on_event(event_collector)

    print("=== Pipeline execution ===")
    await pipeline.execute(run_id)
    print()

    # Verify
    with Session(engine) as session:
        run_obj = session.get(Run, run_id)
        jobs = session.exec(select(Job).where(Job.run_id == run_id)).all()
        run_events = session.exec(
            select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.timestamp)
        ).all()

    print(f"=== Results ===")
    print(f"Run status: {run_obj.status}")
    print(f"Duration: {run_obj.duration_ms}ms")
    print(f"Jobs found: {len(jobs)}")
    print(f"Events emitted: {len(run_events)}")
    print()

    for j in jobs:
        print(
            f"  {j.title:35s} | {j.company:20s} | {j.location_type:7s} | "
            f"${j.salary_min or 0}/{j.salary_max or 0} | "
            f"conf={j.confidence:.2f} | {j.tech_stack}"
        )

    print()
    print(f"=== Verdict ===")
    if run_obj.status == "completed":
        print("✅ Pipeline completed successfully")
    elif run_obj.status == "failed":
        print("⚠️  Pipeline finished with errors (partial results persisted)")
    else:
        print(f"❌ Unexpected status: {run_obj.status}")

    if len(jobs) > 0:
        print(f"✅ {len(jobs)} jobs persisted to database")
    else:
        print("⚠️  No jobs found (may be expected if fixture structure doesn't match)")

    # Cleanup test data
    with Session(engine) as session:
        for j in jobs:
            session.delete(j)
        for e in run_events:
            session.delete(e)
        session.delete(run_obj)
        session.commit()

    print("✅ Test data cleaned up")
    return len(jobs) > 0


if __name__ == "__main__":
    success = asyncio.run(test_pipeline())
    sys.exit(0 if success else 1)
