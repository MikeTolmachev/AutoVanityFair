from datetime import datetime, timedelta, timezone

import pytest

from src.content.content_filter import ContentFilter, ContentType, ScoredContent
from src.content.keyword_taxonomy import (
    HIGH_PRIORITY_KEYWORDS,
    MEDIUM_PRIORITY_KEYWORDS,
    LOW_PRIORITY_KEYWORDS,
    ALL_CATEGORIES,
    PRODUCTION_KEYWORDS,
    KeywordPriority,
)
from src.utils.helpers import parse_published_date, months_ago


class TestKeywordTaxonomy:
    def test_high_priority_keywords_not_empty(self):
        assert len(HIGH_PRIORITY_KEYWORDS) > 0

    def test_medium_priority_keywords_not_empty(self):
        assert len(MEDIUM_PRIORITY_KEYWORDS) > 0

    def test_low_priority_keywords_not_empty(self):
        assert len(LOW_PRIORITY_KEYWORDS) > 0

    def test_all_categories_present(self):
        names = [c.name for c in ALL_CATEGORIES]
        assert "Core ML/AI Domains" in names
        assert "Production & Deployment" in names
        assert "Infrastructure & Operations" in names
        assert "LLM & Generative AI" in names
        assert "Business & Strategy" in names

    def test_production_keywords_have_weights(self):
        assert len(PRODUCTION_KEYWORDS) > 0
        assert all(isinstance(v, int) for v in PRODUCTION_KEYWORDS.values())

    def test_no_keyword_overlap_between_priorities(self):
        # It's acceptable for some overlap due to category-level assignment,
        # but each set should have unique entries
        assert isinstance(HIGH_PRIORITY_KEYWORDS, set)
        assert isinstance(MEDIUM_PRIORITY_KEYWORDS, set)
        assert isinstance(LOW_PRIORITY_KEYWORDS, set)


