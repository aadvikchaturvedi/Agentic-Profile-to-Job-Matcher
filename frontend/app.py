import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import streamlit as st
import requests

from app.models import AgentResponse

API_BASE = "http://localhost:8000"

st.set_page_config(
    page_title="Job Match AI",
    page_icon="🎯",
    layout="wide",
)

st.title("🎯 Agentic Profile-to-Job Matcher")
st.markdown("Upload a resume and search for jobs — the multi-agent pipeline handles the rest.")


def poll_sse(url: str, files: Dict, data: Dict) -> Optional[AgentResponse]:
    with requests.post(url, files=files, data=data, stream=True) as resp:
        if resp.status_code != 200:
            st.error(f"Server error {resp.status_code}: {resp.text[:300]}")
            return None

        progress_bar = st.progress(0)
        status_text = st.empty()

        event_type = None
        for raw in resp.iter_lines(decode_unicode=True):
            line = raw.strip()
            if not line:
                continue
            if line.startswith("event:"):
                event_type = line[6:].strip()
                continue
            if line.startswith("data:"):
                payload = json.loads(line[5:].strip())
                if event_type == "complete":
                    progress_bar.empty()
                    status_text.empty()
                    return AgentResponse(**payload)
                if "step" in payload:
                    pct = payload.get("percent", 0)
                    msg = payload.get("message", "")
                    status_text.info(f"**{payload.get('step', '').title()}**: {msg}")
                    progress_bar.progress(pct / 100.0)
                continue

        return None


def poll_json(url: str, files: Dict, data: Dict) -> Optional[AgentResponse]:
    with st.spinner("Matching..."):
        try:
            resp = requests.post(url, files=files, data=data, timeout=120)
            if resp.status_code == 200:
                return AgentResponse(**resp.json())
            st.error(f"Error {resp.status_code}: {resp.text[:300]}")
        except requests.exceptions.ConnectionError:
            st.error("Cannot connect to API. Is `uvicorn app.main:app --reload` running?")
        except Exception as e:
            st.error(str(e))
    return None


def display_result(result: AgentResponse) -> None:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Overall Match", f"{result.overall_match_score}%")
    col2.metric("Status", result.status.upper())

    if result.skill_analysis:
        matched_count = len(result.skill_analysis.matched_skills)
        missing_count = len(result.skill_analysis.missing_skills)
        col3.metric("Matched Skills", matched_count)
        col4.metric("Missing Skills", missing_count)

    with st.expander("📊 Score Breakdown", expanded=True):
        tab1, tab2 = st.tabs(["Skills Chart", "Component Scores"])

        with tab1:
            if result.skill_analysis:
                col_a, col_b = st.columns([3, 2])
                with col_a:
                    chart_data = {
                        "Matched": matched_count,
                        "Missing": missing_count,
                        "Transferable": len(result.skill_analysis.transferable_skills),
                    }
                    st.bar_chart(chart_data)
                with col_b:
                    st.metric("Skills Score", f"{result.overall_match_score}%")
                    if result.skill_analysis.matched_skills:
                        st.success(f"**Matched ({matched_count}):** {', '.join(result.skill_analysis.matched_skills)}")
                    if result.skill_analysis.missing_skills:
                        st.warning(f"**Missing ({missing_count}):** {', '.join(result.skill_analysis.missing_skills)}")
                    if result.skill_analysis.transferable_skills:
                        st.info(f"**Transferable:** {', '.join(result.skill_analysis.transferable_skills)}")

        with tab2:
            scores = {
                "Skills Score": result.overall_match_score,
            }
            st.caption("Overall match percentage based on weighted skill, experience, and relevance scoring. Details shown per job in the All Scored Jobs section.")

    with st.expander("📄 Parsed Candidate Profile", expanded=True):
        p = result.parsed_candidate_profile
        st.write(f"**Name:** {p.name or '(not found)'}")
        st.write(f"**Email:** {p.email or '(not found)'}")
        st.write(f"**Title:** {p.current_title or '(not found)'}")
        st.write(f"**Experience:** {p.total_years_experience} years")
        st.write(f"**Skills:** {', '.join(p.core_skills) if p.core_skills else '(none)'}")

    if result.skill_analysis:
        with st.expander("🔍 Skill Analysis", expanded=True):
            sa = result.skill_analysis
            if sa.matched_skills:
                st.success(f"**Matched:** {', '.join(sa.matched_skills)}")
            if sa.missing_skills:
                st.warning(f"**Missing:** {', '.join(sa.missing_skills)}")
            if sa.transferable_skills:
                st.info(f"**Transferable:** {', '.join(sa.transferable_skills)}")

    if result.all_jobs:
        with st.expander("📋 All Scored Jobs", expanded=False):
            jobs_sorted = sorted(result.all_jobs, key=lambda x: x.get("score", 0), reverse=True)
            for j in jobs_sorted:
                title = j.get("title", "?")
                company = j.get("company", "?")
                score = j.get("score", 0)
                job_url = j.get("url") or ""
                source = j.get("source", "")
                matched = j.get("matched_skills", [])
                missing = j.get("missing_skills", [])
                link = f" [🔗]({job_url})" if job_url else ""
                st.markdown(f"**{title}** @ {company} — **{score}/100**{link}  \n"
                            f"<small>Source: {source} | Matched: {', '.join(matched[:3]) or '—'} | Missing: {', '.join(missing[:3]) or '—'}</small>",
                            unsafe_allow_html=True)
                st.divider()

    with st.expander("💬 Justification", expanded=False):
        st.write(result.justification_summary or "No justification available.")
        st.write(f"**Experience:** {result.experience_fit_verdict}")
        if result.action_plan:
            st.write(f"**Action Plan:** {result.action_plan}")

    if result.overall_match_score > 0:
        export_data = result.model_dump_json(indent=2)
        st.download_button(
            "📥 Download Result (JSON)",
            data=export_data,
            file_name="match_result.json",
            mime="application/json",
        )


# --- Sidebar ---
with st.sidebar:
    st.header("Settings")
    mode = st.radio(
        "Mode",
        ["Match (JD text)", "Fetch & Match (scrape jobs)"],
        index=0,
    )

# --- Main form ---
uploaded_file = st.file_uploader(
    "Upload Resume (PDF, DOCX, PNG, JPG, TXT)",
    type=["pdf", "docx", "png", "jpg", "jpeg", "txt"],
)

if mode == "Match (JD text)":
    jd_text = st.text_area("Paste Job Description", height=200)
    if not uploaded_file:
        st.info("👆 Upload a resume to get started")
    if st.button("Match", type="primary", disabled=not (uploaded_file and jd_text.strip())):
        result = poll_json(
            f"{API_BASE}/api/match",
            files={"resume": (uploaded_file.name, uploaded_file.getvalue())},
            data={"job_description": jd_text},
        )
        if result:
            display_result(result)
else:
    search_query = st.text_input("Job Search Query", placeholder="e.g., software engineer")
    location = st.text_input("Location (optional)", placeholder="e.g., San Francisco")
    if not uploaded_file:
        st.info("👆 Upload a resume to get started")
    if st.button("Fetch & Match", type="primary", disabled=not (uploaded_file and search_query.strip())):
        result = poll_sse(
            f"{API_BASE}/api/match-jobs",
            files={"resume": (uploaded_file.name, uploaded_file.getvalue())},
            data={"search_query": search_query, "location": location},
        )
        if result:
            display_result(result)
