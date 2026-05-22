"""
matcher_agent
─────────────
LangGraph node that scores how well the candidate matches the
currently selected job.

• LLM reasoning: evaluate skill overlap, experience relevance
• Deterministic: input assembly, score validation
"""

from __future__ import annotations

import logging
from typing import Any

from graph.state import JobAgentState
from tools.matcher_tool import compute_match_score

logger = logging.getLogger(__name__)


def matcher_agent(state: JobAgentState, *, llm) -> dict[str, Any]:
    """
    Node: Score candidate–job match for state["selected_job"].
    """
    resume_data = state.get("resume_data", {})
    selected_job = state.get("selected_job")

    # ── Validation ───────────────────────────────────────────────────────
    if not selected_job:
        return {
            "match_score": 0.0,
            "match_reasoning": "No job selected for matching.",
            "logs": ["⚠️ matcher_agent: no selected_job — skipping"],
        }

    if not resume_data.get("skills"):
        return {
            "match_score": 0.0,
            "match_reasoning": "Resume has no skills to match against.",
            "logs": ["⚠️ matcher_agent: resume has no skills"],
        }

    # ── LLM reasoning: compute score ────────────────────────────────────
    try:
        result = compute_match_score(llm, resume_data, selected_job)
    except Exception as exc:
        logger.exception("Match scoring failed")
        return {
            "match_score": 0.0,
            "match_reasoning": f"Error: {exc}",
            "logs": [f"❌ matcher_agent: scoring error — {exc}"],
        }

    score = result["match_score"]
    reasoning = result["reasoning"]

    return {
        "match_score": score,
        "match_reasoning": reasoning,
        "logs": [
            f"✅ matcher_agent: {selected_job.get('title', '?')} @ "
            f"{selected_job.get('company', '?')} → score={score:.0f}/100"
        ],
    }
