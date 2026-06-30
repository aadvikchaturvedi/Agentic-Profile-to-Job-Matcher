import json
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))         # backend/ for app.core.config
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))  # backend/app/ for models

from agents.fetch_agent.agent import (
    FetchAgent,
    LinkedInScraper,
    NaukriScraper,
    UnstopScraper,
    GlassdoorScraper,
)
from models import JobDescription


def _make_page_mock():
    """Return a MagicMock that stands in for a playwright Page."""
    page = MagicMock()
    page.content.return_value = "<html></html>"
    return page


class TestRegexParse(unittest.TestCase):
    def setUp(self):
        self.agent = FetchAgent(ollama_base_url="http://nonexistent:11434")
        self.agent._ollama_available = False

    def test_extract_experience(self):
        jd = self.agent._regex_parse("Software Engineer with 3+ years of experience in Python")
        self.assertEqual(jd.min_years_experience, 3.0)

    def test_extract_experience_variant(self):
        jd = self.agent._regex_parse("Requires 5 years experience in React")
        self.assertEqual(jd.min_years_experience, 5.0)

    def test_no_experience_defaults_to_zero(self):
        jd = self.agent._regex_parse("Entry level position. No experience needed.")
        self.assertGreaterEqual(jd.min_years_experience, 0)

    def test_extract_skills(self):
        jd = self.agent._regex_parse(
            "We need a Python developer with AWS, Docker, and PostgreSQL experience"
        )
        self.assertIn("Python", jd.required_skills)
        self.assertIn("AWS", jd.required_skills)
        self.assertIn("Docker", jd.required_skills)
        self.assertIn("PostgreSQL", jd.required_skills)

    def test_extract_title_from_first_line(self):
        jd = self.agent._regex_parse("Senior Frontend Engineer\nCompany Inc\nDescription...")
        self.assertIn("Senior", jd.title)
        self.assertIn("Frontend", jd.title)


class TestParseJobTextToJd(unittest.TestCase):
    def setUp(self):
        self.agent = FetchAgent(ollama_base_url="http://nonexistent:11434")
        self.agent._ollama_available = False

    def test_fallback_regex(self):
        result = self.agent.parse_job_text_to_jd(
            "Senior DevOps 5+ years AWS Kubernetes"
        )
        self.assertIsNotNone(result)
        self.assertIn("AWS", result.required_skills)


class TestJsonToJobDescription(unittest.TestCase):
    def setUp(self):
        self.agent = FetchAgent(ollama_base_url="http://nonexistent:11434")

    def test_parses_valid_json(self):
        text = (
            '```json\n{"title": "Engineer", "company": "Acme", '
            '"min_years_experience": 3, "required_skills": ["Python"], '
            '"preferred_skills": ["Go"], "critical_keywords": ["AWS"]}\n```'
        )
        result = self.agent._json_to_job_description(text)
        self.assertIsNotNone(result)
        self.assertEqual(result.title, "Engineer")
        self.assertEqual(result.company, "Acme")
        self.assertEqual(result.min_years_experience, 3.0)
        self.assertEqual(result.required_skills, ["Python"])
        self.assertEqual(result.preferred_skills, ["Go"])

    def test_parses_bare_json(self):
        text = (
            '{"title": "Dev", "company": null, "min_years_experience": 0, '
            '"required_skills": [], "preferred_skills": [], "critical_keywords": []}'
        )
        result = self.agent._json_to_job_description(text)
        self.assertIsNotNone(result)
        self.assertEqual(result.title, "Dev")
        self.assertIsNone(result.company)

    def test_returns_none_on_garbage(self):
        result = self.agent._json_to_job_description("not json at all")
        self.assertIsNone(result)


class TestDeduplicate(unittest.TestCase):
    def setUp(self):
        self.agent = FetchAgent(ollama_base_url="http://nonexistent:11434")

    def test_removes_duplicates(self):
        jobs = [
            JobDescription(title="Engineer", company="Acme", min_years_experience=0, required_skills=[], preferred_skills=[], critical_keywords=[]),
            JobDescription(title="Engineer", company="Acme", min_years_experience=2, required_skills=["Python"], preferred_skills=[], critical_keywords=[]),
            JobDescription(title="Designer", company="Beta", min_years_experience=0, required_skills=[], preferred_skills=[], critical_keywords=[]),
        ]
        result = self.agent._deduplicate(jobs)
        self.assertEqual(len(result), 2)

    def test_case_insensitive(self):
        jobs = [
            JobDescription(title="Engineer", company="Acme", min_years_experience=0, required_skills=[], preferred_skills=[], critical_keywords=[]),
            JobDescription(title="engineer", company="ACME", min_years_experience=0, required_skills=[], preferred_skills=[], critical_keywords=[]),
        ]
        result = self.agent._deduplicate(jobs)
        self.assertEqual(len(result), 1)


