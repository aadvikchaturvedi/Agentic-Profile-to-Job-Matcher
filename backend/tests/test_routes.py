import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from fastapi.testclient import TestClient

from app.main import app


class TestHealthEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_returns_ok(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")


class TestMatchEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("app.api.routes.orchestrator")
    def test_match_requires_file_and_jd(self, mock_orch):
        resp = self.client.post("/api/match")
        self.assertEqual(resp.status_code, 422)

    def test_match_returns_500_on_bad_file(self):
        resp = self.client.post(
            "/api/match",
            files={"resume": ("bad.pdf", b"not a pdf")},
            data={"job_description": "some jd"},
        )
        self.assertIn(resp.status_code, (400, 500))


class TestMatchJobsEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_requires_query(self):
        resp = self.client.post("/api/match-jobs")
        self.assertEqual(resp.status_code, 422)


if __name__ == "__main__":
    unittest.main()
