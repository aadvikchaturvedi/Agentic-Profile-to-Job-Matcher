import sys
import json
import re
import random
from typing import List, Optional, Dict, Any
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
from loguru import logger

from models import ParsedResume, JobDescription, MatchResult
from app.core.config import settings
from app.utils.json_utils import extract_json_from_response


SKILL_SYNONYMS: Dict[str, List[str]] = {
    "machine learning": ["ml", "machinelearning", "machine-learning"],
    "deep learning": ["dl", "deeplearning", "deep-learning"],
    "natural language processing": ["nlp", "naturallanguageprocessing"],
    "computer vision": ["cv", "computervision"],
    "artificial intelligence": ["ai", "artificialintelligence"],
    "react": ["reactjs", "react.js", "react-js"],
    "node.js": ["node", "nodejs", "node-js"],
    "typescript": ["ts", "type-script"],
    "javascript": ["js", "java-script"],
    "python": ["python3", "python-3", "py"],
    "aws": ["amazon web services", "amazon aws", "aws cloud"],
    "gcp": ["google cloud platform", "google cloud", "gcloud"],
    "azure": ["microsoft azure", "azure cloud"],
    "kubernetes": ["k8s", "kube", "k8"],
    "docker": ["docker container", "containerization"],
    "frontend": ["front-end", "front end", "fe", "frontend development"],
    "backend": ["back-end", "back end", "be", "backend development"],
    "full stack": ["fullstack", "full-stack", "full stack development"],
    "sql": ["mysql", "postgresql", "postgres", "relational database"],
    "nosql": ["mongodb", "cassandra", "dynamodb", "redis"],
    "api": ["rest api", "restful", "rest", "restapi"],
    "graphql": ["gql", "graph-ql"],
    "ci/cd": ["ci", "cd", "cicd", "continuous integration"],
    "devops": ["dev-ops", "dev ops"],
    "data science": ["datascience", "data-science"],
    "data engineering": ["dataengineering", "data-engineering"],
    "software engineering": ["software development", "swe"],
    "oop": ["object oriented", "object-oriented"],
    "agile": ["scrum", "agile/scrum"],
    "git": ["github", "gitlab", "git-"],
    "linux": ["unix", "linux/unix", "posix"],
    "aws lambda": ["lambda", "serverless"],
    "microservices": ["micro-services", "micro services", "microservice"],
    "tensorflow": ["tf", "tensor-flow"],
    "pytorch": ["torch", "py-torch"],
}

