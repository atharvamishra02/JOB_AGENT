"""
deep_apply_agent.py — Production Orchestrator
─────────────────────────────────────────────
Refactored autonomous loop using the modular Engine architecture.
"""

import logging
import os
import json
import time
import base64
from typing import Any, Dict
from playwright.sync_api import sync_playwright

try:
    from server.workflow_manager import wf_manager
except ImportError:
    wf_manager = None

# Core Tools
from tools.deep_browser_tools import get_session_manager, find_apply_modal_selector, APPLY_MODAL_SELECTORS
from tools.form_parser import extract_form_json
from tools.deterministic_filler import DeterministicFiller
from tools.dom_optimizer import DOMOptimizer
from tools.pinchtab_tool import PinchTabManager

# Engine Components
from engine.wait_manager import SmartWaitManager
from engine.memory import AgentMemoryManager
from engine.validator import ActionValidator, InteractionHumanizer
from engine.executor import ActionExecutor
from engine.recovery import RecoveryEngine
from engine.planner import ExecutionPlanner
from engine.uploader import resolve_resume_path

from graph.state import JobAgentState
from .deep_apply.platforms import login_platform
from .deep_apply.memory import load_learned_data, save_learned_data

logger = logging.getLogger(__name__)

# Load system prompt
PROMPT_PATH = os.path.join(os.path.dirname(__file__), "system_prompt_job_agent.md")
with open(PROMPT_PATH, "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()

SUCCESS_TERMS = [
    "application submitted", "application sent", "submitted application",
    "successfully applied", "application received", "response recorded",
    "your response has been recorded", "applied successfully",
    "thank you for applying", "thank you for your application",
    "thank you for your interest", "response has been recorded",
    "submission successful", "form submitted", "thanks for applying",
    "thanks for your interest", "successfully submitted", "application is sent",
    "thank you! your application has been submitted"
]

PRIMARY_BUTTON_LABELS = [
    "Easy Apply", "Apply Now", "Apply on company site", "Apply on company website",
    "Apply", "Next", "Continue", "Review", "Submit Application", "Submit",
    "Send Application", "Send", "Finish"
]

FORM_FLOW_BUTTON_LABELS = [
    "Next", "Continue", "Review", "Submit Application", "Submit",
    "Send Application", "Send", "Finish", "Start Application",
    "Save and next", "Save"
]

COOKIE_BUTTON_LABELS = ["Accept all", "Accept", "Allow all", "I agree", "Agree"]

APPLY_BUTTON_LABELS = [
    "Easy Apply", "Apply Now", "Simple Apply", "Apply on company site",
    "Apply on company website", "Apply"
]

BLOCKED_TERMS = [
    "no longer accepting applications", "no longer accepting applicants",
    "job is closed", "applications are closed", "job has expired",
    "not accepting applications"
]

CAPTCHA_TERMS = [
    "captcha", "recaptcha", "security verification", "verify you are human",
    "hcaptcha"
]

def _main_page_text(page) -> str:
    try:
        return (page.locator("body").inner_text(timeout=400) or "").lower()
    except Exception:
        return ""

def _all_frames_text(page) -> str:
    texts = [_main_page_text(page)]
    try:
        for frame in page.frames:
            try:
                if frame != page.main_frame and not frame.is_detached():
                    texts.append((frame.locator("body").inner_text(timeout=200) or "").lower())
            except Exception:
                pass
    except Exception:
        pass
    return "\n".join(texts)

def _is_success_state(page, dom: str = "") -> bool:
    haystack = dom.lower()
    if not haystack:
        haystack = _all_frames_text(page)
    else:
        haystack = f"{haystack}\n{_all_frames_text(page)}"
    return any(term in haystack for term in SUCCESS_TERMS)

def _is_blocked_or_closed(page, dom: str = "") -> str:
    haystack = f"{dom}\n{_main_page_text(page)}".lower()
    for term in CAPTCHA_TERMS:
        if term in haystack:
            return "captcha"
    for term in BLOCKED_TERMS:
        if term in haystack:
            return term
    return ""

def _count_apply_fields(form_json: dict) -> int:
    application_field_terms = (
        "first name", "last name", "full name", "name", "email", "phone", "mobile",
        "resume", "cv", "cover letter", "linkedin", "notice period", "current ctc",
        "salary", "experience", "years", "location", "city", "designation",
        "company", "employer", "expected", "current", "annual", "lakh",
        "gender", "dob", "date of birth", "nationality", "address",
        "skill", "qualification", "education", "degree", "college",
        "portfolio", "github", "website", "url",
    )
    count = 0
    for field in form_json.get("fields", []):
        hints = " ".join(
            str(field.get(k, "")) for k in ("label", "placeholder", "name", "aria_label", "text", "id")
        ).lower()
        if any(term in hints for term in application_field_terms):
            count += 1
        if field.get("type", "").lower() == "file":
            count += 1
    return count


def _has_application_surface(form_json: dict, page, after_apply_click: bool = False) -> bool:
    """True only when a real apply modal/form is open — not the job listing page."""
    scope = form_json.get("_scope", "")
    url = page.url.lower()
    fields = form_json.get("fields", [])
    buttons = form_json.get("buttons", [])
    n_fields = len(fields)
    n_buttons = len(buttons)
    apply_fields = _count_apply_fields(form_json)

    logger.info("Surface check: scope=%s, url_trunc=%s, fields=%d, apply_fields=%d, buttons=%d, after_click=%s",
                scope, url[:60], n_fields, apply_fields, n_buttons, after_apply_click)

    # If we are already in a modal and it has content, it's likely the surface.
    # LinkedIn pages can expose generic navigation iframes; a frame is only an
    # application surface when it has recognizable application fields.
    if "modal" in scope:
        if apply_fields >= 1 or n_buttons >= 1:
            logger.info("Surface detected via scope: %s", scope)
            return True
    if "frame" in scope:
        if apply_fields >= 1:
            logger.info("Surface detected via frame fields: %s", scope)
            return True

    # If the URL looks like an application form, be very lenient
    url_terms = ("apply", "application", "form", "jobs/", "careers/",
                 "naukri.com", "interview", "recruit", "lever.co", "greenhouse.io",
                 "workday", "icims", "taleo")
    if any(term in url for term in url_terms):
        if apply_fields >= 1 or (n_fields >= 1 and after_apply_click):
            logger.info("Surface detected via URL and fields")
            return True

    if find_apply_modal_selector(page):
        logger.info("Surface detected via modal selector")
        return apply_fields >= 1 or n_buttons >= 1

    # After we already clicked Apply and there are fields, be lenient
    if after_apply_click and n_fields >= 1:
        logger.info("Surface detected: post-apply-click with %d fields", n_fields)
        return True

    if apply_fields >= 1:
        flow_buttons = 0
        for btn in buttons:
            text = f"{btn.get('label', '')} {btn.get('text', '')}".lower()
            if any(term in text for term in ("submit", "review", "next", "continue", "apply", "save", "send")):
                flow_buttons += 1
        if flow_buttons >= 1:
            logger.info("Surface detected via %d fields + %d flow buttons", apply_fields, flow_buttons)
            return True

    return False


def _wait_for_apply_modal(page, timeout_ms: int = 3000) -> bool:
    """Fast parallel check: combine key selectors into one CSS query."""
    fast_selectors = (
        ".jobs-easy-apply-modal, .jobs-easy-apply-content, .artdeco-modal, "
        "[role='dialog'], .apply-popup, .application-wrap, "
        "[class*='apply-drawer' i], [class*='ApplyForm' i], "
        "#apply-form, .apply-form, .application-form, "
        "[id*='apply-container' i], [id*='apply-modal' i], .modal-content"
    )
    try:
        page.locator(fast_selectors).first.wait_for(state="visible", timeout=timeout_ms)
        return True
    except Exception:
        pass
    try:
        page.locator("form input:not([type='hidden'])").first.wait_for(state="visible", timeout=timeout_ms)
        return True
    except Exception:
        pass
    return False


def _button_text(button: dict) -> str:
    return " ".join(
        str(button.get(k, "")) for k in ("label", "text", "aria_label", "name")
    ).strip()


def _click_form_flow_button(executor, form_json: dict, labels: list[str]) -> str:
    """Prefer buttons extracted from the current form over global page matches."""
    wanted = [label.lower() for label in labels]
    candidates = []
    for btn in form_json.get("buttons", []):
        btn_id = btn.get("id")
        if not btn_id:
            continue
        text = _button_text(btn)
        text_low = text.lower()
        if not text_low:
            continue
        for rank, label in enumerate(wanted):
            if text_low == label or label in text_low:
                candidates.append((rank, len(text_low), btn_id, text))
                break
    if not candidates:
        return ""

    candidates.sort()
    _, _, btn_id, text = candidates[0]
    selector = f"[data-agent-idx='{btn_id}']"
    executor.execute_action({"type": "click", "selector": selector})
    return f"{selector} ({text})"


def _click_apply_until_started(session_tools, waiter, validator, executor, recovery, emit_log, max_attempts: int = 5) -> tuple[bool, str]:
    """
    Do not let the agent drift into form filling until the initial Apply action
    has actually opened a modal, side panel, or external application form.
    """
    for attempt in range(1, max_attempts + 1):
        page = _sync_active_page(session_tools, waiter, validator, executor, recovery)

        emit_log(f"  Apply attempt {attempt}: URL={page.url[:80]}")

        blocked = _is_blocked_or_closed(page)
        if blocked:
            if blocked == "captcha":
                emit_log("🛑 CAPTCHA DETECTED! Waiting for human intervention...")
                solved = False
                for i in range(12):
                    time.sleep(5)
                    emit_log(f"  ... still waiting for captcha solution ({i*5}s)")
                    page = _sync_active_page(session_tools, waiter, validator, executor, recovery)
                    if _is_blocked_or_closed(page) != "captcha":
                        solved = True
                        break
                if solved:
                    emit_log("✅ Captcha solved! Resuming...")
                    waiter.smart_wait()
                    continue
            return False, f"blocked_or_closed:{blocked}"

        form_json = extract_form_json(page)
        btn_labels = [b.get("label", b.get("text", "?"))[:40] for b in form_json.get("buttons", [])]
        field_count = len(form_json.get("fields", []))
        emit_log(f"  Found {field_count} fields, {len(btn_labels)} buttons: {btn_labels[:5]}")

        if _has_application_surface(form_json, page):
            emit_log("  ✅ Application surface detected!")
            return True, "application_surface_detected"

        clicked = executor.click_first_matching_text(APPLY_BUTTON_LABELS)
        if clicked:
            emit_log(f"  ✅ Clicked: {clicked}")
            _wait_for_apply_modal(page, timeout_ms=3000)
            waiter.smart_wait()
            page = _sync_active_page(session_tools, waiter, validator, executor, recovery)
            emit_log(f"  After click URL: {page.url[:80]}")
            post_form = extract_form_json(page)
            if _has_application_surface(post_form, page, after_apply_click=True):
                return True, "apply_clicked"
            if _is_success_state(page):
                return True, "success_after_apply_click"
            continue

        emit_log("  ❌ No Apply button matched; scrolling down...")
        try:
            executor.execute_action({"type": "scroll", "value": "down"})
        except Exception:
            pass
        waiter.quick_wait()

    return False, "apply_button_not_opened"


def _sync_active_page(session_tools, waiter, validator, executor, recovery):
    """After clicks can open tabs, make all engine components use the active page."""
    session_tools.get_state(reindex=False)
    active_page = session_tools.page
    waiter.set_page(active_page)
    validator.set_page(active_page)
    executor.set_page(active_page)
    recovery.set_page(active_page)
    return active_page


def deep_apply_agent(state: JobAgentState, llm) -> dict[str, Any]:
    job = state.get("selected_job", {})
    job_url = job.get("url")
    user_profile = state.get("user_profile", {})
    user_id = user_profile.get("user_id", 1)

    if not job_url:
        return {"application_status": "failed", "application_error": "No URL"}

    logs = []
    def emit_log(msg: str):
        logs.append(msg)
        logger.info(msg)
        if wf_manager:
            try:
                wf_manager.add_log(user_id, msg, "info", "apply_agent")
            except Exception:
                pass

    emit_log(f"🚀 Starting production-grade agent for {job.get('company')}")

    with sync_playwright() as p:
        # Use the SAME browser_data dir as the scraper so we share login cookies
        user_data_dir = os.path.join(os.getcwd(), "browser_data")
        session_tools = get_session_manager(p, user_data_dir)
        page = session_tools.page

        # Initialize Engine Components
        waiter = SmartWaitManager(page)
        memory = AgentMemoryManager()
        validator = ActionValidator(page)
        resume_path = resolve_resume_path(state.get("resume_path", ""))
        cover_letter = (state.get("cover_letter") or "").strip()
        executor = ActionExecutor(page, resume_path=resume_path)
        recovery = RecoveryEngine(page)
        planner = ExecutionPlanner(max_steps=60)
        optimizer = DOMOptimizer(token_budget=5000)
        pinchtab = PinchTabManager()
        
        needs_visual = False
        llm_form_calls = 0
        max_llm_form_calls = int(os.getenv("FORM_FILL_LLM_MAX_CALLS", "2"))
        empty_form_steps = 0
        resume_data = state.get("resume_data", {})
        if resume_path:
            emit_log(f"📄 Resume file: {resume_path}")
        local_profile = {
            **resume_data,
            **{k: v for k, v in user_profile.items() if v not in (None, "", [], {})},
        }
        contact = dict(resume_data.get("contact", {}) or {})
        for key in ("name", "email", "phone", "location", "linkedin", "github", "portfolio"):
            if user_profile.get(key) and not contact.get(key):
                contact[key] = user_profile[key]
        local_profile["contact"] = contact
        learned = load_learned_data(user_id)
        root_learned_path = os.path.join(os.getcwd(), "learned_placeholders.json")
        if os.path.exists(root_learned_path):
            try:
                with open(root_learned_path, "r", encoding="utf-8") as f:
                    learned = {**json.load(f), **learned}
            except Exception:
                pass
        filler = DeterministicFiller(local_profile, learned, cover_letter=cover_letter)
        executor.set_resume_path(resume_path)

        try:
            # 1. Platform Login & Navigation
            login_platform(session_tools, job_url)
            emit_log(f"🌐 Navigating to: {job_url}")
            page.goto(job_url, wait_until="domcontentloaded", timeout=20000)
            waiter.smart_wait()
            emit_log(f"📍 Landed on: {page.url}")
            emit_log(f"📄 Page title: {page.title()}")

            started, start_reason = _click_apply_until_started(
                session_tools, waiter, validator, executor, recovery, emit_log
            )
            page = _sync_active_page(session_tools, waiter, validator, executor, recovery)
            if _is_success_state(page):
                emit_log("SUCCESS: Application submitted confirmed.")
                return {"application_status": "success", "logs": logs}
            if not started:
                emit_log(f"FAILED: Could not open application flow ({start_reason}).")
                return {
                    "application_status": "failed",
                    "application_error": start_reason,
                    "logs": logs,
                }

            step = 0
            while planner.should_continue(step, page.url):
                step += 1
                emit_log(f"\n--- [Step {step}] ---")

                # 2. Capture compact state. Avoid screenshots unless the agent
                # explicitly escalates to visual mode.
                screenshot_b64 = ""

                if not needs_visual:
                    emit_log("👀 Eyes: Integrated AX mode (Token-Saving)")
                    ax_snapshot = pinchtab.get_snapshot(page)
                    has_ax_content = bool(ax_snapshot and ax_snapshot.get("children"))
                    if has_ax_content:
                        browser_state = {
                            "url": page.url,
                            "title": page.title(),
                            "simplified_dom": json.dumps(ax_snapshot, separators=(",", ":")),
                            "screenshot": ""
                        }
                        optimized_dom = browser_state["simplified_dom"]
                        raw_dom = optimized_dom
                    else:
                        emit_log("⚠️ AX tree empty. Falling back to Playwright.")
                        needs_visual = True
                        continue
                
                if needs_visual:
                    emit_log("📸 Eyes: Playwright (Full Vision)")
                    browser_state = session_tools.get_state()
                    page = _sync_active_page(session_tools, waiter, validator, executor, recovery)
                    raw_dom = browser_state["simplified_dom"]
                    optimized_dom = optimizer.optimize(raw_dom)
                    try:
                        screenshot_bytes = page.screenshot(type="jpeg", quality=40)
                        screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
                        browser_state["screenshot"] = screenshot_b64
                    except Exception:
                        browser_state["screenshot"] = ""
                
                # Check for Success/Stop
                if _is_success_state(page, optimized_dom):
                    emit_log("✅ SUCCESS: Application submitted confirmed.")
                    return {"application_status": "success", "logs": logs}

                blocked = _is_blocked_or_closed(page, optimized_dom)
                if blocked:
                    if blocked == "captcha":
                        emit_log("🛑 CAPTCHA DETECTED! Waiting for human intervention...")
                        solved = False
                        for i in range(12):
                            time.sleep(5)
                            emit_log(f"  ... still waiting for captcha solution ({i*5}s)")
                            if _is_blocked_or_closed(page) != "captcha":
                                solved = True
                                break
                        if solved:
                            emit_log("✅ Captcha solved! Resuming...")
                            waiter.smart_wait()
                            continue
                        else:
                            emit_log("❌ Timeout waiting for captcha solution.")
                    
                    emit_log(f"FAILED: Application blocked or closed ({blocked}).")
                    return {
                        "application_status": "failed",
                        "application_error": f"blocked_or_closed:{blocked}",
                        "logs": logs,
                    }
                
                if memory.is_stuck(raw_dom):
                    emit_log("⚠️ Stuck on same step — clicking Next/Submit to advance...")
                    memory.clear()
                    stuck_form = extract_form_json(page)
                    clicked = _click_form_flow_button(executor, stuck_form, FORM_FLOW_BUTTON_LABELS)
                    if not clicked and not stuck_form.get("buttons"):
                        clicked = executor.click_first_matching_text(FORM_FLOW_BUTTON_LABELS)
                    if clicked:
                        emit_log(f"Unstuck via {clicked}")
                    if not clicked:
                        try:
                            executor.execute_action({"type": "scroll", "value": "down"})
                        except Exception:
                            pass
                    waiter.smart_wait()
                    continue

                # 3. Hybrid Orchestration: Deterministic first
                form_json = extract_form_json(page)
                logger.info("Buttons found: %s", [b.get("text", b.get("label", "")) for b in form_json.get("buttons", [])])
                det_actions, remaining_form = filler.determine_actions(form_json)

                if step <= 2:
                    clicked = executor.click_first_matching_text(COOKIE_BUTTON_LABELS)
                    if clicked:
                        emit_log(f"Accepted banner via {clicked}")
                        waiter.smart_wait()
                        continue
                
                if det_actions:
                    new_actions = det_actions
                    if not new_actions:
                        emit_log("⚡ All known fields already filled this session — advancing")
                        clicked = _click_form_flow_button(executor, form_json, FORM_FLOW_BUTTON_LABELS)
                        if not clicked and not form_json.get("buttons"):
                            clicked = executor.click_first_matching_text(FORM_FLOW_BUTTON_LABELS)
                        if clicked:
                            emit_log(f"Advanced via {clicked}")
                            waiter.smart_wait()
                            continue
                    emit_log(f"⚡ Deterministic: Filling {len(new_actions)} known fields")
                    learned_updates = {}
                    for act in new_actions:
                        field_meta = act.pop("_field", None)
                        try:
                            res = executor.execute_action(act)
                            emit_log(res)
                            if field_meta and act.get("value"):
                                key = filler.memory_key_for_field(field_meta)
                                if key:
                                    learned_updates[key] = act["value"]
                        except Exception as e:
                            emit_log(f"⚠️ Deterministic fail: {e}")
                    if learned_updates:
                        save_learned_data(user_id, learned_updates)
                    waiter.smart_wait()
                    if _is_success_state(page):
                        emit_log("SUCCESS: Application submitted confirmed.")
                        return {"application_status": "success", "logs": logs}
                    if not remaining_form.get("fields"):
                        clicked = _click_form_flow_button(executor, form_json, FORM_FLOW_BUTTON_LABELS)
                        if not clicked and not form_json.get("buttons"):
                            clicked = executor.click_first_matching_text(FORM_FLOW_BUTTON_LABELS)
                        if clicked:
                            emit_log(f"Advanced form step via {clicked}")
                            waiter.smart_wait()
                            continue

                unresolved_fields = remaining_form.get("fields", [])
                if not unresolved_fields:
                    empty_form_steps += 1
                    clicked = _click_form_flow_button(executor, form_json, FORM_FLOW_BUTTON_LABELS)
                    if not clicked and not form_json.get("buttons"):
                        clicked = _click_form_flow_button(executor, remaining_form, FORM_FLOW_BUTTON_LABELS)
                        if not clicked and not remaining_form.get("buttons"):
                            clicked = executor.click_first_matching_text(FORM_FLOW_BUTTON_LABELS)
                    if clicked:
                        emit_log(f"Local flow clicked primary control via {clicked}")
                        waiter.smart_wait()
                        continue
                    emit_log("No unresolved fields or safe primary control; scrolling without LLM.")
                    try:
                        executor.execute_action({"type": "scroll", "value": "down"})
                    except Exception:
                        pass
                    waiter.quick_wait()
                    if empty_form_steps >= 3:
                        return {
                            "application_status": "failed",
                            "application_error": "no_form_progress_without_llm",
                            "logs": logs,
                        }
                    continue
                empty_form_steps = 0

                if llm_form_calls >= max_llm_form_calls:
                    emit_log(f"LLM form budget exhausted ({max_llm_form_calls}); continuing deterministically.")
                    clicked = _click_form_flow_button(executor, form_json, FORM_FLOW_BUTTON_LABELS)
                    if not clicked and not form_json.get("buttons"):
                        clicked = executor.click_first_matching_text(FORM_FLOW_BUTTON_LABELS)
                    if clicked:
                        emit_log(f"Budget fallback clicked primary control via {clicked}")
                        waiter.smart_wait()
                    else:
                        try:
                            executor.execute_action({"type": "scroll", "value": "down"})
                        except Exception:
                            pass
                        waiter.quick_wait()
                    continue

                # 4. LLM Planning
                emit_log("🧠 LLM Reasoning...")
                llm_form_calls += 1
                applicant_data = {
                    "contact": local_profile.get("contact", {}),
                    "name": local_profile.get("name", ""),
                    "current_title": local_profile.get("current_title", ""),
                    "years_of_experience": local_profile.get("years_of_experience", ""),
                    "skills": resume_data.get("skills", [])[:12],
                    "cover_letter": cover_letter,
                    "resume_path": resume_path,
                }
                
                prompt = (
                    f"### PROFILE\n{json.dumps(applicant_data)}\n\n"
                    f"### URL\n{page.url}\n\n"
                    f"### STRUCTURED_FORM_JSON\n{json.dumps(remaining_form)}\n\n"
                    f"### TASK\nReturn JSON actions only for the listed fields/buttons. "
                    f"Use at most 4 actions. Do not navigate away."
                )

                user_content = [{"type": "text", "text": prompt}]
                if needs_visual and browser_state.get("screenshot"):
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{browser_state['screenshot']}"}
                    })

                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content}
                ]

                try:
                    response = llm.invoke(messages)
                    content = response.content
                    if isinstance(content, list):
                        content = "".join([part.get("text", "") if isinstance(part, dict) else str(part) for part in content])
                    
                    # Strip markdown blocks if present
                    if "```json" in content:
                        content = content.split("```json")[1].split("```")[0].strip()
                    elif "```" in content:
                        content = content.split("```")[1].split("```")[0].strip()
                    
                    plan = json.loads(content)
                except Exception as e:
                    emit_log(f"⚠️ LLM Parsing Error: {e}")
                    clicked = _click_form_flow_button(executor, remaining_form, FORM_FLOW_BUTTON_LABELS)
                    if not clicked and not remaining_form.get("buttons"):
                        clicked = executor.click_first_matching_text(FORM_FLOW_BUTTON_LABELS)
                    if clicked:
                        emit_log(f"Fallback clicked primary flow control via {clicked}")
                        waiter.smart_wait()
                    else:
                        try:
                            executor.execute_action({"type": "scroll", "value": "down"})
                        except Exception:
                            pass
                    continue

                # 5. Validated Execution
                actions = plan.get("actions", [])
                allowed_ids = {
                    str(item.get("id"))
                    for item in remaining_form.get("fields", []) + remaining_form.get("buttons", [])
                    if item.get("id")
                }
                if not actions:
                    emit_log(f"⚠️ LLM returned no actions! Raw plan: {json.dumps(plan)[:200]}")
                
                # Handle Request Visual Fallback
                if any(a.get("type") == "request_visual" for a in actions):
                    if needs_visual:
                        emit_log("⚠️ Agent requested visual context but we ALREADY provided it! Forcing fallback to prevent infinite loop.")
                        clicked = executor.click_first_matching_text(FORM_FLOW_BUTTON_LABELS)
                        if clicked:
                            emit_log(f"Fallback clicked primary flow control via {clicked}")
                            waiter.smart_wait()
                        else:
                            try:
                                executor.execute_action({"type": "scroll", "value": "down"})
                            except Exception:
                                pass
                    else:
                        emit_log("🔍 Agent requested visual context. Switching to Playwright...")
                        needs_visual = True
                    continue

                executed_any = False
                for action in actions:
                    if action.get("type", "").lower() == "navigate":
                        target_url = str(action.get("value", "")).lower()
                        blocked_nav_terms = (
                            "mail.google.com", "accounts.google.com", "mailto:",
                            "calendar.google.com", "drive.google.com"
                        )
                        if any(term in target_url for term in blocked_nav_terms):
                            emit_log(f"Skipping unrelated navigation: {target_url[:120]}")
                            continue
                    selector = action.get("selector", "")
                    if selector and "data-agent-idx" in selector and allowed_ids:
                        if not any(
                            f"data-agent-idx='{item_id}'" in selector
                            or f'data-agent-idx="{item_id}"' in selector
                            for item_id in allowed_ids
                        ):
                            emit_log(f"Skipping out-of-form LLM selector: {selector}")
                            continue
                    is_valid, reason, recovered = validator.validate_action(action)
                    if not is_valid:
                        emit_log(f"🚫 Skipping invalid action: {reason}")
                        continue
                    
                    target_selector = recovered if recovered else action.get("selector", "")
                    if target_selector:
                        action["selector"] = target_selector
                    
                    try:
                        emit_log(f"🎯 Act: {action['type']} on {target_selector}")
                        res = executor.execute_action(action)
                        emit_log(res)

                        if action.get("type") in ("fill", "type") and action.get("value"):
                            for field in unresolved_fields:
                                sel = action.get("selector", "")
                                field_id = field.get("id", "")
                                if field_id and field_id in sel:
                                    key = filler.memory_key_for_field(field)
                                    if key:
                                        save_learned_data(user_id, {key: action["value"]})
                                    break

                        executed_any = True
                        memory.update(raw_dom, action, "SUCCESS")
                    except Exception as e:
                        fail_type = recovery.classify_failure(e, action)
                        emit_log(f"⚠️ Failed: {fail_type}")
                        recovery.attempt_recovery(fail_type, action)
                        memory.update(raw_dom, action, f"FAIL: {fail_type}")

                if not executed_any:
                    clicked = _click_form_flow_button(executor, remaining_form, FORM_FLOW_BUTTON_LABELS)
                    if not clicked and not remaining_form.get("buttons"):
                        clicked = executor.click_first_matching_text(FORM_FLOW_BUTTON_LABELS)
                    if clicked:
                        emit_log(f"Fallback clicked primary flow control via {clicked}")
                        memory.update(raw_dom, {"type": "click", "selector": clicked}, "FALLBACK_SUCCESS")
                    else:
                        emit_log("No executable LLM action or primary fallback found; scrolling for more fields.")
                        try:
                            executor.execute_action({"type": "scroll", "value": "down"})
                        except Exception:
                            pass

                # Reset visual flag for next step to save tokens again
                if needs_visual:
                    emit_log("🔄 Action completed. Reverting to token-saving AX mode.")
                    needs_visual = False

                waiter.smart_wait()
                page = _sync_active_page(session_tools, waiter, validator, executor, recovery)
                if _is_success_state(page):
                    emit_log("✅ SUCCESS: Application submitted confirmed.")
                    return {"application_status": "success", "logs": logs}

            if _is_success_state(page):
                return {"application_status": "success", "logs": logs}
            return {
                "application_status": "failed",
                "application_error": "application_not_submitted_before_budget",
                "logs": logs,
            }

        except Exception as e:
            logger.exception("Agent Crash")
            return {"application_status": "failed", "application_error": str(e), "logs": logs}
        finally:
            try:
                session_tools.context.close()
            except Exception:
                pass
