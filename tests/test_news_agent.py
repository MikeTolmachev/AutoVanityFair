"""Tests for src.content.news_agent — topic extraction, normalization, research pipeline."""

import hashlib
import json
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from src.content.news_agent import (
    VALID_SOURCES,
    _normalize_item,
    _research_topic,
    extract_topics,
    run_research,
)
from src.database.crud import FeedItemCRUD, ContentLibraryCRUD, FeedbackCRUD
from src.database.models import Database


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def feed_crud(tmp_db):
    return FeedItemCRUD(tmp_db)


@pytest.fixture
def content_crud(tmp_db):
    return ContentLibraryCRUD(tmp_db)


@pytest.fixture
def feedback_crud(tmp_db):
    return FeedbackCRUD(tmp_db)


def _make_mock_config():
    """Create a minimal mock config for tests."""
    config = MagicMock()
    config.aggregation.auto_save_threshold = 999.0  # don't auto-save in tests
    config.vertex_ai.project_id = ""  # skip embeddings
    return config


SAMPLE_LAST30DAYS_OUTPUT = {
    "topic": "AI agents",
    "reddit": [
        {
            "id": "abc123",
            "title": "Built a multi-agent system for customer support",
            "url": "https://www.reddit.com/r/MachineLearning/comments/1abc123/built_a_multi_agent/",
            "subreddit": "MachineLearning",
            "date": "2026-03-15",
            "engagement": {"upvotes": 150, "comments": 42},
            "top_comments": ["Great work!", "How does it handle failures?"],
            "score": 85,
        },
        {
            "id": "def456",
            "title": "NVIDIA announces new inference chip",
            "url": "https://www.reddit.com/r/hardware/comments/1def456/nvidia_announces/",
            "subreddit": "hardware",
            "date": "2026-03-14",
            "engagement": {"upvotes": 500, "comments": 120},
            "top_comments": [],
            "score": 92,
        },
    ],
    "hackernews": [
        {
            "title": "Show HN: Open-source LLM router for cost optimization",
            "url": "https://news.ycombinator.com/item?id=99999",
            "author": "techfounder",
            "date": "2026-03-16",
            "score": 78,
        },
    ],
    "x": [],
    "web": [],
    "youtube": [],
}


# ---------------------------------------------------------------------------
# _normalize_item tests
# ---------------------------------------------------------------------------

class TestNormalizeItem:
    def test_reddit_item(self):
        raw = {
            "_platform": "reddit",
            "_topic": "AI agents",
            "title": "Built a multi-agent system",
            "url": "https://www.reddit.com/r/MachineLearning/comments/1abc123/built/",
            "subreddit": "MachineLearning",
            "date": "2026-03-15",
        }
        result = _normalize_item(raw)

        assert result["title"] == "Built a multi-agent system"
        assert result["url"] == "https://www.reddit.com/r/MachineLearning/comments/1abc123/built/"
        assert result["source_name"] == "Reddit MachineLearning"
        assert result["source_category"] == "AI agents"
        assert result["published_at"] == "2026-03-15"
        assert len(result["item_hash"]) == 16

    def test_hackernews_item(self):
        raw = {
            "_platform": "hackernews",
            "_topic": "LLM inference",
            "title": "Show HN: Fast inference engine",
            "url": "https://news.ycombinator.com/item?id=12345",
            "author": "techfounder",
            "date": "2026-03-16",
        }
        result = _normalize_item(raw)

        assert result["source_name"] == "Hackernews @techfounder"
        assert result["author"] == "techfounder"

    def test_x_post_title_truncated_to_first_line(self):
        raw = {
            "_platform": "x",
            "_topic": "AI news",
            "title": "First line of tweet\nSecond line\nThird line",
            "url": "https://x.com/user/status/123",
            "username": "karpathy",
        }
        result = _normalize_item(raw)

        assert result["title"] == "First line of tweet"
        assert result["source_name"] == "X @karpathy"

    def test_empty_title_produces_empty(self):
        raw = {"_platform": "web", "_topic": "test", "title": "", "url": "https://example.com"}
        result = _normalize_item(raw)
        assert result["title"] == ""

    def test_hash_deterministic(self):
        raw = {"_platform": "web", "title": "Hello", "url": "https://example.com"}
        r1 = _normalize_item(raw)
        r2 = _normalize_item(raw)
        assert r1["item_hash"] == r2["item_hash"]

        expected = hashlib.sha256("Hellohttps://example.com".encode()).hexdigest()[:16]
        assert r1["item_hash"] == expected

    def test_source_name_fallback_to_platform(self):
        raw = {"_platform": "web", "_topic": "test", "title": "Article", "url": "https://example.com"}
        result = _normalize_item(raw)
        assert result["source_name"] == "Web"

    def test_content_from_body_field(self):
        raw = {"_platform": "reddit", "title": "Title", "body": "Full body text", "url": ""}
        result = _normalize_item(raw)
        assert result["content"] == "Full body text"


