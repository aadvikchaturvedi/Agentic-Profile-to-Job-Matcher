"""
Parser Agent Main Module
Demonstrates how to use the resume parser to extract structured data from raw resume text.
Uses local Ollama models for processing.
"""

import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from models import UserQuery, ParsedResume, JobDescription
from agent import Parser


def parse_resume(resume_text: str, candidate_id: str) -> ParsedResume:
    """
    Main function to parse a resume from raw text using local Ollama model.

    Args:
        resume_text: Raw resume text in any format
        candidate_id: Optional candidate identifier

    Returns:
        ParsedResume: Structured resume data

    Note:
        Requires Ollama to be running locally on localhost:11434
        Run: ollama serve
    """
    query = UserQuery(
        raw_job_description=resume_text,
        candidate_id=candidate_id,
    )

    parser = Parser(query)
    parsed_resume = parser.parse()

    return parsed_resume


if __name__ == "__main__":
    sample_resume = """
    John Doe
    Email: john.doe@example.com

    PROFESSIONAL SUMMARY
    Experienced Full Stack Developer with 5 years of expertise in building scalable web applications.

    CURRENT POSITION
    Senior Software Engineer at TechCorp Inc.

    CORE SKILLS
    - Python, JavaScript, TypeScript
    - React, Node.js, Django
    - PostgreSQL, MongoDB
    - AWS, Docker, Kubernetes
    - Agile/Scrum

    EXPERIENCE HIGHLIGHTS
    - Led migration of monolithic application to microservices, reducing deployment time by 40%
    - Architected real-time data processing pipeline handling 1M+ events per day
    - Mentored 3 junior developers and improved team code quality by 25%
    - Implemented comprehensive API testing strategy using pytest and Jest
    """

    try:
        print("Starting resume parsing with local Ollama model...")
        print("Make sure Ollama is running: ollama serve\n")

        result = parse_resume(sample_resume, candidate_id="CAND_001")

        print("✓ Resume Parsed Successfully!")
        print("=" * 50)
        print(f"Name: {result.name}")
        print(f"Email: {result.email}")
        print(f"Current Title: {result.current_title}")
        print(f"Years of Experience: {result.total_years_experience}")
        print(f"Core Skills: {', '.join(result.core_skills)}")
        print(f"Highlights: {'; '.join(result.experience_highlights)}")
        print("=" * 50)
    except ConnectionError as e:
        print("Error: Cannot connect to Ollama")
        print("Please ensure Ollama is running: ollama serve")
        print(f"Details: {str(e)}")
    except Exception as e:
        print(f"Error parsing resume: {str(e)}")
