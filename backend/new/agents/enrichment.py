import re
import json
from loguru import logger
from new.agents.base import BaseAgent, LLMClient, EventCallback
from new.llm_client import LLMClient as LLMClientImpl


TECH_TAXONOMY = {
    "python", "javascript", "typescript", "java", "go", "golang", "rust",
    "c++", "c#", "csharp", "ruby", "php", "swift", "kotlin", "scala",
    "react", "reactjs", "angular", "vue", "vuejs", "svelte", "nextjs",
    "node", "nodejs", "express", "django", "flask", "fastapi", "spring",
    "rails", "laravel", "asp.net",
    "postgresql", "postgres", "mysql", "mongodb", "redis", "elasticsearch",
    "sqlite", "mariadb", "cassandra", "dynamodb",
    "aws", "azure", "gcp", "google cloud", "docker", "kubernetes", "k8s",
    "terraform", "ansible", "jenkins", "github actions", "gitlab ci",
    "pytorch", "tensorflow", "scikit-learn", "pandas", "numpy",
    "kafka", "rabbitmq", "redis", "graphql", "rest", "grpc",
    "html", "css", "sass", "tailwind", "bootstrap",
    "git", "linux", "bash", "powershell",
    "agile", "scrum", "jira", "confluence",
}

LOCATION_KEYWORDS = {
    "remote": ["remote", "work from home", "wfh", "anywhere", "virtual", "distributed"],
    "hybrid": ["hybrid", "flexible", "mix"],
    "onsite": ["onsite", "on-site", "in-office", "in office", "on site"],
}

SALARY_PATTERNS = [
    re.compile(r"(?:€|\$|£|INR|USD|EUR|GBP)?\s*(\d{2,3}(?:,\d{3})*(?:\.\d+)?)\s*[-–to]+\s*(?:€|\$|£|INR|USD|EUR|GBP)?\s*(\d{2,3}(?:,\d{3})*(?:\.\d+)?)\s*(?:k|K|/yr|/year|/annum|/pa)?", re.I),
    re.compile(r"(?:€|\$|£|INR|USD|EUR|GBP)?\s*(\d{2,3}(?:,\d{3})*(?:\.\d+)?)\s*(?:k|K)\s*[-–to]+\s*(?:€|\$|£|INR|USD|EUR|GBP)?\s*(\d{2,3}(?:,\d{3})*(?:\.\d+)?)\s*(?:k|K)", re.I),
    re.compile(r"(?:€|\$|£|INR|USD|EUR|GBP)\s*(\d{4,6}(?:,\d{3})*)\s*[-–to]+\s*(?:€|\$|£|INR|USD|EUR|GBP)?\s*(\d{4,6}(?:,\d{3})*)", re.I),
]

CURRENCY_MAP = {
    "$": "USD", "€": "EUR", "£": "GBP", "₹": "INR",
    "usd": "USD", "eur": "EUR", "gbp": "GBP", "inr": "INR",
}


