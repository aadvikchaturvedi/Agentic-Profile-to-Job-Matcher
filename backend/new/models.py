from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import SQLModel, Field, Column, JSON, Text
import uuid


class Run(SQLModel, table=True):
    __tablename__ = "runs"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12], primary_key=True)
    url: str
    max_pages: int = 3
    filters: str = Field(default="{}", sa_type=Text)
    status: str = Field(default="pending")
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    job_count: int = 0
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12], primary_key=True)
    run_id: str = Field(foreign_key="runs.id", index=True)
    title: str = ""
    company: str = ""
    location_type: str = "onsite"
    location_raw: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    currency: Optional[str] = None
    tech_stack: str = Field(default="[]", sa_type=Text)
    confidence: float = 0.0
    source_url: str = ""
    raw_data: Optional[str] = Field(default=None, sa_type=Text)


class RunEvent(SQLModel, table=True):
    __tablename__ = "run_events"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12], primary_key=True)
    run_id: str = Field(foreign_key="runs.id", index=True)
    agent: str = ""
    status: str = ""
    message: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RunCreate(SQLModel):
    url: str
    max_pages: int = 3
    filters: str = "{}"


class RunSummary(SQLModel):
    id: str
    url: str
    domain: str
    status: str
    duration_ms: Optional[int] = None
    job_count: int
    started_at: Optional[datetime] = None
    created_at: datetime
    latest_event: Optional[str] = None


class JobOut(SQLModel):
    id: str
    title: str
    company: str
    location_type: str
    location_raw: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    currency: Optional[str] = None
    tech_stack: List[str]
    confidence: float
    source_url: str

    class Config:
        from_attributes = True


class RunDetail(SQLModel):
    id: str
    url: str
    domain: str
    max_pages: int
    filters: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    job_count: int
    error: Optional[str] = None
    created_at: datetime
    jobs: List[JobOut]
    events: List["RunEventOut"]


class RunEventOut(SQLModel):
    id: str
    agent: str
    status: str
    message: str
    timestamp: datetime

    class Config:
        from_attributes = True


class Resume(SQLModel, table=True):
    __tablename__ = "resumes"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12], primary_key=True)
    filename: str = ""
    raw_text: str = Field(default="", sa_type=Text)
    parsed_skills: str = Field(default="[]", sa_type=Text)
    years_experience: Optional[float] = None
    seniority_level: Optional[str] = None
    titles_held: str = Field(default="[]", sa_type=Text)
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = False


class JobMatch(SQLModel, table=True):
    __tablename__ = "job_matches"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12], primary_key=True)
    job_id: str = Field(foreign_key="jobs.id", index=True)
    resume_id: str = Field(foreign_key="resumes.id", index=True)
    match_score: Optional[float] = None
    matched_skills: str = Field(default="[]", sa_type=Text)
    missing_skills: str = Field(default="[]", sa_type=Text)
    improvement_notes: str = ""
    llm_scored: bool = False
    embedding_similarity: Optional[float] = None


class ResumeOut(SQLModel):
    id: str
    filename: str
    parsed_skills: list[str]
    years_experience: Optional[float] = None
    seniority_level: Optional[str] = None
    titles_held: list[str]
    uploaded_at: str
    is_active: bool


class WSEvent(SQLModel):
    type: str
    data: dict
