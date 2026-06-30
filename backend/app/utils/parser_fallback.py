import re
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import ParsedResume


EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_RE = re.compile(r"[\+]?[\d\s\-\(\)]{7,20}")
NAME_RE = re.compile(
    r"^([A-Z][a-z]+)\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)",
)
YEARS_RE = re.compile(r"(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp)", re.I)

COMMON_SKILLS: List[str] = [
    "Python", "JavaScript", "TypeScript", "Java", "Go", "Rust", "C++", "C#",
    "React", "Vue", "Angular", "Next.js", "Node.js", "Django", "Flask",
    "FastAPI", "Spring Boot", "Ruby on Rails", "AWS", "Azure", "GCP",
    "Docker", "Kubernetes", "Terraform", "PostgreSQL", "MySQL", "MongoDB",
    "Redis", "Elasticsearch", "GraphQL", "REST", "gRPC", "SQL", "NoSQL",
    "Kafka", "Spark", "Hadoop", "TensorFlow", "PyTorch", "scikit-learn",
    "Machine Learning", "Deep Learning", "NLP", "Computer Vision",
    "CI/CD", "Git", "Linux", "Agile", "Scrum", "DevOps",
    "Communication", "Leadership", "Problem Solving", "Teamwork",
    "Data Engineering", "Data Science", "Data Analysis",
    "System Design", "Microservices", "API",
]


SKILL_SET = {s.lower() for s in sorted(COMMON_SKILLS, key=len, reverse=True)}


def fallback_parse(resume_text: str) -> Optional[ParsedResume]:
    if not resume_text.strip():
        return None

    name = _extract_name(resume_text)
    email = _extract_email(resume_text)
    title = _extract_title(resume_text)
    years = _extract_years(resume_text)
    skills = _extract_skills(resume_text)
    highlights = _extract_highlights(resume_text)

    return ParsedResume(
        name=name or "",
        email=email,
        current_title=title,
        total_years_experience=years,
        core_skills=skills,
        experience_highlights=highlights,
    )


def _extract_name(text: str) -> Optional[str]:
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines[:5]:
        if len(line) < 50 and not EMAIL_RE.search(line):
            m = NAME_RE.match(line)
            if m:
                return line.strip()
    return None


def _extract_email(text: str) -> Optional[str]:
    m = EMAIL_RE.search(text)
    return m.group(0) if m else None


def _extract_title(text: str) -> Optional[str]:
    keywords = [
        "engineer", "developer", "scientist", "analyst", "manager",
        "architect", "designer", "lead", "head", "director", "intern",
        "consultant", "specialist", "associate", "fellow",
    ]
    for line in text.split("\n")[:20]:
        low = line.strip().lower()
        if any(k in low for k in keywords):
            stripped = line.strip()
            if 10 < len(stripped) < 100:
                return stripped
    return None


def _extract_years(text: str) -> float:
    m = YEARS_RE.search(text)
    if m:
        return float(m.group(1))
    return 0.0


def _extract_skills(text: str) -> List[str]:
    low = text.lower()
    found = []
    for skill in sorted(COMMON_SKILLS, key=len, reverse=True):
        if skill.lower() in low:
            found.append(skill)
    return found


def _extract_highlights(text: str) -> List[str]:
    highlights = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("-") or line.startswith("•") or line.startswith("*"):
            clean = line.lstrip("- •*").strip()
            if clean and len(clean) > 20:
                highlights.append(clean)
    return highlights[:5]
