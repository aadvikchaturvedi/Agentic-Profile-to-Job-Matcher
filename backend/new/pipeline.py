import asyncio
import time
import json
import traceback
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from sqlmodel import Session, select

from new.db import engine
from new.models import Run, Job, RunEvent
from new.config import settings
from new.llm_client import LLMClient
from new.agents.base import BaseAgent, EventCallback
from new.agents.scraper import ScraperAgent
from new.agents.parser import ParserAgent
from new.agents.enrichment import EnrichmentAgent
from new.agents.matching import MatchingAgent
from new.models import Resume, JobMatch
from new.rate_limiter import DomainRateLimiter
from loguru import logger


class Pipeline:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            api_key=settings.groq_api_key
        )
        self.rate_limiter = DomainRateLimiter(settings.rate_limit_per_domain)
        self._event_handlers: list[EventCallback] = []
        self._stop_requested = False
        self._paused = False
        self._pause_cond = asyncio.Condition()

    def on_event(self, handler: EventCallback):
        self._event_handlers.append(handler)

    async def _broadcast_event(self, agent: str, status: str, message: str):
        for handler in self._event_handlers:
            try:
                await handler(agent, status, message)
            except Exception:
                pass

    async def _emit(self, agent: str, status: str, message: str):
        await self._broadcast_event(agent, status, message)

    async def _save_event(self, run_id: str, agent: str, status: str, message: str):
        with Session(engine) as session:
            event = RunEvent(
                run_id=run_id, agent=agent, status=status, message=message
            )
            session.add(event)
            session.commit()

    async def _make_event_callback(self, run_id: str) -> EventCallback:
        async def callback(agent: str, status: str, message: str):
            if self._stop_requested:
                return
            async with self._pause_cond:
                while self._paused:
                    await self._pause_cond.wait()
            await self._emit(agent, status, message)
            await self._save_event(run_id, agent, status, message)

        return callback

    def request_stop(self):
        self._stop_requested = True
        self._paused = False

    def request_pause(self):
        self._paused = True

    def request_resume(self):
        self._paused = False

    async def _retry_agent(self, agent: BaseAgent, context: dict, name: str) -> dict:
        last_error = None
        for attempt in range(1 + settings.max_retries):
            if self._stop_requested:
                return {"error": "Stopped", "_stopped": True}
            try:
                logger.info("[PIPELINE] running agent '{}' (attempt {}/{})", name, attempt + 1, 1 + settings.max_retries)
                return await agent.run(context)
            except Exception as e:
                last_error = str(e)
                logger.warning("Pipeline: agent '{}' failed on attempt {}: {}", name, attempt + 1, last_error[:120])
                if attempt < settings.max_retries:
                    delay = settings.retry_base_delay * (2 ** attempt)
                    await self._emit(
                        name,
                        "progress",
                        f"Retry {attempt + 1}/{1 + settings.max_retries} "
                        f"after {delay:.1f}s: {last_error[:60]}",
                    )
                    await asyncio.sleep(delay)
                else:
                    await self._emit(name, "failed", f"Failed: {last_error[:100]}")
        logger.error("Pipeline: agent '{}' exhausted all retries: {}", name, last_error[:200])
        return {"error": last_error}

    async def execute(self, run_id: str):
        logger.info("[PIPELINE] execute() ENTERED for run_id={}", run_id)
        start_time = time.monotonic()

        cb = await self._make_event_callback(run_id)
        scraper = ScraperAgent(self.llm_client, cb, self.rate_limiter)
        parser = ParserAgent(self.llm_client, cb)
        enrichment = EnrichmentAgent(self.llm_client, cb)
        matching = MatchingAgent(self.llm_client, cb)

        with Session(engine) as session:
            run_obj = session.get(Run, run_id)
            if not run_obj:
                logger.warning("Run {} not found in DB, aborting", run_id)
                return
            run_obj.status = "running"
            run_obj.started_at = datetime.now(timezone.utc)
            session.add(run_obj)
            session.commit()
            run_url = run_obj.url
            run_max_pages = run_obj.max_pages

        logger.info("Run {} starting — url={} max_pages={}", run_id, run_url, run_max_pages)
        scrape_error = False
        parse_error = False
        enrich_error = False
        match_error = False

        try:
            # Stage 1: Scrape
            logger.info("Run {} — Stage 1: Scrape starting", run_id)
            logger.info(f"[PIPELINE] starting {scraper.__class__.__name__} run_id={run_id}")
            scrape_result = await self._retry_agent(
                scraper,
                {
                    "url": run_url,
                    "max_pages": run_max_pages,
                    "run_id": run_id,
                },
                "scraper",
            )
            if self._stop_requested:
                await self._finalize_run(run_id, "stopped", start_time)
                return
            if scrape_result.get("error"):
                scrape_error = True
            logger.info("Run {} — Stage 1: Scrape done ({} pages, error={})", run_id, len(scrape_result.get("pages", [])), scrape_result.get("error"))

            # Stage 2: Parse
            logger.info("Run {} — Stage 2: Parse starting", run_id)
            if scrape_result.get("pages"):
                logger.info(f"[PIPELINE] starting {parser.__class__.__name__} run_id={run_id}")
                parse_result = await self._retry_agent(
                    parser,
                    {"pages": scrape_result["pages"], "run_id": run_id},
                    "parser",
                )
            else:
                parse_result = {"jobs": [], "total": 0}

            if self._stop_requested:
                await self._finalize_run(run_id, "stopped", start_time)
                return
            if parse_result.get("error"):
                parse_error = True
            logger.info("Run {} — Stage 2: Parse done ({} jobs, error={})", run_id, parse_result.get("total", 0), parse_result.get("error"))

            # Stage 3: Enrich
            logger.info("Run {} — Stage 3: Enrich starting", run_id)
            if parse_result.get("jobs"):
                logger.info(f"[PIPELINE] starting {enrichment.__class__.__name__} run_id={run_id}")
                enrich_result = await self._retry_agent(
                    enrichment,
                    {"jobs": parse_result["jobs"], "run_id": run_id},
                    "enrichment",
                )
            else:
                logger.info(f"[PIPELINE] starting {enrichment.__class__.__name__} run_id={run_id}")
                enrich_result = await self._retry_agent(
                    enrichment,
                    {"jobs": parse_result.get("jobs", []), "run_id": run_id},
                    "enrichment",
                )

            if self._stop_requested:
                await self._finalize_run(run_id, "stopped", start_time)
                return
            if enrich_result.get("error"):
                enrich_error = True
            enriched_jobs = enrich_result.get("enriched_jobs", [])
            logger.info("Run {} — Stage 3: Enrich done ({} enriched, error={})", run_id, len(enriched_jobs), enrich_result.get("error"))

            # Persist enriched jobs
            with Session(engine) as session:
                for ej in enriched_jobs:
                    job = Job(
                        run_id=run_id,
                        title=ej.get("title", ""),
                        company=ej.get("company", ""),
                        location_type=ej.get("location_type", "onsite"),
                        location_raw=ej.get("location_raw"),
                        salary_min=ej.get("salary_min"),
                        salary_max=ej.get("salary_max"),
                        currency=ej.get("currency"),
                        tech_stack=json.dumps(ej.get("tech_stack", [])),
                        confidence=ej.get("confidence", 0.0),
                        source_url=ej.get("source_url", ""),
                    )
                    session.add(job)
                session.commit()

            if not enriched_jobs and parse_result.get("jobs"):
                with Session(engine) as session:
                    for rj in parse_result["jobs"]:
                        job = Job(
                            run_id=run_id,
                            title=rj.get("title", ""),
                            company=rj.get("company", ""),
                            location_type="onsite",
                            confidence=0.1,
                            source_url=rj.get("source_url", ""),
                        )
                        session.add(job)
                    session.commit()

            # Stage 4: Match — only runs if an active resume exists.
            # MatchingAgent has its own LLM health check and handles
            # LLM unavailability gracefully (fallback to embedding-only).
            logger.info("Run {} — Stage 4: Match starting", run_id)
            match_result = {}
            with Session(engine) as session:
                active_resume = session.exec(
                    select(Resume).where(Resume.is_active == True)
                ).first()

            if active_resume:
                logger.info("Run {} — active resume found, running MatchingAgent", run_id)
                resume_dict = {
                    "parsed_skills": active_resume.parsed_skills,
                    "years_experience": active_resume.years_experience,
                    "titles_held": active_resume.titles_held,
                    "seniority_level": active_resume.seniority_level,
                }
                logger.info(f"[PIPELINE] starting {matching.__class__.__name__} run_id={run_id}")
                match_result = await self._retry_agent(
                    matching,
                    {
                        "enriched_jobs": enriched_jobs or [],
                        "resume": resume_dict,
                        "run_id": run_id,
                    },
                    "matching",
                )

                # Persist matches
                if match_result.get("matches") and enriched_jobs:
                    with Session(engine) as session:
                        db_jobs = session.exec(
                            select(Job).where(Job.run_id == run_id)
                        ).all()
                        for m in match_result["matches"]:
                            idx = m.get("job_index")
                            if idx is not None and idx < len(db_jobs):
                                match_record = JobMatch(
                                    job_id=db_jobs[idx].id,
                                    resume_id=active_resume.id,
                                    match_score=m.get("match_score"),
                                    matched_skills=json.dumps(m.get("matched_skills", [])),
                                    missing_skills=json.dumps(m.get("missing_skills", [])),
                                    improvement_notes=m.get("improvement_notes", ""),
                                    llm_scored=m.get("llm_scored", False),
                                    embedding_similarity=m.get("embedding_similarity"),
                                )
                                session.add(match_record)
                        session.commit()

                logger.info("Run {} — Matching done ({} matches)", run_id, len(match_result.get("matches", [])))

            if match_result.get("error"):
                match_error = True

            if self._stop_requested:
                logger.info("Run {} — stop requested, aborting", run_id)
                await self._finalize_run(run_id, "stopped", start_time)
                return

            any_error = scrape_error or parse_error or enrich_error or match_error
            if scrape_result.get("pages") and not scrape_error and (parse_error or enrich_error or match_error):
                final_status = "partial"
            elif any_error:
                final_status = "failed"
            else:
                final_status = "completed"
            logger.info("Run {} — pipeline finished with status={}", run_id, final_status)
            await self._finalize_run(run_id, final_status, start_time)

        except Exception as e:
            logger.error("[PIPELINE] execute() FAILED for run_id={}: {}", run_id, e)
            logger.error(traceback.format_exc())
            await self._emit(
                "pipeline", "failed", f"Pipeline error: {str(e)[:200]}"
            )
            await self._finalize_run(run_id, "failed", start_time)
        finally:
            await scraper.cleanup()

    async def _finalize_run(
        self, run_id: str, status: str, start_time: float
    ):
        duration_ms = int((time.monotonic() - start_time) * 1000)
        logger.info("Run {} — finalizing with status='{}' duration={}ms", run_id, status, duration_ms)
        with Session(engine) as session:
            run_obj = session.get(Run, run_id)
            if run_obj:
                run_obj.status = status
                run_obj.completed_at = datetime.now(timezone.utc)
                run_obj.duration_ms = duration_ms
                jobs = session.exec(
                    select(Job).where(Job.run_id == run_id)
                ).all()
                run_obj.job_count = len(jobs)
                session.add(run_obj)
                session.commit()

        domain = ""
        with Session(engine) as session:
            r = session.get(Run, run_id)
            if r:
                domain = urlparse(r.url).hostname or ""

        await self._emit(
            "pipeline",
            status,
            f"Pipeline {status}: {duration_ms}ms",
        )
