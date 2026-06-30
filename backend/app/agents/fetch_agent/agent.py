import sys
import json
import re
import random
from typing import List, Optional, Set, Dict, Any, cast
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page, Browser, Playwright, TimeoutError as PlaywrightTimeout
from loguru import logger

from models import JobDescription
from app.core.config import settings
from app.utils.json_utils import extract_json_from_response

COMMON_TECH_SKILLS: Set[str] = {
    # Languages
    "Python", "JavaScript", "TypeScript", "Java", "Go", "Rust", "C++", "C#",
    "Ruby", "PHP", "Kotlin", "Swift", "Scala", "Perl", "R", "MATLAB",
    "Shell", "Bash", "HTML", "CSS", "Sass", "LESS",
    # Frontend
    "React", "Vue", "Angular", "Next.js", "Nuxt", "Svelte", "Solid",
    "jQuery", "Bootstrap", "Tailwind", "Redux", "Zustand", "Webpack",
    "Vite", "Babel", "ESLint", "Prettier",
    # Backend
    "Node.js", "Express", "Django", "Flask", "FastAPI", "Spring Boot",
    "Ruby on Rails", "ASP.NET", "Laravel", "Phoenix", "Gin",
    "GraphQL", "REST", "gRPC", "WebSocket",
    # Cloud & Infrastructure
    "AWS", "Azure", "GCP", "Docker", "Kubernetes", "Terraform",
    "Ansible", "Puppet", "Chef", "CloudFormation", "CDK",
    "CI/CD", "Jenkins", "GitHub Actions", "GitLab CI", "CircleCI",
    # Databases
    "PostgreSQL", "MySQL", "SQLite", "MongoDB", "Redis", "Elasticsearch",
    "Cassandra", "DynamoDB", "CouchDB", "Neo4j", "ClickHouse",
    "SQL", "NoSQL",
    # Data & ML
    "Machine Learning", "Deep Learning", "NLP", "Computer Vision",
    "TensorFlow", "PyTorch", "scikit-learn", "Keras", "XGBoost",
    "LightGBM", "Pandas", "NumPy", "Jupyter", "Hugging Face",
    "LLM", "LangChain", "RAG", "Vector Database",
    "Kafka", "Spark", "Hadoop", "Flink", "Airflow", "dbt",
    "Data Engineering", "Data Science", "Data Analysis", "Data Pipeline",
    # DevOps & Tools
    "Git", "Linux", "Unix", "Agile", "Scrum", "Jira", "Confluence",
    "System Design", "Microservices", "API", "DevOps", "SRE",
    "Monitoring", "Prometheus", "Grafana", "Datadog", "New Relic",
    # Testing
    "Jest", "Pytest", "Mocha", "Cypress", "Selenium", "Playwright",
    "Unit Testing", "Integration Testing", "E2E Testing", "TDD",
    # Soft skills
    "Communication", "Leadership", "Problem Solving", "Teamwork",
    "Mentoring", "Project Management", "Product Management",
}


