import sys
from typing import List
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
from loguru import logger

from models import MatchResult, ParsedResume, SkillGapAnalysis, AgentResponse
from app.core.config import settings


class ReportAgent:
    def __init__(self) -> None:
        self.ollama_url = settings.effective_ollama_url
        self.model = settings.llm_model or settings.ollama_model

    def generate(
        self, match: MatchResult, resume: ParsedResume, job_title: str = ""
    ) -> AgentResponse:
        llm_summary = self._llm_justification(match, resume, job_title)
        strengths, gaps = self._build_skill_narrative(match)
        action_plan = self._build_action_plan(match)

        logger.info("Report generated", overall=match.overall_score, job_title=job_title or "(none)")

        return AgentResponse(
            status="success",
            overall_match_score=min(int(round(match.overall_score)), 100),
            experience_fit_verdict=self._experience_verdict(match),
            skill_analysis=SkillGapAnalysis(
                matched_skills=match.matched_skills,
                missing_skills=match.missing_skills,
                transferable_skills=self._infer_transferable(match),
            ),
            justification_summary=llm_summary,
            parsed_candidate_profile=resume,
            action_plan=action_plan,
        )

    def _experience_verdict(self, match: MatchResult) -> str:
        exp = match.experience_score
        if exp >= 90:
            return "Strong experience match — candidate meets or exceeds requirements."
        if exp >= 70:
            return "Adequate experience — candidate is close to requirements."
        if exp >= 50:
            return "Partial experience match — some gap in years."
        return "Significant experience gap — candidate falls short of requirements."

    def _build_skill_narrative(self, match: MatchResult) -> tuple:
        if match.matched_skills:
            strengths = f"Strengths: strong alignment on {', '.join(match.matched_skills[:5])}."
        else:
            strengths = "Strengths: no direct skill matches found from the job requirements."

        if match.missing_skills:
            gaps = f"Gaps: missing {', '.join(match.missing_skills[:5])}."
        else:
            gaps = "Gaps: all required skills are present."
        return strengths, gaps

    def _infer_transferable(self, match: MatchResult) -> List[str]:
        inferred = [s for s in match.matched_skills if s.lower() not in {m.lower() for m in match.missing_skills}]
        return inferred[:5]

    def _build_action_plan(self, match: MatchResult) -> str:
        parts = []
        if match.missing_skills:
            parts.append(
                f"Acquire or demonstrate proficiency in: {', '.join(match.missing_skills[:4])}."
            )
        if match.experience_score < 70:
            parts.append("Highlight adjacent or internship experience to offset the experience gap.")
        if not parts:
            parts.append("Candidate is well-aligned. No major gaps identified.")
        return "Action Plan: " + " ".join(parts)

    def _llm_justification(self, match: MatchResult, resume: ParsedResume, job_title: str) -> str:
        prompt = (
            f"Write a 2-3 sentence justification for this match score.\n"
            f"Score: {match.overall_score}/100\n"
            f"Skills: {', '.join(match.matched_skills)} matched, "
            f"{', '.join(match.missing_skills)} missing.\n"
            f"Experience: {resume.total_years_experience}y candidate.\n"
            f"Job: {job_title or 'Not specified'}\n"
            f"Keep it concise and professional."
        )
        try:
            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False, "temperature": 0.3},
                timeout=30,
            )
            if resp.status_code == 200:
                text = resp.json().get("response", "").strip()
                if text:
                    return text
        except Exception as e:
            logger.warning("LLM justification failed, using template", error=str(e))

        strengths, gaps = self._build_skill_narrative(match)
        return (
            f"Match score of {match.overall_score}/100. "
            f"{strengths} {gaps}"
        )
