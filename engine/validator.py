import logging
import random
import time
from typing import Dict, Any, List, Optional, Tuple
from playwright.sync_api import Page, ElementHandle

logger = logging.getLogger(__name__)

class ActionValidator:
    """
    Validates and recovers LLM-proposed actions before execution.
    Prevents blind execution of broken selectors.
    """
    
    def __init__(self, page: Page):
        self.page = page

    def set_page(self, page: Page):
        self.page = page

    def validate_action(self, action: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
        """
        Returns (is_valid, reason, recovered_selector).
        Checks if selector exists and handles fuzzy recovery.
        """
        selector = action.get("selector")
        action_type = action.get("type", "").lower()
        
        if not selector:
            # Scroll/Wait don't need selectors
            if action_type in ["scroll", "wait", "navigate", "close_tab"]:
                return True, "Valid", None
            return False, "Missing selector", None

        # 1. Direct check
        try:
            if self.page.locator(selector).count() > 0:
                return True, "Found", None
        except:
            pass

        # 1b. Frame check. form_parser prefixes iframe fields (f1_, f2_, ...)
        # and Playwright page.locator() does not resolve into frames.
        try:
            for frame in self.page.frames:
                if frame == self.page.main_frame or frame.is_detached():
                    continue
                if frame.locator(selector).count() > 0:
                    return True, "Found in frame", None
        except Exception:
            pass

        # 2. Fuzzy recovery if data-agent-idx is used
        # If [data-agent-idx='p_5'] fails, it might have changed to 'p_6' but with same label
        if "data-agent-idx" in selector:
            recovered = self._attempt_fuzzy_recovery(action)
            if recovered:
                logger.info(f"Validator: Recovered selector {selector} -> {recovered}")
                return True, "Recovered", recovered

        return False, f"Selector {selector} not found", None

    def _attempt_fuzzy_recovery(self, action: Dict[str, Any]) -> Optional[str]:
        """Attempts to find the element by other attributes if index fails."""
        # This requires metadata from the original state which we might not have here
        # But we can try to find elements by text if the LLM provided a label/thought
        return None # Placeholder for advanced recovery logic

class InteractionHumanizer:
    """
    Adds entropy and realistic behavior to Playwright interactions.
    Reduces anti-bot detection footprint.
    """
    
    def __init__(self, page: Page):
        self.page = page

    def human_click(self, selector: str):
        """Clicks with randomized offset and slight delay."""
        loc = self.page.locator(selector).first
        loc.scroll_into_view_if_needed(timeout=3000)
        box = loc.bounding_box()
        if not box:
            loc.click(force=True, timeout=5000)
            return

        # Random point within the middle 60% of the element
        x = box["x"] + box["width"] * random.uniform(0.2, 0.8)
        y = box["y"] + box["height"] * random.uniform(0.2, 0.8)
        
        self.page.mouse.move(x, y, steps=random.randint(5, 10))
        time.sleep(random.uniform(0.1, 0.3))
        try:
            self.page.mouse.click(x, y)
        except Exception:
            try:
                loc.click(force=True, timeout=5000)
            except Exception:
                loc.evaluate("el => el.click()")

    def human_type(self, selector: str, value: str):
        """Types with randomized intervals between keypresses."""
        loc = self.page.locator(selector).first
        loc.scroll_into_view_if_needed(timeout=3000)
        loc.click(timeout=5000)
        try:
            loc.fill("", timeout=1500)
        except Exception:
            try:
                self.page.keyboard.press("Control+A")
                self.page.keyboard.press("Backspace")
            except Exception:
                pass
        for char in str(value):
            self.page.keyboard.type(char)
            time.sleep(random.uniform(0.05, 0.15))
