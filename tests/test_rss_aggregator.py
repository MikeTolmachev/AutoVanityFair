import pytest

from src.content.rss_aggregator import (
    RSSAggregator,
    FeedSource,
    FeedItem,
    _parse_rss,
    _strip_html,
    ALL_FEEDS,
    PRIORITY_1_FEEDS,
    PRIORITY_2_FEEDS,
    PRIORITY_3_FEEDS,
    PRIORITY_4_FEEDS,
    CHINESE_AI_FEEDS,
)
from src.content.content_filter import ContentFilter


SAMPLE_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
    <title>Test Feed</title>
    <item>
        <title>How we deployed ML at scale with MLOps</title>
        <link>https://example.com/post1</link>
        <description>A production deployment case study with PyTorch inference optimization.</description>
        <pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
        <author>test@example.com</author>
    </item>
    <item>
        <title>New research paper on neural networks</title>
        <link>https://example.com/post2</link>
        <description>Novel experiment results and benchmark comparisons.</description>
        <pubDate>Tue, 02 Jan 2024 12:00:00 GMT</pubDate>
    </item>
    <item>
        <title>GPU optimization guide for distributed training</title>
        <link>https://example.com/post3</link>
        <description>&lt;p&gt;Step-by-step tutorial on CUDA and TensorRT.&lt;/p&gt;</description>
    </item>
</channel>
</rss>"""


SAMPLE_ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
    <title>Test Atom Feed</title>
    <entry>
        <title>Atom Entry: LLM Deployment</title>
        <link href="https://example.com/atom1"/>
        <summary>Deploying large language models to production.</summary>
        <published>2024-01-01T12:00:00Z</published>
        <author><name>Author Name</name></author>
    </entry>
</feed>"""


class TestStripHtml:
    def test_removes_tags(self):
        assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_handles_empty(self):
        assert _strip_html("") == ""

    def test_no_tags(self):
        assert _strip_html("plain text") == "plain text"


class TestParseRss:
    def test_parse_rss_items(self):
        source = FeedSource(
            name="Test",
            url="https://example.com/feed",
            source_type="rss",
            priority=1,
            category="Test",
        )
        items = _parse_rss(SAMPLE_RSS, source)
        assert len(items) == 3
        assert items[0].title == "How we deployed ML at scale with MLOps"
        assert items[0].url == "https://example.com/post1"
        assert items[0].source_name == "Test"
        assert items[0].source_priority == 1

    def test_parse_atom_items(self):
        source = FeedSource(
            name="Atom Test",
            url="https://example.com/atom",
            source_type="rss",
            priority=2,
            category="Test",
        )
        items = _parse_rss(SAMPLE_ATOM, source)
        assert len(items) == 1
        assert items[0].title == "Atom Entry: LLM Deployment"
        assert items[0].url == "https://example.com/atom1"
        assert items[0].author == "Author Name"

    def test_strips_html_from_content(self):
        source = FeedSource(
            name="Test", url="", source_type="rss", priority=1, category="Test"
        )
        items = _parse_rss(SAMPLE_RSS, source)
        # Third item has HTML in description
        assert "<p>" not in items[2].content
        assert "Step-by-step" in items[2].content

    def test_handles_malformed_xml(self):
        source = FeedSource(
            name="Bad", url="", source_type="rss", priority=1, category="Test"
        )
        items = _parse_rss(b"<not valid xml", source)
        assert items == []


class TestFeedItem:
    def test_auto_hash(self):
        item = FeedItem(
            title="Test Title",
            content="Content",
            url="https://example.com",
            source_name="Test",
            source_priority=1,
            source_category="Test",
        )
        assert len(item.item_hash) == 16

    def test_explicit_hash(self):
        item = FeedItem(
            title="Test",
            content="Content",
            url="",
            source_name="Test",
            source_priority=1,
            source_category="Test",
            item_hash="custom_hash",
        )
        assert item.item_hash == "custom_hash"


