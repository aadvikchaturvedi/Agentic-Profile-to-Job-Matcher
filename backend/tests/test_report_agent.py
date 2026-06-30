import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from agents.report_agent.agent import ReportAgent
from models import MatchResult, ParsedResume


class TestExperienceVerdict(unittest.TestCase):
    def setUp(self):
        self.reporter = ReportAgent()

    def test_strong_match(self):
        match = MatchResult(
            skills_score=90, experience_score=95, relevance_score=80, overall_score=90,
            matched_skills=["Python"], missing_skills=[],
        )
        verdict = self.reporter._experience_verdict(match)
        self.assertIn("Strong", verdict)

    def test_significant_gap(self):
        match = MatchResult(
            skills_score=30, experience_score=30, relevance_score=30, overall_score=30,
            matched_skills=[], missing_skills=["Python"],
        )
        verdict = self.reporter._experience_verdict(match)
        self.assertIn("gap", verdict.lower())


class TestSkillNarrative(unittest.TestCase):
    def setUp(self):
        self.reporter = ReportAgent()

    def test_strengths_with_matches(self):
        match = MatchResult(
            skills_score=80, experience_score=80, relevance_score=80, overall_score=80,
            matched_skills=["Python", "AWS"], missing_skills=["Docker"],
        )
        strengths, gaps = self.reporter._build_skill_narrative(match)
        self.assertIn("Python", strengths)
        self.assertIn("Docker", gaps)

    def test_no_gaps(self):
        match = MatchResult(
            skills_score=100, experience_score=100, relevance_score=100, overall_score=100,
            matched_skills=["Python"], missing_skills=[],
        )
        _, gaps = self.reporter._build_skill_narrative(match)
        self.assertIn("all required skills are present", gaps)


class TestInferTransferable(unittest.TestCase):
    def setUp(self):
        self.reporter = ReportAgent()

    def test_returns_matched_skills_not_in_missing(self):
        match = MatchResult(
            skills_score=80, experience_score=80, relevance_score=80, overall_score=80,
            matched_skills=["Python", "AWS"], missing_skills=["Docker", "K8s"],
        )
        result = self.reporter._infer_transferable(match)
        self.assertIn("Python", result)
        self.assertNotIn("Docker", result)


class TestActionPlan(unittest.TestCase):
    def setUp(self):
        self.reporter = ReportAgent()

    def test_acquire_missing_skills(self):
        match = MatchResult(
            skills_score=50, experience_score=80, relevance_score=80, overall_score=60,
            matched_skills=["Python"], missing_skills=["AWS", "Docker"],
        )
        plan = self.reporter._build_action_plan(match)
        self.assertIn("AWS", plan)
        self.assertIn("Docker", plan)

    def test_well_aligned(self):
        match = MatchResult(
            skills_score=100, experience_score=100, relevance_score=100, overall_score=100,
            matched_skills=["Python"], missing_skills=[],
        )
        plan = self.reporter._build_action_plan(match)
        self.assertIn("well-aligned", plan.lower())


class TestGenerate(unittest.TestCase):
    def setUp(self):
        self.reporter = ReportAgent()

    def test_generates_valid_response(self):
        match = MatchResult(
            skills_score=80, experience_score=80, relevance_score=80, overall_score=80,
            matched_skills=["Python"], missing_skills=["Docker"],
        )
        resume = ParsedResume(
            name="Alice", total_years_experience=5,
            core_skills=["Python"], experience_highlights=["Led team"],
        )
        result = self.reporter.generate(match, resume, job_title="Engineer")
        self.assertEqual(result.status, "success")
        self.assertEqual(result.overall_match_score, 80)
        self.assertIsNotNone(result.skill_analysis)
        self.assertIn("Python", result.skill_analysis.matched_skills)
        self.assertIn("Docker", result.skill_analysis.missing_skills)
        self.assertTrue(len(result.action_plan) > 0)


if __name__ == "__main__":
    unittest.main()