# ---------------------------------------------------------------------------
# _research_topic tests (mocked subprocess)
# ---------------------------------------------------------------------------

class TestResearchTopic:
    def test_successful_research(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(SAMPLE_LAST30DAYS_OUTPUT)

        with patch("src.content.news_agent.subprocess.run", return_value=mock_result):
            items = _research_topic("AI agents", "/fake/script.py")

        # 2 reddit + 1 HN = 3 items (x, web, youtube are empty lists)
        assert len(items) == 3
        assert items[0]["_platform"] == "reddit"
        assert items[0]["_topic"] == "AI agents"
        assert items[2]["_platform"] == "hackernews"

    def test_failed_subprocess_returns_empty(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Error: something went wrong"

        with patch("src.content.news_agent.subprocess.run", return_value=mock_result):
            items = _research_topic("test", "/fake/script.py")

        assert items == []

    def test_timeout_returns_empty(self):
        import subprocess as sp

        with patch("src.content.news_agent.subprocess.run", side_effect=sp.TimeoutExpired("cmd", 5)):
            items = _research_topic("test", "/fake/script.py", timeout=5)

        assert items == []

    def test_invalid_json_returns_empty(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json{{"

        with patch("src.content.news_agent.subprocess.run", return_value=mock_result):
            items = _research_topic("test", "/fake/script.py")

        assert items == []

    def test_flag_like_topic_rejected(self):
        items = _research_topic("--malicious-flag", "/fake/script.py")
        assert items == []

    def test_long_topic_rejected(self):
        items = _research_topic("x" * 201, "/fake/script.py")
        assert items == []

    def test_sources_filter_applied(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"reddit": [], "hackernews": []})

        with patch("src.content.news_agent.subprocess.run", return_value=mock_result) as mock_run:
            _research_topic("test", "/fake/script.py", sources=["hn", "reddit"])
            cmd = mock_run.call_args[0][0]
            assert "--search" in cmd
            idx = cmd.index("--search")
            assert cmd[idx + 1] == "hn,reddit"

    def test_invalid_sources_filtered_out(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"reddit": []})

        with patch("src.content.news_agent.subprocess.run", return_value=mock_result) as mock_run:
            _research_topic("test", "/fake/script.py", sources=["hn", "--evil", "invalid"])
            cmd = mock_run.call_args[0][0]
            assert "--search" in cmd
            idx = cmd.index("--search")
            assert cmd[idx + 1] == "hn"  # only valid source kept


# ---------------------------------------------------------------------------
# extract_topics tests
# ---------------------------------------------------------------------------

class TestExtractTopics:
    def test_fallback_when_no_posts(self, tmp_db):
        config = _make_mock_config()
        topics = extract_topics(tmp_db, config, n=3)

        assert len(topics) == 3
        assert all(isinstance(t, str) for t in topics)

    def test_llm_topics_parsed(self, tmp_db):
        config = _make_mock_config()

        # Insert a published post
        with tmp_db.connect() as conn:
            conn.execute(
                "INSERT INTO posts (content, strategy, status, published_at) VALUES (?, ?, ?, datetime('now'))",
                ("AI inference optimization is the key trend", "thought_leadership", "published"),
            )

        @dataclass
        class FakeResult:
            content: str = '["LLM inference scaling", "NVIDIA AI chips", "on-device ML"]'

        mock_ai = MagicMock()
        mock_ai.generate.return_value = FakeResult()

        with patch("src.content.generator.create_ai_provider", return_value=mock_ai):
            topics = extract_topics(tmp_db, config, n=3)

        assert topics == ["LLM inference scaling", "NVIDIA AI chips", "on-device ML"]

    def test_llm_markdown_code_block_stripped(self, tmp_db):
        config = _make_mock_config()

        with tmp_db.connect() as conn:
            conn.execute(
                "INSERT INTO posts (content, strategy, status, published_at) VALUES (?, ?, ?, datetime('now'))",
                ("Some post content", "thought_leadership", "published"),
            )

        @dataclass
        class FakeResult:
            content: str = '```json\n["topic1", "topic2"]\n```'

        mock_ai = MagicMock()
        mock_ai.generate.return_value = FakeResult()

        with patch("src.content.generator.create_ai_provider", return_value=mock_ai):
            topics = extract_topics(tmp_db, config, n=5)

        assert topics == ["topic1", "topic2"]

    def test_llm_failure_falls_back(self, tmp_db):
        config = _make_mock_config()

        with tmp_db.connect() as conn:
            conn.execute(
                "INSERT INTO posts (content, strategy, status, published_at) VALUES (?, ?, ?, datetime('now'))",
                ("Some post", "thought_leadership", "published"),
            )

        mock_ai = MagicMock()
        mock_ai.generate.side_effect = RuntimeError("API down")

        with patch("src.content.generator.create_ai_provider", return_value=mock_ai):
            topics = extract_topics(tmp_db, config, n=3)

        # Should fall back to HIGH_PRIORITY_KEYWORDS
        assert len(topics) == 3

    def test_curly_braces_in_post_content(self, tmp_db):
        """Posts containing { or } should not crash topic extraction."""
        config = _make_mock_config()

        with tmp_db.connect() as conn:
            conn.execute(
                "INSERT INTO posts (content, strategy, status, published_at) VALUES (?, ?, ?, datetime('now'))",
                ('Code example: {"key": "value"} and f-string {var}', "thought_leadership", "published"),
            )

        @dataclass
        class FakeResult:
            content: str = '["AI trends"]'

        mock_ai = MagicMock()
        mock_ai.generate.return_value = FakeResult()

        with patch("src.content.generator.create_ai_provider", return_value=mock_ai):
            topics = extract_topics(tmp_db, config, n=3)

        assert topics == ["AI trends"]


# ---------------------------------------------------------------------------
# run_research tests (fully mocked)
# ---------------------------------------------------------------------------

class TestRunResearch:
    def test_deduplication(self, feed_crud, content_crud):
        config = _make_mock_config()

        # Two identical items from different topics
        duplicate_output = {
            "reddit": [{
                "title": "Same article",
                "url": "https://example.com/same",
                "subreddit": "MachineLearning",
                "date": "2026-03-15",
            }],
        }

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(duplicate_output)

        with patch("src.content.news_agent.subprocess.run", return_value=mock_result), \
             patch("src.content.news_agent._find_skill_root", return_value="/fake/script.py"):
            result = run_research(
                topics=["topic1", "topic2"],
                config=config,
                feed_crud=feed_crud,
                content_crud=content_crud,
            )

        # Both topics return the same item — should deduplicate to 1
        assert result["items_persisted"] == 1
        assert feed_crud.count() == 1

    def test_empty_results(self, feed_crud, content_crud):
        config = _make_mock_config()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"reddit": [], "hackernews": []})

        with patch("src.content.news_agent.subprocess.run", return_value=mock_result), \
             patch("src.content.news_agent._find_skill_root", return_value="/fake/script.py"):
            result = run_research(
                topics=["empty topic"],
                config=config,
                feed_crud=feed_crud,
                content_crud=content_crud,
            )

        assert result["items_persisted"] == 0
        assert result["items_found"] == 0

    def test_items_persisted_to_db(self, feed_crud, content_crud):
        config = _make_mock_config()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(SAMPLE_LAST30DAYS_OUTPUT)

        with patch("src.content.news_agent.subprocess.run", return_value=mock_result), \
             patch("src.content.news_agent._find_skill_root", return_value="/fake/script.py"):
            result = run_research(
                topics=["AI agents"],
                config=config,
                feed_crud=feed_crud,
                content_crud=content_crud,
            )

        assert result["items_persisted"] == 3
        assert feed_crud.count() == 3

        # Verify URLs are real
        items = feed_crud.get_top_scored(limit=10)
        for item in items:
            assert "1xxxxx" not in item["url"]

    def test_sources_passed_through(self, feed_crud, content_crud):
        config = _make_mock_config()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"hackernews": []})

        with patch("src.content.news_agent.subprocess.run", return_value=mock_result) as mock_run, \
             patch("src.content.news_agent._find_skill_root", return_value="/fake/script.py"):
            run_research(
                topics=["test"],
                config=config,
                feed_crud=feed_crud,
                content_crud=content_crud,
                sources=["hn"],
            )

        cmd = mock_run.call_args[0][0]
        assert "--search" in cmd
        assert "hn" in cmd[cmd.index("--search") + 1]

    def test_empty_titles_skipped(self, feed_crud, content_crud):
        config = _make_mock_config()

        output = {
            "reddit": [
                {"title": "", "url": "https://example.com/empty", "subreddit": "test"},
                {"title": "Real title", "url": "https://example.com/real", "subreddit": "test"},
            ],
        }

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(output)

        with patch("src.content.news_agent.subprocess.run", return_value=mock_result), \
             patch("src.content.news_agent._find_skill_root", return_value="/fake/script.py"):
            result = run_research(
                topics=["test"],
                config=config,
                feed_crud=feed_crud,
                content_crud=content_crud,
            )

        assert result["items_persisted"] == 1


# ---------------------------------------------------------------------------
# VALID_SOURCES allowlist
# ---------------------------------------------------------------------------

class TestValidSources:
    def test_known_sources_in_allowlist(self):
        for source in ["hn", "reddit", "web", "youtube", "x", "bluesky", "tiktok", "polymarket"]:
            assert source in VALID_SOURCES

    def test_malicious_values_not_in_allowlist(self):
        for bad in ["--emit=shell", "../etc/passwd", "'; DROP TABLE", ""]:
            assert bad not in VALID_SOURCES