class FetchAgent:
    def __init__(
        self,
        ollama_base_url: Optional[str] = None,
        ollama_model: Optional[str] = None,
        headless: Optional[bool] = None,
    ) -> None:
        self.ollama_base_url = ollama_base_url or settings.effective_ollama_url
        self.model_name = ollama_model or settings.llm_model or settings.ollama_model
        self.headless = headless if headless is not None else settings.headless
        self._ollama_available: Optional[bool] = None
        self._playwright: Optional[Any] = None
        self._browser: Optional[Browser] = None
        self._proxies = settings.proxy_list_parsed
        self._proxy_index = 0
        self._cookie_file = settings.cookie_file or Path("fetch_cookies.json")
        logger.debug(
            "FetchAgent initialized",
            headless=self.headless,
            proxies=len(self._proxies),
            model=self.model_name,
        )

    def _get_user_agent(self) -> str:
        try:
            from fake_useragent import UserAgent
            return UserAgent(os=["mac", "windows"]).random
        except ImportError:
            return (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            )

    def _next_proxy(self) -> Optional[str]:
        if not self._proxies:
            return None
        proxy = self._proxies[self._proxy_index % len(self._proxies)]
        self._proxy_index += 1
        logger.debug("Using proxy", proxy=proxy)
        return proxy

    def _ensure_browser(self) -> None:
        if self._browser is None:
            pw = sync_playwright().start()
            self._playwright = pw
            launch_opts: Dict[str, Any] = {"headless": self.headless}
            proxy = self._next_proxy()
            if proxy:
                launch_opts["proxy"] = {"server": proxy}
            self._browser = pw.chromium.launch(**launch_opts)
            self._load_cookies()

    def close(self) -> None:
        if self._browser:
            self._save_cookies()
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None

    def __del__(self) -> None:
        if self._browser or self._playwright:
            try:
                self.close()
            except Exception:
                pass

    def _load_cookies(self) -> None:
        cookie_path = Path(str(self._cookie_file))
        if cookie_path.exists():
            try:
                cookies = json.loads(cookie_path.read_text())
                context = self._browser.contexts[0] if self._browser and self._browser.contexts else None
                if context:
                    context.add_cookies(cookies)
                    logger.info("Loaded cookies from file", path=str(cookie_path), count=len(cookies))
            except Exception as e:
                logger.warning("Failed to load cookies", error=str(e))

    def _save_cookies(self) -> None:
        if not self._browser or not self._browser.contexts:
            return
        try:
            cookies = self._browser.contexts[0].cookies()
            Path(str(self._cookie_file)).write_text(json.dumps(cookies, indent=2))
            logger.debug("Saved cookies", path=str(self._cookie_file), count=len(cookies))
        except Exception as e:
            logger.warning("Failed to save cookies", error=str(e))

    def _new_page(self) -> Page:
        self._ensure_browser()
        browser = cast(Browser, self._browser)
        context = browser.contexts[0] if browser.contexts else browser.new_context(
            user_agent=self._get_user_agent(),
            viewport={"width": 1280, "height": 1024},
        )
        page = context.new_page()
        return page

    def ollama_available(self) -> bool:
        if self._ollama_available is not None:
            return self._ollama_available
        try:
            import requests
            r = requests.get(f"{self.ollama_base_url}/api/tags", timeout=5)
            self._ollama_available = r.status_code == 200
        except Exception:
            self._ollama_available = False
        return self._ollama_available

    def parse_job_text_to_jd(self, raw_text: str) -> Optional[JobDescription]:
        return self._parse_from_text(raw_text)

    def fetch_jobs(self, query: str, location: str = "", max_per_source: int = 5) -> List[JobDescription]:
        logger.info("Fetching jobs", query=query, location=location or "(any)")

        all_jobs: List[JobDescription] = []
        scrapers: List[BaseScraper] = [
            LinkedInScraper(self._new_page(), self),
            NaukriScraper(self._new_page(), self),
            UnstopScraper(self._new_page(), self),
            GlassdoorScraper(self._new_page(), self),
        ]

        for scraper in scrapers:
            try:
                jobs = scraper.search(query, location, max_per_source)
                logger.info("Scraper results", source=scraper.name, count=len(jobs))
                all_jobs.extend(jobs)
            except Exception as e:
                logger.error("Scraper failed", source=scraper.name, error=str(e))
            finally:
                try:
                    scraper.page.close()
                except Exception:
                    pass

        deduped = self._deduplicate(all_jobs)
        logger.info("Fetch complete", total=len(all_jobs), unique=len(deduped))
        return deduped

    def enrich_job(self, job: JobDescription, raw_text: str) -> JobDescription:
        parsed = self._parse_from_text(raw_text)
        if parsed:
            if not job.title and parsed.title:
                job.title = parsed.title
            if not job.company and parsed.company:
                job.company = parsed.company
            if job.min_years_experience == 0:
                job.min_years_experience = parsed.min_years_experience
            if not job.required_skills:
                job.required_skills = parsed.required_skills
            if not job.preferred_skills:
                job.preferred_skills = parsed.preferred_skills
            if not job.critical_keywords:
                job.critical_keywords = parsed.critical_keywords
        return job

    def _parse_from_text(self, raw_text: str) -> Optional[JobDescription]:
        base = self._regex_parse(raw_text)
        if self.ollama_available():
            llm_result = self._ollama_parse(raw_text)
            if llm_result:
                return JobDescription(
                    title=llm_result.title or base.title,
                    company=llm_result.company or base.company,
                    min_years_experience=llm_result.min_years_experience or base.min_years_experience,
                    required_skills=llm_result.required_skills or base.required_skills,
                    preferred_skills=llm_result.preferred_skills or base.preferred_skills,
                    critical_keywords=llm_result.critical_keywords or base.critical_keywords,
                )
        return base if (base.title or base.required_skills) else None

    REGEX_EXP = re.compile(r'(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp)', re.I)
    REGEX_ANY_NUM_EXP = re.compile(r'(\d+)\+?\s*years?', re.I)
    KNOWN_SKILLS = sorted(COMMON_TECH_SKILLS, key=len, reverse=True)

    def _regex_parse(self, text: str) -> JobDescription:
        low = text.lower()
        exp_match = self.REGEX_EXP.search(low)
        if not exp_match:
            exp_match = self.REGEX_ANY_NUM_EXP.search(text[:500])
        min_exp = float(exp_match.group(1)) if exp_match else 0

        found_skills = [s for s in self.KNOWN_SKILLS if s.lower() in low]

        title = ""
        for line in text.split("\n"):
            line = line.strip()
            if line and len(line) < 120 and not line.startswith("http"):
                title = line
                break
        if not title and text.strip():
            title = text.strip().split(".")[0][:100]

        return JobDescription(
            title=title or "",
            company=None,
            min_years_experience=min_exp,
            required_skills=found_skills,
            preferred_skills=[],
            critical_keywords=found_skills,
        )

    def _ollama_parse(self, text: str) -> Optional[JobDescription]:
        import requests
        prompt = (
            f"You are a job description parser. Analyze the following job posting text "
            f"and extract structured information.\n\nJOB TEXT:\n{text[:3000]}\n\n"
            f"Extract and return ONLY this JSON with no extra text:\n"
            f'{{"title": "Job title", "company": "Company name or null", '
            f'"min_years_experience": 0.0, "required_skills": ["skill1", "skill2"], '
            f'"preferred_skills": ["skill1", "skill2"], '
            f'"critical_keywords": ["keyword1", "keyword2"]}}\n\n'
            f"Rules:\n- title: exact job title\n"
            f"- company: company name if visible, else null\n"
            f"- min_years_experience: minimum years required (e.g. \"3+ years\" -> 3). 0 if not found.\n"
            f"- required_skills: skills marked as required/mandatory\n"
            f"- preferred_skills: skills listed as preferred/nice-to-have\n"
            f"- critical_keywords: key technologies and terms mentioned\n"
            f"Return ONLY valid JSON, no extra text."
        )
        try:
            resp = requests.post(
                f"{self.ollama_base_url}/api/generate",
                json={"model": self.model_name, "prompt": prompt, "stream": False, "temperature": 0.2},
                timeout=60,
            )
            if resp.status_code != 200:
                return None
            return self._json_to_job_description(resp.json().get("response", ""))
        except requests.exceptions.ConnectionError:
            self._ollama_available = False
            return None
        except Exception:
            return None

    def _json_to_job_description(self, text: str) -> Optional[JobDescription]:
        data = extract_json_from_response(text)
        if data is None:
            return None
        try:
            return JobDescription(
                title=data.get("title", ""),
                company=data.get("company"),
                min_years_experience=float(data.get("min_years_experience", 0)),
                required_skills=data.get("required_skills", []),
                preferred_skills=data.get("preferred_skills", []),
                critical_keywords=data.get("critical_keywords", []),
            )
        except (ValueError, TypeError):
            return None

    def _deduplicate(self, jobs: List[JobDescription]) -> List[JobDescription]:
        seen: Set[tuple] = set()
        unique: List[JobDescription] = []
        for j in jobs:
            key = (j.title.lower().strip(), (j.company or "").lower().strip())
            if key not in seen:
                seen.add(key)
                unique.append(j)
        return unique


