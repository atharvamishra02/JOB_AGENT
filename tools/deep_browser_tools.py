"""
deep_browser_tools.py — Session & Lifecycle Management
"""

import logging
import os
import base64
from urllib.parse import parse_qs, urlparse, urljoin
from typing import Any, Dict
from playwright.sync_api import Page, BrowserContext

from tools.dom_optimizer import simplify_html

logger = logging.getLogger(__name__)

INDEX_ELEMENTS_JS = """
(args) => {
    const prefix = args.prefix || 'p_';
    const rootSelector = args.rootSelector || '';
    const reset = !!args.reset;
    const root = rootSelector ? document.querySelector(rootSelector) : document;
    if (!root) return;

    if (reset) {
        root.querySelectorAll('[data-agent-idx]').forEach(el => el.removeAttribute('data-agent-idx'));
    }

    const interactive = 'a, button, input:not([type="hidden"]), select, textarea, [role="button"], [role="link"], [role="checkbox"], [role="radio"], [role="option"], [role="listbox"], [role="combobox"], [role="tab"], [role="textbox"], [contenteditable="true"], .btn, .button, [onclick], label[for], [class*="apply" i], [id*="apply" i], [data-test*="apply" i], [aria-label*="apply" i], [name*="apply" i]';
    const elements = Array.from(root.querySelectorAll(interactive));

    root.querySelectorAll('div, span, label').forEach(el => {
        const text = (el.innerText || '').trim();
        if (text.length > 0 && text.length < 40) {
            const low = text.toLowerCase();
            const exactPatterns = [
                'easy apply', 'apply now', 'apply on company site', 'apply on company website',
                'submit application', 'next', 'continue', 'review', 'submit', 'save and next'
            ];
            if (exactPatterns.some(p => low === p || low.startsWith(p + ' '))) {
                if (!elements.includes(el)) elements.push(el);
            }
        }
    });

    let counter = 1;
    elements.forEach(el => {
        if (el.hasAttribute('data-agent-idx')) return;
        const rect = el.getBoundingClientRect();
        if (rect.width < 4 || rect.height < 4) return;
        if (rect.bottom < 0 || rect.top > window.innerHeight * 10) return;
        el.setAttribute('data-agent-idx', `${prefix}${counter++}`);
    });
}
"""

FIND_APPLY_ROOT_JS = """
() => {
    const isVisible = (el) => {
        const r = el.getBoundingClientRect();
        // If it's a known apply container, be extremely lenient
        const isKnown = el.matches('.jobs-easy-apply-modal, .artdeco-modal, .jobs-apply-form, .application-outlet');
        if (isKnown) return r.width > 0 && r.height > 0;
        
        const hasSize = r.width > 20 && r.height > 20;
        const inView = r.top < window.innerHeight * 5 && r.bottom > -window.innerHeight * 2;
        return hasSize && inView;
    };
    const scoreEl = (el) => {
        let s = 0;
        const t = (el.innerText || '').toLowerCase();
        if (t.includes('easy apply')) s += 50;
        if (t.includes('submit application') || t.includes('review your application')) s += 40;
        if (t.includes('additional questions') || t.includes('contact info')) s += 25;
        const inputs = el.querySelectorAll('input:not([type="hidden"]), textarea, select');
        s += Math.min(inputs.length * 4, 40);
        if (el.querySelector('input[type="file"]')) s += 25;
        if (el.querySelector('input[type="email"], input[name*="email" i]')) s += 20;
        if (el.querySelector('input[name*="phone" i], input[type="tel"]')) s += 15;
        return s;
    };

    document.querySelectorAll('[data-agent-apply-root]').forEach(el => {
        el.removeAttribute('data-agent-apply-root');
    });

    const selectors = [
        '.jobs-easy-apply-modal', '.jobs-easy-apply-content', '.jobs-apply-form',
        '[data-test-modal-id*="easyApply" i]', '[data-test-modal]',
        '.artdeco-modal', '[role="dialog"]', '.jobs-details-module',
        '.apply-popup', '.application-wrap', '[class*="apply-drawer" i]',
        '[class*="ApplyForm" i]', 'form[action*="apply" i]', 'form',
        '#apply-form', '.apply-form', '.application-form', '[id*="apply-container" i]',
        '[class*="apply-container" i]', '[id*="apply-modal" i]', '.jobs-easy-apply-form-section__grouping',
        '.modal-content', '.jobs-easy-apply-modal-container', '.artdeco-modal__content',
        '.jobs-easy-apply-footer', '.jobs-apply-form__footer'
    ];
    const candidates = [];
    const seen = new Set();
    selectors.forEach(sel => {
        document.querySelectorAll(sel).forEach(el => {
            if (seen.has(el) || !isVisible(el)) return;
            seen.add(el);
            const sc = scoreEl(el);
            if (sc >= 12) candidates.push({ el, sc });
        });
    });

    candidates.sort((a, b) => b.sc - a.sc);
    if (!candidates.length) return '';
    candidates[0].el.setAttribute('data-agent-apply-root', '1');
    return '[data-agent-apply-root="1"]';
}
"""


