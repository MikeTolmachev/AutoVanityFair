"""
LinkedInBot -- high-level LinkedIn actions with robust selectors and logging.
"""

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from src.automation.openoutreach_adapter import human_type, paste_content, goto_page, playwright_login
from src.automation.session_manager import LinkedInSession
from src.automation.feed_scraper import FeedScraper, FeedPost
from src.core.safety_monitor import SafetyMonitor

logger = logging.getLogger("openlinkedin.bot")


def strip_linkedin_markdown(text: str) -> str:
    """Convert markdown-formatted text to LinkedIn-compatible plain text.

    LinkedIn's editor does not render markdown, so asterisks and hashes
    appear literally.  This function strips them while preserving structure.
    """
    # Bold + italic (***text*** or ___text___)
    text = re.sub(r"\*{3}(.+?)\*{3}", r"\1", text)
    text = re.sub(r"_{3}(.+?)_{3}", r"\1", text)
    # Bold (**text** or __text__)
    text = re.sub(r"\*{2}(.+?)\*{2}", r"\1", text)
    text = re.sub(r"_{2}(.+?)_{2}", r"\1", text)
    # Italic (*text* or _text_) -- avoid matching bullet lines
    text = re.sub(r"(?<!\w)\*([^\s*].*?[^\s*])\*(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)_([^\s_].*?[^\s_])_(?!\w)", r"\1", text)
    # Headers (## Title)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Markdown bullet lists (* item or - item at line start) → bullet
    text = re.sub(r"^[\*\-]\s+", "• ", text, flags=re.MULTILINE)
    return text


@dataclass
class LinkedInSearchResult:
    """A post found via LinkedIn search."""
    author: str = ""
    content: str = ""
    url: str = ""
    likes: int = 0
    published_at: str = ""


