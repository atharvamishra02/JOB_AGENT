"""
job_discovery_agent
───────────────────
LangGraph node that discovers job opportunities based on the candidate's
parsed profile.

• Deterministic: job fetching, filtering, state update
• LLM: NOT used here — keyword extraction is rules-based
"""

from __future__ import annotations

import logging
from typing import Any

from graph.state import JobAgentState
from tools.job_scraper_tool import scrape_jobs_real

logger = logging.getLogger(__name__)


def job_discovery_agent(state: JobAgentState, **_kwargs) -> dict[str, Any]:
    """
    Node: Discover jobs matching the candidate's skills/preferences.
    """
    resume_data = state.get("resume_data", {})
    user_profile = state.get("user_profile", {})

    # ── Build search terms from profile (deterministic) ──────────────────
    skills = resume_data.get("skills", [])
    preferred_roles = user_profile.get("preferred_roles", [])

    # Use top skills + preferred roles as keywords
    keywords = list(set(preferred_roles + skills[:5]))
    location = user_profile.get("preferred_locations", [""])[0] if user_profile.get("preferred_locations") else None

    if not keywords:
        # Fallback: use generic terms from experience titles
        experience = resume_data.get("experience", [])
        keywords = [exp.get("title", "") for exp in experience[:3] if exp.get("title")]

    # ── Tool execution: scrape/fetch jobs (deterministic) ────────────────
    user_id = user_profile.get("user_id")
    try:
        # Switch to real scraping
        job_list = scrape_jobs_real(keywords=keywords, location=location, user_id=user_id)
    except Exception as exc:
        logger.exception("Job scraping failed")
        return {
            "logs": [f"❌ job_discovery_agent: scraping error — {exc}"],
            "job_list": [],
        }

    if not job_list:
        # If keyword filter returned nothing, fetch unconditionally
        logger.info("No keyword-matched jobs — fetching all available")
        job_list = scrape_jobs_real(keywords=["Python", "Developer"], location=location, user_id=user_id)

    return {
        "job_list": job_list,
        "current_job_index": 0,
        "selected_job": job_list[0] if job_list else None,
        "logs": [
            f"✅ job_discovery_agent: found {len(job_list)} jobs "
            f"(keywords: {keywords[:5]})"
        ],
    }