class TestEnrichJob(unittest.TestCase):
    def setUp(self):
        self.agent = FetchAgent(ollama_base_url="http://nonexistent:11434")
        self.agent._ollama_available = False

    def test_enriches_empty_fields(self):
        job = JobDescription(
            title="Engineer", company=None, min_years_experience=0,
            required_skills=[], preferred_skills=[], critical_keywords=[],
        )
        text = "Software Engineer role. 3+ years experience. Python, AWS, Docker required."
        result = self.agent.enrich_job(job, text)
        self.assertEqual(result.min_years_experience, 3.0)
        self.assertIn("Python", result.required_skills)
        self.assertIn("AWS", result.required_skills)


class TestLinkedInScraper(unittest.TestCase):
    def setUp(self):
        self.agent = FetchAgent(ollama_base_url="http://nonexistent:11434")
        self.agent._ollama_available = False
        self.scraper = LinkedInScraper(_make_page_mock(), self.agent)

    def test_parse_search_card(self):
        from bs4 import BeautifulSoup
        html = """
        <li>
            <div data-entity-urn="urn:li:jobPosting:12345">
                <h3 class="base-search-card__title">Software Engineer</h3>
                <h4 class="base-search-card__subtitle">Acme Corp</h4>
                <a class="base-card__full-link" href="/jobs/view/12345/"></a>
            </div>
        </li>
        """
        soup = BeautifulSoup(html, "html.parser")
        card = self.scraper._parse_search_card(soup.select_one("li"))
        self.assertIsNotNone(card)
        self.assertEqual(card["title"], "Software Engineer")
        self.assertEqual(card["company"], "Acme Corp")
        self.assertEqual(card["job_id"], "12345")

    def test_extract_job_id_from_urn(self):
        from bs4 import BeautifulSoup
        html = '<li><div data-entity-urn="urn:li:jobPosting:98765"></div></li>'
        soup = BeautifulSoup(html, "html.parser")
        job_id = self.scraper._extract_job_id(soup.select_one("li"))
        self.assertEqual(job_id, "98765")

    def test_extract_job_id_from_link(self):
        from bs4 import BeautifulSoup
        html = '<li><a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/engineer-54321?position=1"></a></li>'
        soup = BeautifulSoup(html, "html.parser")
        job_id = self.scraper._extract_job_id(soup.select_one("li"))
        self.assertEqual(job_id, "54321")

    def test_returns_nil_on_no_id(self):
        from bs4 import BeautifulSoup
        html = "<li><div>no link here</div></li>"
        soup = BeautifulSoup(html, "html.parser")
        job_id = self.scraper._extract_job_id(soup.select_one("li"))
        self.assertIsNone(job_id)

    def test_fetch_job_details_extracts_description(self):
        self.scraper.page.content.return_value = """
        <html>
            <div class="description__text">
                We are looking for a Senior Software Engineer with 5+ years experience.
                Required skills: Python, AWS, Docker.
            </div>
        </html>
        """
        result = self.scraper._fetch_job_details("12345")
        self.assertIsNotNone(result)
        self.assertIn("Senior Software Engineer", result)
        self.assertIn("Python", result)
        self.assertIn("AWS", result)

    def test_fetch_job_details_returns_none_on_failure(self):
        self.scraper.page.goto.side_effect = Exception("timeout")
        result = self.scraper._fetch_job_details("12345")
        self.assertIsNone(result)

    @patch.object(LinkedInScraper, "_navigate")
    @patch.object(LinkedInScraper, "_fetch_job_details")
    def test_search_integrates_results(self, mock_details, mock_nav):
        html = """
        <html><body>
        <li>
            <div data-entity-urn="urn:li:jobPosting:111">
                <h3 class="base-search-card__title">Engineer</h3>
                <h4 class="base-search-card__subtitle">Acme</h4>
                <a class="base-card__full-link" href="/jobs/view/engineer-111"></a>
            </div>
        </li>
        <li>
            <div data-entity-urn="urn:li:jobPosting:222">
                <h3 class="base-search-card__title">Designer</h3>
                <h4 class="base-search-card__subtitle">Beta</h4>
                <a class="base-card__full-link" href="/jobs/view/designer-222"></a>
            </div>
        </li>
        </body></html>
        """
        mock_nav.return_value = html
        mock_details.return_value = "3+ years Python required"

        jobs = self.scraper.search("Engineer", "", max_results=5)
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0].title, "Engineer")
        self.assertEqual(jobs[0].company, "Acme")
        self.assertEqual(jobs[1].title, "Designer")


