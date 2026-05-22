"""
decision_agent
──────────────
LangGraph node that makes the apply / skip / ask decision based on
the match score.

This is 100 % deterministic — NO LLM is used here.
The decision boundaries are hard-coded business rules.
"""

from __future__ import annotations

import logging
from typing import Any

from graph.state import JobAgentState

logger = logging.getLogger(__name__)

# ── Thresholds (configurable business rules) ─────────────────────────────
APPLY_THRESHOLD = 75      # score ≥ 75 → apply
ASK_THRESHOLD = 50        # 50 ≤ score < 75 → ask user


def decision_agent(state: JobAgentState, **_kwargs) -> dict[str, Any]:
    """
    Node: Route to apply / ask / skip based on match_score.

    Rules:
        score ≥ 75  → "apply"
        50 ≤ score  → "ask"
        score < 50  → "skip"
    """
    score = state.get("match_score", 0.0)
    selected_job = state.get("selected_job") or {}
    job_title = selected_job.get("title", "unknown")
    company = selected_job.get("company", "unknown")

    if score >= APPLY_THRESHOLD:
        decision = "apply"
    elif score >= ASK_THRESHOLD:
        decision = "ask"
    else:
        decision = "skip"

    log_msg = (
        f"✅ decision_agent: {job_title} @ {company} — "
        f"score={score:.0f} → decision={decision.upper()}"
    )

    result: dict[str, Any] = {
        "decision": decision,
        "logs": [log_msg],
    }

    # If asking user, prepare the clarification request
    if decision == "ask":
        result["clarification_request"] = (
            f"Match score for '{job_title}' at {company} is {score:.0f}/100.\n"
            f"Reasoning: {state.get('match_reasoning', 'N/A')}\n\n"
            f"Would you like to apply? (yes/no)"
        )

    return result


def route_after_decision(state: JobAgentState) -> str:
    """
    Conditional edge function used by LangGraph.

    Returns the name of the next node:
        "cover_letter" | "tracker_skip" | "ask_user"
    """
    decision = state.get("decision", "skip")

    if decision == "apply":
        return "cover_letter"
    elif decision == "ask":
        return "ask_user"
    else:
        return "tracker_skip"
