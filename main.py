"""
main.py — Runnable entry-point for the Job Agent system
═══════════════════════════════════════════════════════════

Usage:
    python main.py                          # uses sample resume
    python main.py --resume path/to/cv.pdf  # your own PDF

The system will:
  1. Parse the résumé
  2. Discover job opportunities (mock data)
  3. Score each job match
  4. Decide: apply / ask / skip
  5. Optimise résumé & apply (if score ≥ 75)
  6. Track everything in SQLite DB
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Fix Windows console encoding for emoji/unicode characters
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

# ── Logging setup ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-30s │ %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("job_agent_run.log", mode="w", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")


# ── Auto-detect résumé PDF in project directory ─────────────────────────────

def find_resume_pdf() -> str | None:
    """Search for a PDF résumé file in the project directory."""
    project_dir = Path(__file__).parent
    pdf_files = list(project_dir.glob("*.pdf"))
    # Filter for likely resume files
    resume_keywords = ["resume", "cv", "curriculum"]
    # First try to find PDFs with resume-related names
    for pdf in pdf_files:
        if any(kw in pdf.stem.lower() for kw in resume_keywords):
            return str(pdf)
    # If none found with keywords, return first PDF if only one exists
    if len(pdf_files) == 1:
        return str(pdf_files[0])
    # If multiple PDFs and none have resume keywords, return None
    if pdf_files:
        logger.warning(
            "Multiple PDFs found but none identified as résumé: %s",
            [p.name for p in pdf_files],
        )
    return None


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Job Agent — Autonomous Application System"
    )
    parser.add_argument(
        "--resume",
        type=str,
        default="",
        help="Path to résumé PDF. If omitted, auto-detects PDF in project directory.",
    )
    args = parser.parse_args()

    # Resolve résumé path
    if args.resume:
        resume_path = args.resume
        if not Path(resume_path).exists():
            logger.error("File not found: %s", resume_path)
            sys.exit(1)
    else:
        # Auto-detect PDF resume in project directory
        resume_path = find_resume_pdf()
        if resume_path:
            logger.info("Auto-detected résumé PDF: %s", resume_path)
        else:
            logger.error(
                "No résumé PDF found in project directory. "
                "Please provide one with --resume path/to/resume.pdf"
            )
            sys.exit(1)

    # Validate API key
    if not os.getenv("OPENAI_API_KEY"):
        logger.error(
            "OPENAI_API_KEY not set.  Copy .env.example → .env and add your key."
        )
        sys.exit(1)

    # ── Run the workflow ─────────────────────────────────────────────────
    logger.info("=" * 70)
    logger.info("  JOB AGENT — Starting autonomous workflow")
    logger.info("  Resume: %s", resume_path)
    logger.info("=" * 70)

    from graph.workflow import run_workflow

    # No hardcoded overrides; rely 100% on the parsed resume
    user_profile = {}

    final_state = run_workflow(resume_path, user_profile)

    # ── Print results ────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  EXECUTION COMPLETE — AUDIT LOG")
    print("=" * 70)

    for entry in final_state.get("logs", []):
        print(f"  {entry}")

    print("\n" + "=" * 70)
    print("  APPLICATION HISTORY")
    print("=" * 70)

    history = final_state.get("application_history", [])
    if not history:
        print("  No applications recorded.")
    else:
        for i, rec in enumerate(history, 1):
            print(
                f"  {i}. {rec.get('title', '?')} @ {rec.get('company', '?')}\n"
                f"     Score: {rec.get('match_score', 0):.0f} | "
                f"Decision: {rec.get('decision', '?')} | "
                f"Status: {rec.get('status', '?')}"
            )

    print("\n" + "=" * 70)
    print(f"  Total jobs evaluated: {len(history)}")
    applied = sum(1 for r in history if r.get("status") == "success")
    skipped = sum(1 for r in history if r.get("status") == "skipped")
    asked = sum(1 for r in history if r.get("status") == "ask_user")
    print(f"  Applied: {applied}  |  Skipped: {skipped}  |  Ask user: {asked}")
    print("=" * 70)


if __name__ == "__main__":
    main()
