"""
cover_letter_agent
───────────────────
LangGraph node that generates a cover letter
optimised for the selected job.

• LLM reasoning: cover letter generation
• Deterministic: input prep, response assignment
"""

from __future__ import annotations

import logging
from typing import Any

from graph.state import JobAgentState
from tools.cover_letter_tool import generate_cover_letter

logger = logging.getLogger(__name__)


def cover_letter_agent(state: JobAgentState, *, llm) -> dict[str, Any]:
    """
    Node: Generate cover letter for selected_job.
    """
    resume_data = state.get("resume_data", {})
    selected_job = state.get("selected_job")

    if not selected_job:
        return {
            "logs": ["⚠️ cover_letter_agent: no selected_job — skipping"],
        }

    # ── LLM reasoning: generate cover letter ───────────────────────────────────
    try:
        result = generate_cover_letter(llm, resume_data, selected_job)
    except Exception as exc:
        logger.exception("Cover letter generation failed")
        return {
            "cover_letter": "",
            "logs": [f"⚠️ cover_letter_agent: LLM error — {exc}, skipping cover letter"],
        }

    cover = result.get("cover_letter", "")

    return {
        "cover_letter": cover,
        "logs": [
            f"✅ cover_letter_agent: generated cover letter ({len(cover)} chars) for "
            f"{selected_job.get('title', '?')} @ {selected_job.get('company', '?')}"
        ],
    }
