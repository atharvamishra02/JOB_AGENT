"""
tracker_agent
─────────────
LangGraph node that persists application results to the database.

• 100 % deterministic — no LLM.
• Writes to SQLAlchemy-backed storage.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from sqlalchemy.exc import IntegrityError

from db.database import init_db, insert_application
from graph.state import ApplicationRecord, JobAgentState

logger = logging.getLogger(__name__)


def tracker_agent(state: JobAgentState, **_kwargs) -> dict[str, Any]:
    """
    Node: Persist the outcome of the current job evaluation to the DB
    and append to in-state application_history.
    """
    selected_job = state.get("selected_job", {})
    decision = state.get("decision", "skip")
    status = state.get("application_status", "skipped")
    score = state.get("match_score", 0.0)
    error = state.get("application_error", "")

    if not selected_job:
        return {"logs": ["⚠️ tracker_agent: nothing to track (no selected_job)"]}

    job_id = selected_job.get("job_id", "unknown")
    company = selected_job.get("company", "unknown")
    title = selected_job.get("title", "unknown")

    # Map decision → final status
    if decision == "skip":
        status = "skipped"
    elif decision == "ask":
        status = "ask_user"
    # else: status comes from apply_agent ("success" | "failed" | "duplicate")

    now = datetime.now(timezone.utc).isoformat()

    # ── DB write (deterministic) ─────────────────────────────────────────
    duplicate_record = False
    user_id = state.get("user_profile", {}).get("user_id") or 1 # Fallback to user 1 for demo/cli
    
    try:
        SessionFactory = init_db()
        with SessionFactory() as session:
            insert_application(session, {
                "user_id": user_id,
                "job_id": job_id,
                "company": company,
                "title": title,
                "url": selected_job.get("url", ""),
                "match_score": score,
                "decision": decision,
                "status": status,
                "error": error,
                "optimized_resume_snippet": state.get("optimized_resume", "")[:500],
            })
    except Exception as exc:
        # IntegrityError (duplicate) or other DB error — log but don't crash
        if isinstance(exc, IntegrityError):
            duplicate_record = True
            logger.info("Duplicate application log skipped for job_id=%s", job_id)
        else:
            logger.warning("DB write failed: %s", exc)

    # ── Append to in-state history ───────────────────────────────────────
    record = ApplicationRecord(
        job_id=job_id,
        company=company,
        title=title,
        status=status,
        match_score=score,
        decision=decision,
        timestamp=now,
        error=error,
    )

    return {
        "application_history": [record],
        "logs": [
            f"📝 tracker_agent: logged {title} @ {company} — "
            f"decision={decision}, status={status}, score={score:.0f}"
        ],
    }
