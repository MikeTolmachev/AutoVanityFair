"""
LinkedInSession -- lightweight replacement for OpenOutreach's Django-coupled AccountSession.

Provides the same interface (.page, .context, .account_cfg, .wait()) that
OpenOutreach's navigation functions expect, without requiring Django models.
"""

import asyncio
import logging
from typing import Optional

from src.automation.openoutreach_adapter import build_playwright

logger = logging.getLogger("openlinkedin.session")


class LinkedInSession:
    """Manages a Playwright browser session for LinkedIn automation."""

    def __init__(
        self,
        email: str,
        password: str,
        headless: bool = False,
        slow_mo: int = 50,
        profile_dir: str = "data/browser_profile",
    ):
        self.account_cfg = {
            "email": email,
            "password": password,
        }
        self.headless = headless
        self.slow_mo = slow_mo
        self.profile_dir = profile_dir

        self._pw = None
        self._context = None
        self._page = None

    @property
    def page(self):
        return self._page

    @property
    def context(self):
        return self._context

    async def start(self) -> None:
        """Initialize browser and open a page."""
        self._pw, self._context = await build_playwright(
            headless=self.headless,
            slow_mo=self.slow_mo,
            profile_dir=self.profile_dir,
        )
        pages = self._context.pages
        self._page = pages[0] if pages else await self._context.new_page()
        logger.info("Browser session started")

    async def wait(self, seconds: float = 1) -> None:
        """Wait with human-like variability."""
        import random

        actual = seconds + random.uniform(-0.3, 0.5)
        await asyncio.sleep(max(0.1, actual))

    async def close(self) -> None:
        """Close browser and cleanup."""
        if self._context:
            await self._context.close()
        if self._pw:
            await self._pw.stop()
        logger.info("Browser session closed")

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