class TestNaukriScraper(unittest.TestCase):
    def setUp(self):
        self.agent = FetchAgent(ollama_base_url="http://nonexistent:11434")
        self.agent._ollama_available = False
        self.scraper = NaukriScraper(_make_page_mock(), self.agent)

    @patch.object(NaukriScraper, "_navigate")
    def test_parse_html_results(self, mock_nav):
        mock_nav.return_value = """
        <html>
            <div class="jobTuple">
                <a class="title">Python Developer</a>
                <span class="subTitle">TechCorp</span>
                <div class="job-description">3+ years experience with Python, Django, PostgreSQL</div>
            </div>
        </html>
        """
        jobs = self.scraper.search("Python", "", max_results=5)
        self.assertEqual(len(jobs), 1)
        self.assertIn("Python", jobs[0].title)
        self.assertIn("Python", jobs[0].required_skills)

    @patch.object(NaukriScraper, "_navigate")
    def test_falls_back_to_api(self, mock_nav):
        mock_nav.return_value = "<html>no job cards here</html>"

        with patch("requests.get") as mock_get:
            api_resp = MagicMock()
            api_resp.status_code = 200
            api_resp.json.return_value = {
                "jobs": [
                    {"title": "Backend Engineer", "companyName": "API Corp",
                     "minExperience": 3, "skills": ["Python", "Go"]}
                ]
            }
            mock_get.return_value = api_resp
            jobs = self.scraper.search("Backend", "", max_results=5)
            self.assertGreaterEqual(len(jobs), 1)


class TestUnstopScraper(unittest.TestCase):
    def setUp(self):
        self.agent = FetchAgent(ollama_base_url="http://nonexistent:11434")
        self.agent._ollama_available = False
        self.scraper = UnstopScraper(_make_page_mock(), self.agent)

    @patch("requests.get")
    def test_parses_api_response(self, mock_get):
        api_resp = MagicMock()
        api_resp.status_code = 200
        api_resp.json.return_value = {
            "data": [
                {"title": "Data Scientist", "organization": {"name": "DataCo"}}
            ]
        }
        mock_get.return_value = api_resp

        jobs = self.scraper.search("Data Scientist", "", max_results=5)
        self.assertEqual(len(jobs), 1)
        self.assertIn("Data Scientist", jobs[0].title)


class TestGlassdoorScraper(unittest.TestCase):
    def setUp(self):
        self.agent = FetchAgent(ollama_base_url="http://nonexistent:11434")
        self.agent._ollama_available = False
        self.scraper = GlassdoorScraper(_make_page_mock(), self.agent)

    @patch.object(GlassdoorScraper, "_navigate")
    def test_parses_html_cards(self, mock_nav):
        mock_nav.return_value = """
        <html>
            <article>
                Senior DevOps Engineer. 5+ years. AWS, Kubernetes, Terraform.
                Company: CloudCo
            </article>
        </html>
        """
        jobs = self.scraper.search("DevOps", "", max_results=5)
        self.assertEqual(len(jobs), 1)
        self.assertIn("AWS", jobs[0].required_skills)


class TestFetchAgentIntegration(unittest.TestCase):
    def setUp(self):
        self.agent = FetchAgent(ollama_base_url="http://nonexistent:11434")
        self.agent._ollama_available = False

    @patch.object(LinkedInScraper, "search")
    @patch.object(NaukriScraper, "search")
    @patch.object(UnstopScraper, "search")
    @patch.object(GlassdoorScraper, "search")
    def test_fetch_jobs_aggregates_from_all_scrapers(
        self, mock_gd, mock_un, mock_nk, mock_li
    ):
        def make_job(title, company):
            return JobDescription(
                title=title, company=company, min_years_experience=0,
                required_skills=[], preferred_skills=[], critical_keywords=[],
            )

        mock_li.return_value = [make_job("Eng", "A")]
        mock_nk.return_value = [make_job("Dev", "B")]
        mock_un.return_value = [make_job("Sci", "C")]
        mock_gd.return_value = [make_job("Ops", "D")]

        result = self.agent.fetch_jobs("test", max_per_source=5)
        self.assertEqual(len(result), 4)


class TestOllamaAvailable(unittest.TestCase):
    @patch("requests.get")
    def test_detects_ollama_is_available(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        agent = FetchAgent(ollama_base_url="http://localhost:11434")
        self.assertTrue(agent.ollama_available())

    @patch("requests.get")
    def test_detects_ollama_unavailable(self, mock_get):
        mock_get.side_effect = Exception("connection refused")

        agent = FetchAgent(ollama_base_url="http://localhost:11434")
        self.assertFalse(agent.ollama_available())


if __name__ == "__main__":
    unittest.main()
