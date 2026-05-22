import logging
import time
import random
import re
from difflib import SequenceMatcher
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
from playwright.sync_api import Page

from engine.validator import InteractionHumanizer
from engine.uploader import UploadManager

logger = logging.getLogger(__name__)

class ActionExecutor:
    """
    Production-grade action executor.
    Coordinates between humanized interactions, file uploads, and standard Playwright actions.
    """
    
    def __init__(self, page: Page, resume_path: str = ""):
        self.page = page
        self.resume_path = resume_path
        self.humanizer = InteractionHumanizer(page)
        self.uploader = UploadManager(page, resume_path=resume_path)

    def set_resume_path(self, resume_path: str) -> None:
        self.resume_path = resume_path or ""
        self.uploader.set_resume_path(self.resume_path)

    def set_page(self, page: Page):
        """Keep executor helpers bound to the active tab/page."""
        self.page = page
        self.humanizer = InteractionHumanizer(page)
        self.uploader = UploadManager(self.page, resume_path=self.resume_path)

    def click_first_matching_text(self, labels: List[str]) -> Optional[str]:
        """
        Deterministic fallback for common application flow buttons when the LLM
        misses a selector or a site uses non-standard button markup.
        """
        candidates: list[tuple[float, str, Any]] = []

        # Combine all labels into fewer selector queries for speed
        all_labels_escaped = [l.replace("'", "\\'") for l in labels]
        
        for label, escaped in zip(labels, all_labels_escaped):
            # Check for exact matches with higher priority
            primary_selectors = [
                f"button:has-text('{escaped}')",
                f"[role='button']:has-text('{escaped}')",
                f"input[type='submit'][value*='{escaped}' i]",
                f"a:has-text('{escaped}')",
            ]
            
            for selector in primary_selectors:
                try:
                    locator = self.page.locator(selector)
                    count = locator.count()
                    if count == 0: continue
                    
                    for idx in range(min(count, 5)): # Only check first 5 matches per selector
                        item = locator.nth(idx)
                        score = self._score_click_candidate(item, label)
                        if score > 0:
                            candidates.append((score, selector, item))
                except Exception:
                    continue
            
            # If we found high-quality matches, stop looking for this label
            if candidates and any(c[0] >= 100 for c in candidates):
                break

        # Secondary pass only if no candidates found yet
        if not candidates:
            for label, escaped in zip(labels, all_labels_escaped):
                secondary_selectors = [
                    f"[aria-label*='{escaped}' i]",
                    f"[data-test*='{escaped}' i]",
                    f"[class*='apply' i]:has-text('{escaped}')",
                ]
                for selector in secondary_selectors:
                    try:
                        locator = self.page.locator(selector)
                        count = locator.count()
                        if count == 0: continue
                        for idx in range(min(count, 3)):
                            item = locator.nth(idx)
                            score = self._score_click_candidate(item, label)
                            if score > 0:
                                candidates.append((score, selector, item))
                    except Exception: continue

        candidates.sort(key=lambda row: row[0], reverse=True)
        if candidates:
            logger.info("Click candidates: %s", [(c[0], c[1]) for c in candidates[:5]])
        
        for _, selector, locator in candidates:
            try:
                locator.scroll_into_view_if_needed(timeout=2000)
                try:
                    locator.click(timeout=3000)
                except Exception:
                    locator.evaluate("el => el.click()")
                return selector
            except Exception:
                continue
        return None

    def _locator_any_frame(self, selector: str):
        """Return the first matching locator in the main page or any iframe."""
        loc = self.page.locator(selector).first
        try:
            if loc.count() > 0:
                return loc
        except Exception:
            pass

        for frame in self.page.frames:
            if frame == self.page.main_frame:
                continue
            try:
                if frame.is_detached():
                    continue
                frame_loc = frame.locator(selector).first
                if frame_loc.count() > 0:
                    return frame_loc
            except Exception:
                continue
        return loc

    def _score_click_candidate(self, locator, label: str) -> float:
        try:
            # IMPORTANT: Use timeout=0 or very low to avoid blocking when checking many candidates
            if not locator.is_visible(timeout=50) or not locator.is_enabled(timeout=50):
                return 0
            box = locator.bounding_box() # Default timeout is low enough or synchronous if already visible
            if not box or box["width"] < 4 or box["height"] < 4:
                return 0

            meta = locator.evaluate(
                """el => ({
                    tag: el.tagName.toLowerCase(),
                    role: (el.getAttribute('role') || '').toLowerCase(),
                    type: (el.getAttribute('type') || '').toLowerCase(),
                    text: ((el.innerText || el.value || el.getAttribute('aria-label') || '') + '').trim(),
                    href: el.href || el.getAttribute('href') || '',
                    disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true'
                })"""
            )
        except Exception:
            return 0

        if meta.get("disabled"):
            return 0

        text = re.sub(r"\s+", " ", meta.get("text", "")).strip().lower()
        wanted = re.sub(r"\s+", " ", label).strip().lower()
        if not text and wanted not in ("next", "continue", "submit"):
            return 0

        score = 0.0
        if text == wanted:
            score += 120
        elif wanted in text and len(text) <= max(len(wanted) + 30, 45):
            score += 75
        else:
            return 0

        tag = meta.get("tag", "")
        role = meta.get("role", "")
        elem_type = meta.get("type", "")
        href = meta.get("href", "")

        if tag == "button" or role == "button" or elem_type in ("submit", "button"):
            score += 40
        elif tag == "a":
            score += 10
            if self._looks_like_non_application_link(href):
                score -= 80

        if wanted == "apply" and text != "apply":
            score -= 20
        if any(term in text for term in ("apply", "next", "continue", "review", "submit", "send", "finish")):
            score += 15

        return score if score >= 60 else 0

    def _looks_like_non_application_link(self, href: str) -> bool:
        if not href:
            return False
        url = href.lower()
        bad_terms = (
            "facebook", "twitter", "instagram", "youtube", "whatsapp",
            "mailto:", "tel:", "/blog", "/news", "/privacy", "/terms",
            "/contact", "/about", "/login", "/signup", "mobile.linkedin.com",
            "play.google.com", "apple.com/app-store"
        )
        return any(term in url for term in bad_terms)

    def _score_option(self, option_text: str, desired: str, keywords: List[str]) -> float:
        text = re.sub(r"\s+", " ", option_text.lower()).strip()
        desired_lower = re.sub(r"\s+", " ", str(desired).lower()).strip()
        if not text:
            return 0
        if desired_lower and desired_lower == text:
            return 100
        if desired_lower and (desired_lower in text or text in desired_lower):
            return 85

        score = SequenceMatcher(None, desired_lower, text).ratio() * 60 if desired_lower else 0
        for keyword in keywords or []:
            key = str(keyword).lower().strip()
            if not key:
                continue
            if key == text:
                score = max(score, 95)
            elif key in text or text in key:
                score = max(score, 80)
            else:
                key_tokens = {t for t in re.split(r"[^a-z0-9+#.]+", key) if len(t) > 1}
                text_tokens = {t for t in re.split(r"[^a-z0-9+#.]+", text) if len(t) > 1}
                overlap = len(key_tokens & text_tokens)
                if overlap:
                    score = max(score, 50 + overlap * 10)
        return score

    def _click_best_visible_option(self, desired: str, keywords: List[str]) -> Optional[str]:
        option_selector = (
            "[role='option'], .ant-select-item-option, .rc-virtual-list-holder-inner [title], "
            "li[role='option'], li, [data-value], [data-testid*='option' i]"
        )
        candidates = []
        roots = [self.page.main_frame] + [
            frame for frame in self.page.frames
            if frame != self.page.main_frame and not frame.is_detached()
        ]
        for root in roots:
            locator = root.locator(option_selector)
            count = min(locator.count(), 80)
            for idx in range(count):
                option = locator.nth(idx)
                try:
                    if not option.is_visible(timeout=300):
                        continue
                    text = option.inner_text(timeout=500).strip()
                    if not text:
                        text = option.get_attribute("title") or option.get_attribute("data-value") or ""
                    score = self._score_option(text, desired, keywords)
                    if score > 0:
                        candidates.append((score, text, option))
                except Exception:
                    continue

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0], reverse=True)
        _, text, option = candidates[0]
        option.scroll_into_view_if_needed(timeout=2000)
        try:
            option.click(timeout=3000)
        except Exception:
            option.evaluate("el => el.click()")
        return text

    def _select_dropdown(self, selector: str, value: str, keywords: List[str]) -> str:
        loc = self._locator_any_frame(selector)
        loc.scroll_into_view_if_needed(timeout=3000)

        try:
            tag_name = loc.evaluate("el => el.tagName.toLowerCase()")
        except Exception:
            tag_name = ""

        if tag_name == "select":
            option_texts = loc.evaluate(
                "el => Array.from(el.options).map(o => ({label: o.textContent.trim(), value: o.value}))"
            )
            best = None
            best_score = -1
            for option in option_texts:
                label = option.get("label", "")
                score = self._score_option(label, value, keywords)
                if score > best_score:
                    best = option
                    best_score = score
            if best and best_score > 0:
                loc.select_option(value=best["value"], timeout=3000)
                return f"Selected {best['label']} in {selector}"
            loc.select_option(label=str(value), timeout=3000)
            return f"Selected {value} in {selector}"

        loc.click(timeout=3000)
        time.sleep(0.4)

        chosen = self._click_best_visible_option(value, keywords)
        if chosen:
            return f"Selected dropdown option {chosen}"

        # Searchable combobox fallback: type desired value, then select best option.
        try:
            self.page.keyboard.type(str(value), delay=20)
            time.sleep(0.5)
            chosen = self._click_best_visible_option(value, keywords)
            if chosen:
                return f"Selected dropdown option {chosen}"
            self.page.keyboard.press("Enter")
            return f"Typed dropdown value {value}"
        except Exception:
            pass

        raise RuntimeError(f"No matching dropdown option found for {value}")

    def execute_action(self, action: Dict[str, Any]) -> str:
        """Executes a single action with appropriate handlers."""
        action_type = action.get("type", "").lower()
        selector = action.get("selector", "")
        value = action.get("value", "")

        try:
            if action_type == "click":
                self.human_click(selector)
                return f"Clicked {selector}"
            
            elif action_type == "fill":
                self.human_type(selector, value)
                return f"Filled {selector}"
            
            elif action_type == "type":
                self.human_type(selector, value)
                return f"Typed into {selector}"
            
            elif action_type == "upload":
                success = self.uploader.find_and_upload_resume(selector)
                return f"Upload {'success' if success else 'failed'} on {selector}"
            
            elif action_type == "check":
                loc = self._locator_any_frame(selector)
                try:
                    loc.check(timeout=3000)
                except Exception:
                    try:
                        loc.evaluate("el => { el.checked = true; el.dispatchEvent(new Event('change', {bubbles: true})); }")
                    except Exception:
                        try:
                            loc.click(timeout=2000)
                        except Exception:
                            pass
                return f"Checked {selector}"
            
            elif action_type == "radio":
                loc = self._locator_any_frame(selector)
                try:
                    loc.click(timeout=3000)
                except Exception:
                    try:
                        loc.evaluate("el => el.click()")
                    except Exception:
                        pass
                return f"Selected radio {selector}"
            
            elif action_type == "select_dropdown":
                return self._select_dropdown(selector, value, action.get("keywords", []))
            
            elif action_type == "scroll":
                # If a modal is open, try to scroll IT instead of the background
                modal_selectors = ".jobs-easy-apply-modal, .artdeco-modal, [role='dialog'], #apply-form, .apply-form"
                scrolled_modal = False
                try:
                    for sel in modal_selectors.split(", "):
                        modal = self.page.locator(sel).first
                        if modal.count() > 0 and modal.is_visible(timeout=200):
                            if value == "down": modal.evaluate("el => el.scrollBy(0, 400)")
                            elif value == "up": modal.evaluate("el => el.scrollBy(0, -400)")
                            elif value == "bottom": modal.evaluate("el => el.scrollTo(0, el.scrollHeight)")
                            scrolled_modal = True
                            break
                except Exception:
                    pass

                if not scrolled_modal:
                    if value == "down": self.page.evaluate("window.scrollBy(0, 500)")
                    elif value == "up": self.page.evaluate("window.scrollBy(0, -500)")
                    elif value == "bottom": self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                return f"Scrolled {value} {'(modal)' if scrolled_modal else '(window)'}"
            
            elif action_type == "wait":
                time.sleep(int(value) / 1000)
                return f"Waited {value}ms"
            
            elif action_type == "navigate":
                self.page.goto(value, wait_until="domcontentloaded")
                return f"Navigated to {value}"

            elif action_type == "close_tab":
                context = self.page.context
                if len(context.pages) > 1:
                    self.page.close()
                    self.page = context.pages[-1]
                    self.page.bring_to_front()
                    self.humanizer = InteractionHumanizer(self.page)
                    self.uploader = UploadManager(self.page)
                    return "Closed current tab"
                return "Skipped close_tab; only one tab is open"
            
            return f"Unknown action type: {action_type}"

        except Exception as e:
            raise e

    def human_click(self, selector: str) -> None:
        loc = self._locator_any_frame(selector)
        loc.scroll_into_view_if_needed(timeout=3000)
        try:
            loc.click(timeout=5000)
        except Exception:
            loc.evaluate("el => el.click()")

    def human_type(self, selector: str, value: str) -> None:
        loc = self._locator_any_frame(selector)
        loc.scroll_into_view_if_needed(timeout=3000)
        loc.click(timeout=5000)
        is_editable_div = False
        try:
            is_editable_div = loc.evaluate(
                """el => el.isContentEditable ||
                    el.getAttribute('role') === 'textbox' ||
                    el.getAttribute('contenteditable') === 'true'"""
            )
        except Exception:
            pass

        if is_editable_div:
            try:
                loc.evaluate(
                    """(el, value) => {
                        el.focus();
                        if (el.isContentEditable || el.getAttribute('contenteditable') === 'true') {
                            el.textContent = '';
                        }
                    }""",
                    str(value),
                )
            except Exception:
                pass
            self.page.keyboard.press("Control+A")
            self.page.keyboard.press("Backspace")
            self.page.keyboard.type(str(value), delay=25)
            return

        try:
            loc.fill(str(value), timeout=3000)
            return
        except Exception:
            self.page.keyboard.press("Control+A")
            self.page.keyboard.press("Backspace")
            self.page.keyboard.type(str(value), delay=25)
