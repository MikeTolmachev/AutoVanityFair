#!/usr/bin/env python3
"""
Test LinkedIn browser login flow.
Opens a browser, attempts login, saves cookies to profile dir.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.config_manager import ConfigManager
from src.automation.session_manager import LinkedInSession
from src.automation.openoutreach_adapter import playwright_login


async def test_login():
    config = ConfigManager()

    if not config.linkedin.email or not config.linkedin.password:
        print("ERROR: LinkedIn credentials not set in .env")
        print("Set LINKEDIN_EMAIL and LINKEDIN_PASSWORD")
        sys.exit(1)

    print(f"Testing login for: {config.linkedin.email}")
    print(f"Profile dir: {config.linkedin.browser_profile_dir}")
    print("Browser will open -- you may need to solve a CAPTCHA.\n")

    session = LinkedInSession(
        email=config.linkedin.email,
        password=config.linkedin.password,
        headless=False,
        slow_mo=config.linkedin.slow_mo,
        profile_dir=config.linkedin.browser_profile_dir,
    )

    async with session:
        await playwright_login(session)

        print(f"\nCurrent URL: {session.page.url}")
        if "feed" in session.page.url:
            print("Login successful! Cookies saved.")
        else:
            print("Login may require manual intervention.")
            print("Check the browser window.")
            # Keep browser open for manual intervention
            input("Press Enter to close browser...")


def main():
    asyncio.run(test_login())


if __name__ == "__main__":
    main()
