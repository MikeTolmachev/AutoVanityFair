"""
LinkedInBot -- high-level LinkedIn actions with safety checks.
"""

import logging
from typing import Optional

from src.automation.openoutreach_adapter import human_type, goto_page, playwright_login
from src.automation.session_manager import LinkedInSession
from src.automation.feed_scraper import FeedScraper, FeedPost
from src.core.safety_monitor import SafetyMonitor

logger = logging.getLogger("openlinkedin.bot")


class LinkedInBot:
    """High-level LinkedIn automation: publish posts, comments, scrape feed."""

    def __init__(
        self,
        session: LinkedInSession,
        safety_monitor: Optional[SafetyMonitor] = None,
    ):
        self.session = session
        self.safety = safety_monitor or SafetyMonitor()
        self.scraper = FeedScraper(session)

    async def login(self) -> bool:
        """Log into LinkedIn."""
        try:
            await playwright_login(self.session)
            self.safety.record_action()
            return True
        except Exception as e:
            logger.error("Login failed: %s", e)
            self.safety.record_error()
            return False

    async def publish_post(self, content: str) -> bool:
        """Publish a text post to LinkedIn."""
        if not self.safety.can_act():
            logger.warning("Safety monitor blocked post publishing")
            return False

        try:
            page = self.session.page

            await goto_page(page, "https://www.linkedin.com/feed/")

            # Click "Start a post" button
            start_post_btn = await page.query_selector(
                'button.share-box-feed-entry__trigger, '
                'button[aria-label*="Start a post"]'
            )
            if not start_post_btn:
                logger.error("Could not find 'Start a post' button")
                self.safety.record_error()
                return False

            await start_post_btn.click()
            await self.session.wait(2)

            # Type in the post editor
            editor = await page.query_selector(
                'div.ql-editor[contenteditable="true"], '
                'div[role="textbox"][contenteditable="true"]'
            )
            if not editor:
                logger.error("Could not find post editor")
                self.safety.record_error()
                return False

            await editor.click()
            await page.keyboard.type(content, delay=30)
            await self.session.wait(1)

            # Click Post button
            post_btn = await page.query_selector(
                'button.share-actions__primary-action, '
                'button[aria-label="Post"]'
            )
            if not post_btn:
                logger.error("Could not find Post button")
                self.safety.record_error()
                return False

            await post_btn.click()
            await self.session.wait(3)

            self.safety.record_action()
            logger.info("Post published successfully")
            return True

        except Exception as e:
            logger.error("Failed to publish post: %s", e)
            self.safety.record_error()
            return False

    async def publish_comment(self, post_url: str, comment: str) -> bool:
        """Publish a comment on a LinkedIn post."""
        if not self.safety.can_act():
            logger.warning("Safety monitor blocked comment publishing")
            return False

        try:
            page = self.session.page
            await goto_page(page, post_url)

            # Click comment button to open comment box
            comment_btn = await page.query_selector(
                'button[aria-label*="Comment"], '
                'button.comment-button'
            )
            if comment_btn:
                await comment_btn.click()
                await self.session.wait(1)

            # Find and type in comment box
            comment_box = await page.query_selector(
                'div.ql-editor[data-placeholder*="Add a comment"], '
                'div[role="textbox"][contenteditable="true"]'
            )
            if not comment_box:
                logger.error("Could not find comment box")
                self.safety.record_error()
                return False

            await comment_box.click()
            await page.keyboard.type(comment, delay=30)
            await self.session.wait(1)

            # Click submit
            submit_btn = await page.query_selector(
                'button.comments-comment-box__submit-button, '
                'button[aria-label="Post comment"]'
            )
            if not submit_btn:
                logger.error("Could not find submit button")
                self.safety.record_error()
                return False

            await submit_btn.click()
            await self.session.wait(2)

            self.safety.record_action()
            logger.info("Comment published on %s", post_url)
            return True

        except Exception as e:
            logger.error("Failed to publish comment: %s", e)
            self.safety.record_error()
            return False

    async def get_feed_posts(
        self, max_posts: int = 10, scroll_count: int = 3
    ) -> list[FeedPost]:
        """Get posts from the LinkedIn feed."""
        return await self.scraper.get_feed_posts(max_posts, scroll_count)
