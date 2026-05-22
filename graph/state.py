"""
Strongly-typed shared state for the LangGraph job automation workflow.

Every agent node reads from and writes to this state.  LangGraph merges
returned dicts into the current state automatically — agents only need to
return the keys they modify.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, Optional, TypedDict


# ── Nested data models ──────────────────────────────────────────────────────

class UserProfile(TypedDict, total=False):
    """Minimal user identity that lives alongside the parsed résumé."""
    user_id: int
    name: str
    email: str
    phone: str
    location: str
    linkedin: str
    github: str
    preferred_roles: list[str]
    preferred_locations: list[str]
    api_keys: dict[str, str]
    preferred_model: str
    min_salary: int


class ResumeData(TypedDict, total=False):
    """Structured résumé data produced by the resume_parser_agent."""
    raw_text: str
    skills: list[str]
    experience: list[dict[str, Any]]     # [{title, company, dates, bullets}]
    education: list[dict[str, Any]]      # [{degree, institution, year}]
    certifications: list[str]
    summary: str
    years_of_experience: float


class JobListing(TypedDict, total=False):
    """A single scraped / API-fetched job posting."""
    job_id: str
    title: str
    company: str
    location: str
    description: str
    requirements: list[str]
    salary_range: str
    url: str
    source: str            # e.g. "linkedin", "indeed", "mock"
    posted_date: str


class ApplicationRecord(TypedDict, total=False):
    """Result of a single application attempt."""
    job_id: str
    company: str
    title: str
    status: Literal["applied", "skipped", "ask_user", "failed", "duplicate"]
    match_score: float
    decision: str
    timestamp: str
    error: str


# ── Root workflow state ──────────────────────────────────────────────────────

class JobAgentState(TypedDict, total=False):
    """
    Root state shared across all LangGraph nodes.

    Keys use Annotated[..., operator.add] where we want *append* semantics
    (logs, application_history).  Everything else uses last-write-wins.
    """

    # ── Identity & résumé ────────────────────────────────────────────────
    user_profile: UserProfile
    resume_data: ResumeData
    resume_path: str                          # path to uploaded PDF

    # ── Job discovery ────────────────────────────────────────────────────
    job_list: list[JobListing]                # all discovered jobs
    current_job_index: int                    # pointer into job_list
    selected_job: JobListing | None           # job currently being evaluated

    # ── Matching & decision ──────────────────────────────────────────────
    match_score: float                        # 0-100
    match_reasoning: str                      # LLM explanation
    decision: Literal["apply", "skip", "ask"] | None

    # ── ATS optimisation ─────────────────────────────────────────────────
    optimized_resume: str                     # rewritten résumé text
    cover_letter: str

    # ── Application ──────────────────────────────────────────────────────
    application_status: Literal["success", "failed", "duplicate", "pending"] | None
    application_error: str

    # ── Tracking ─────────────────────────────────────────────────────────
    application_history: Annotated[list[ApplicationRecord], operator.add]

    # ── Diagnostics ──────────────────────────────────────────────────────
    logs: Annotated[list[str], operator.add]  # append-only audit trail
    missing_info: list[str]                   # fields the system couldn't extract
    clarification_request: str                # question posed back to the user


def build_initial_state(resume_path: str, user_profile: UserProfile | None = None) -> JobAgentState:
    """Factory for a clean initial state dict."""
    return JobAgentState(
        user_profile=user_profile or UserProfile(),
        resume_data=ResumeData(),
        resume_path=resume_path,
        job_list=[],
        current_job_index=0,
        selected_job=None,
        match_score=0.0,
        match_reasoning="",
        decision=None,
        optimized_resume="",
        cover_letter="",
        application_status=None,
        application_error="",
        application_history=[],
        logs=[],
        missing_info=[],
        clarification_request="",
    )