class ScoringAgent:
    def __init__(self) -> None:
        self.ollama_url = settings.effective_ollama_url
        self.model = settings.llm_model or settings.ollama_model
        self.weights = self._load_weights()
        self._embedder = None

    @staticmethod
    def _build_synonym_map() -> Dict[str, set]:
        mapping: Dict[str, set] = {}
        for canonical, aliases in SKILL_SYNONYMS.items():
            canonical_lower = canonical.lower()
            mapping.setdefault(canonical_lower, set()).add(canonical_lower)
            for alias in aliases:
                mapping.setdefault(alias.lower(), set()).add(canonical_lower)
                mapping[alias.lower()].add(alias.lower())
        return mapping

    def _load_weights(self) -> Dict[str, Any]:
        try:
            import yaml
            with open(settings.weights_path) as f:
                data = yaml.safe_load(f)
            w = data.get("weights", {})
            self._relevance_sub_weights = data.get("relevance", {})
            emb_cfg = data.get("embeddings", {})
            if emb_cfg.get("enabled", False) and not settings.enable_embeddings:
                settings.enable_embeddings = True
            if emb_cfg.get("model"):
                settings.embedding_model = emb_cfg["model"]
            logger.info("Loaded YAML scoring weights", weights=w)
            return w
        except Exception as e:
            logger.warning("Failed to load YAML weights, using defaults", error=str(e))
            self._relevance_sub_weights = {}
            return {"skills": 0.50, "experience": 0.30, "relevance": 0.20}

    @property
    def embedder(self):
        if self._embedder is None and settings.enable_embeddings:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer(settings.embedding_model)
                logger.info("Loaded embedding model", model=settings.embedding_model)
            except ImportError:
                logger.warning("sentence-transformers not installed, embeddings disabled")
            except Exception as e:
                logger.warning("Failed to load embedding model", error=str(e))
        return self._embedder

    def score(self, resume: ParsedResume, job: JobDescription) -> MatchResult:
        skills_score, matched_skills, missing_skills, skill_details = self._score_skills(
            resume.core_skills, job.required_skills, job.preferred_skills
        )
        experience_score, exp_details = self._score_experience(
            resume.total_years_experience, job.min_years_experience
        )
        relevance_score, rel_details = self._score_relevance(resume, job)

        w = self.weights
        overall = (
            skills_score * w.get("skills", 0.50)
            + experience_score * w.get("experience", 0.30)
            + relevance_score * w.get("relevance", 0.20)
        )

        logger.info(
            "Scoring complete",
            skills_score=round(skills_score, 1),
            experience_score=round(experience_score, 1),
            relevance_score=round(relevance_score, 1),
            overall=round(overall, 1),
        )

        return MatchResult(
            skills_score=round(skills_score, 1),
            experience_score=round(experience_score, 1),
            relevance_score=round(relevance_score, 1),
            overall_score=round(overall, 1),
            matched_skills=matched_skills,
            missing_skills=missing_skills,
            skill_details=skill_details,
            experience_details=exp_details,
            relevance_details=rel_details,
        )

    def _score_skills(
        self, core_skills: List[str], required: List[str], preferred: List[str]
    ) -> tuple:
        all_relevant = required + preferred
        if not all_relevant:
            return 100.0, [], [], "No skills listed in job description."

        ollama_result = self._ollama_skill_match(core_skills, required, preferred)
        if ollama_result is not None:
            return ollama_result

        return self._static_skill_match(core_skills, required, preferred, all_relevant)

    def _ollama_skill_match(
        self, core_skills: List[str], required: List[str], preferred: List[str]
    ) -> Optional[tuple]:
        if not core_skills or not required:
            return None
        prompt = (
            f"Compare the candidate's skills with the job's required and preferred skills.\n\n"
            f"Candidate skills: {', '.join(core_skills)}\n"
            f"Job required skills: {', '.join(required)}\n"
            f"Job preferred skills: {', '.join(preferred)}\n\n"
            f"Return ONLY valid JSON with these exact keys (no extra text):\n"
            f'{{"matched": ["skill1", "skill2"], "missing": ["skill3"], '
            f'"details": "Matched X/Y skills. Matched: ... Missing: ..."}}\n'
            f'A skill "matches" if the candidate has an equivalent skill '
            f'(e.g. "ML" matches "Machine Learning", "ReactJS" matches "React", '
            f'"AWS" matches "Amazon Web Services", "TS" matches "TypeScript").'
        )
        try:
            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False, "temperature": 0.1},
                timeout=30,
            )
            if resp.status_code == 200:
                text = resp.json().get("response", "")
                data = extract_json_from_response(text)
                if data and "matched" in data and "missing" in data:
                    matched = data["matched"]
                    missing_req = data["missing"]
                    all_relevant = required + preferred
                    if not all_relevant:
                        return 100.0, [], [], "No skills listed in job description."
                    score = (len(matched) / max(len(set(all_relevant)), 1)) * 100
                    details = data.get("details", f"Matched {len(matched)}/{len(set(all_relevant))} skills.")
                    return round(score, 1), matched, missing_req, details
        except requests.exceptions.ConnectionError:
            logger.warning("Ollama unavailable for skill matching, using static matching")
        except Exception as e:
            logger.warning("Ollama skill matching failed", error=str(e))
        return None

    def _static_skill_match(
        self, core_skills: List[str], required: List[str], preferred: List[str],
        all_relevant: List[str]
    ) -> tuple:
        core_set = {s.lower() for s in core_skills}
        core_words = set()
        for s in core_skills:
            for w in s.lower().replace("-", " ").replace("/", " ").split():
                if len(w) > 1:
                    core_words.add(w)

        synonym_map = self._build_synonym_map()

        def normalize(skill: str) -> set:
            lowered = skill.lower().strip()
            if lowered in synonym_map:
                return synonym_map[lowered]
            return {lowered}

        def skill_matches(job_skill: str) -> bool:
            job_norms = normalize(job_skill)
            for cs in core_skills:
                core_norms = normalize(cs)
                if job_norms & core_norms:
                    return True
            for jn in job_norms:
                if jn in core_set:
                    return True
                words = jn.replace("-", " ").replace("/", " ").split()
                if any(w in core_words for w in words if len(w) > 1):
                    return True
            return False

        matched = [s for s in required if skill_matches(s)]
        matched += [s for s in preferred if skill_matches(s) and s not in matched]
        missing_req = [s for s in required if not skill_matches(s)]

        score = (len(matched) / max(len(set(all_relevant)), 1)) * 100
        details = f"Matched {len(matched)}/{len(set(all_relevant))} skills."
        if matched:
            details += f" Matched: {', '.join(matched)}."
        if missing_req:
            details += f" Missing required: {', '.join(missing_req)}."

        return score, matched, missing_req, details

    def _score_experience(self, candidate_years: float, required_years: float) -> tuple:
        if required_years <= 0:
            return 100.0, "No minimum experience required."

        if candidate_years >= required_years:
            score = 100.0
            details = (
                f"Candidate has {candidate_years}y vs {required_years}y required (exceeds)."
            )
        else:
            score = (candidate_years / required_years) * 100
            details = (
                f"Candidate has {candidate_years}y vs {required_years}y required "
                f"(short by {required_years - candidate_years}y)."
            )

        return round(min(score, 100), 1), details

    def _score_relevance(self, resume: ParsedResume, job: JobDescription) -> tuple:
        emb_score = self._embedding_relevance(resume, job)
        if emb_score is not None:
            return emb_score, f"Embedding similarity score: {emb_score}/100"

        return self._llm_relevance(resume, job)

    def _embedding_relevance(self, resume: ParsedResume, job: JobDescription) -> Optional[float]:
        emb = self.embedder
        if emb is None:
            return None
        try:
            resume_text = f"{resume.current_title or ''} {' '.join(resume.core_skills)}"
            job_text = f"{job.title} {' '.join(job.required_skills)} {' '.join(job.critical_keywords)}"
            vectors = emb.encode([resume_text, job_text])
            from numpy import dot
            from numpy.linalg import norm
            sim = dot(vectors[0], vectors[1]) / (norm(vectors[0]) * norm(vectors[1]) + 1e-8)
            score = max(0, min(100, (sim + 1) * 50))
            logger.debug("Embedding relevance", similarity=round(sim, 4), score=round(score, 1))
            return round(score, 1)
        except Exception as e:
            logger.warning("Embedding relevance failed", error=str(e))
            return None

    def _llm_relevance(self, resume: ParsedResume, job: JobDescription) -> tuple:
        prompt = (
            f"Rate the relevance of this candidate profile to this job description "
            f"on a scale of 0-100.\n\n"
            f"CANDIDATE:\n"
            f"Title: {resume.current_title}\n"
            f"Skills: {', '.join(resume.core_skills)}\n"
            f"Highlights: {'; '.join(resume.experience_highlights)}\n\n"
            f"JOB:\n"
            f"Title: {job.title}\n"
            f"Required: {', '.join(job.required_skills)}\n"
            f"Keywords: {', '.join(job.critical_keywords)}\n\n"
            f"Return ONLY a number 0-100. No explanation."
        )
        try:
            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False, "temperature": 0.1},
                timeout=30,
            )
            if resp.status_code == 200:
                text = resp.json().get("response", "")
                m = re.search(r"(\d{1,3})", text)
                if m:
                    score = min(max(float(m.group(1)), 0), 100)
                    return score, f"LLM relevance score: {score}/100"

            keywords = set(k.lower() for k in job.critical_keywords)
            resume_text = " ".join(resume.core_skills).lower()
            if keywords:
                overlap = sum(1 for k in keywords if k in resume_text)
                score = (overlap / len(keywords)) * 100
                return score, f"Keyword overlap score: {score}/100"
            return 50.0, "Default relevance (no keywords to compare)."

        except requests.exceptions.ConnectionError:
            if job.critical_keywords:
                keywords = set(k.lower() for k in job.critical_keywords)
                resume_text = " ".join(resume.core_skills).lower()
                overlap = sum(1 for k in keywords if k in resume_text)
                score = (overlap / len(keywords)) * 100
                return score, f"Keyword overlap score (Ollama unavailable): {score}/100"
            return 50.0, "Default relevance (Ollama unavailable)."
        except Exception:
            return 50.0, "Default relevance (error in LLM call)."
