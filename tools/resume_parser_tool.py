"""
resume_parser_tool
──────────────────
Extracts structured data from a PDF résumé.

Uses pdfplumber for text extraction.  The LLM is invoked only once
to convert raw text → structured JSON; execution (file I/O) stays in
deterministic Python code.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_path: str) -> str:
    """Deterministic tool: read PDF → raw text."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"Resume PDF not found: {pdf_path}")

    # Handle non-PDF files (e.g. .txt) directly as plain text
    if path.suffix.lower() != ".pdf":
        logger.info("Non-PDF file detected (%s) — reading as plain text", path.suffix)
        return path.read_text(encoding="utf-8", errors="ignore")

    try:
        import pdfplumber
        text_parts: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return "\n\n".join(text_parts)
    except ImportError:
        # Fallback: read as plain-text (for testing without pdfplumber)
        logger.warning("pdfplumber not installed — reading file as plain text")
        return path.read_text(encoding="utf-8", errors="ignore")


def parse_resume_with_llm(llm, raw_text: str) -> dict[str, Any]:
    """
    LLM reasoning step: convert raw résumé text into structured JSON.

    Returns a dict with keys:
      skills, experience, education, certifications, summary,
      years_of_experience, name, email, phone, location, linkedin, github
    """
    system_prompt = SystemMessage(content="""\
You are a precise résumé parser.  Given raw text extracted from a PDF résumé,
return ONLY a JSON object (no markdown fences, no commentary) with these keys:

{
  "name": "",
  "email": "",
  "phone": "",
  "location": "",
  "linkedin": "",
  "github": "",
  "skills": [],
  "experience": [
    {"title": "", "company": "", "dates": "", "bullets": []}
  ],
  "education": [
    {"degree": "", "institution": "", "year": ""}
  ],
  "certifications": [],
  "summary": "",
  "years_of_experience": 0.0,
  "target_platforms": [],
  "credentials": {}
}

If a field cannot be determined, use an empty string or empty list or empty object.
If the candidate lists specific websites/job boards to apply on, put them in target_platforms.
If the candidate lists username/passwords for job boards, put them in credentials.
""")

    human_msg = HumanMessage(content=f"Parse the following résumé:\n\n{raw_text}")
    response = llm.invoke([system_prompt, human_msg])

    # Robustly extract JSON from the response
    content = response.content
    if isinstance(content, list):
        # Concatenate text parts if it's a list (common in some 2026 model responses)
        content = "".join([part.get("text", "") if isinstance(part, dict) else str(part) for part in content])
    
    content = content.strip()
    # Strip markdown code fences if present
    if content.startswith("```"):
        content = content.split("\n", 1)[1]  # remove first line
        content = content.rsplit("```", 1)[0]  # remove closing fence
    return json.loads(content)