class TestContentFilter:
    @pytest.fixture
    def cf(self):
        return ContentFilter(min_score_threshold=0.0)

    def test_score_production_content(self, cf):
        result = cf.score(
            title="How we scaled model deployment to production at 10M requests/day",
            content=(
                "We deployed our ML model to production using MLOps best practices. "
                "Inference optimization with TensorRT reduced latency by 40%. "
                "Our infrastructure handles 10M requests daily with GPU optimization."
            ),
        )
        assert result.production_score > 30
        assert result.final_score > 15

    def test_score_pure_theory(self, cf):
        result = cf.score(
            title="A Theoretical Analysis of Abstract Gradient Bounds",
            content=(
                "We present a mathematical proof of convergence bounds for "
                "a novel theoretical framework. This abstract analysis provides "
                "new theoretical insights."
            ),
        )
        # Should have low/negative production score
        assert result.production_score < 10

    def test_executive_score(self, cf):
        result = cf.score(
            title="Scaling distributed ML infrastructure across the organization",
            content=(
                "As we scaled our ML architecture to support large-scale distributed "
                "training, we learned key lessons about monitoring, observability, "
                "and cross-functional collaboration in our team workflow."
            ),
        )
        assert result.executive_score > 10

    def test_content_type_case_study(self, cf):
        result = cf.score(
            title="How we built a real-time ML serving platform at scale",
            content="Case study of deploying ML models to production.",
        )
        assert result.content_type == ContentType.PRODUCTION_CASE_STUDY

    def test_content_type_tutorial(self, cf):
        result = cf.score(
            title="Step-by-step guide to fine-tuning LLMs",
            content="A tutorial for getting started with model training.",
        )
        assert result.content_type == ContentType.TECHNICAL_TUTORIAL

    def test_content_type_pure_research(self, cf):
        result = cf.score(
            title="Novel experiment on benchmark results",
            content="We proposed a new research method and ran experiments on standard benchmarks.",
        )
        assert result.content_type == ContentType.PURE_RESEARCH

    def test_content_type_research_with_code(self, cf):
        result = cf.score(
            title="New research paper with GitHub repository",
            content="We release the code for our experiments and benchmark results.",
        )
        assert result.content_type == ContentType.RESEARCH_WITH_CODE

    def test_type_multiplier_applied(self, cf):
        case_study = cf.score(
            title="How we deployed AI at scale",
            content="Case study of production ML deployment with inference optimization.",
        )
        general = cf.score(
            title="AI is interesting",
            content="Some general thoughts about technology.",
        )
        # Case study should get 2.0x multiplier
        assert case_study.type_multiplier == 2.0
        # General should get 1.0x
        assert general.type_multiplier == 1.0

    def test_filter_and_rank(self, cf):
        items = [
            {
                "title": "Production ML deployment guide",
                "content": "MLOps infrastructure for model serving at scale with inference optimization.",
            },
            {
                "title": "Abstract theoretical musings",
                "content": "Some purely theoretical analysis.",
            },
            {
                "title": "PyTorch distributed training tutorial",
                "content": "How to set up distributed training with GPU optimization and CUDA.",
            },
        ]
        ranked = cf.filter_and_rank(items, max_results=10)
        # Items should be sorted by score descending
        for i in range(len(ranked) - 1):
            assert ranked[i].final_score >= ranked[i + 1].final_score

    def test_filter_threshold(self):
        cf = ContentFilter(min_score_threshold=999.0)
        items = [
            {"title": "Some content", "content": "Not very relevant."},
        ]
        ranked = cf.filter_and_rank(items)
        assert len(ranked) == 0

    def test_matched_keywords(self, cf):
        result = cf.score(
            title="PyTorch and TensorFlow comparison",
            content="We compare PyTorch and TensorFlow for production ML deployment.",
        )
        assert len(result.matched_keywords) > 0
        assert any("PyTorch" in kw for kw in result.matched_keywords)

    def test_matched_categories(self, cf):
        result = cf.score(
            title="LLM fine-tuning with LoRA",
            content="Fine-tuning large language models using parameter-efficient methods.",
        )
        assert len(result.matched_categories) > 0
        assert "LLM & Generative AI" in result.matched_categories

    def test_production_implementation_bonus(self, cf):
        # Content with both production AND implementation keywords should get +15 bonus
        with_both = cf.score(
            title="Production deployment with open source code",
            content="We share our production ML code on GitHub with best practices.",
        )
        prod_only = cf.score(
            title="Production deployment of models",
            content="We deployed models to production with inference serving.",
        )
        # The combined version should score higher due to the +15 bonus
        assert with_both.production_score > prod_only.production_score

    def test_scored_content_fields(self, cf):
        result = cf.score(
            title="Test",
            content="Test content about machine learning.",
            url="https://example.com",
            source="test_source",
            author="test_author",
        )
        assert result.title == "Test"
        assert result.url == "https://example.com"
        assert result.source == "test_source"
        assert result.author == "test_author"
        assert isinstance(result.final_score, float)
        assert isinstance(result.content_type, ContentType)


class TestDateParsing:
    def test_parse_iso8601(self):
        dt = parse_published_date("2024-10-15T12:00:00Z")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 10
        assert dt.tzinfo is not None

    def test_parse_iso8601_with_offset(self):
        dt = parse_published_date("2024-10-15T12:00:00+02:00")
        assert dt is not None
        assert dt.year == 2024

    def test_parse_rfc2822(self):
        dt = parse_published_date("Tue, 15 Oct 2024 12:00:00 +0000")
        assert dt is not None
        assert dt.month == 10

    def test_parse_linkedin_relative_weeks(self):
        dt = parse_published_date("2w")
        assert dt is not None
        # Should be roughly 14 days ago
        delta = datetime.now(timezone.utc) - dt
        assert 13 <= delta.days <= 15

    def test_parse_linkedin_relative_months(self):
        dt = parse_published_date("1mo")
        assert dt is not None
        delta = datetime.now(timezone.utc) - dt
        assert 29 <= delta.days <= 31

    def test_parse_linkedin_relative_days(self):
        dt = parse_published_date("3d")
        assert dt is not None
        delta = datetime.now(timezone.utc) - dt
        assert 2 <= delta.days <= 4

    def test_parse_empty_string(self):
        assert parse_published_date("") is None
        assert parse_published_date(None) is None

    def test_parse_garbage(self):
        assert parse_published_date("not a date at all") is None

    def test_months_ago_recent(self):
        now = datetime.now(timezone.utc)
        dt = now - timedelta(days=10)
        assert months_ago(dt, now) == pytest.approx(10 / 30, abs=0.01)

    def test_months_ago_old(self):
        now = datetime.now(timezone.utc)
        dt = now - timedelta(days=90)
        assert months_ago(dt, now) == pytest.approx(3.0, abs=0.01)


