"""
RSS/API Aggregator for production-focused AI content.

Fetches from multiple RSS feeds and APIs, applies content filtering,
and stores scored items for content generation grounding.
"""

import hashlib
import json
import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

from src.content.content_filter import ContentFilter, ScoredContent

logger = logging.getLogger("openlinkedin.rss_aggregator")

USER_AGENT = (
    "Mozilla/5.0 (compatible; OpenLinkedIn/1.0; "
    "+https://github.com/openlinkedin)"
)


# ---------------------------------------------------------------------------
# Feed source definitions
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FeedSource:
    name: str
    url: str
    source_type: str  # "rss", "api"
    priority: int     # 1-4, lower = higher priority
    category: str
    enabled: bool = True


# Priority 1: Production AI & MLOps Sources
PRIORITY_1_FEEDS: list[FeedSource] = [
    FeedSource(
        name="Hugging Face Daily Papers",
        url="https://huggingface.co/api/daily_papers",
        source_type="api",
        priority=1,
        category="Production AI & MLOps",
    ),
    FeedSource(
        name="Hugging Face Blog",
        url="https://huggingface.co/blog/feed.xml",
        source_type="rss",
        priority=1,
        category="Production AI & MLOps",
    ),
    FeedSource(
        name="MLOps Community Blog",
        url="https://mlops.community/feed/",
        source_type="rss",
        priority=1,
        category="Production AI & MLOps",
    ),
    FeedSource(
        name="The New Stack (AI Section)",
        url="https://thenewstack.io/category/ai/feed/",
        source_type="rss",
        priority=1,
        category="Production AI & MLOps",
    ),
    FeedSource(
        name="Neptune.ai Blog",
        url="https://neptune.ai/blog/feed",
        source_type="rss",
        priority=1,
        category="Production AI & MLOps",
    ),
    FeedSource(
        name="Weights & Biases Blog",
        url="https://wandb.ai/fully-connected/rss.xml",
        source_type="rss",
        priority=1,
        category="Production AI & MLOps",
    ),
    FeedSource(
        name="PyTorch Blog",
        url="https://pytorch.org/blog/feed.xml",
        source_type="rss",
        priority=1,
        category="Production AI & MLOps",
    ),
    FeedSource(
        name="NVIDIA Technical Blog (AI)",
        url="https://developer.nvidia.com/blog/feed/",
        source_type="rss",
        priority=1,
        category="Production AI & MLOps",
    ),
]

# Priority 2: Engineering-Focused Research Sources
PRIORITY_2_FEEDS: list[FeedSource] = [
    FeedSource(
        name="Google AI Blog",
        url="https://blog.google/technology/ai/rss/",
        source_type="rss",
        priority=2,
        category="Engineering Research",
    ),
    FeedSource(
        name="Meta AI Research",
        url="https://engineering.fb.com/category/ai-research/feed/",
        source_type="rss",
        priority=2,
        category="Engineering Research",
    ),
    FeedSource(
        name="OpenAI Blog",
        url="https://openai.com/news/rss.xml",
        source_type="rss",
        priority=2,
        category="Engineering Research",
    ),
]

# Priority 3: Infrastructure & Deployment Sources
PRIORITY_3_FEEDS: list[FeedSource] = [
    FeedSource(
        name="Ray Blog",
        url="https://www.anyscale.com/rss.xml",
        source_type="rss",
        priority=3,
        category="Infrastructure & Deployment",
    ),
    FeedSource(
        name="AWS Machine Learning Blog",
        url="https://aws.amazon.com/blogs/machine-learning/feed/",
        source_type="rss",
        priority=3,
        category="Infrastructure & Deployment",
    ),
    FeedSource(
        name="Google Cloud AI Blog",
        url="https://cloudblog.withgoogle.com/products/ai-machine-learning/rss/",
        source_type="rss",
        priority=3,
        category="Infrastructure & Deployment",
    ),
    FeedSource(
        name="Azure AI Blog",
        url="https://azure.microsoft.com/en-us/blog/tag/ai/feed/",
        source_type="rss",
        priority=3,
        category="Infrastructure & Deployment",
    ),
]