APPLY_MODAL_SELECTORS = [
    "[data-agent-apply-root='1']",
    ".jobs-easy-apply-modal",
    ".jobs-easy-apply-content",
    ".jobs-apply-form",
    "[data-test-modal-id*='easyApply' i]",
    "[data-test-modal]",
    ".artdeco-modal.jobs-easy-apply-modal",
    ".artdeco-modal",
    "[role='dialog']",
    ".apply-popup",
    ".application-wrap",
    "[class*='apply-drawer' i]",
    "[class*='ApplyForm' i]",
    "form",
    "#apply-form",
    ".apply-form",
    ".application-form",
    "[id*='apply-container' i]",
    "[class*='apply-container' i]",
    "[id*='apply-modal' i]",
    ".jobs-easy-apply-modal",
    ".artdeco-modal",
    "[role='dialog']",
]


def index_page_elements(page: Page, prefix: str = "p_", root_selector: str = "", reset: bool = True) -> None:
    """Tag interactive elements with data-agent-idx."""
    payload = {"prefix": prefix, "rootSelector": root_selector, "reset": reset}
    try:
        page.evaluate(INDEX_ELEMENTS_JS, payload)
        if not root_selector and hasattr(page, "frames"):
            for i, frame in enumerate(page.frames[1:], start=1):
                try:
                    if not frame.is_detached():
                        frame.evaluate(
                            INDEX_ELEMENTS_JS,
                            {"prefix": f"f{i}_", "rootSelector": "", "reset": reset},
                        )
                except Exception:
                    pass
    except Exception as exc:
        logger.error("index_page_elements failed: %s", exc)


def find_apply_modal_selector(page: Page) -> str:
    """Find the best visible apply modal/form container."""
    try:
        js_root = page.evaluate(FIND_APPLY_ROOT_JS)
        if js_root:
            loc = page.locator(js_root).first
            if loc.count() > 0 and loc.is_visible(timeout=500):
                logger.info("Apply root found via JS: %s", js_root)
                return js_root
    except Exception as exc:
        logger.debug("JS apply root search failed: %s", exc)

    for sel in APPLY_MODAL_SELECTORS:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible(timeout=300):
                text = ""
                try:
                    text = (loc.inner_text(timeout=800) or "").lower()[:500]
                except Exception:
                    pass
                if sel == "form" and not any(
                    t in text for t in ("email", "phone", "resume", "apply", "name", "submit")
                ):
                    continue
                return sel
        except Exception:
            continue
    return ""


UNRELATED_TAB_TERMS = (
    "doubleclick.net", "googleadservices.com", "googlesyndication.com",
    "facebook.com/tr", "analytics.google.com", "googletagmanager.com",
    "/blog", "/news", "/privacy", "/terms", "/contact", "/about",
    "bankruptcy", "advertis", "utm_campaign", "mobile.linkedin.com",
    "apple.com/app-store", "play.google.com/store",
    "ambitionbox.com", "glassdoor.com",
)


