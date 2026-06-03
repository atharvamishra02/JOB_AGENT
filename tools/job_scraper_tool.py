"""
job_scraper_tool
────────────────
Scrapes real job listings from LinkedIn and Naukri (primary focus).
Uses Playwright to navigate, login, and extract job URLs + metadata.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
import random
from typing import Any
from urllib.parse import quote

from db.database import init_db, ApplicationLog

logger = logging.getLogger(__name__)


def _make_job_id(job: dict) -> str:
    """Deterministic ID from URL (preferred) or company + title so we can detect duplicates."""
    url = job.get("url", "")
    if url:
        clean_url = url.split("?")[0].strip("/")
        raw = clean_url.lower()
    else:
        raw = f"{job.get('company', '')}::{job.get('title', '')}".lower()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _human_delay(lo: float = 1.5, hi: float = 3.0) -> None:
    """Random sleep to mimic human browsing."""
    time.sleep(random.uniform(lo, hi))


def scrape_jobs_real(
    keywords: list[str] | None = None,
    location: str | None = None,
    user_id: int | None = None,
) -> list[dict[str, Any]]:
    """
    Real scraping — focuses on LinkedIn and Naukri.
    Authenticates via .env credentials, searches, and extracts job card data.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright not installed. Run: pip install playwright && playwright install")
        return []

    results: list[dict[str, Any]] = []
    search_terms = keywords[:3] if keywords else ["Software", "Engineer"]
    kw_str = quote(" ".join(search_terms))
    loc_str = quote(location or "India")
    
    seen_db_job_ids = set()
    seen_db_urls = set()
    try:
        SessionFactory = init_db()
        with SessionFactory() as db_session:
            rows = db_session.query(ApplicationLog.job_id, ApplicationLog.url).all()
            for row in rows:
                if row.job_id:
                    seen_db_job_ids.add(row.job_id)
                if row.url:
                    clean_url = row.url.split("?")[0].strip("/").lower()
                    seen_db_urls.add(clean_url)
    except Exception as e:
        logger.warning(f"Failed to fetch past job IDs from DB: {e}")

    with sync_playwright() as p:
        # Use a SEPARATE profile for scraping to avoid lock conflicts with the agent
        user_data_dir = os.path.join(os.getcwd(), "browser_data")
        os.makedirs(user_data_dir, exist_ok=True)
        is_docker = os.environ.get("DOCKER_ENV", "").lower() in ("1", "true")
        launch_opts = dict(
            user_data_dir=user_data_dir,
            headless=False,  # Reverted to False to display on NoVNC X11 server
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-popup-blocking",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--js-flags=--max-old-space-size=512",
                "--disable-extensions",
                "--no-first-run",
                "--no-default-browser-check",
                "--mute-audio",
            ],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="en-US",
        )
        launch_opts["channel"] = "chrome"
        
        # Force kill any existing singleton locks to prevent "Profile in use" errors
        for lock_name in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
            lock_file = os.path.join(user_data_dir, lock_name)
            if os.path.lexists(lock_file):
                try:
                    logger.info(f"Removing stale Chrome lock file: {lock_file}")
                    os.remove(lock_file)
                except Exception as e:
                    logger.warning(f"Could not remove lock file {lock_file}: {e}")

        context = p.chromium.launch_persistent_context(**launch_opts)
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        if len(context.pages) > 0:
            page = context.pages[0]
        else:
            page = context.new_page()

        # ──────────────────────────────────────────────────────────────────
        # 1. LinkedIn (Primary)
        # ──────────────────────────────────────────────────────────────────
        try:
            logger.info("🔵 Scraping LinkedIn for: %s", " ".join(search_terms))
            li_user = os.environ.get("LINKEDIN_USER")
            li_pass = os.environ.get("LINKEDIN_PASS")

            if li_user and li_pass:
                # Check if already logged in by visiting feed
                page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
                _human_delay(1.5, 3.0)
                
                if "/feed" not in (page.url or "") or "/login" in (page.url or ""):
                    logger.info("  🔑 Logging into LinkedIn...")
                    page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
                    _human_delay(3.0, 5.0)

                    # If it redirected back to feed, we are logged in
                    if "/feed" in (page.url or ""):
                        logger.info("✅ LinkedIn: auto-redirected to feed, session active")
                    else:
                        try:
                            if page.is_visible("input#username", timeout=3000):
                                page.type("input#username", li_user, delay=random.randint(50, 120))
                                _human_delay(0.5, 1.0)
                                page.type("input#password", li_pass, delay=random.randint(50, 120))
                                _human_delay(0.8, 1.5)
                                page.click("button[type='submit']")
                                _human_delay(4, 7)
                        except Exception as inner_e:
                            logger.warning("LinkedIn login inputs not found: %s", inner_e)

                    # Handle checkpoint if it appears
                    if "checkpoint" in (page.url or ""):
                        logger.warning("  ⚠️ LinkedIn checkpoint — waiting 30s for manual solve")
                        try:
                            page.wait_for_url("**/feed/**", timeout=60000)
                        except:
                            pass
                else:
                    logger.info("✅ LinkedIn: already logged in (session active)")

            # Search for jobs (authenticated search gives better results)
            li_url = f"https://www.linkedin.com/jobs/search/?keywords={kw_str}&location={loc_str}"
            page.goto(li_url, wait_until="domcontentloaded", timeout=20000)
            _human_delay(3, 5)

            # Extract job cards inside a scroll loop so we can find new ones
            seen_hrefs = set()
            from server.workflow_manager import wf_manager
            for scroll_idx in range(6):
                if user_id:
                    from server.workflow_manager import wf_manager
                    if not wf_manager.get_state(user_id).is_running:
                        logger.info("🛑 Stop requested during LinkedIn scrape")
                        break
                for card_sel in [
                    "a.job-card-container__link",
                    "a.job-card-list__title",
                    ".job-card-container a[href*='/jobs/view/']",
                    "a[href*='/jobs/view/']",
                    ".base-card__full-link",
                ]:
                    try:
                        anchors = page.query_selector_all(card_sel)
                        for a in anchors:
                            title_text = a.inner_text().strip()
                            href = a.get_attribute("href") or ""

                            if not href or href in seen_hrefs:
                                continue
                            seen_hrefs.add(href)

                            clean_href = href.split("?")[0] if "linkedin.com" in href else href
                            full_url = f"https://www.linkedin.com{clean_href}" if clean_href.startswith("/") else clean_href

                            test_url = full_url.split("?")[0].strip("/").lower()
                            if test_url in seen_db_urls:
                                continue

                            company = "LinkedIn Company"
                            try:
                                card_parent = a.evaluate(
                                    "el => el.closest('.job-card-container, .base-card, li')"
                                    "?.querySelector('.job-card-container__primary-description, "
                                    ".base-search-card__subtitle, .artdeco-entity-lockup__subtitle')"
                                    "?.innerText || 'LinkedIn Company'"
                                )
                                company = (card_parent or "LinkedIn Company").strip()
                            except:
                                pass

                            job_data = {
                                "title": title_text.split("\n")[0].strip(),
                                "company": company,
                                "location": location or "India",
                                "description": f"LinkedIn Job: {title_text}. Apply via LinkedIn.",
                                "requirements": keywords or [],
                                "salary_range": "Undisclosed",
                                "url": full_url,
                                "source": "linkedin",
                                "posted_date": "Recent",
                            }
                            
                            job_id = _make_job_id(job_data)
                            if job_id in seen_db_job_ids:
                                continue

                            results.append(job_data)
                            if len(results) >= 8:
                                break
                    except:
                        continue
                        
                    if len(results) >= 8:
                        break
                        
                if len(results) >= 8:
                    break
                    
                # Scroll to load more cards
                page.evaluate("window.scrollBy(0, 800)")
                _human_delay(1.5, 2.5)

            logger.info("  📊 LinkedIn: found %d jobs", sum(1 for r in results if r["source"] == "linkedin"))

        except Exception as e:
            logger.warning("LinkedIn scrape failed: %s", e)

        # ──────────────────────────────────────────────────────────────────
        # 2. Naukri (Primary)
        # ──────────────────────────────────────────────────────────────────
        naukri_start = len(results)
        try:
            if page.is_closed():
                page = context.new_page()

            logger.info("🟢 Scraping Naukri for: %s", " ".join(search_terms))
            nk_user = os.environ.get("NAUKRI_USER")
            nk_pass = os.environ.get("NAUKRI_PASS")

            if nk_user and nk_pass:
                logger.info("  🔑 Logging into Naukri...")
                page.goto("https://www.naukri.com/", wait_until="domcontentloaded")
                _human_delay(3.0, 5.0)
                
                login_button_selector = "a#login_Layer, a[title='Jobseeker Login']"
                
                if not page.is_visible(login_button_selector):
                    logger.info("✅ Naukri: already logged in (Login button missing)")
                else:
                    # Click the Login button on the homepage to open strictly the login modal
                    try:
                        page.click(login_button_selector)
                        _human_delay(1.5, 2.5)
                    except:
                        pass

                    # Naukri login selectors (multiple patterns for resilience)
                    for sel in ["input#usernameField", "input[placeholder*='Email' i]", "input[type='email']"]:
                        try:
                            if page.is_visible(sel, timeout=2000):
                                page.type(sel, nk_user, delay=random.randint(50, 120))
                                break
                        except:
                            continue

                    _human_delay(0.5, 1.0)

                    for sel in ["input#passwordField", "input[placeholder*='Password' i]", "input[type='password']"]:
                        try:
                            if page.is_visible(sel, timeout=2000):
                                page.type(sel, nk_pass, delay=random.randint(50, 120))
                                break
                        except:
                            continue

                    _human_delay(0.8, 1.5)

                    for sel in ["button:has-text('Login')", "button[type='submit']"]:
                        try:
                            page.click(sel, timeout=3000)
                            break
                        except:
                            continue

                    _human_delay(4, 7)

            # Build Naukri search URL
            naukri_kw = "-".join(search_terms).lower().replace(" ", "-")
            naukri_url = f"https://www.naukri.com/{naukri_kw}-jobs"
            page.goto(naukri_url, wait_until="domcontentloaded", timeout=20000)
            _human_delay(3, 5)

            seen_naukri_hrefs: set[str] = set()
            from server.workflow_manager import wf_manager
            for scroll_idx in range(6):
                if user_id:
                    from server.workflow_manager import wf_manager
                    if not wf_manager.get_state(user_id).is_running:
                        logger.info("🛑 Stop requested during Naukri scrape")
                        break
                for card_sel in [
                    "a.title",
                    ".jobTupleHeader a",
                    "a[href*='naukri.com/job-listings']",
                    ".srp-jobtuple-wrapper a.title",
                    ".cust-job-tuple a.title",
                ]:
                    try:
                        anchors = page.query_selector_all(card_sel)
                        for a in anchors:
                            title_text = a.inner_text().strip()
                            href = a.get_attribute("href") or ""

                            if not href or href in seen_naukri_hrefs:
                                continue
                            seen_naukri_hrefs.add(href)

                            test_url = href.split("?")[0].strip("/").lower()
                            if test_url in seen_db_urls:
                                continue

                            # Extract company name
                            company = "Naukri Company"
                            try:
                                comp = a.evaluate(
                                    "el => el.closest('.jobTuple, .srp-jobtuple-wrapper, article, li')"
                                    "?.querySelector('.comp-name, .subTitle a, .companyInfo a')"
                                    "?.innerText || 'Naukri Company'"
                                )
                                company = (comp or "Naukri Company").strip()
                            except:
                                pass

                            job_data = {
                                "title": title_text.split("\n")[0].strip(),
                                "company": company,
                                "location": location or "India",
                                "description": f"Naukri Job: {title_text}. Apply via Naukri.",
                                "requirements": keywords or [],
                                "salary_range": "Undisclosed",
                                "url": href,
                                "source": "naukri",
                                "posted_date": "Recent",
                            }
                            
                            job_id = _make_job_id(job_data)
                            if job_id in seen_db_job_ids:
                                continue

                            results.append(job_data)

                            if len(results) - naukri_start >= 8:
                                break
                    except:
                        continue

                    if len(results) - naukri_start >= 8:
                        break
                        
                if len(results) - naukri_start >= 8:
                    break
                    
                # Scroll
                page.evaluate("window.scrollBy(0, 800)")
                _human_delay(1.5, 2.5)

            logger.info("  📊 Naukri: found %d jobs", sum(1 for r in results if r["source"] == "naukri"))

        except Exception as e:
            logger.warning("Naukri scrape failed: %s", e)

        context.close()

    # ── Deduplicate and assign IDs ───────────────────────────────────────
    final_results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for job in results:
        url = job.get("url", "")
        if url and url not in seen_urls:
            job["job_id"] = _make_job_id(job)
            final_results.append(job)
            seen_urls.add(url)

    if not final_results:
        logger.warning("⚠️ Scraping returned 0 jobs — check credentials and bot protection.")
    else:
        li_count = sum(1 for r in final_results if r["source"] == "linkedin")
        nk_count = sum(1 for r in final_results if r["source"] == "naukri")
        logger.info(
            "📊 job_scraper: %d total jobs (LinkedIn=%d, Naukri=%d)",
            len(final_results), li_count, nk_count,
        )

    return final_results
