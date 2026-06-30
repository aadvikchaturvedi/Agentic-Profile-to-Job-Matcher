from pydantic import BaseModel, Field
from typing import List, Optional


class JobDescription(BaseModel):
    title: str
    company: Optional[str] = None
    min_years_experience: float
    required_skills: List[str]
    preferred_skills: List[str] = []
    critical_keywords: List[str] = []
    url: Optional[str] = None
    source: str = ""


class UserQuery(BaseModel):
    raw_job_description: str
    candidate_id: Optional[str] = None


class ParsedResume(BaseModel):
    name: str
    email: Optional[str] = None
    current_title: Optional[str] = None
    total_years_experience: float
    core_skills: List[str]
    experience_highlights: List[str]


class SkillGapAnalysis(BaseModel):
    matched_skills: List[str]
    missing_skills: List[str]
    transferable_skills: List[str] = []


class MatchResult(BaseModel):
    skills_score: float = Field(..., ge=0, le=100)
    experience_score: float = Field(..., ge=0, le=100)
    relevance_score: float = Field(..., ge=0, le=100)
    overall_score: float = Field(..., ge=0, le=100)
    matched_skills: List[str] = []
    missing_skills: List[str] = []
    skill_details: str = ""
    experience_details: str = ""
    relevance_details: str = ""


class AgentResponse(BaseModel):
    status: str = "success"
    overall_match_score: int = Field(..., ge=0, le=100)
    experience_fit_verdict: str
    skill_analysis: Optional[SkillGapAnalysis] = None
    justification_summary: str
    parsed_candidate_profile: ParsedResume
    action_plan: str = ""
    all_jobs: List[dict] = []


class ProgressUpdate(BaseModel):
    step: str
    message: str
    percent: int = Field(..., ge=0, le=100)
    detail: str = ""