def normalize_href(href: str, current_url: str = "") -> str:
    if not href or href.startswith(("javascript:", "#")):
        return ""
    if not href.startswith("http"):
        full_url = urljoin(current_url, href) if current_url else f"https://www.linkedin.com{href}"
    else:
        full_url = href
    parsed = urlparse(full_url)
    if parsed.netloc.endswith("linkedin.com") and parsed.path.startswith("/safety/go/"):
        target = parse_qs(parsed.query).get("url", [""])[0]
        if target:
            return target
    return full_url


def looks_unrelated_tab(url: str) -> bool:
    if not url or url in ("about:blank", "chrome://newtab/"):
        return True
    low = url.lower()
    return any(term in low for term in UNRELATED_TAB_TERMS)


class DeepBrowserSession:
    def __init__(self, context: BrowserContext, page: Page):
        self.context = context
        self.page = page

    def _sync_active_page(self) -> None:
        """Switch to the newest tab if multiple are open, and ensure it is focused."""
        if not self.context:
            return
            
        pages = self.context.pages
        if not pages:
            return
            
        # Get all non-closed pages
        active_pages = [p for p in pages if not p.is_closed()]
        if not active_pages:
            return
            
        latest_page = active_pages[-1]
        
        # Check if we should switch (new tab opened)
        if self.page != latest_page:
            url = latest_page.url
            if url and url not in ("about:blank", "chrome://newtab/"):
                logger.info("DeepAgent: Switching to latest tab: %s", url)
                self.page = latest_page
                try:
                    self.page.bring_to_front()
                    # Force re-indexing on new tab
                    index_page_elements(self.page, reset=True)
                except Exception as e:
                    logger.warning("Could not bring tab to front: %s", e)
        
        # Ensure current page is valid and responsive
        try:
            self.page.url
        except Exception:
            if len(active_pages) > 0:
                self.page = active_pages[-1]
                try:
                    self.page.bring_to_front()
                except Exception: pass

    def get_state(self, reindex: bool = True) -> Dict[str, Any]:
        self._sync_active_page()

        if reindex:
            root = find_apply_modal_selector(self.page)
            index_page_elements(self.page, root_selector=root or "", reset=True)

        try:
            html = self.page.content()
        except Exception as exc:
            logger.warning("Could not read page content after sync: %s", exc)
            self._sync_active_page()
            try:
                html = self.page.content()
            except Exception:
                return {
                    "url": getattr(self.page, "url", ""),
                    "title": "",
                    "simplified_dom": "",
                    "screenshot": "",
                }
        simplified = simplify_html(html)
        screenshot_b64 = ""
        try:
            screenshot_bytes = self.page.screenshot(type="jpeg", quality=70)
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        except Exception:
            pass

        return {
            "url": self.page.url,
            "title": self.page.title(),
            "simplified_dom": simplified,
            "screenshot": screenshot_b64,
        }


class DeepBrowserTools:
    def __init__(self, session: DeepBrowserSession):
        self.session = session

    @property
    def page(self):
        return self.session.page

    @property
    def context(self):
        return self.session.context

    def get_state(self, reindex: bool = True):
        return self.session.get_state(reindex=reindex)


def get_session_manager(p, user_data_dir: str) -> DeepBrowserTools:
    launch_opts = dict(
        user_data_dir=user_data_dir,
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-popup-blocking",
            "--disable-dev-shm-usage",
        ],
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1366, "height": 768},
        channel="chrome",
    )

    for lock in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
        f = os.path.join(user_data_dir, lock)
        if os.path.lexists(f):
            try:
                os.remove(f)
            except Exception:
                pass

    context = p.chromium.launch_persistent_context(**launch_opts)
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    page = context.pages[0] if context.pages else context.new_page()
    return DeepBrowserTools(DeepBrowserSession(context, page))
