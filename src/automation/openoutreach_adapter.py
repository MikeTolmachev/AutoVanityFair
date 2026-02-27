"""
Playwright helpers for LinkedIn browser automation.

Provides: build_playwright(), human_type(), playwright_login(), goto_page().
"""

import logging
import random

logger = logging.getLogger("openlinkedin.adapter")


async def build_playwright(headless: bool = False, slow_mo: int = 50, profile_dir: str = ""):
    """Build a Playwright persistent browser context."""
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


async def paste_content(page, editor, text: str) -> None:
    """Insert text into a contenteditable editor instantly via JS evaluation.

    Much faster than human_type() and immune to focus-stealing overlays.
    Falls back to clipboard paste if JS injection doesn't stick.
    """
    # Approach 1: Set innerText via JS and dispatch input event
    await editor.focus()
    await page.wait_for_timeout(300)

    await editor.evaluate("""(el, text) => {
        el.innerText = text;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }""", text)
    await page.wait_for_timeout(500)

    # Verify content was inserted
    actual = await editor.evaluate("el => el.innerText")
    actual_stripped = (actual or "").strip()
    expected_stripped = text.strip()

    if len(actual_stripped) >= len(expected_stripped) * 0.8:
        logger.info("paste_content: JS injection succeeded (%d chars)", len(actual_stripped))
        return

    # Approach 2: Clipboard paste fallback
    logger.warning("paste_content: JS injection incomplete (%d/%d chars), trying clipboard paste",
                   len(actual_stripped), len(expected_stripped))

    # Clear any partial content
    await editor.evaluate("el => { el.innerText = ''; }")
    await editor.focus()
    await page.wait_for_timeout(200)

    await page.evaluate("text => navigator.clipboard.writeText(text)", text)
    await page.keyboard.press("Meta+v")
    await page.wait_for_timeout(500)

    # Final verification
    actual = await editor.evaluate("el => el.innerText")
    actual_stripped = (actual or "").strip()
    if len(actual_stripped) >= len(expected_stripped) * 0.5:
        logger.info("paste_content: clipboard paste succeeded (%d chars)", len(actual_stripped))
    else:
        logger.error("paste_content: both approaches failed (got %d chars, expected ~%d)",
                     len(actual_stripped), len(expected_stripped))
        raise RuntimeError(f"Failed to insert content into editor (got {len(actual_stripped)} chars)")


async def human_type(page, text: str) -> None:
    """Type text character-by-character with human-like delays into the currently focused element."""
    for char in text:
        await page.keyboard.type(char, delay=random.randint(50, 150))
        if random.random() < 0.1:
            await page.wait_for_timeout(random.randint(100, 300))


async def playwright_login(session) -> None:
    """Log into LinkedIn. Skips login if cookies already have an active session."""
    page = session.page
    email = session.account_cfg["email"]
    password = session.account_cfg["password"]

    # Check if already logged in via saved cookies
    logger.info("Checking if already logged in...")
    await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)

    if "/feed" in page.url and "login" not in page.url:
        logger.info("Already logged in via saved cookies")
        return

    # Navigate to login page
    logger.info("Not logged in, navigating to login page...")
    await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    # Find and fill email field -- try multiple selectors
    email_selectors = [
        'input#username',
        'input[name="session_key"]',
        'input[autocomplete="username"]',
        'input[type="text"]',
    ]
    email_filled = False
    for sel in email_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=2000):
                await el.click()
                await el.fill("")
                await human_type(page, email)
                email_filled = True
                logger.info("Email entered via selector: %s", sel)
                break
        except Exception:
            continue

    if not email_filled:
        raise RuntimeError("Could not find email input on login page")

    # Find and fill password field
    password_selectors = [
        'input#password',
        'input[name="session_password"]',
        'input[autocomplete="current-password"]',
        'input[type="password"]',
    ]
    password_filled = False
    for sel in password_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=2000):
                await el.click()
                await el.fill("")
                await human_type(page, password)
                password_filled = True
                logger.info("Password entered via selector: %s", sel)
                break
        except Exception:
            continue

    if not password_filled:
        raise RuntimeError("Could not find password input on login page")

    # Click sign in button
    submit_selectors = [
        'button[type="submit"]',
        'button[aria-label="Sign in"]',
        'button:has-text("Sign in")',
    ]
    clicked = False
    for sel in submit_selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=2000):
                await btn.click()
                clicked = True
                logger.info("Sign in clicked via: %s", sel)
                break
        except Exception:
            continue

    if not clicked:
        raise RuntimeError("Could not find Sign in button")

    await page.wait_for_timeout(5000)

    current_url = page.url
    if "feed" in current_url or "mynetwork" in current_url:
        logger.info("LinkedIn login successful, URL: %s", current_url)
    elif "checkpoint" in current_url or "challenge" in current_url:
        logger.warning("Security challenge detected at %s -- manual intervention needed", current_url)
        # Wait up to 60 seconds for user to solve challenge
        for _ in range(12):
            await page.wait_for_timeout(5000)
            if "feed" in page.url:
                logger.info("Challenge resolved, now on feed")
                return
        raise RuntimeError(f"Login stuck at security challenge: {current_url}")
    else:
        raise RuntimeError(f"Login failed -- unexpected URL: {current_url}")


async def goto_page(page, url: str, wait_seconds: float = 2) -> None:
    """Navigate to a URL with human-like delay."""
    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_timeout(int(wait_seconds * 1000))
