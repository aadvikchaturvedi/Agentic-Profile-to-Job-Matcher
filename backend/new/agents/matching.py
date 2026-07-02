import json
import re
import math
import hashlib
import asyncio
from functools import lru_cache
from typing import Optional
from pydantic import BaseModel

from loguru import logger

from new.agents.base import BaseAgent, EventCallback
from new.llm_client import LLMClient as LLMClientImpl
from new.config import settings


class ScoringSchema(BaseModel):
    match_score: int
    matched_skills: list[str]
    missing_skills: list[str]
    improvement_notes: str
    reasoning: str


SCORING_RUBRIC = (
    "Score each job against the candidate's resume on a 1-10 scale:\n"
    "- 9-10: directly matches title/seniority, nearly all required skills present\n"
    "- 6-8: strong overlap, 1-3 notable skill gaps, comparable seniority\n"
    "- 3-5: partial overlap, meaningfully different seniority or missing core requirements\n"
    "- 1-2: different domain/role entirely, resume not a reasonable fit\n"
    "Respond ONLY with valid JSON. No preamble, no markdown, no code fences."
)

SCORING_TIMEOUT = 60.0

_EMBEDDER_LOCK = asyncio.Lock()
_EMBEDDER_INSTANCE = None
_NUMPY = None
_EMBEDDER_ATTEMPTED = False


async def _try_load_embedder_background():
    """Attempt to load the embedder in a background task. Doesn't block."""
    global _EMBEDDER_INSTANCE, _NUMPY, _EMBEDDER_ATTEMPTED
    if _EMBEDDER_ATTEMPTED:
        return
    _EMBEDDER_ATTEMPTED = True
    try:
        import numpy as np
        _NUMPY = np

        def _load():
            from sentence_transformers import SentenceTransformer
            return SentenceTransformer("all-MiniLM-L6-v2")

        loop = asyncio.get_running_loop()
        model = await asyncio.wait_for(
            loop.run_in_executor(None, _load),
            timeout=15.0,
        )
        _EMBEDDER_INSTANCE = model
    except Exception:
        pass


def _has_embedder() -> bool:
    return _EMBEDDER_INSTANCE is not None and _NUMPY is not None


@lru_cache(maxsize=4096)
def _keyword_overlap(a_words: frozenset, b_words: frozenset) -> float:
    if not a_words or not b_words:
        return 0.0
    intersection = a_words & b_words
    union = a_words | b_words
    return len(intersection) / max(len(union), 1)


def _tokenize(text: str) -> frozenset:
    return frozenset(re.findall(r"[a-z][a-z0-9_+#.]+", text.lower()))


def _make_cache_key(text_a: str, text_b: str) -> str:
    return hashlib.sha256(f"{text_a}|{text_b}".encode()).hexdigest()


class EmbeddingCache:
    """LRU cache for computed embeddings, keyed by text hash."""

    def __init__(self, maxsize: int = 2048):
        self._cache: dict[str, list[float]] = {}
        self._maxsize = maxsize
        self._order: list[str] = []

    def get(self, text: str) -> Optional[list[float]]:
        key = hashlib.sha256(text.encode()).hexdigest()
        return self._cache.get(key)

    def put(self, text: str, vector: list[float]):
        key = hashlib.sha256(text.encode()).hexdigest()
        if key in self._cache:
            self._order.remove(key)
        elif len(self._cache) >= self._maxsize:
            oldest = self._order.pop(0)
            self._cache.pop(oldest, None)
        self._cache[key] = vector
        self._order.append(key)

    @property
    def size(self) -> int:
        return len(self._cache)


_embedding_cache = EmbeddingCache(maxsize=2048)


