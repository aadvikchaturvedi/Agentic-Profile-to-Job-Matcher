from pydantic import BaseModel, Field
from typing import List, Optional

class JobDescription(BaseModel):
    title: str
    company: Optional[str] = None
    min_years_experience: float
    required_skills: List[str]
    preferred_skills: List[str] = []
    critical_keywords: List[str] = []

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

class AgentResponse(BaseModel):
    status: str = "success"
    overall_match_score: int = Field(..., ge=0, le=100)
    experience_fit_verdict: str
    skill_analysis: SkillGapAnalysis
    justification_summary: str
    parsed_candidate_profile: ParsedResume