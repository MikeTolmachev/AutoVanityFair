"""
LinkedInBot -- high-level LinkedIn actions with robust selectors and logging.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from src.automation.openoutreach_adapter import human_type, goto_page, playwright_login
from src.automation.session_manager import LinkedInSession
from src.automation.feed_scraper import FeedScraper, FeedPost
from src.core.safety_monitor import SafetyMonitor

logger = logging.getLogger("openlinkedin.bot")


@dataclass
class LinkedInSearchResult:
    """A post found via LinkedIn search."""
    author: str = ""
    content: str = ""
    url: str = ""
    likes: int = 0
    published_at: str = ""


class LinkedInBot:
    """High-level LinkedIn automation: publish posts, comments, search, scrape feed."""

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
            raise

    async def publish_post(self, content: str) -> bool:
        """Publish a text post to LinkedIn."""
        if not self.safety.can_act():
            logger.warning("Safety monitor blocked post publishing")
            return False

        page = self.session.page

        # Step 1: Go to feed
        logger.info("Step 1: Navigating to feed...")
        await goto_page(page, "https://www.linkedin.com/feed/")
        await page.wait_for_timeout(2000)

        # Step 2: Click "Start a post"
        logger.info("Step 2: Looking for 'Start a post' button...")
        start_selectors = [
            'button:has-text("Start a post")',
            'button[aria-label*="Start a post"]',
            'button.share-box-feed-entry__trigger',
            'div.share-box-feed-entry__trigger',
            '.share-box-feed-entry__top-bar',
        ]
        clicked = False
        for sel in start_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=3000):
                    await el.click()
                    clicked = True
                    logger.info("Clicked 'Start a post' via: %s", sel)
                    break
            except Exception:
                continue

        if not clicked:
            logger.error("Could not find 'Start a post' button")
            self.safety.record_error()
            return False

        await page.wait_for_timeout(2000)

        # Step 3: Find and type in editor
        logger.info("Step 3: Finding post editor...")
        editor_selectors = [
            'div[role="textbox"][contenteditable="true"]',
            'div.ql-editor[contenteditable="true"]',
            'div[data-placeholder*="What do you want to talk about"]',
            'div.editor-content[contenteditable="true"]',
            '[contenteditable="true"]',
        ]
        editor = None
        for sel in editor_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=3000):
                    editor = el
                    logger.info("Found editor via: %s", sel)
                    break
            except Exception:
                continue

        if not editor:
            logger.error("Could not find post editor")
            self.safety.record_error()
            return False

        await editor.click()
        await page.wait_for_timeout(500)

        # Type content with human-like speed
        logger.info("Step 4: Typing post content (%d chars)...", len(content))
        await human_type(page, content)
        await page.wait_for_timeout(500)

        # Dispatch input/change events so LinkedIn's React editor recognizes the content
        await editor.evaluate("""el => {
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }""")
        await page.wait_for_timeout(1500)

        # Step 5: Click Post button -- wait for it to become enabled
        logger.info("Step 5: Waiting for Post button to become enabled...")
        post_selectors = [
            'button.share-actions__primary-action:not([disabled])',
            'button[aria-label="Post"]:not([disabled])',
            'button:has-text("Post"):not([disabled])',
        ]
        post_clicked = False
        # Retry up to 5 times (10 seconds total) waiting for the button to enable
        for attempt in range(5):
            for sel in post_selectors:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=1000) and await el.is_enabled(timeout=1000):
                        await el.click()
                        post_clicked = True
                        logger.info("Clicked Post via: %s (attempt %d)", sel, attempt + 1)
                        break
                except Exception:
                    continue
            if post_clicked:
                break
            logger.info("Post button not enabled yet, retrying... (%d/5)", attempt + 1)
            # Nudge the editor again
            if editor:
                await editor.evaluate("""el => {
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                }""")
            await page.wait_for_timeout(2000)

        if not post_clicked:
            logger.error("Post button never became enabled after 5 attempts")
            self.safety.record_error()
            return False

        await page.wait_for_timeout(4000)

        self.safety.record_action()
        logger.info("Post published successfully")
        return True

    async def get_my_latest_post_url(self) -> Optional[str]:
        """Navigate to own profile's recent posts and return the latest post URL."""
        page = self.session.page

        # Go to own profile's posts tab
        logger.info("Finding own latest post URL...")
        await page.goto(
            "https://www.linkedin.com/in/me/recent-activity/all/",
            wait_until="domcontentloaded",
        )
        await page.wait_for_timeout(3000)

        # The activity page shows "Posted by <name>" - find the first post with an activity URN
        # These are links like /feed/update/urn:li:activity:1234/
        all_links = await page.locator('a[href*="urn:li:activity:"]').all()
        for link in all_links[:5]:
            try:
                href = await link.get_attribute("href")
                if href and "urn:li:activity:" in href:
                    if href.startswith("/"):
                        href = f"https://www.linkedin.com{href}"
                    # Clean up tracking params
                    if "?" in href:
                        href = href.split("?")[0]
                    logger.info("Found own latest post: %s", href)
                    return href
            except Exception:
                continue

        logger.warning("Could not find own latest post URL")
        return None

    async def comment_on_own_latest_post(self, comment_text: str) -> bool:
        """Find own latest post and comment on it."""
        post_url = await self.get_my_latest_post_url()
        if not post_url:
            logger.error("Cannot comment: could not find own latest post")
            return False
        return await self.publish_comment(post_url, comment_text)

    async def publish_comment(self, post_url: str, comment: str) -> bool:
        """Publish a comment on a LinkedIn post."""
        if not self.safety.can_act():
            logger.warning("Safety monitor blocked comment publishing")
            return False

        page = self.session.page
        logger.info("Navigating to post: %s", post_url)
        await goto_page(page, post_url)
        await page.wait_for_timeout(3000)

        # Click comment button to expand comment area
        comment_btn_selectors = [
            'button[aria-label*="Comment"]',
            'button:has-text("Comment")',
            'button.comment-button',
        ]
        for sel in comment_btn_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=3000):
                    await el.click()
                    logger.info("Clicked comment button via: %s", sel)
                    break
            except Exception:
                continue

        await page.wait_for_timeout(2000)

        # Find comment textbox
        comment_selectors = [
            'div[role="textbox"][contenteditable="true"][aria-label*="comment" i]',
            'div[role="textbox"][contenteditable="true"][aria-placeholder*="comment" i]',
            'div.ql-editor[data-placeholder*="Add a comment"]',
            # Last resort: any textbox, but skip the main share box
            'div.comments-comment-texteditor div[role="textbox"][contenteditable="true"]',
            'form.comments-comment-box div[role="textbox"]',
        ]
        comment_box = None
        for sel in comment_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=3000):
                    comment_box = el
                    logger.info("Found comment box via: %s", sel)
                    break
            except Exception:
                continue

        if not comment_box:
            logger.error("Could not find comment box")
            self.safety.record_error()
            return False

        await comment_box.click()
        await page.wait_for_timeout(500)
        await human_type(page, comment)
        await page.wait_for_timeout(1000)

        # Dispatch events
        await comment_box.evaluate("""el => {
            el.dispatchEvent(new Event('input', { bubbles: true }));
        }""")
        await page.wait_for_timeout(1000)

        # Submit -- look specifically for the comment submit button, not the share "Post" button
        submit_selectors = [
            'button.comments-comment-box__submit-button:not([disabled])',
            'form.comments-comment-box button[type="submit"]:not([disabled])',
            'button[aria-label*="Post comment"]:not([disabled])',
            'button[aria-label*="Submit comment"]:not([disabled])',
            # Fallback: the smaller "Post" button inside the comments section
            '.comments-comment-box button:has-text("Post"):not([disabled])',
        ]
        submit_clicked = False
        for attempt in range(3):
            for sel in submit_selectors:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=2000) and await el.is_enabled(timeout=1000):
                        await el.click()
                        submit_clicked = True
                        logger.info("Submitted comment via: %s", sel)
                        break
                except Exception:
                    continue
            if submit_clicked:
                break
            await page.wait_for_timeout(2000)

        if not submit_clicked:
            logger.error("Could not find submit button for comment")
            self.safety.record_error()
            return False

        await page.wait_for_timeout(3000)
        self.safety.record_action()
        logger.info("Comment published on %s", post_url)
        return True

    async def search_posts(self, query: str, max_results: int = 10) -> list[LinkedInSearchResult]:
        """Search LinkedIn for posts matching a query.

        Uses JavaScript DOM extraction since LinkedIn's CSS classes change frequently.
        """
        page = self.session.page
        from urllib.parse import quote

        search_url = f"https://www.linkedin.com/search/results/content/?keywords={quote(query)}&sortBy=%22date_posted%22"
        logger.info("Searching LinkedIn for: %s", query)
        await page.goto(search_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)

        # Scroll to load results
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await page.wait_for_timeout(2000)

        # Extract posts using JavaScript -- more robust than CSS selectors
        raw_posts = await page.evaluate("""() => {
            const posts = [];

            // Find all activity links on the page to identify post containers
            const allLinks = document.querySelectorAll('a[href*="urn:li:activity:"]');
            const seenUrns = new Set();

            for (const link of allLinks) {
                const href = link.getAttribute('href') || '';
                // Extract the activity URN
                const match = href.match(/urn:li:activity:\\d+/);
                if (!match || seenUrns.has(match[0])) continue;
                seenUrns.add(match[0]);

                // Walk up to find the post container (usually 3-6 levels up)
                let container = link;
                for (let i = 0; i < 8; i++) {
                    if (!container.parentElement) break;
                    container = container.parentElement;
                    // Stop at elements that look like post cards
                    const cls = container.className || '';
                    if (cls.includes('feed-shared-update') ||
                        cls.includes('update-components') ||
                        cls.includes('search-content') ||
                        container.getAttribute('data-urn')) {
                        break;
                    }
                }

                // Extract text content from the container
                const fullText = container.innerText || '';

                // Try to separate author from content
                const lines = fullText.split('\\n').filter(l => l.trim().length > 0);
                let author = '';
                let content = '';

                if (lines.length >= 2) {
                    // First non-empty line is usually the author name
                    author = lines[0].trim();
                    // Content is usually the longest block of text
                    let longestLine = '';
                    for (const line of lines) {
                        if (line.length > longestLine.length && line.length > 30) {
                            longestLine = line;
                        }
                    }
                    content = longestLine || lines.slice(1).join(' ').trim();
                }

                let url = href;
                if (url.startsWith('/')) url = 'https://www.linkedin.com' + url;
                // Strip query params
                const qIdx = url.indexOf('?');
                if (qIdx > 0) url = url.substring(0, qIdx);

                // Try to extract a relative timestamp (e.g. "2w", "1mo", "3d")
                let publishedAt = '';
                const timeEl = container.querySelector('time');
                if (timeEl) {
                    // Prefer the datetime attribute (ISO 8601)
                    publishedAt = timeEl.getAttribute('datetime') || timeEl.innerText.trim();
                } else {
                    // Fallback: look for short tokens like "2w", "1mo", "3d"
                    const timeMatch = fullText.match(/\b(\d+(?:s|m|mi|min|h|hr|d|w|mo|yr))\b/i);
                    if (timeMatch) publishedAt = timeMatch[1];
                }

                if (content.length > 20) {
                    posts.push({ author, content: content.substring(0, 500), url, publishedAt });
                }
            }

            return posts;
        }""")

        results = []
        seen_urls = set()
        for p in raw_posts[:max_results]:
            url = p.get("url", "")
            if url in seen_urls:
                continue
            seen_urls.add(url)
            results.append(LinkedInSearchResult(
                author=p.get("author", ""),
                content=p.get("content", ""),
                url=url,
                published_at=p.get("publishedAt", ""),
            ))

        logger.info("Extracted %d search results for '%s'", len(results), query)
        return results

    async def get_feed_posts(
        self, max_posts: int = 10, scroll_count: int = 3
    ) -> list[FeedPost]:
        """Get posts from the LinkedIn feed."""
        return await self.scraper.get_feed_posts(max_posts, scroll_count)
