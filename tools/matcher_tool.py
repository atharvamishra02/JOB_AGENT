"""
matcher_tool
─────────────
Uses LLM reasoning to produce a numeric match score (0-100) and
explanation for how well a candidate matches a job listing.

Deterministic code: prompt assembly, JSON parsing, score validation.
LLM: reasoning about skills overlap, experience relevance, etc.
"""

from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


def compute_match_score(
    llm,
    resume_data: dict,
    job: dict,
) -> dict[str, float | str]:
    """
    LLM reasoning: evaluate candidate–job fit.

    Returns:
        {
            "match_score": <float 0-100>,
            "reasoning": "<explanation string>"
        }
    """
    system_prompt = SystemMessage(content="""\
You are a precise job-matching evaluator.

Given a candidate's résumé data and a job posting, produce a JSON object
(no markdown fences, no commentary) with exactly these keys:

{
  "match_score": <integer 0–100>,
  "reasoning": "<2-3 sentence justification>"
}

Scoring guide:
  90-100 = near-perfect fit (most requirements met, strong experience)
  75-89  = strong fit (majority of requirements met)
  50-74  = partial fit (some overlap, transferable skills)
  25-49  = weak fit (few requirements met)
  0-24   = poor fit (unrelated background)

Be honest and precise.  Do NOT inflate scores.
""")

    human_msg = HumanMessage(content=f"""\
=== CANDIDATE ===
Skills: {", ".join(resume_data.get("skills", []))}
Experience: {json.dumps(resume_data.get("experience", []), default=str)}
Education: {json.dumps(resume_data.get("education", []), default=str)}
Summary: {resume_data.get("summary", "N/A")}
Years of experience: {resume_data.get("years_of_experience", "unknown")}

=== JOB POSTING ===
Title: {job.get("title", "")}
Company: {job.get("company", "")}
Description: {job.get("description", "")}
Requirements: {", ".join(job.get("requirements", []))}
Location: {job.get("location", "")}
""")

    response = llm.invoke([system_prompt, human_msg])
    content = response.content
    if isinstance(content, list):
        content = "".join([part.get("text", "") if isinstance(part, dict) else str(part) for part in content])
    content = content.strip()

    if content.startswith("```"):
        content = content.split("\n", 1)[1]
        content = content.rsplit("```", 1)[0]

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        logger.error("Matcher LLM returned invalid JSON — defaulting to 0")
        return {"match_score": 0.0, "reasoning": f"Parse error. Raw: {content[:200]}"}

    score = float(result.get("match_score", 0))
    # Clamp to valid range
    score = max(0.0, min(100.0, score))

    return {
        "match_score": score,
        "reasoning": result.get("reasoning", ""),
    }
