import logging
import time
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

class SmartWaitManager:
    """
    Intelligent wait manager for production-grade web agents.
    Replaces brittle time.sleep() with state-based stabilization.
    """
    
    def __init__(self, page: Page):
        self.page = page

    def set_page(self, page: Page):
        self.page = page

    def wait_for_stable_dom(self, timeout_ms: int = 2000, interval_ms: int = 300):
        """
        Waits for the DOM to stop changing significantly.
        """
        if self.page.is_closed():
            return
        start_time = time.time()
        try:
            last_dom_len = len(self.page.content())
        except:
            return
        
        while (time.time() - start_time) * 1000 < timeout_ms:
            time.sleep(interval_ms / 1000)
            try:
                current_dom_len = len(self.page.content())
                if current_dom_len == last_dom_len:
                    break
                last_dom_len = current_dom_len
            except:
                break

    def wait_for_network_idle(self, timeout_ms: int = 1500):
        """Waits for network activity to settle."""
        try:
            if self.page.is_closed():
                return
            self.page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except PlaywrightTimeoutError:
            pass  # LinkedIn/Naukri never idle — this is expected
        except Exception as exc:
            if "closed" not in str(exc).lower():
                logger.debug("wait_for_network_idle: %s", exc)

    def wait_for_hydration(self):
        """Attempts to detect if a framework is done hydrating."""
        try:
            self.page.wait_for_function(
                "() => !document.querySelector('.loading-spinner, .spinner, .loader') && document.readyState === 'complete'",
                timeout=2000
            )
        except:
            pass

    def smart_wait(self):
        """Standard production wait sequence — fast but thorough."""
        self.wait_for_stable_dom(timeout_ms=2000)
        self.wait_for_network_idle(timeout_ms=1500)

    def quick_wait(self):
        """Wait after Apply click — modal needs time to render."""
        time.sleep(1.0)
        self.wait_for_stable_dom(timeout_ms=2000, interval_ms=250)
