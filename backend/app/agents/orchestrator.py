import sys
from typing import Callable, Optional, List
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from models import (
    AgentResponse,
    ParsedResume,
    JobDescription,
    MatchResult,
    UserQuery,
    ProgressUpdate,
)
from agents.parser_agent.agent import Parser
from agents.scoring_agent.agent import ScoringAgent
from agents.report_agent.agent import ReportAgent
from agents.fetch_agent.agent import FetchAgent


ProgressCallback = Callable[[ProgressUpdate], None]


class MultiAgentOrchestrator:
    def __init__(self) -> None:
        self.scorer = ScoringAgent()
        self.reporter = ReportAgent()

    def run(
        self,
        resume_text: str,
        jd_text: str,
        on_progress: Optional[ProgressCallback] = None,
    ) -> AgentResponse:
        self._emit(on_progress, "parsing", "Parsing resume...", 10)
        parsed = self._parse_resume(resume_text)
        self._emit(on_progress, "parsing", "Resume parsed successfully", 30)

        self._emit(on_progress, "scoring", "Analyzing job description...", 40)
        job_desc = self._parse_jd(jd_text)
        if not job_desc:
            self._emit(on_progress, "error", "Failed to parse job description", 100)
            return AgentResponse(
                status="error",
                overall_match_score=0,
                experience_fit_verdict="Failed to parse job description.",
                justification_summary="Job description could not be parsed from the provided text.",
                parsed_candidate_profile=parsed,
            )
        self._emit(on_progress, "scoring", f"Matching against: {job_desc.title}", 50)

        match = self.scorer.score(parsed, job_desc)
        self._emit(on_progress, "scoring", f"Score: {match.overall_score}/100", 70)

        self._emit(on_progress, "reporting", "Generating report...", 80)
        result = self.reporter.generate(match, parsed, job_title=job_desc.title)
        self._emit(on_progress, "complete", "Done", 100)

        return result

    def run_with_fetch(
        self,
        resume_text: str,
        search_query: str,
        location: str = "",
        on_progress: Optional[ProgressCallback] = None,
    ) -> AgentResponse:
        self._emit(on_progress, "parsing", "Parsing resume...", 5)
        parsed = self._parse_resume(resume_text)
        self._emit(on_progress, "parsing", f"Resume: {parsed.name or '(no name)'}", 15)

        self._emit(on_progress, "fetching", "Scraping job listings...", 20)
        fetcher = FetchAgent()

        try:
            jobs = fetcher.fetch_jobs(search_query, location, max_per_source=5)
        except Exception as e:
            logger.error("Fetch failed", error=str(e))
            self._emit(on_progress, "error", f"Scraping error: {str(e)[:100]}", 100)
            return AgentResponse(
                status="error",
                overall_match_score=0,
                experience_fit_verdict="Failed to fetch jobs.",
                skill_analysis=None,
                justification_summary=str(e),
                parsed_candidate_profile=parsed,
            )
        finally:
            fetcher.close()

        if not jobs:
            self._emit(on_progress, "complete", "No jobs found", 100)
            return AgentResponse(
                status="error",
                overall_match_score=0,
                experience_fit_verdict="No jobs found for the given query.",
                skill_analysis=None,
                justification_summary="Unable to fetch job listings.",
                parsed_candidate_profile=parsed,
            )

        self._emit(on_progress, "fetching", f"Found {len(jobs)} jobs, scoring...", 40)

        best_job = jobs[0]
        best_match: Optional[MatchResult] = None
        best_score = -1.0
        for i, j in enumerate(jobs):
            pct = 40 + int((i + 1) / len(jobs) * 30)
            self._emit(on_progress, "scoring", f"Scoring job {i+1}/{len(jobs)}: {j.title}", pct)
            m = self.scorer.score(parsed, j)
            if m.overall_score > best_score:
                best_score = m.overall_score
                best_job = j
                best_match = m

        self._emit(on_progress, "scoring", f"Best match: {best_job.title} ({round(best_score, 1)}/100)", 80)
        result = self.reporter.generate(best_match, parsed, job_title=best_job.title)
        self._emit(on_progress, "complete", "Done", 100)

        scored_jobs = []
        for j in jobs[:10]:
            m = self.scorer.score(parsed, j)
            scored_jobs.append({
                "title": j.title,
                "company": j.company,
                "score": round(m.overall_score, 1),
                "url": j.url,
                "source": j.source,
                "matched_skills": m.matched_skills[:5],
                "missing_skills": m.missing_skills[:5],
            })
        result.all_jobs = scored_jobs
        return result

    def _parse_resume(self, resume_text: str) -> ParsedResume:
        query = UserQuery(raw_job_description=resume_text)
        parser = Parser(query)
        return parser.parse()

    def _parse_jd(self, jd_text: str) -> Optional[JobDescription]:
        fetcher = FetchAgent()
        try:
            result = fetcher.parse_job_text_to_jd(jd_text)
            if result:
                return result
            logger.warning("JD parse returned empty result")
            return None
        finally:
            fetcher.close()

    @staticmethod
    def _emit(
        cb: Optional[ProgressCallback],
        step: str,
        message: str,
        percent: int,
        detail: str = "",
    ) -> None:
        if cb:
            cb(ProgressUpdate(step=step, message=message, percent=percent, detail=detail))
        logger.info("Progress", step=step, percent=percent, message=message)
