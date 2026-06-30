import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent import FetchAgent


def trunc(text: str, n: int = 60) -> str:
    return text if len(text) <= n else text[: n - 3] + "..."


def demo():
    query = sys.argv[1] if len(sys.argv) > 1 else "Software Engineer"
    location = sys.argv[2] if len(sys.argv) > 2 else ""

    print(f"Fetching jobs for: {query}" + (f" in {location}" if location else ""))

    agent = FetchAgent()
    ollama_ok = agent.ollama_available()
    print(f"Ollama: {'available' if ollama_ok else 'NOT running — using regex-only parsing'}\n")

    jobs = agent.fetch_jobs(query, location, max_per_source=5)

    if not jobs:
        print("\nNo jobs found. Tips:")
        print("  - Most job sites (Glassdoor, Naukri, Unstop) block plain HTTP requests.")
        print("  - LinkedIn guest API works but may be rate-limited.")
        print(f"  - Try: python {__file__} \"Software Engineer\" \"remote\"")
        print("  - For production, add Playwright/Selenium to handle JS rendering.")
        return

    print(f"\n{'=' * 65}")
    print(f"Found {len(jobs)} unique job(s):")
    print(f"{'=' * 65}")
    for i, job in enumerate(jobs, 1):
        print(f"\n{'─' * 50}")
        print(f"  Job {i}")
        print(f"{'─' * 50}")
        print(f"  Title:             {job.title}")
        print(f"  Company:           {job.company or 'N/A'}")
        print(f"  Min Experience:    {job.min_years_experience} years")
        print(f"  Required Skills:   {', '.join(job.required_skills[:8]) if job.required_skills else '(none extracted)'}")
        print(f"  Preferred Skills:  {', '.join(job.preferred_skills[:5]) if job.preferred_skills else '(none extracted)'}")
        print(f"  Keywords:          {', '.join(job.critical_keywords[:8]) if job.critical_keywords else '(none extracted)'}")


if __name__ == "__main__":
    demo()
