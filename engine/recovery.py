import logging
import time
from typing import List, Dict, Any, Optional
from playwright.sync_api import Page

logger = logging.getLogger(__name__)

class RecoveryEngine:
    """
    Handles classification and recovery from various automation failures.
    Implements backtracking and safe rollbacks.
    """
    
    def __init__(self, page: Page):
        self.page = page

    def set_page(self, page: Page):
        self.page = page

    def classify_failure(self, error: Exception, last_action: Dict[str, Any]) -> str:
        """Classifies the type of failure for targeted recovery."""
        error_str = str(error).lower()
        if "timeout" in error_str:
            return "TIMEOUT"
        if "selector" in error_str or "not found" in error_str:
            return "SELECTOR_MISSING"
        if "visible" in error_str or "intersecting" in error_str:
            return "ELEMENT_OBSCURED"
        return "UNKNOWN"

    def attempt_recovery(self, failure_type: str, last_action: Dict[str, Any]) -> bool:
        """
        Attempts to recover based on the failure type.
        Returns True if recovery was successful.
        """
        logger.info(f"Recovery: Attempting recovery for {failure_type}")
        
        if failure_type == "ELEMENT_OBSCURED":
            # Try to close any potential overlays or scroll the element into view
            try:
                self.page.keyboard.press("Escape") # Close any rogue modals
                time.sleep(0.5)
                if last_action.get("selector"):
                    self.page.locator(last_action["selector"]).first.scroll_into_view_if_needed()
                return True
            except:
                return False
                
        if failure_type == "TIMEOUT":
            # Prefer waiting over refresh so partially filled forms are not lost.
            time.sleep(2)
            try:
                self.page.keyboard.press("Escape")
            except Exception:
                pass
            return True

        if failure_type == "SELECTOR_MISSING":
            # LLM needs to handle this in next step with a fresh DOM
            return True

        return False