def search_linkedin_via_google(query: str, max_results: int = 20) -> list[LinkedInSearchResult]:
    """Search for LinkedIn posts via Google News RSS (no browser needed).

    This is a fallback when the Playwright-based LinkedIn search returns 0
    results (e.g. due to DOM changes or auth issues).
    """
    import xml.etree.ElementTree as ET
    from urllib.parse import quote
    from src.content.rss_aggregator import _fetch_url, _strip_html

    search_query = f"site:linkedin.com/posts {query}"
    url = f"https://news.google.com/rss/search?q={quote(search_query)}&hl=en-US&gl=US&ceid=US:en"

    logger.info("Google fallback search: %s", query)
    raw = _fetch_url(url, timeout=15)
    if not raw:
        return []

    results: list[LinkedInSearchResult] = []
    try:
        root = ET.fromstring(raw)
        for item in root.iter("item"):
            title_el = item.find("title")
            link_el = item.find("link")
            desc_el = item.find("description")
            pub_el = item.find("pubDate")
            source_el = item.find("source")

            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            link = link_el.text.strip() if link_el is not None and link_el.text else ""
            description = _strip_html(desc_el.text) if desc_el is not None and desc_el.text else ""
            pub_date = pub_el.text.strip() if pub_el is not None and pub_el.text else ""
            author = source_el.text.strip() if source_el is not None and source_el.text else ""

            content = f"{title} {description}".strip()
            if content and len(content) > 20:
                results.append(LinkedInSearchResult(
                    author=author,
                    content=content[:500],
                    url=link,
                    published_at=pub_date,
                ))
                if len(results) >= max_results:
                    break
    except ET.ParseError as e:
        logger.warning("Google RSS parse error: %s", e)

    logger.info("Google fallback found %d results for '%s'", len(results), query)
    return results


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

    async def _take_debug_screenshot(self, step_name: str) -> str | None:
        """Save a timestamped screenshot to data/debug/ for post-mortem analysis."""
        try:
            debug_dir = "data/debug"
            os.makedirs(debug_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{debug_dir}/{ts}_{step_name}.png"
            await self.session.page.screenshot(path=filename, full_page=False)
            logger.info("Debug screenshot saved: %s", filename)
            return filename
        except Exception as e:
            logger.warning("Failed to save debug screenshot: %s", e)
            return None

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

    async def publish_post(self, content: str, asset_path: str = "") -> bool:
        """Publish a post to LinkedIn, optionally with a media attachment.

        Uses instant JS injection (paste_content) instead of character-by-character
        typing to avoid focus-steal issues from LinkedIn overlays.
        """
        if not self.safety.can_act():
            logger.warning("Safety monitor blocked post publishing")
            return False

        # Strip markdown so LinkedIn doesn't show raw asterisks/hashes
        content = strip_linkedin_markdown(content)

        page = self.session.page

        # Step 1: Go to feed
        logger.info("Step 1/6: Navigating to feed...")
        await goto_page(page, "https://www.linkedin.com/feed/")
        await page.wait_for_timeout(2000)

        # Step 2: Click "Start a post"
        logger.info("Step 2/6: Looking for 'Start a post' button...")
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
            await self._take_debug_screenshot("start_post_not_found")
            self.safety.record_error()
            return False

        await page.wait_for_timeout(2000)

        # Step 3: Find editor
        logger.info("Step 3/6: Finding post editor...")
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
            await self._take_debug_screenshot("editor_not_found")
            self.safety.record_error()
            return False

        # Step 4: Paste content instantly (no char-by-char typing)
        logger.info("Step 4/6: Pasting post content (%d chars)...", len(content))
        try:
            await paste_content(page, editor, content)
        except RuntimeError:
            await self._take_debug_screenshot("paste_content_failed")
            self.safety.record_error()
            return False

        # Step 5: Upload media asset (after content is in place)
        if asset_path:
            logger.info("Step 5/6: Uploading media asset: %s", asset_path)
            try:
                media_selectors = [
                    'button[aria-label*="Add media"]',
                    'button[aria-label*="Add a photo"]',
                    'button[aria-label*="photo"]',
                    'button.share-creation-state__action-button:has(li-icon[type="image"])',
                ]
                media_btn = None
                for sel in media_selectors:
                    try:
                        el = page.locator(sel).first
                        if await el.is_visible(timeout=2000):
                            media_btn = el
                            logger.info("Found media button via: %s", sel)
                            break
                    except Exception:
                        continue

                if media_btn:
                    async with page.expect_file_chooser() as fc_info:
                        await media_btn.click()
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(asset_path)
                    logger.info("File set via file_chooser, waiting for upload...")

                    # Wait for the image preview to appear
                    await page.wait_for_timeout(3000)
                    upload_done = False
                    for wait_attempt in range(15):
                        preview_selectors = [
                            'div.share-media-upload-manager__preview',
                            'img.share-media-upload-manager__image',
                            'div[class*="media-preview"]',
                            'div[class*="upload"] img',
                            '.share-creation-state__media-container img',
                        ]
                        for ps in preview_selectors:
                            try:
                                if await page.locator(ps).first.is_visible(timeout=500):
                                    upload_done = True
                                    logger.info("Upload preview detected via: %s", ps)
                                    break
                            except Exception:
                                continue
                        if upload_done:
                            break
                        logger.info("Waiting for upload... (%d/15)", wait_attempt + 1)
                        await page.wait_for_timeout(2000)

                    if not upload_done:
                        logger.warning("Could not detect upload preview, waiting 5s fallback")
                        await self._take_debug_screenshot("upload_preview_not_detected")
                        await page.wait_for_timeout(5000)

                    # Dismiss crop/edit overlay if LinkedIn shows one
                    crop_selectors = [
                        'button[aria-label="Done"]',
                        'button:has-text("Done")',
                        'button:has-text("Next")',
                        'button:has-text("Apply")',
                        'button[aria-label="Done cropping"]',
                    ]
                    for dismiss_sel in crop_selectors:
                        try:
                            dismiss_btn = page.locator(dismiss_sel).first
                            if await dismiss_btn.is_visible(timeout=1000):
                                await dismiss_btn.click()
                                logger.info("Dismissed upload overlay via: %s", dismiss_sel)
                                await page.wait_for_timeout(1000)
                                break
                        except Exception:
                            continue
                else:
                    logger.warning("Could not find media upload button, posting without asset")
                    await self._take_debug_screenshot("media_button_not_found")
            except Exception as e:
                logger.warning("Media upload failed, posting without asset: %s", e)
                await self._take_debug_screenshot("media_upload_error")
        else:
            logger.info("Step 5/6: No asset to upload, skipping.")

        # Re-dispatch events so LinkedIn's React editor registers the content
        await editor.evaluate("""el => {
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }""")
        await page.wait_for_timeout(1500)

        # Verify editor still has content (overlays may have cleared it)
        actual = await editor.evaluate("el => (el.innerText || '').trim()")
        if len(actual) < len(content.strip()) * 0.5:
            logger.error("Editor content lost after media upload (%d chars remaining)", len(actual))
            await self._take_debug_screenshot("content_lost")
            self.safety.record_error()
            return False

        # Step 6: Click Post button
        logger.info("Step 6/6: Waiting for Post button to become enabled...")
        post_selectors = [
            'button.share-actions__primary-action:not([disabled])',
            'button[aria-label="Post"]:not([disabled])',
            'button:has-text("Post"):not([disabled])',
        ]
        post_clicked = False
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
            await editor.evaluate("""el => {
                el.dispatchEvent(new Event('input', { bubbles: true }));
            }""")
            await page.wait_for_timeout(2000)

        if not post_clicked:
            logger.error("Post button never became enabled after 5 attempts")
            await self._take_debug_screenshot("post_button_disabled")
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

    async def search_posts(self, query: str, max_results: int = 20) -> list[LinkedInSearchResult]:
        """Search LinkedIn for posts matching a query.

        Uses JavaScript DOM extraction with multiple strategies since
        LinkedIn's CSS classes change frequently.
        """
        page = self.session.page
        from urllib.parse import quote

        search_url = (
            f"https://www.linkedin.com/search/results/content/"
            f"?keywords={quote(query)}"
        )
        logger.info("Searching LinkedIn for: %s", query)
        await page.goto(search_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)

        # Scroll more aggressively to load results
        for i in range(6):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await page.wait_for_timeout(2000 + i * 500)

        # Extract posts using JavaScript -- multiple extraction strategies
        raw_posts = await page.evaluate(r"""() => {
            const posts = [];
            const seenUrns = new Set();

            // --- Strategy 1: Activity URN links ---
            const actLinks = document.querySelectorAll('a[href*="urn:li:activity:"]');
            for (const link of actLinks) {
                const href = link.getAttribute('href') || '';
                const match = href.match(/urn:li:activity:\d+/);
                if (!match || seenUrns.has(match[0])) continue;
                seenUrns.add(match[0]);

                let container = link;
                for (let i = 0; i < 10; i++) {
                    if (!container.parentElement) break;
                    container = container.parentElement;
                    const cls = container.className || '';
                    if (cls.includes('feed-shared-update') ||
                        cls.includes('update-components') ||
                        cls.includes('search-content') ||
                        cls.includes('reusable-search__result-container') ||
                        container.getAttribute('data-urn') ||
                        container.getAttribute('data-chameleon-result-urn')) {
                        break;
                    }
                }

                const fullText = container.innerText || '';
                const lines = fullText.split('\n').filter(l => l.trim().length > 0);
                let author = lines.length >= 1 ? lines[0].trim() : '';
                let content = '';
                if (lines.length >= 2) {
                    let longest = '';
                    for (const line of lines) {
                        if (line.length > longest.length && line.length > 20) longest = line;
                    }
                    content = longest || lines.slice(1).join(' ').trim();
                }

                let url = href;
                if (url.startsWith('/')) url = 'https://www.linkedin.com' + url;
                const qIdx = url.indexOf('?');
                if (qIdx > 0) url = url.substring(0, qIdx);

                let publishedAt = '';
                const timeEl = container.querySelector('time');
                if (timeEl) publishedAt = timeEl.getAttribute('datetime') || timeEl.innerText.trim();

                if (content.length > 20) {
                    posts.push({ author, content: content.substring(0, 500), url, publishedAt });
                }
            }

            // --- Strategy 2: Search result containers (newer LinkedIn DOM) ---
            if (posts.length === 0) {
                const containers = document.querySelectorAll(
                    '.reusable-search__result-container, ' +
                    '[data-chameleon-result-urn], ' +
                    '.search-content__result, ' +
                    '.feed-shared-update-v2'
                );
                for (const container of containers) {
                    const fullText = container.innerText || '';
                    if (fullText.length < 50) continue;

                    const lines = fullText.split('\n').filter(l => l.trim().length > 0);
                    let author = lines.length >= 1 ? lines[0].trim() : '';
                    let content = '';
                    let longest = '';
                    for (const line of lines) {
                        if (line.length > longest.length && line.length > 20) longest = line;
                    }
                    content = longest || lines.slice(1, 5).join(' ').trim();
                    if (content.length < 20) continue;

                    // Try to find a post link
                    let url = '';
                    const aLink = container.querySelector('a[href*="urn:li:activity:"], a[href*="/feed/update/"]');
                    if (aLink) {
                        url = aLink.getAttribute('href') || '';
                        if (url.startsWith('/')) url = 'https://www.linkedin.com' + url;
                        const qIdx = url.indexOf('?');
                        if (qIdx > 0) url = url.substring(0, qIdx);
                    }

                    let publishedAt = '';
                    const timeEl = container.querySelector('time');
                    if (timeEl) publishedAt = timeEl.getAttribute('datetime') || timeEl.innerText.trim();

                    const key = url || content.substring(0, 80);
                    if (!seenUrns.has(key)) {
                        seenUrns.add(key);
                        posts.push({ author, content: content.substring(0, 500), url, publishedAt });
                    }
                }
            }

            return posts;
        }""")

        results = []
        seen_urls = set()
        for p in raw_posts[:max_results]:
            url = p.get("url", "")
            key = url or p.get("content", "")[:80]
            if key in seen_urls:
                continue
            seen_urls.add(key)
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
