"""
LangGraph workflow wiring
─────────────────────────
Assembles all agent nodes into a compiled StateGraph with:
  • Deterministic edges for the happy path
  • Conditional routing at the decision node
  • Per-job iteration loop

Flow:
  resume_parser → job_discovery → [select_job] → matcher → decision
                                                            │
                                        ┌───────────────────┼───────────────┐
                                        ▼                   ▼               ▼
                                   cover_letter          ask_user      tracker_skip
                                        │                                   │
                                        ▼                                   ▼
                                    apply_agent                         next_job?
                                        │                                   │
                                        ▼                              ┌────┴────┐
                                   tracker_apply                       ▼         ▼
                                        │                          select_job   END
                                        ▼
                                    next_job?
                                   ┌────┴────┐
                                   ▼         ▼
                               select_job   END
"""

from __future__ import annotations

import logging
import os
from functools import partial
from typing import Any

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from agents.deep_apply_agent import deep_apply_agent
from agents.cover_letter_agent import cover_letter_agent
from agents.decision_agent import decision_agent, route_after_decision
from agents.job_discovery_agent import job_discovery_agent
from agents.matcher_agent import matcher_agent
from agents.resume_parser_agent import resume_parser_agent
from agents.tracker_agent import tracker_agent
from graph.state import JobAgentState

load_dotenv()
logger = logging.getLogger(__name__)


# ── LLM factory ─────────────────────────────────────────────────────────────

def get_user_llm(state: JobAgentState):
    """
    Returns a configured LLM based on user settings in state.
    Prioritizes user-owned API keys, then falls back to system .env.
    """
    profile = state.get("user_profile", {})
    api_keys = profile.get("api_keys", {})
    pref_model = profile.get("preferred_model", "") or os.getenv("LLM_MODEL", "gpt-4o-mini")
    
    logger.info(f"LLM Factory: preferred_model='{pref_model}', "
                f"has_openai_key={bool(api_keys.get('openai'))}, "
                f"has_gemini_key={bool(api_keys.get('gemini'))}")
    
    # 1. Determine Provider
    if "gemini" in pref_model.lower():
        from langchain_google_genai import ChatGoogleGenerativeAI
        key = api_keys.get("gemini") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise ValueError(
                "Gemini model selected but no Gemini API key found. "
                "Please set your Gemini API key in Settings."
            )
        logger.info(f"Using Gemini: model={pref_model}")
        # Use a retry-capable model configuration
        return ChatGoogleGenerativeAI(
            model=pref_model, 
            google_api_key=key, 
            temperature=0,
            max_retries=5, # Built-in langchain retry
            timeout=60
        )
    else:
        # Default to OpenAI
        key = api_keys.get("openai") or os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError(
                "OpenAI model selected but no OpenAI API key found. "
                "Please set your OpenAI API key in Settings."
            )
        logger.info(f"Using OpenAI: model={pref_model}")
        return ChatOpenAI(model=pref_model, api_key=key, temperature=0, timeout=45)


# ── Node Wrappers (Late-binding LLM) ────────────────────────────────────────

def resume_parser_node(state: JobAgentState) -> dict[str, Any]:
    llm = get_user_llm(state)
    return resume_parser_agent(state, llm=llm)

def matcher_node(state: JobAgentState) -> dict[str, Any]:
    llm = get_user_llm(state)
    return matcher_agent(state, llm=llm)

def cover_letter_node(state: JobAgentState) -> dict[str, Any]:
    llm = get_user_llm(state)
    return cover_letter_agent(state, llm=llm)

def apply_agent_node(state: JobAgentState) -> dict[str, Any]:
    llm = get_user_llm(state)
    return deep_apply_agent(state, llm=llm)


# ── Helper nodes ─────────────────────────────────────────────────────────────

def select_job_node(state: JobAgentState) -> dict[str, Any]:
    """Pick the job at current_job_index from job_list."""
    idx = state.get("current_job_index", 0)
    job_list = state.get("job_list", [])

    if idx >= len(job_list):
        return {
            "selected_job": None,
            "logs": ["⏹ select_job: no more jobs to evaluate"],
        }

    job = job_list[idx]
    return {
        "selected_job": job,
        "match_score": 0.0,
        "match_reasoning": "",
        "decision": None,
        "optimized_resume": "",
        "cover_letter": "",
        "application_status": None,
        "application_error": "",
        "clarification_request": "",
        "logs": [
            f"👉 select_job: evaluating [{idx + 1}/{len(job_list)}] "
            f"{job.get('title', '?')} @ {job.get('company', '?')}"
        ],
    }