class TestFeedSources:
    def test_all_feeds_populated(self):
        assert len(ALL_FEEDS) > 0
        assert len(ALL_FEEDS) == (
            len(PRIORITY_1_FEEDS) + len(PRIORITY_2_FEEDS) + len(CHINESE_AI_FEEDS)
            + len(PRIORITY_3_FEEDS) + len(PRIORITY_4_FEEDS)
        )

    def test_priority_1_feeds(self):
        assert len(PRIORITY_1_FEEDS) == 8
        assert all(f.priority == 1 for f in PRIORITY_1_FEEDS)

    def test_priority_2_feeds(self):
        assert len(PRIORITY_2_FEEDS) == 3
        assert all(f.priority == 2 for f in PRIORITY_2_FEEDS)

    def test_all_feeds_have_urls(self):
        for feed in ALL_FEEDS:
            assert feed.url, f"{feed.name} has no URL"

    def test_all_feeds_have_names(self):
        for feed in ALL_FEEDS:
            assert feed.name, f"Feed with URL {feed.url} has no name"


class TestRSSAggregator:
    def test_default_initialization(self):
        agg = RSSAggregator()
        assert len(agg.feeds) == len(ALL_FEEDS)
        assert agg.content_filter is not None

    def test_custom_feeds(self):
        custom = [
            FeedSource("Custom", "https://example.com/rss", "rss", 1, "Test"),
        ]
        agg = RSSAggregator(feeds=custom)
        assert len(agg.feeds) == 1

    def test_enabled_feeds(self):
        feeds = [
            FeedSource("A", "url1", "rss", 1, "Cat", enabled=True),
            FeedSource("B", "url2", "rss", 1, "Cat", enabled=False),
            FeedSource("C", "url3", "rss", 2, "Cat", enabled=True),
        ]
        agg = RSSAggregator(feeds=feeds)
        assert len(agg.enabled_feeds) == 2

    def test_get_feeds_by_priority(self):
        agg = RSSAggregator()
        p1 = agg.get_feeds_by_priority(1)
        assert all(f.priority == 1 for f in p1)
        assert len(p1) == len(PRIORITY_1_FEEDS)

    def test_get_source_stats(self):
        agg = RSSAggregator()
        stats = agg.get_source_stats()
        assert "total_feeds" in stats
        assert "enabled_feeds" in stats
        assert "by_priority" in stats
        assert "by_category" in stats
        assert stats["total_feeds"] == len(ALL_FEEDS)


class TestFeedItemCRUD:
    def test_upsert_and_get(self, tmp_db):
        from src.database.crud import FeedItemCRUD

        crud = FeedItemCRUD(tmp_db)
        crud.upsert(
            item_hash="abc123",
            title="Test Feed Item",
            content="Content about MLOps",
            url="https://example.com",
            source_name="Test Source",
            final_score=25.5,
            content_type="production_case_study",
            matched_keywords=["MLOps", "production"],
        )
        assert crud.count() == 1

        top = crud.get_top_scored(limit=5)
        assert len(top) == 1
        assert top[0]["title"] == "Test Feed Item"
        assert top[0]["final_score"] == 25.5

    def test_upsert_deduplicates(self, tmp_db):
        from src.database.crud import FeedItemCRUD

        crud = FeedItemCRUD(tmp_db)
        crud.upsert(item_hash="dup1", title="First", final_score=10.0)
        crud.upsert(item_hash="dup1", title="First Updated", final_score=20.0)
        assert crud.count() == 1

        top = crud.get_top_scored()
        assert top[0]["final_score"] == 20.0

    def test_count_by_source(self, tmp_db):
        from src.database.crud import FeedItemCRUD

        crud = FeedItemCRUD(tmp_db)
        crud.upsert(item_hash="a", title="A", source_name="Source1")
        crud.upsert(item_hash="b", title="B", source_name="Source1")
        crud.upsert(item_hash="c", title="C", source_name="Source2")

        counts = crud.count_by_source()
        assert counts["Source1"] == 2
        assert counts["Source2"] == 1

    def test_mark_saved(self, tmp_db):
        from src.database.crud import FeedItemCRUD

        crud = FeedItemCRUD(tmp_db)
        crud.upsert(item_hash="s1", title="Saveable")
        items = crud.get_top_scored()
        crud.mark_saved(items[0]["id"])

        updated = crud.get_top_scored()
        assert updated[0]["saved_to_library"] == 1


@pytest.fixture
def tmp_db(tmp_path):
    from src.database.models import Database
    return Database(str(tmp_path / "test_feed.db"))