class MatchingAgent(BaseAgent):
    def __init__(
        self,
        llm_client: LLMClientImpl = None,
        on_event: EventCallback = None,
    ):
        super().__init__("matching", llm_client, on_event)
        self._top_n = 30

    async def _compute_similarity(self, resume_text: str, job_text: str) -> float:
        if _has_embedder():
            try:
                cached = _embedding_cache.get(job_text)
                r_cached = _embedding_cache.get(resume_text)
                if cached is not None and r_cached is not None:
                    return float(_NUMPY.dot(_NUMPY.array(r_cached), _NUMPY.array(cached)))

                loop = asyncio.get_running_loop()
                vecs = await loop.run_in_executor(
                    None,
                    lambda: _EMBEDDER_INSTANCE.encode(
                        [resume_text, job_text], normalize_embeddings=True
                    ),
                )
                _embedding_cache.put(resume_text, vecs[0].tolist())
                _embedding_cache.put(job_text, vecs[1].tolist())
                return float(_NUMPY.dot(vecs[0], vecs[1]))
            except Exception:
                pass
        r_tokens = _tokenize(resume_text)
        j_tokens = _tokenize(job_text)
        return _keyword_overlap(r_tokens, j_tokens)

    async def _llm_score_job(
        self, resume_profile: dict, job: dict, similarity: float
    ) -> Optional[dict]:
        prompt = (
            f"{SCORING_RUBRIC}\n\n"
            f"Candidate Resume:\n"
            f"  Skills: {', '.join(resume_profile.get('skills', []))}\n"
            f"  Years Experience: {resume_profile.get('years_experience', 'N/A')}\n"
            f"  Titles Held: {', '.join(resume_profile.get('titles_held', []))}\n"
            f"  Seniority: {resume_profile.get('seniority_level', 'N/A')}\n\n"
            f"Job:\n"
            f"  Title: {job.get('title', '')}\n"
            f"  Company: {job.get('company', '')}\n"
            f"  Tech Stack: {', '.join(job.get('tech_stack', []))}\n"
            f"  Description: {job.get('text_snippet', '')[:2000]}\n"
            f"  Embedding Similarity: {similarity:.3f}\n"
        )

        raw = ""
        for attempt in range(2):  # original + 1 retry
            try:
                raw = await self.llm_client.complete(prompt, expect_json=True)
                data = LLMClientImpl.parse_json(raw)
                return {
                    "match_score": min(10, max(1, int(data.get("match_score", 5)))),
                    "matched_skills": data.get("matched_skills", []),
                    "missing_skills": data.get("missing_skills", []),
                    "improvement_notes": data.get("improvement_notes", ""),
                    "reasoning": data.get("reasoning", ""),
                    "llm_scored": True,
                }
            except Exception as e:
                logger.error(
                    "LLM scoring attempt {} failed for job '{}': {} | raw={}",
                    attempt + 1,
                    job.get("title", "Unknown"),
                    f"{type(e).__name__}: {e}",
                    repr(raw) if raw else "N/A",
                )
                if attempt == 0:
                    prompt = (
                        "Your previous response was not valid JSON. "
                        "Return ONLY the JSON object, no other text.\n\n"
                        + prompt
                    )
                else:
                    return None

    async def run(self, context: dict) -> dict:
        run_id = context.get("run_id", "?")
        enriched_jobs = context.get("enriched_jobs", [])
        resume = context.get("resume")
        logger.info("[AGENT:MatchingAgent] run() ENTERED for run_id={}", run_id)

        if not resume:
            logger.info("MatchingAgent: no resume, skipping")
            await self.emit("skipped", "No active resume — skipping matching")
            return {"matches": [], "total": 0, "skipped": True}

        # LLM is optional: if it's down, we still score via similarity fallback.
        llm_ok = False
        try:
            llm_ok = await self.llm_client.health_check()
        except Exception as e:
            logger.warning(
                "MatchingAgent: LLM check failed (will fallback): {}: {}",
                type(e).__name__,
                e,
            )
            llm_ok = False

        if not llm_ok:
            logger.warning("MatchingAgent: LLM unavailable at {} — using similarity-only scoring", settings.llm_base_url)
            await self.emit(
                "progress",
                "LLM server is not reachable — using similarity-only scoring. "
                f"(If you want LLM scoring, start Ollama at {settings.llm_base_url})",
            )

        # Fire off background embedder loading (won't block the pipeline)
        asyncio.ensure_future(_try_load_embedder_background())

        resume_skills = resume.get("parsed_skills", [])
        if isinstance(resume_skills, str):
            resume_skills = json.loads(resume_skills)

        resume_profile = {
            "skills": resume_skills,
            "years_experience": resume.get("years_experience"),
            "titles_held": resume.get("titles_held", []),
            "seniority_level": resume.get("seniority_level"),
        }
        if isinstance(resume_profile["titles_held"], str):
            resume_profile["titles_held"] = json.loads(resume_profile["titles_held"])

        if not enriched_jobs:
            await self.emit("completed", "No jobs to match")
            return {"matches": [], "total": 0}

        await self.emit(
            "started",
            f"Pre-filtering {len(enriched_jobs)} jobs...",
        )

        resume_text = (
            f"{' '.join(resume_profile['skills'])} "
            f"{resume_profile.get('years_experience', 0)} years "
            f"{' '.join(resume_profile['titles_held'])}"
        )
        job_texts = [
            f"{j.get('title', '')} {j.get('company', '')} {' '.join(j.get('tech_stack', []))}"
            for j in enriched_jobs
        ]

        try:
            tasks = [
                self._compute_similarity(resume_text, jt) for jt in job_texts
            ]
            similarities = await asyncio.gather(*tasks)
            scored = sorted(
                [(similarities[i], i) for i in range(len(similarities))],
                key=lambda x: x[0],
                reverse=True,
            )
            await self.emit(
                "progress",
                f"Pre-filter complete — top score: {scored[0][0]:.3f} (cache: {_embedding_cache.size} embeddings)",
            )
        except Exception as e:
            await self.emit("failed", f"Pre-filter failed: {str(e)[:80]}")
            return {"matches": [], "total": 0, "error": str(e)}

        total_jobs = len(enriched_jobs)
        llm_count = min(self._top_n, total_jobs) if total_jobs > 50 else total_jobs
        if not llm_ok:
            llm_count = 0

        await self.emit(
            "progress",
            f"LLM-scoring top {llm_count}/{total_jobs} jobs against resume...",
        )

        matches = []
        for rank, (sim, idx) in enumerate(scored):
            job = enriched_jobs[idx]
            job_title = job.get("title", "Unknown")

            if rank < llm_count:
                result = await self._llm_score_job(resume_profile, job, sim)
                if result is None:
                    result = {
                        "match_score": round(1 + 9 * sim, 1),
                        "matched_skills": [],
                        "missing_skills": [],
                        "improvement_notes": "LLM scoring failed — estimated from embedding similarity.",
                        "llm_scored": False,
                        "embedding_similarity": float(sim),
                    }
                else:
                    result["embedding_similarity"] = float(sim)
                result["job_index"] = idx
                matches.append(result)

                if (rank + 1) % max(1, llm_count // 5) == 0 or rank == llm_count - 1:
                    await self.emit(
                        "progress",
                        f"Scored job {rank + 1}/{llm_count}: {job_title[:50]} → {result.get('match_score', '?')}/10",
                    )
            else:
                matches.append({
                    "match_score": round(1 + 9 * sim, 1),
                    "matched_skills": [],
                    "missing_skills": [],
                    "improvement_notes": "Estimated from embedding similarity only.",
                    "llm_scored": False,
                    "embedding_similarity": float(sim),
                    "job_index": idx,
                })

        matches.sort(key=lambda m: m["job_index"])

        llm_count_actual = sum(1 for m in matches if m.get("llm_scored"))
        logger.info("MatchingAgent: completed — {} matches ({} LLM-scored)", len(matches), llm_count_actual)
        await self.emit(
            "completed",
            f"Scored {total_jobs} jobs ({llm_count_actual} LLM-analyzed, "
            f"{total_jobs - llm_count_actual} embedding-estimated)",
        )

        return {"matches": matches, "total": len(matches), "skipped": False}