class EnrichmentAgent(BaseAgent):
    def __init__(
        self,
        llm_client: LLMClientImpl = None,
        on_event: EventCallback = None,
    ):
        super().__init__("enrichment", llm_client, on_event)

    def _extract_tech_stack(self, text: str) -> list[str]:
        text_lower = text.lower()
        found = set()
        for tech in TECH_TAXONOMY:
            if tech in text_lower:
                found.add(tech)
        return sorted(found)

    def _infer_location_type(self, text: str) -> tuple[str, str]:
        text_lower = text.lower()
        for ltype, keywords in LOCATION_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    raw = re.search(
                        r".{0,40}" + re.escape(kw) + r".{0,40}",
                        text_lower,
                        re.I,
                    )
                    return ltype, (raw.group(0).strip() if raw else kw)
        return "onsite", ""

    def _normalize_salary(self, text: str) -> tuple:
        for pattern in SALARY_PATTERNS:
            m = pattern.search(text)
            if m:
                g1 = m.group(1).replace(",", "")
                g2 = m.group(2).replace(",", "")
                try:
                    v1 = float(g1)
                    v2 = float(g2)
                except ValueError:
                    continue
                before = text[: m.start()].strip()
                currency = "USD"
                for sym, cur in CURRENCY_MAP.items():
                    if sym in before or sym in text[m.start() : m.end()]:
                        currency = cur
                        break
                if v1 < 1000:
                    v1 *= 1000
                if v2 < 1000:
                    v2 *= 1000
                if v1 > v2:
                    v1, v2 = v2, v1
                return (int(v1), int(v2), currency)
        return (None, None, None)

    def _compute_confidence(self, job: dict) -> float:
        score = 0.0
        weights = {
            "title": 0.25,
            "company": 0.20,
            "tech_stack": 0.20,
            "salary": 0.15,
            "location": 0.10,
            "source_url": 0.10,
        }
        try:
            if job.get("title"):
                score += weights["title"]
            if job.get("company"):
                score += weights["company"]
            if job.get("tech_stack"):
                score += weights["tech_stack"] * min(len(job["tech_stack"]) / 3, 1.0)
            if job.get("salary_min") and job.get("salary_max"):
                score += weights["salary"]
            elif job.get("salary_text"):
                score += weights["salary"] * 0.5
            if job.get("location_raw") or job.get("location_type"):
                score += weights["location"]
            if job.get("source_url"):
                score += weights["source_url"]
            if job.get("from_llm"):
                score *= 0.85
        except Exception as e:
            logger.error(
                "[AGENT:EnrichmentAgent] _compute_confidence error: {}: {}",
                type(e).__name__,
                e,
            )
            score = 0.0
        # Always return a float clamped to [0.0, 1.0]. Never return None
        # or an out-of-range value.
        return float(round(min(max(score, 0.0), 1.0), 2))

    async def run(self, context: dict) -> dict:
        run_id = context.get("run_id", "?")
        raw_jobs = context.get("jobs", [])
        logger.info("[AGENT:EnrichmentAgent] run() ENTERED for run_id={}", run_id)
        if not raw_jobs:
            logger.warning("EnrichmentAgent: no raw jobs to enrich")
            await self.emit("failed", "No raw jobs to enrich")
            return {"enriched_jobs": [], "total": 0}

        await self.emit("started", f"Enriching {len(raw_jobs)} job(s)")
        enriched = []

        for i, job in enumerate(raw_jobs):
            title = job.get("title", "")
            company = job.get("company", "")
            text_snippet = job.get("text_snippet", "") or job.get("source_snippet", "") or ""
            link = job.get("link", "") or job.get("source_url", "")

            combined_text = f"{title} {company} {text_snippet}"

            tech_stack = self._extract_tech_stack(combined_text)
            location_type, location_raw = self._infer_location_type(combined_text)
            salary_min, salary_max, currency = self._normalize_salary(combined_text)

            if not location_raw:
                location_raw = job.get("location_raw") or ""

            enriched_job = {
                "title": title,
                "company": company,
                "location_type": location_type,
                "location_raw": location_raw,
                "salary_min": salary_min,
                "salary_max": salary_max,
                "currency": currency,
                "tech_stack": tech_stack,
                "source_url": link,
            }
            enriched_job["confidence"] = self._compute_confidence(enriched_job)
            enriched.append(enriched_job)

            if (i + 1) % max(1, len(raw_jobs) // 5) == 0 or i == len(raw_jobs) - 1:
                await self.emit(
                    "progress",
                    f"Enriched {i + 1}/{len(raw_jobs)} jobs",
                )

        await self.emit(
            "completed",
            f"Enriched {len(enriched)} jobs (avg confidence: "
            f"{sum(j['confidence'] for j in enriched) / max(len(enriched), 1):.2f})",
        )
        return {"enriched_jobs": enriched, "total": len(enriched)}
