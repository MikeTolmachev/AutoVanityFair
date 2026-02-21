"""
FeedScraper -- scrolls LinkedIn feed and extracts post cards.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("openlinkedin.feed_scraper")


@dataclass
class FeedPost:
    author: str = ""
    content: str = ""
    url: str = ""
    likes: int = 0
    comments: int = 0
    reposts: int = 0


class FeedScraper:
    """Scrolls LinkedIn feed and extracts post data using DOM selectors."""

    FEED_URL = "https://www.linkedin.com/feed/"

    # LinkedIn DOM selectors (may need updating as LinkedIn changes their markup)
    SELECTORS = {
        "post_card": "div.feed-shared-update-v2",
        "author": "span.feed-shared-actor__name",
        "content": "div.feed-shared-update-v2__description",
        "post_link": "a.app-aware-link[href*='/posts/'], a.app-aware-link[href*='/activity/']",
        "reactions": "span.social-details-social-counts__reactions-count",
        "comments_count": "button.social-details-social-counts__comments",
    }

    def __init__(self, session):
        self.session = session
        self.page = session.page

    async def scroll_feed(self, scroll_count: int = 5) -> None:
        """Scroll the feed to load more posts."""
        for i in range(scroll_count):
            await self.page.evaluate("window.scrollBy(0, window.innerHeight)")
            await self.session.wait(2)
            logger.debug("Feed scroll %d/%d", i + 1, scroll_count)

    async def get_feed_posts(
        self, max_posts: int = 10, scroll_count: int = 3
    ) -> list[FeedPost]:
        """Navigate to feed, scroll, and extract posts."""
        await self.page.goto(self.FEED_URL)
        await self.page.wait_for_load_state("networkidle")
        await self.session.wait(2)

        await self.scroll_feed(scroll_count)

        cards = await self.page.query_selector_all(self.SELECTORS["post_card"])
        logger.info("Found %d post cards in feed", len(cards))

        posts = []
        for card in cards[:max_posts]:
            post = await self._extract_post(card)
            if post and post.content:
                posts.append(post)

        logger.info("Extracted %d posts from feed", len(posts))
        return posts

    async def _extract_post(self, card) -> Optional[FeedPost]:
        """Extract data from a single post card element."""
        try:
            post = FeedPost()

            author_el = await card.query_selector(self.SELECTORS["author"])
            if author_el:
                post.author = (await author_el.inner_text()).strip()

            content_el = await card.query_selector(self.SELECTORS["content"])
            if content_el:
                post.content = (await content_el.inner_text()).strip()

            link_el = await card.query_selector(self.SELECTORS["post_link"])
            if link_el:
                post.url = await link_el.get_attribute("href") or ""

            reactions_el = await card.query_selector(self.SELECTORS["reactions"])
            if reactions_el:
                text = (await reactions_el.inner_text()).strip()
                try:
                    post.likes = int(text.replace(",", ""))
                except ValueError:
                    pass

            return post
        except Exception as e:
            logger.debug("Failed to extract post: %s", e)
            return None
