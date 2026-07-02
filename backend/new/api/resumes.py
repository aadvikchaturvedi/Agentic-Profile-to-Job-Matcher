import json
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from sqlmodel import Session, select

from new.db import engine
from new.models import Resume
from new.llm_client import LLMClient

router = APIRouter(prefix="/api/new/resumes", tags=["new-resumes"])


async def _parse_resume_text(raw_text: str) -> dict:
    from new.config import settings
    llm = LLMClient(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key=settings.groq_api_key
    )
    prompt = (
        "Extract a structured profile from this resume text. "
        "Return JSON with keys: skills (list of strings), "
        "years_experience (float, total years of professional experience), "
        "titles_held (list of job title strings), "
        "seniority_level (one of: entry, mid, senior, lead, executive).\n\n"
        "Resume text:\n" + raw_text[:8000]
    )
    try:
        raw = await llm.complete(prompt)
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)
        data = json.loads(cleaned)
        return {
            "skills": data.get("skills", []),
            "years_experience": data.get("years_experience"),
            "titles_held": data.get("titles_held", []),
            "seniority_level": data.get("seniority_level"),
        }
    except Exception:
        # Fallback: basic heuristic extraction
        return _fallback_parse(raw_text)


def _fallback_parse(text: str) -> dict:
    lines = text.split("\n")
    skills = []
    years = None
    titles = []
    seniority = "mid"

    skill_keywords = {
        "python", "javascript", "typescript", "java", "go", "rust",
        "react", "angular", "vue", "node", "django", "flask",
        "aws", "docker", "kubernetes", "sql", "git", "linux",
    }
    text_lower = text.lower()
    for kw in skill_keywords:
        if kw in text_lower:
            skills.append(kw)

    yr_match = re.search(r"(\d+)\s*\+?\s*years?", text_lower)
    if yr_match:
        years = float(yr_match.group(1))

    for line in lines[:20]:
        line = line.strip()
        if re.search(r"(engineer|developer|manager|lead|director|architect|intern)", line, re.I):
            titles.append(line[:60])

    title_text = " ".join(titles).lower()
    if any(w in title_text for w in ("director", "vp", "chief", "head", "president")):
        seniority = "executive"
    elif any(w in title_text for w in ("lead", "senior", "staff", "principal")):
        seniority = "senior"
    elif any(w in title_text for w in ("junior", "graduate", "intern")):
        seniority = "entry"

    return {
        "skills": skills,
        "years_experience": years,
        "titles_held": titles,
        "seniority_level": seniority,
    }


async def _extract_text_from_file(file: UploadFile) -> str:
    content = await file.read()
    if file.filename and file.filename.lower().endswith(".pdf"):
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return content.decode("utf-8", errors="replace")


@router.post("", response_model=dict)
async def upload_resume(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    allowed_types = {
        "application/pdf",
        "text/plain",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    if file.content_type and file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail="Only PDF, text, and Word documents are supported.",
        )

    try:
        raw_text = await _extract_text_from_file(file)
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Could not extract text from file",
        )
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from file")

    parsed = await _parse_resume_text(raw_text)

    with Session(engine) as session:
        # Deactivate all existing resumes
        existing = session.exec(select(Resume)).all()
        for r in existing:
            r.is_active = False
            session.add(r)

        resume = Resume(
            filename=file.filename,
            raw_text=raw_text[:50000],
            parsed_skills=json.dumps(parsed.get("skills", [])),
            years_experience=parsed.get("years_experience"),
            seniority_level=parsed.get("seniority_level"),
            titles_held=json.dumps(parsed.get("titles_held", [])),
            is_active=True,
        )
        session.add(resume)
        session.commit()
        session.refresh(resume)

    return {
        "id": resume.id,
        "filename": resume.filename,
        "parsed_skills": parsed.get("skills", []),
        "years_experience": parsed.get("years_experience"),
        "seniority_level": parsed.get("seniority_level"),
        "titles_held": parsed.get("titles_held", []),
        "uploaded_at": resume.uploaded_at.isoformat(),
        "is_active": True,
    }


@router.get("/active", response_model=Optional[dict])
async def get_active_resume():
    with Session(engine) as session:
        resume = session.exec(
            select(Resume).where(Resume.is_active == True)
        ).first()
    if not resume:
        return None

    return {
        "id": resume.id,
        "filename": resume.filename,
        "parsed_skills": json.loads(resume.parsed_skills) if resume.parsed_skills else [],
        "years_experience": resume.years_experience,
        "seniority_level": resume.seniority_level,
        "titles_held": json.loads(resume.titles_held) if resume.titles_held else [],
        "uploaded_at": resume.uploaded_at.isoformat(),
        "is_active": True,
    }


@router.delete("/{resume_id}")
async def delete_resume(resume_id: str):
    with Session(engine) as session:
        resume = session.get(Resume, resume_id)
        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found")
        session.delete(resume)
        session.commit()
    return {"status": "deleted"}