# Priority 4: Community & Discussion Sources
PRIORITY_4_FEEDS: list[FeedSource] = [
    FeedSource(
        name="Reddit r/MachineLearning",
        url="https://www.reddit.com/r/MachineLearning/.rss",
        source_type="rss",
        priority=4,
        category="Community & Discussion",
    ),
    FeedSource(
        name="Hacker News (AI/ML)",
        url="https://hnrss.org/newest?q=machine+learning+OR+AI+OR+LLM",
        source_type="rss",
        priority=4,
        category="Community & Discussion",
    ),
    FeedSource(
        name="LangChain Blog",
        url="https://blog.langchain.dev/rss/",
        source_type="rss",
        priority=4,
        category="Community & Discussion",
    ),
    FeedSource(
        name="LlamaIndex Blog",
        url="https://medium.com/feed/llamaindex-blog",
        source_type="rss",
        priority=4,
        category="Community & Discussion",
    ),
    FeedSource(
        name="TensorFlow Blog",
        url="https://blog.tensorflow.org/feeds/posts/default",
        source_type="rss",
        priority=4,
        category="Legacy Frameworks",
    ),
]

# Priority 2: Chinese AI Models & Research
CHINESE_AI_FEEDS: list[FeedSource] = [
    FeedSource(
        name="Tencent Hunyuan (GitHub)",
        url="https://github.com/Tencent-Hunyuan.atom",
        source_type="rss",
        priority=2,
        category="Chinese AI Models",
    ),
    FeedSource(
        name="Qwen Blog",
        url="https://qwenlm.github.io/blog/index.xml",
        source_type="rss",
        priority=2,
        category="Chinese AI Models",
    ),
    FeedSource(
        name="Baidu ERNIE (GitHub)",
        url="https://github.com/PaddlePaddle/ERNIE/releases.atom",
        source_type="rss",
        priority=2,
        category="Chinese AI Models",
    ),
    FeedSource(
        name="DeepSeek (GitHub)",
        url="https://github.com/deepseek-ai.atom",
        source_type="rss",
        priority=2,
        category="Chinese AI Models",
    ),
    FeedSource(
        name="Huawei",
        url="https://www.huawei.com/en/rss-feeds/huawei-updates/rss",
        source_type="rss",
        priority=2,
        category="Chinese AI Models",
    ),
    FeedSource(
        name="SenseTime OpenMMLab (GitHub)",
        url="https://github.com/open-mmlab.atom",
        source_type="rss",
        priority=2,
        category="Chinese AI Models",
    ),
    FeedSource(
        name="iFLYTEK (Google News)",
        url="https://news.google.com/rss/search?q=iFLYTEK+AI&hl=en-US&gl=US&ceid=US:en",
        source_type="rss",
        priority=2,
        category="Chinese AI Models",
    ),
    FeedSource(
        name="Chinese AI (TechNode)",
        url="https://technode.com/feed/",
        source_type="rss",
        priority=2,
        category="Chinese AI Models",
    ),
    FeedSource(
        name="Chinese AI (PandaDaily)",
        url="https://pandaily.com/feed/",
        source_type="rss",
        priority=2,
        category="Chinese AI Models",
    ),
]

ALL_FEEDS: list[FeedSource] = (
    PRIORITY_1_FEEDS + PRIORITY_2_FEEDS + CHINESE_AI_FEEDS
    + PRIORITY_3_FEEDS + PRIORITY_4_FEEDS
)


# ---------------------------------------------------------------------------
# Raw feed item
# ---------------------------------------------------------------------------
@dataclass
class FeedItem:
    title: str
    content: str
    url: str
    source_name: str
    source_priority: int
    source_category: str
    published_at: Optional[str] = None
    author: str = ""
    item_hash: str = ""

    def __post_init__(self):
        if not self.item_hash:
            raw = f"{self.title}{self.url}"
            self.item_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# RSS parser
# ---------------------------------------------------------------------------
def _fetch_url(url: str, timeout: int = 15) -> Optional[bytes]:
    """Fetch raw bytes from a URL."""
    import ssl

    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        # Try default SSL first, fall back to unverified for feeds with
        # broken certificate chains (e.g. hnrss.org).
        try:
            with urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except URLError as ssl_err:
            if "CERTIFICATE_VERIFY_FAILED" in str(ssl_err):
                logger.warning("SSL verify failed for %s, retrying without verification", url)
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urlopen(req, timeout=timeout, context=ctx) as resp:
                    return resp.read()
            raise
    except (URLError, OSError, TimeoutError) as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return None