def advance_job_node(state: JobAgentState) -> dict[str, Any]:
    """Move the pointer to the next job."""
    idx = state.get("current_job_index", 0) + 1
    return {
        "current_job_index": idx,
        "logs": [f"➡️ advance_job: moving to job index {idx}"],
    }


def ask_user_node(state: JobAgentState) -> dict[str, Any]:
    """
    Terminal 'ask' node — in a real system this would pause execution
    and wait for user input.  For now, we log the question and skip.
    """
    selected_job = state.get("selected_job", {})
    return {
        "application_status": "ask_user",
        "logs": [
            f"❓ ask_user: awaiting user decision for "
            f"{selected_job.get('title', '?')} @ {selected_job.get('company', '?')}\n"
            f"   → {state.get('clarification_request', '')}"
        ],
    }


# ── Conditional routers ─────────────────────────────────────────────────────

def has_more_jobs(state: JobAgentState) -> str:
    """After tracking, decide whether to loop back or finish."""
    idx = state.get("current_job_index", 0) + 1   # +1 because we haven't advanced yet
    total = len(state.get("job_list", []))
    if idx < total:
        return "advance"
    return "done"


def has_more_jobs_after_apply(state: JobAgentState) -> str:
    """After applying (success or fail), continue to the next job."""
    status = state.get("application_status")
    if status != "success":
        logger.warning(
            "Apply did not succeed for job index %s (%s) — continuing to next job",
            state.get("current_job_index", 0),
            state.get("application_error", "unknown error"),
        )
    return has_more_jobs(state)


def has_more_jobs_after_advance(state: JobAgentState) -> str:
    """After advancing the pointer, check if the new index is valid."""
    idx = state.get("current_job_index", 0)
    total = len(state.get("job_list", []))
    if idx < total:
        return "continue"
    return "done"


# ── Graph builder ────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """
    Construct and compile the full LangGraph workflow.

    Returns a compiled graph ready for `.invoke()`.
    """
    # ── Build graph ──────────────────────────────────────────────────────
    graph = StateGraph(JobAgentState)

    # Add nodes
    graph.add_node("resume_parser", resume_parser_node)
    graph.add_node("job_discovery", job_discovery_agent)
    graph.add_node("select_job", select_job_node)
    graph.add_node("matcher", matcher_node)
    graph.add_node("decision", decision_agent)
    graph.add_node("cover_letter", cover_letter_node)
    graph.add_node("apply_agent", apply_agent_node)
    graph.add_node("tracker_apply", tracker_agent)
    graph.add_node("tracker_skip", tracker_agent)
    graph.add_node("ask_user", ask_user_node)
    graph.add_node("tracker_ask", tracker_agent)
    graph.add_node("advance_job", advance_job_node)

    # ── Deterministic edges ──────────────────────────────────────────────
    graph.set_entry_point("resume_parser")
    graph.add_edge("resume_parser", "job_discovery")
    graph.add_edge("job_discovery", "select_job")
    graph.add_edge("select_job", "matcher")
    graph.add_edge("matcher", "decision")

    # ── Conditional edge: decision routing ───────────────────────────────
    graph.add_conditional_edges(
        "decision",
        route_after_decision,
        {
            "cover_letter": "cover_letter",
            "ask_user": "ask_user",
            "tracker_skip": "tracker_skip",
        },
    )

    # Apply path
    graph.add_edge("cover_letter", "apply_agent")
    graph.add_edge("apply_agent", "tracker_apply")

    # After tracking (apply path) → check for more jobs
    graph.add_conditional_edges(
        "tracker_apply",
        has_more_jobs_after_apply,
        {"advance": "advance_job", "done": END},
    )

    # After tracking (skip path) → check for more jobs
    graph.add_conditional_edges(
        "tracker_skip",
        has_more_jobs,
        {"advance": "advance_job", "done": END},
    )

    # Ask user → track → check for more jobs
    graph.add_edge("ask_user", "tracker_ask")
    graph.add_conditional_edges(
        "tracker_ask",
        has_more_jobs,
        {"advance": "advance_job", "done": END},
    )

    # Advance job → loop back to select_job
    graph.add_edge("advance_job", "select_job")

    return graph.compile()


def run_workflow(resume_path: str, user_profile: dict | None = None) -> JobAgentState:
    """
    Entry-point: run the full workflow end-to-end.

    Args:
        resume_path: Path to the candidate's PDF résumé.
        user_profile: Optional dict with name, email, preferred_roles, etc.

    Returns:
        Final state dict after the entire pipeline completes.
    """
    from graph.state import build_initial_state

    initial_state = build_initial_state(resume_path, user_profile)
    compiled = build_graph()
    final_state = compiled.invoke(initial_state)
    return final_state
