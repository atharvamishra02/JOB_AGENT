"""
cover_letter_tool
──────────────────
Uses LLM to generate a cover letter targeted at a specific job description.

Execution (prompt construction, response parsing) is deterministic Python.
"""

from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


def generate_cover_letter(
    llm,
    resume_data: dict,
    job: dict,
) -> dict[str, str]:
    """
    LLM reasoning: generate a cover letter for the target `job`.

    Returns:
        {"cover_letter": "..."}
    """
    system_prompt = SystemMessage(content="""\
You are an expert career consultant.

Given a candidate's structured résumé data and a target job description,
produce a concise, compelling cover letter (3 paragraphs max).

Respond ONLY with a JSON object (no markdown, no commentary) in this format:
{
  "cover_letter": "<your cover letter here>"
}

Rules:
1. Mirror the job posting's exact terminology and keywords.
2. Quantify achievements where possible (%, $, metrics).
3. Do NOT fabricate skills or experience the candidate doesn't have.
4. Emphasise transferable skills when direct experience is missing.
""")

    human_msg = HumanMessage(content=f"""\
=== CANDIDATE RÉSUMÉ DATA ===
{json.dumps(resume_data, indent=2, default=str)}

=== TARGET JOB ===
Title: {job.get("title", "")}
Company: {job.get("company", "")}
Description: {job.get("description", "")}
Requirements: {", ".join(job.get("requirements", []))}
""")

    response = llm.invoke([system_prompt, human_msg])
    content = response.content
    if isinstance(content, list):
        content = "".join([part.get("text", "") if isinstance(part, dict) else str(part) for part in content])
    content = content.strip()

    # Strip markdown fences if present
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
        content = content.rsplit("```", 1)[0]

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("Cover letter generator returned non-JSON — using raw text")
        result = {
            "cover_letter": content,
        }

    return {
        "cover_letter": result.get("cover_letter", ""),
    }