def _parse_rss(raw_xml: bytes, source: FeedSource) -> list[FeedItem]:
    """Parse RSS/Atom XML into FeedItems."""
    items: list[FeedItem] = []
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as e:
        logger.warning("XML parse error for %s: %s", source.name, e)
        return items

    # Namespace handling for Atom feeds
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    # Try RSS 2.0 first
    for item_el in root.iter("item"):
        title = _text(item_el, "title")
        link = _text(item_el, "link")
        description = _text(item_el, "description")
        pub_date = _text(item_el, "pubDate")
        author = _text(item_el, "author") or _text(item_el, "dc:creator")

        if title:
            items.append(FeedItem(
                title=title,
                content=_strip_html(description or ""),
                url=link or "",
                source_name=source.name,
                source_priority=source.priority,
                source_category=source.category,
                published_at=pub_date,
                author=author or "",
            ))

    # Try Atom format if no RSS items found
    if not items:
        for entry in root.findall("atom:entry", ns):
            title = _text(entry, "atom:title", ns)
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            summary = _text(entry, "atom:summary", ns) or _text(entry, "atom:content", ns)
            published = _text(entry, "atom:published", ns) or _text(entry, "atom:updated", ns)
            author_el = entry.find("atom:author/atom:name", ns)
            author = author_el.text if author_el is not None and author_el.text else ""

            if title:
                items.append(FeedItem(
                    title=title,
                    content=_strip_html(summary or ""),
                    url=link,
                    source_name=source.name,
                    source_priority=source.priority,
                    source_category=source.category,
                    published_at=published,
                    author=author,
                ))

        # Fallback: try without namespace
        if not items:
            for entry in root.iter("entry"):
                title_el = entry.find("title")
                title = title_el.text if title_el is not None and title_el.text else ""
                link_el = entry.find("link")
                link = link_el.get("href", "") if link_el is not None else ""
                summary_el = entry.find("summary") or entry.find("content")
                summary = summary_el.text if summary_el is not None and summary_el.text else ""
                pub_el = entry.find("published") or entry.find("updated")
                published = pub_el.text if pub_el is not None and pub_el.text else ""

                if title:
                    items.append(FeedItem(
                        title=title,
                        content=_strip_html(summary),
                        url=link,
                        source_name=source.name,
                        source_priority=source.priority,
                        source_category=source.category,
                        published_at=published,
                        author="",
                    ))

    return items


def _text(el: ET.Element, tag: str, ns: Optional[dict] = None) -> str:
    """Get text content of a child element."""
    child = el.find(tag, ns) if ns else el.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return ""


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    import re
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


# ---------------------------------------------------------------------------
# Hugging Face Daily Papers API
# ---------------------------------------------------------------------------
def _fetch_huggingface_daily_papers(max_results: int = 20) -> list[FeedItem]:
    """Fetch trending papers from Hugging Face Daily Papers JSON API."""
    url = "https://huggingface.co/api/daily_papers"
    raw = _fetch_url(url, timeout=20)
    if not raw:
        return []

    items: list[FeedItem] = []
    try:
        papers = json.loads(raw)
        if not isinstance(papers, list):
            papers = papers.get("results", papers.get("data", []))

        for paper in papers[:max_results]:
            # The API returns paper objects; exact schema may vary
            paper_data = paper.get("paper", paper)
            title = paper_data.get("title", paper.get("title", ""))
            summary = paper_data.get("summary", paper.get("summary", ""))
            paper_id = paper_data.get("id", paper.get("id", ""))
            paper_url = f"https://huggingface.co/papers/{paper_id}" if paper_id else ""
            authors = paper_data.get("authors", paper.get("authors", []))
            author_names = []
            for a in authors[:3]:
                if isinstance(a, dict):
                    author_names.append(a.get("name", a.get("user", "")))
                elif isinstance(a, str):
                    author_names.append(a)
            published = paper.get("publishedAt", paper.get("published", ""))

            if title:
                items.append(FeedItem(
                    title=title,
                    content=summary[:500] if summary else "",
                    url=paper_url,
                    source_name="Hugging Face Daily Papers",
                    source_priority=1,
                    source_category="Production AI & MLOps",
                    published_at=published,
                    author=", ".join(author_names),
                ))
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("Hugging Face Daily Papers parse error: %s", e)

    return items


