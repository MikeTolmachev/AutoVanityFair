"""
Adapter for OpenOutreach's Django-free Playwright functions.

Wraps functions from `external/OpenOutreach/` that don't depend on Django:
- build_playwright() from linkedin/navigation/login.py
- human_type() from linkedin/navigation/utils.py
- playwright_login() from linkedin/navigation/login.py

If OpenOutreach is not cloned, provides standalone fallback implementations.
"""

import logging
import os
import random
import sys
import time

logger = logging.getLogger("openlinkedin.adapter")

_OPENOUTREACH_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "external", "OpenOutreach"
)

_openoutreach_available = False

if os.path.isdir(_OPENOUTREACH_PATH):
    sys.path.insert(0, _OPENOUTREACH_PATH)
    try:
        from linkedin.navigation.utils import human_type as _oo_human_type
        from linkedin.navigation.login import build_playwright as _oo_build_playwright

        _openoutreach_available = True
        logger.info("OpenOutreach modules loaded from %s", _OPENOUTREACH_PATH)
    except ImportError as e:
        logger.warning("OpenOutreach import failed: %s. Using fallbacks.", e)


async def build_playwright(headless: bool = False, slow_mo: int = 50, profile_dir: str = ""):
    """Build a Playwright browser instance.

    Uses OpenOutreach's implementation if available, otherwise standalone.
    """
    if _openoutreach_available:
        return await _oo_build_playwright(headless=headless, slow_mo=slow_mo)

    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    browser = await pw.chromium.launch_persistent_context(
        user_data_dir=profile_dir or "data/browser_profile",
        headless=headless,
        slow_mo=slow_mo,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
    )

    try:
        from playwright_stealth import stealth_async

        page = browser.pages[0] if browser.pages else await browser.new_page()
        await stealth_async(page)
    except ImportError:
        logger.warning("playwright-stealth not available, skipping stealth setup")

    return pw, browser


async def human_type(page, selector: str, text: str) -> None:
    """Type text with human-like delays."""
    if _openoutreach_available:
        await _oo_human_type(page, selector, text)
        return

    element = await page.query_selector(selector)
    if element:
        await element.click()
        for char in text:
            await page.keyboard.type(char, delay=random.randint(50, 150))
            if random.random() < 0.1:
                await page.wait_for_timeout(random.randint(100, 300))


async def playwright_login(session) -> None:
    """Log into LinkedIn using session credentials.

    Args:
        session: Object with .page, .account_cfg (dict with 'email', 'password'), .wait()
    """
    page = session.page
    email = session.account_cfg["email"]
    password = session.account_cfg["password"]

    await page.goto("https://www.linkedin.com/login")
    await page.wait_for_load_state("networkidle")

    await human_type(page, "#username", email)
    await human_type(page, "#password", password)

    await page.click('button[type="submit"]')
    await page.wait_for_load_state("networkidle")
    await session.wait(3)

    if "feed" in page.url or "mynetwork" in page.url:
        logger.info("LinkedIn login successful")
    elif "checkpoint" in page.url or "challenge" in page.url:
        logger.warning("LinkedIn security challenge detected - manual intervention may be needed")
    else:
        logger.warning("Unexpected post-login URL: %s", page.url)


async def goto_page(page, url: str, wait_seconds: float = 2) -> None:
    """Navigate to a URL with human-like delay."""
    await page.goto(url)
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(int(wait_seconds * 1000))
