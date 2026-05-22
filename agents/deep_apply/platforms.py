import logging
import os
import time

logger = logging.getLogger(__name__)

def login_platform(session, job_url: str) -> bool:
    """Login to LinkedIn or Naukri based on the job URL before applying."""
    if "linkedin.com" in job_url:
        li_user = os.environ.get("LINKEDIN_USER", "")
        li_pass = os.environ.get("LINKEDIN_PASS", "")
        if not li_user or not li_pass:
            logger.warning("LINKEDIN_USER/LINKEDIN_PASS not set — skipping login")
            return False
        try:
            session.page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=15000)
            time.sleep(2)
            if "/feed" in session.page.url and "/login" not in session.page.url:
                logger.info("✅ LinkedIn: already logged in")
                return True
            # Need to login
            session.page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=15000)
            time.sleep(2)
            if "/feed" in session.page.url:
                logger.info("✅ LinkedIn: session auto-redirected to feed")
                return True
            
            # Form login
            session.page.fill("#username", li_user)
            session.page.fill("#password", li_pass)
            session.page.click("button[type='submit']")
            time.sleep(3)
            return "/feed" in session.page.url
        except Exception as e:
            logger.error(f"LinkedIn login failed: {e}")
            return False

    elif "naukri.com" in job_url:
        nk_user = os.environ.get("NAUKRI_USER", "")
        nk_pass = os.environ.get("NAUKRI_PASS", "")
        if not nk_user or not nk_pass:
            logger.warning("NAUKRI_USER/NAUKRI_PASS not set — skipping login")
            return False
        try:
            session.page.goto("https://www.naukri.com/mnjuser/homepage", wait_until="domcontentloaded", timeout=15000)
            time.sleep(2)
            if "/homepage" in session.page.url:
                logger.info("✅ Naukri: already logged in")
                return True
            session.page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded", timeout=15000)
            time.sleep(2)
            session.page.fill("#usernameField", nk_user)
            session.page.fill("#passwordField", nk_pass)
            session.page.click("button[type='submit']")
            time.sleep(3)
            return "/homepage" in session.page.url
        except Exception as e:
            logger.error(f"Naukri login failed: {e}")
            return False
    
    return True