# ---------------------------------------------------------------------------
# Main Aggregator
# ---------------------------------------------------------------------------
class RSSAggregator:
    """
    Aggregates content from multiple RSS feeds and APIs,
    applies content filtering, and returns scored results.
    """

    def __init__(
        self,
        feeds: Optional[list[FeedSource]] = None,
        content_filter: Optional[ContentFilter] = None,
        fetch_timeout: int = 15,
        max_items_per_feed: int = 20,
    ):
        self.feeds = feeds if feeds is not None else ALL_FEEDS
        self.content_filter = content_filter or ContentFilter()
        self.fetch_timeout = fetch_timeout
        self.max_items_per_feed = max_items_per_feed
        self._cache: dict[str, tuple[float, list[FeedItem]]] = {}
        self._cache_ttl = 1800  # 30 minutes

    @property
    def enabled_feeds(self) -> list[FeedSource]:
        return [f for f in self.feeds if f.enabled]

    def get_feeds_by_priority(self, priority: int) -> list[FeedSource]:
        return [f for f in self.enabled_feeds if f.priority == priority]

    def fetch_feed(self, source: FeedSource) -> list[FeedItem]:
        """Fetch and parse a single feed source."""
        # Check cache
        now = time.time()
        if source.url in self._cache:
            cached_time, cached_items = self._cache[source.url]
            if now - cached_time < self._cache_ttl:
                logger.debug("Cache hit for %s", source.name)
                return cached_items

        logger.info("Fetching feed: %s", source.name)

        if source.source_type == "api" and "huggingface.co/api/daily_papers" in source.url:
            items = _fetch_huggingface_daily_papers(self.max_items_per_feed)
        else:
            raw = _fetch_url(source.url, timeout=self.fetch_timeout)
            if not raw:
                return []
            items = _parse_rss(raw, source)

        items = items[:self.max_items_per_feed]
        self._cache[source.url] = (now, items)
        logger.info("Fetched %d items from %s", len(items), source.name)
        return items

    def fetch_all(
        self,
        priorities: Optional[list[int]] = None,
    ) -> list[FeedItem]:
        """Fetch from all (or priority-filtered) feeds."""
        feeds_to_fetch = self.enabled_feeds
        if priorities:
            feeds_to_fetch = [f for f in feeds_to_fetch if f.priority in priorities]

        all_items: list[FeedItem] = []
        for source in feeds_to_fetch:
            try:
                items = self.fetch_feed(source)
                all_items.extend(items)
            except Exception as e:
                logger.error("Error fetching %s: %s", source.name, e)

        logger.info("Total items fetched: %d from %d feeds", len(all_items), len(feeds_to_fetch))
        return all_items

    def fetch_and_filter(
        self,
        priorities: Optional[list[int]] = None,
        max_results: int = 20,
    ) -> list[ScoredContent]:
        """Fetch, score, filter, and rank content from feeds."""
        raw_items = self.fetch_all(priorities)

        # Convert FeedItems to dicts for the content filter
        item_dicts = [
            {
                "title": item.title,
                "content": item.content,
                "url": item.url,
                "source": item.source_name,
                "author": item.author,
                "published_at": item.published_at,
            }
            for item in raw_items
        ]

        scored = self.content_filter.filter_and_rank(item_dicts, max_results)
        logger.info(
            "Filtered to %d items from %d raw (threshold: %.1f)",
            len(scored),
            len(raw_items),
            self.content_filter.min_score_threshold,
        )
        return scored

    def get_source_stats(self) -> dict:
        """Return stats about configured feed sources."""
        stats = {
            "total_feeds": len(self.feeds),
            "enabled_feeds": len(self.enabled_feeds),
            "by_priority": {},
            "by_category": {},
            "cached_feeds": len(self._cache),
        }
        for feed in self.feeds:
            p = f"priority_{feed.priority}"
            stats["by_priority"][p] = stats["by_priority"].get(p, 0) + 1
            stats["by_category"][feed.category] = (
                stats["by_category"].get(feed.category, 0) + 1
            )
        return stats
