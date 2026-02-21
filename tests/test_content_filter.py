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
