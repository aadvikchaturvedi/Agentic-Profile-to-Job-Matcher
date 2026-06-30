import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from agents.scoring_agent.agent import ScoringAgent
from models import ParsedResume, JobDescription


class TestScoreSkills(unittest.TestCase):
    def setUp(self):
        self.scorer = ScoringAgent()

    def test_perfect_match(self):
        resume = ParsedResume(
            name="Test", total_years_experience=5,
            core_skills=["Python", "AWS", "Docker"], experience_highlights=[],
        )
        job = JobDescription(
            title="Engineer", min_years_experience=3,
            required_skills=["Python", "AWS", "Docker"],
        )
        match = self.scorer.score(resume, job)
        self.assertEqual(match.skills_score, 100.0)
        self.assertIn("Python", match.matched_skills)

    def test_partial_match(self):
        resume = ParsedResume(
            name="Test", total_years_experience=5,
            core_skills=["Python"], experience_highlights=[],
        )
        job = JobDescription(
            title="Engineer", min_years_experience=3,
            required_skills=["Python", "AWS", "Docker"],
        )
        match = self.scorer.score(resume, job)
        self.assertAlmostEqual(match.skills_score, 100 / 3, places=1)

    def test_no_skills_in_jd(self):
        resume = ParsedResume(
            name="Test", total_years_experience=5,
            core_skills=["Python"], experience_highlights=[],
        )
        job = JobDescription(
            title="Engineer", min_years_experience=0,
            required_skills=[],
        )
        match = self.scorer.score(resume, job)
        self.assertEqual(match.skills_score, 100.0)


class TestScoreExperience(unittest.TestCase):
    def setUp(self):
        self.scorer = ScoringAgent()

    def test_exceeds_requirement(self):
        score, _ = self.scorer._score_experience(5, 3)
        self.assertEqual(score, 100.0)

    def test_meets_requirement(self):
        score, _ = self.scorer._score_experience(3, 3)
        self.assertEqual(score, 100.0)

    def test_below_requirement(self):
        score, _ = self.scorer._score_experience(2, 5)
        self.assertAlmostEqual(score, 40.0, places=1)

    def test_no_requirement(self):
        score, _ = self.scorer._score_experience(0, 0)
        self.assertEqual(score, 100.0)


class TestScoreRelevance(unittest.TestCase):
    def setUp(self):
        self.scorer = ScoringAgent()

    def test_keyword_overlap_fallback(self):
        resume = ParsedResume(
            name="Test", total_years_experience=3,
            core_skills=["Python", "AWS"], experience_highlights=[],
        )
        job = JobDescription(
            title="Engineer", min_years_experience=0,
            required_skills=[], critical_keywords=["Python", "AWS", "Docker"],
        )
        score, _ = self.scorer._llm_relevance(resume, job)
        self.assertAlmostEqual(score, 200 / 3, places=1)

    def test_default_relevance_when_no_keywords(self):
        resume = ParsedResume(
            name="Test", total_years_experience=3,
            core_skills=["Python"], experience_highlights=[],
        )
        job = JobDescription(
            title="Engineer", min_years_experience=0,
            required_skills=[], critical_keywords=[],
        )
        score, _ = self.scorer._llm_relevance(resume, job)
        self.assertEqual(score, 50.0)


if __name__ == "__main__":
    unittest.main()