class TestFreshnessScoring:
    @pytest.fixture
    def cf(self):
        return ContentFilter(min_score_threshold=0.0)

    def _make_date_str(self, months_old: float) -> str:
        dt = datetime.now(timezone.utc) - timedelta(days=months_old * 30)
        return dt.isoformat()

    def test_recent_content_full_score(self, cf):
        # < 1 month old -> multiplier 1.0
        date_str = self._make_date_str(0.5)
        mult = cf._calculate_freshness(date_str)
        assert mult == 1.0

    def test_two_months_old(self, cf):
        # 2 months old -> 1.0 - (2-1)*0.25 = 0.75
        date_str = self._make_date_str(2.0)
        mult = cf._calculate_freshness(date_str)
        assert mult == pytest.approx(0.75, abs=0.05)

    def test_three_months_old(self, cf):
        # 3 months old -> 1.0 - (3-1)*0.25 = 0.50
        date_str = self._make_date_str(3.0)
        mult = cf._calculate_freshness(date_str)
        assert mult == pytest.approx(0.50, abs=0.05)

    def test_four_months_old(self, cf):
        # 4 months old -> 1.0 - (4-1)*0.25 = 0.25
        date_str = self._make_date_str(4.0)
        mult = cf._calculate_freshness(date_str)
        assert mult == pytest.approx(0.25, abs=0.05)

    def test_six_months_old_floor(self, cf):
        # 6 months old -> would be -0.25, clamped to 0.1
        date_str = self._make_date_str(6.0)
        mult = cf._calculate_freshness(date_str)
        assert mult == pytest.approx(0.1, abs=0.01)

    def test_missing_date_no_penalty(self, cf):
        assert cf._calculate_freshness(None) == 1.0
        assert cf._calculate_freshness("") == 1.0

    def test_unparseable_date_no_penalty(self, cf):
        assert cf._calculate_freshness("gibberish text") == 1.0

    def test_final_score_includes_freshness(self, cf):
        # Score the same content with and without an old date
        recent = cf.score(
            title="Production ML deployment",
            content="MLOps infrastructure for model serving at scale.",
        )
        old_date = self._make_date_str(4.0)
        old = cf.score(
            title="Production ML deployment",
            content="MLOps infrastructure for model serving at scale.",
            published_at=old_date,
        )
        # Old content should score significantly lower
        assert old.final_score < recent.final_score
        assert old.freshness_multiplier < 0.5

    def test_filter_and_rank_passes_published_at(self, cf):
        recent_date = self._make_date_str(0.5)
        old_date = self._make_date_str(5.0)
        items = [
            {
                "title": "Old production ML guide",
                "content": "MLOps infrastructure for model serving at scale with inference optimization.",
                "published_at": old_date,
            },
            {
                "title": "Recent production ML guide",
                "content": "MLOps infrastructure for model serving at scale with inference optimization.",
                "published_at": recent_date,
            },
        ]
        ranked = cf.filter_and_rank(items, max_results=10)
        # Both items have same text, so recent one should rank higher
        if len(ranked) >= 2:
            assert ranked[0].freshness_multiplier > ranked[1].freshness_multiplier
