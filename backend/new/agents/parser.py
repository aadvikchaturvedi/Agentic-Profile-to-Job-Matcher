from bs4 import BeautifulSoup
from loguru import logger
from new.agents.base import BaseAgent, LLMClient, EventCallback
from new.llm_client import LLMClient as LLMClientImpl


JOB_INDICATORS = [
    "job", "position", "opening", "career", "employment",
    "hiring", "role", "vacancy",
]
TITLE_INDICATORS = [
    "engineer", "developer", "manager", "analyst", "designer",
    "scientist", "architect", "consultant", "specialist",
    "coordinator", "associate", "intern", "lead", "head",
    "director", "president", "officer", "admin",
    "technician", "representative", "assistant",
]


class ParserAgent(BaseAgent):
    def __init__(
        self,
        llm_client: LLMClientImpl = None,
        on_event: EventCallback = None,
    ):
        super().__init__("parser", llm_client, on_event)

    def _find_job_cards_heuristic(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        candidates = []

        containers = soup.find_all(["div", "li", "article", "section", "tr"])
        for el in containers:
            text = el.get_text(separator=" ", strip=True)
            if len(text) < 30 or len(text) > 3000:
                continue
            class_str = " ".join(el.get("class", [])).lower() if el.get("class") else ""
            id_str = (el.get("id", "") or "").lower()
            combined = class_str + " " + id_str

            if not any(
                ind in combined or ind in text[:200].lower()
                for ind in JOB_INDICATORS + ["job-card", "jobcard", "listing"]
            ):
                continue

            links = el.find_all("a", href=True)
            link = links[0]["href"] if links else ""
            title_el = el.find(["h2", "h3", "h4", "a", "strong", "span"])
            title = title_el.get_text(strip=True) if title_el else ""
            if not title or not any(ti in title.lower() for ti in TITLE_INDICATORS):
                continue

            company_el = el.find(
                lambda tag: tag.name in ["div", "span", "p", "a"]
                and tag.get("class")
                and any("company" in " ".join(tag.get("class", [])).lower() for tag in [tag])
            )
            if not company_el:
                company_el = el.find(["span", "div", "p", "small"])
                while company_el and (
                    company_el.get_text(strip=True) == title
                    or not company_el.get_text(strip=True)
                ):
                    company_el = company_el.find_next(["span", "div", "p", "small"])

            company = company_el.get_text(strip=True) if company_el else ""
            if company and title and company.lower() != title.lower()[:len(company)]:
                candidates.append({
                    "title": title,
                    "company": company,
                    "text_snippet": text[:500],
                    "link": link if link.startswith("http") else "",
                })
        return candidates

    async def _parse_with_llm(self, html_snippets: list[str]) -> list[dict]:
        # Skip the LLM call entirely when there's nothing meaningful to parse.
        if not html_snippets or not any((s or "").strip() for s in html_snippets):
            return []

        prompt = (
            "You are a job listing parser. Extract structured job data from the "
            "following HTML snippets. For each job, extract: title, company, "
            "location (if found), and any salary information.\n\n"
            "Return a JSON array of objects with keys: title, company, "
            "location_raw, salary_text, source_snippet.\n"
            "If you cannot find any jobs, return an empty array [].\n"
            "Do NOT wrap in markdown code blocks.\n\n"
            "HTML snippets:\n"
        )
        for i, snippet in enumerate(html_snippets[:5], 1):
            prompt += f"\n--- snippet {i} ---\n{snippet[:1500]}\n"

        try:
            raw = await self.llm_client.complete(prompt)
            # Use the shared robust JSON parser so markdown fences and
            # preamble text are handled correctly.
            data = LLMClientImpl.parse_json(raw)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "jobs" in data:
                jobs_value = data["jobs"]
                return jobs_value if isinstance(jobs_value, list) else []
            return []
        except Exception as e:
            logger.error(
                "[AGENT:ParserAgent] _parse_with_llm failed: {}: {}",
                type(e).__name__,
                e,
            )
            return []

    async def run(self, context: dict) -> dict:
        run_id = context.get("run_id", "?")
        pages = context.get("pages", [])
        logger.info("[AGENT:ParserAgent] run() ENTERED for run_id={}", run_id)

        # Handle empty/None input gracefully: no pages at all OR every
        # page is missing/empty HTML. Emit ``completed`` so the pipeline
        # can continue with an empty job list.
        if not pages or not any((p or {}).get("html", "").strip() for p in pages):
            logger.info(
                "ParserAgent: no usable pages to parse (pages={}, run_id={})",
                len(pages) if pages else 0,
                run_id,
            )
            await self.emit("completed", "No pages to parse")
            return {"jobs": [], "total": 0}

        await self.emit("started", f"Parsing {len(pages)} page(s) for job listings")
        all_jobs = []
        all_snippets = []

        for page in pages:
            html = page.get("html", "")
            url = page.get("url", "")
            await self.emit(
                "progress",
                f"Heuristic parsing page {page.get('page_num', '?')}...",
            )
            cards = self._find_job_cards_heuristic(html)
            for c in cards:
                c["source_url"] = url
                c["page_num"] = page.get("page_num", 1)
            all_jobs.extend(cards)
            all_snippets.append(
                f"--- Page {page.get('page_num', '?')}: {url} ---\n"
                + "\n".join(
                    f"Title: {c['title']} | Company: {c['company']}"
                    for c in cards[:10]
                )
            )

        await self.emit(
            "progress",
            f"Heuristic parsing found {len(all_jobs)} candidate(s)",
        )

        if len(all_jobs) < 2 and pages:
            await self.emit(
                "progress",
                "Few results found, attempting LLM-assisted extraction...",
            )
            html_for_llm = [p.get("html", "")[:8000] for p in pages[:3]]
            llm_jobs = await self._parse_with_llm(html_for_llm)
            existing_titles = {j["title"].lower() for j in all_jobs}
            for j in llm_jobs:
                if j.get("title", "").lower() not in existing_titles:
                    j["source_url"] = pages[0].get("url", "")
                    j["page_num"] = 1
                    j["from_llm"] = True
                    all_jobs.append(j)

        await self.emit(
            "completed",
            f"Parsed {len(all_jobs)} total job(s)",
        )
        return {"jobs": all_jobs, "total": len(all_jobs)}