class BaseScraper:
    name = "base"

    def __init__(self, page: Page, agent: FetchAgent) -> None:
        self.page = page
        self.agent = agent

    def search(self, query: str, location: str, max_results: int) -> List[JobDescription]:
        raise NotImplementedError

    def _navigate(self, url: str, wait_selector: Optional[str] = None) -> Optional[str]:
        try:
            resp = self.page.goto(url, timeout=30000, wait_until="domcontentloaded")
            status = resp.status if resp else None
            if status and status in (403, 429):
                logger.warning("Got status code, cycling proxy", status=status, url=url[:80])
                # Force new browser on next call
                self.agent.close()
                self.agent._ensure_browser()
                return None
            if wait_selector:
                self.page.wait_for_selector(wait_selector, timeout=10000)
            import time
            time.sleep(1.5)
            return self.page.content()
        except (PlaywrightTimeout, Exception) as e:
            logger.warning("Navigation failed", url=url[:80], error=str(e)[:100])
            return None


class LinkedInScraper(BaseScraper):
    name = "LinkedIn"

    def search(self, query: str, location: str, max_results: int) -> List[JobDescription]:
        url = (
            f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
            f"?keywords={query}&location={location or 'United States'}"
        )
        html = self._navigate(url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        cards = []
        for li in soup.select("li")[:max_results]:
            card = self._parse_search_card(li)
            if card:
                cards.append(card)

        jobs: List[JobDescription] = []
        for card in cards:
            job_url = f"https://www.linkedin.com/jobs/view/{card['job_id']}/" if card.get("job_id") else None
            base = JobDescription(
                title=card["title"],
                company=card["company"],
                min_years_experience=0,
                required_skills=[],
                preferred_skills=[],
                critical_keywords=[],
                url=job_url,
                source="LinkedIn",
            )
            raw_text = self._fetch_job_details(card["job_id"]) if card["job_id"] else None
            if raw_text:
                base = self.agent.enrich_job(base, raw_text)
            jobs.append(base)
        return jobs

    def _parse_search_card(self, li) -> Optional[Dict[str, Any]]:
        title_el = li.select_one(".base-search-card__title")
        company_el = li.select_one(".base-search-card__subtitle")
        if not title_el:
            return None
        job_id = self._extract_job_id(li)
        return {
            "title": title_el.get_text(strip=True),
            "company": company_el.get_text(strip=True) if company_el else None,
            "job_id": job_id,
        }

    def _extract_job_id(self, li) -> Optional[str]:
        card = li.select_one("[data-entity-urn]")
        if card:
            urn = card.get("data-entity-urn", "")
            m = re.search(r':(\d+)$', urn)
            if m:
                return m.group(1)
        link = li.select_one("a.base-card__full-link")
        if link:
            href = link.get("href", "")
            m = re.search(r'(\d+)(?:\?|$)', href)
            if m:
                return m.group(1)
        return None

    def _fetch_job_details(self, job_id: str) -> Optional[str]:
        import time
        url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
        try:
            self.page.goto(url, timeout=30000, wait_until="domcontentloaded")
            time.sleep(1.5)
            html = self.page.content()
            soup = BeautifulSoup(html, "html.parser")
            desc = soup.select_one(
                ".description__text, .show-more-less-html__markup, "
                "[class*='description'], .job-description"
            )
            if desc:
                return desc.get_text(" ", strip=True)
            return soup.get_text(" ", strip=True)[:4000]
        except (PlaywrightTimeout, Exception):
            return None


class NaukriScraper(BaseScraper):
    name = "Naukri"

    def search(self, query: str, location: str, max_results: int) -> List[JobDescription]:
        slug = query.lower().replace(" ", "-")
        url = f"https://www.naukri.com/{slug}-jobs"
        if location:
            url += f"-in-{location.lower().replace(' ', '-')}"

        html = self._navigate(url, wait_selector=".jobTuple, .job-card, [class*='job']")
        if not html:
            return self._try_search_api(query, location, max_results)

        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(".jobTuple, .job-card, [class*='job']")
        if not cards:
            return self._try_search_api(query, location, max_results)

        jobs = []
        for card in cards[:max_results]:
            title_el = card.select_one(".title, a[class*='title'], [class*='title']")
            company_el = card.select_one(".subTitle, [class*='company'], [class*='subTitle']")
            link_el = card.select_one("a[href]")
            if not title_el:
                continue
            text = card.get_text(" ", strip=True)
            card_url = link_el.get("href") if link_el else None
            if card_url and not card_url.startswith("http"):
                card_url = f"https://www.naukri.com{card_url}"
            base_job = JobDescription(
                title=title_el.get_text(strip=True),
                company=company_el.get_text(strip=True) if company_el else None,
                min_years_experience=0,
                required_skills=[],
                preferred_skills=[],
                critical_keywords=[],
                url=card_url,
                source="Naukri",
            )
            enriched = self.agent.enrich_job(base_job, text)
            jobs.append(enriched)
        return jobs

    def _try_search_api(self, query: str, location: str, max_results: int) -> List[JobDescription]:
        import requests
        headers = {"Accept": "application/json"}
        req_params: Dict[str, str] = {"q": query}
        if location:
            req_params["location"] = location
        for api_url in [
            "https://www.naukri.com/api/v1/search",
            "https://www.naukri.com/jobsearch/api/v1/search",
        ]:
            try:
                resp = requests.get(api_url, params=req_params, headers=headers, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    jobs_data = (
                        data.get("jobs", []) or data.get("jobDetails", []) or data.get("results", [])
                    )
                    jobs = []
                    for jd in jobs_data[:max_results]:
                        text = json.dumps(jd)
                        job_url = jd.get("url") or jd.get("jobUrl") or ""
                        base_job = JobDescription(
                            title=jd.get("title") or jd.get("jobTitle", ""),
                            company=jd.get("company") or jd.get("companyName"),
                            min_years_experience=float(jd.get("minExperience", 0) or 0),
                            required_skills=jd.get("skills", []) or [],
                            preferred_skills=[],
                            critical_keywords=jd.get("skills", []) or [],
                            url=job_url,
                            source="Naukri",
                        )
                        enriched = self.agent.enrich_job(base_job, text)
                        jobs.append(enriched)
                    return jobs
            except requests.RequestException:
                continue
        return []


class UnstopScraper(BaseScraper):
    name = "Unstop"

    def search(self, query: str, location: str, max_results: int) -> List[JobDescription]:
        import requests
        api_resp = None
        try:
            resp = requests.get(
                "https://unstop.com/api/public/job/list",
                params={"q": query, "page": "1", "per_page": str(max_results)},
                headers={"Accept": "application/json"},
                timeout=15,
            )
            if resp.status_code == 200:
                api_resp = resp.json()
        except Exception:
            pass

        if api_resp:
            try:
                jobs_data = api_resp.get("data", []) or api_resp.get("jobs", []) or []
                jobs = []
                for jd in jobs_data[:max_results]:
                    text = json.dumps(jd)
                    title = jd.get("title") or jd.get("name", "")
                    company = jd.get("company") or jd.get("organization", {}).get("name")
                    job_url = jd.get("url") or jd.get("jobUrl") or ""
                    base_job = JobDescription(
                        title=title,
                        company=company,
                        min_years_experience=0,
                        required_skills=[],
                        preferred_skills=[],
                        critical_keywords=[],
                        url=job_url,
                        source="Unstop",
                    )
                    enriched = self.agent.enrich_job(base_job, text)
                    jobs.append(enriched)
                return jobs
            except (json.JSONDecodeError, KeyError):
                pass

        html = self._navigate(f"https://unstop.com/jobs?q={query}")
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        jobs = []
        for card in soup.select("[class*='job'], [class*='card'], article")[:max_results]:
            text = card.get_text(" ", strip=True)
            if len(text) < 60:
                continue
            link_el = card.select_one("a[href]")
            card_url = link_el.get("href") if link_el else None
            base_job = JobDescription(
                title="", company=None, min_years_experience=0,
                required_skills=[], preferred_skills=[], critical_keywords=[],
                url=card_url,
                source="Unstop",
            )
            enriched = self.agent.enrich_job(base_job, text)
            if enriched.title:
                jobs.append(enriched)
        return jobs


class GlassdoorScraper(BaseScraper):
    name = "Glassdoor"

    def search(self, query: str, location: str, max_results: int) -> List[JobDescription]:
        html = self._navigate(f"https://www.glassdoor.com/Job/jobs.htm?sc.keyword={query}&srs=RECENT_SEARCHES")
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("[data-test='jobListing'], .jobListing, .job-card, article")
        if not cards:
            return []

        jobs = []
        for card in cards[:max_results]:
            text = card.get_text(" ", strip=True)
            if len(text) < 60:
                continue
            link_el = card.select_one("a[href]")
            card_url = link_el.get("href") if link_el else None
            base_job = JobDescription(
                title="", company=None, min_years_experience=0,
                required_skills=[], preferred_skills=[], critical_keywords=[],
                url=card_url,
                source="Glassdoor",
            )
            enriched = self.agent.enrich_job(base_job, text)
            if enriched.title:
                jobs.append(enriched)
        return jobs
