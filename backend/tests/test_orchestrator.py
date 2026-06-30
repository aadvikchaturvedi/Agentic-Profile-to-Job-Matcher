import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from agents.orchestrator import MultiAgentOrchestrator
from models import AgentResponse, ParsedResume


class TestOrchestrator(unittest.TestCase):
    def setUp(self):
        self.orchestrator = MultiAgentOrchestrator()

    @patch("agents.orchestrator.Parser")
    @patch("agents.orchestrator.FetchAgent")
    def test_run_returns_agent_response(self, mock_fa, mock_parser):
        parsed_resume = ParsedResume(
            name="Jane", email=None, current_title=None,
            total_years_experience=5, core_skills=["Python"], experience_highlights=[],
        )
        mock_parser_instance = MagicMock()
        mock_parser_instance.parse.return_value = parsed_resume
        mock_parser.return_value = mock_parser_instance

        mock_fa_instance = MagicMock()
        mock_fa_instance.parse_job_text_to_jd.return_value = None
        mock_fa.return_value = mock_fa_instance

        result = self.orchestrator.run(
            "John Doe\nEngineer", "Software Engineer job description"
        )
        self.assertIsInstance(result, AgentResponse)
        self.assertEqual(result.status, "error")

    @patch("agents.orchestrator.Parser")
    def test_run_handles_empty_jd_gracefully(self, mock_parser):
        parsed_resume = ParsedResume(
            name="Jane", email=None, current_title=None,
            total_years_experience=5, core_skills=["Python"], experience_highlights=[],
        )
        mock_parser_instance = MagicMock()
        mock_parser_instance.parse.return_value = parsed_resume
        mock_parser.return_value = mock_parser_instance

        with patch.object(self.orchestrator, "_parse_jd", return_value=None):
            result = self.orchestrator.run("resume text", "jd text")
            self.assertIsInstance(result, AgentResponse)
            self.assertEqual(result.status, "error")


if __name__ == "__main__":
    unittest.main()
