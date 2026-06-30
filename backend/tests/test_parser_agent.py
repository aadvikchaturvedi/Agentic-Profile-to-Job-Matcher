import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from agents.parser_agent.agent import Parser
from models import UserQuery


class TestParserOllama(unittest.TestCase):
    def test_ollama_parse_returns_valid_resume(self):
        with patch("requests.get") as mock_get, patch("requests.post") as mock_post:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {"models": [{"name": "mistral:latest"}]}
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "response": (
                    '```json\n{"name": "John Doe", "email": "john@example.com", '
                    '"current_title": "Engineer", "total_years_experience": 5, '
                    '"core_skills": ["Python", "AWS"], '
                    '"experience_highlights": ["Built platform"]}\n```'
                )
            }
            query = UserQuery(raw_job_description="John Doe\nEngineer\nPython")
            parser = Parser(query)
            result = parser.parse()
            self.assertEqual(result.name, "John Doe")
            self.assertEqual(result.total_years_experience, 5)
            self.assertIn("Python", result.core_skills)

    def test_falls_back_to_regex_when_ollama_unavailable(self):
        with patch("requests.get") as mock_get:
            mock_get.side_effect = Exception("Ollama down")
            query = UserQuery(raw_job_description=(
                "Alice Smith\nEngineer\n5 years experience\nPython, AWS, Docker\n"
            ))
            parser = Parser(query)
            result = parser.parse()
            self.assertEqual(result.name, "Alice Smith")

    def test_returns_empty_resume_on_total_failure(self):
        with patch("requests.get") as mock_get:
            mock_get.side_effect = Exception("Ollama down")
            query = UserQuery(raw_job_description="garbage text with no structure whatsoever")
            parser = Parser(query)
            result = parser.parse()
            self.assertEqual(result.name, "")


if __name__ == "__main__":
    unittest.main()
