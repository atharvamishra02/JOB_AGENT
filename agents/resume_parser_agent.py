"""
resume_parser_agent
───────────────────
LangGraph node that parses the user's PDF résumé into structured data.

• Deterministic: file I/O, input validation
• LLM reasoning: text → structured JSON conversion
"""

from __future__ import annotations

import logging
from typing import Any

from graph.state import JobAgentState
from tools.resume_parser_tool import extract_text_from_pdf, parse_resume_with_llm

logger = logging.getLogger(__name__)


def resume_parser_agent(state: JobAgentState, *, llm) -> dict[str, Any]:
    """
    Node: Parse PDF résumé → structured resume_data + user_profile fields.
    """

    resume_path = state.get("resume_path", "")

    # ── Input validation (deterministic) ─────────────────────────────────
    if not resume_path:
        return {
            "logs": ["❌ resume_parser_agent: no resume_path in state"],
            "missing_info": ["resume_path"],
        }

    # ── Tool execution: extract raw text (deterministic) ─────────────────
    try:
        raw_text = extract_text_from_pdf(resume_path)
    except FileNotFoundError as exc:
        return {
            "logs": [f"❌ resume_parser_agent: {exc}"],
            "missing_info": ["resume_file"],
        }

    if not raw_text.strip():
        return {
            "logs": ["❌ resume_parser_agent: PDF appears empty"],
            "missing_info": ["resume_content"],
        }

    # ── LLM reasoning: structure the text ────────────────────────────────
    try:
        parsed = parse_resume_with_llm(llm, raw_text)
    except Exception as exc:
        logger.exception("LLM parsing failed")
        return {
            "logs": [f"❌ resume_parser_agent: LLM parse error — {exc}"],
            "resume_data": {"raw_text": raw_text},
        }

    # ── Build resume_data & user_profile from parsed output ──────────────
    resume_data = {
        "raw_text": raw_text,
        "skills": parsed.get("skills", []),
        "experience": parsed.get("experience", []),
        "education": parsed.get("education", []),
        "certifications": parsed.get("certifications", []),
        "summary": parsed.get("summary", ""),
        "years_of_experience": float(parsed.get("years_of_experience", 0)),
    }

    base_profile = state.get("user_profile", {})
    user_profile = {
        **base_profile,
        "name": parsed.get("name", "") or base_profile.get("name", ""),
        "email": parsed.get("email", "") or base_profile.get("email", ""),
        "phone": parsed.get("phone", "") or base_profile.get("phone", ""),
        "location": parsed.get("location", "") or base_profile.get("location", ""),
        "linkedin": parsed.get("linkedin", "") or base_profile.get("linkedin", ""),
        "github": parsed.get("github", "") or base_profile.get("github", ""),
        "target_platforms": parsed.get("target_platforms", []),
        "credentials": parsed.get("credentials", {}),
    }

    # Flag any critical missing fields
    missing: list[str] = []
    if not resume_data["skills"]:
        missing.append("skills")
    if not resume_data["experience"]:
        missing.append("experience")
    if not user_profile["name"]:
        missing.append("candidate_name")
    if not user_profile["email"]:
        missing.append("candidate_email")

    return {
        "resume_data": resume_data,
        "user_profile": user_profile,
        "missing_info": missing,
        "logs": [
            f"✅ resume_parser_agent: parsed résumé — "
            f"{len(resume_data['skills'])} skills, "
            f"{len(resume_data['experience'])} roles, "
            f"{resume_data['years_of_experience']} YoE"
        ],
    }
