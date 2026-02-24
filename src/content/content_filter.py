"""
Multi-stage content filtering with production-relevance scoring,
executive positioning filter, and content type prioritization.
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.content.keyword_taxonomy import (
    PRODUCTION_KEYWORDS,
    RESEARCH_KEYWORDS,
    BUSINESS_KEYWORDS,
    IMPLEMENTATION_KEYWORDS,
    FRAMEWORK_WEIGHTS,
    EXECUTIVE_SCALE_INDICATORS,
    EXECUTIVE_LEADERSHIP_SIGNALS,
    EXECUTIVE_OPERATIONAL_EXCELLENCE,
    EXECUTIVE_TEAM_ORG,
    EXECUTIVE_BUSINESS_OUTCOMES,
    THEORY_ONLY_INDICATORS,
    HIGH_PRIORITY_KEYWORDS,
    MEDIUM_PRIORITY_KEYWORDS,
    LOW_PRIORITY_KEYWORDS,
    ALL_CATEGORIES,
    KeywordPriority,
)

logger = logging.getLogger("openlinkedin.content_filter")


class ContentType(Enum):
    """Content types ranked by value for executive positioning."""
    PRODUCTION_CASE_STUDY = "production_case_study"
    INFRA_DEEP_DIVE = "infrastructure_deep_dive"
    FRAMEWORK_COMPARISON = "framework_comparison"
    BENCHMARK_REAL_WORKLOAD = "benchmark_real_workload"
    RESEARCH_WITH_CODE = "research_with_code"
    TECHNICAL_TUTORIAL = "technical_tutorial"
    PURE_RESEARCH = "pure_research"
    GENERAL = "general"


# Content type score multipliers
CONTENT_TYPE_MULTIPLIERS: dict[ContentType, float] = {
    ContentType.PRODUCTION_CASE_STUDY: 2.0,
    ContentType.INFRA_DEEP_DIVE: 2.0,
    ContentType.FRAMEWORK_COMPARISON: 1.5,
    ContentType.BENCHMARK_REAL_WORKLOAD: 1.5,
    ContentType.RESEARCH_WITH_CODE: 1.2,
    ContentType.TECHNICAL_TUTORIAL: 1.2,
    ContentType.PURE_RESEARCH: 0.8,
    ContentType.GENERAL: 1.0,
}


@dataclass
class ScoredContent:
    """A piece of content with multi-stage relevance scoring."""
    title: str
    content: str
    url: str = ""
    source: str = ""
    author: str = ""

    published_at: Optional[str] = None

    # Scoring results
    production_score: float = 0.0
    executive_score: float = 0.0
    keyword_score: float = 0.0
    content_type: ContentType = ContentType.GENERAL
    type_multiplier: float = 1.0
    freshness_multiplier: float = 1.0
    final_score: float = 0.0

    matched_keywords: list[str] = field(default_factory=list)
    matched_categories: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.matched_keywords = list(self.matched_keywords)
        self.matched_categories = list(self.matched_categories)


class ContentFilter:
    """
    Multi-stage content filter for production-focused AI executive positioning.

    Stage 1: Production-Relevance Scoring
    Stage 2: Executive Positioning Filter
    Stage 3: Content Type Prioritization
    """

    def __init__(
        self,
        min_score_threshold: float = 10.0,
        enable_executive_filter: bool = True,
        max_age_months: int = 3,
    ):
        self.min_score_threshold = min_score_threshold
        self.enable_executive_filter = enable_executive_filter
        self.max_age_months = max_age_months

    def score(
        self,
        title: str,
        content: str,
        url: str = "",
        source: str = "",
        author: str = "",
        published_at: Optional[str] = None,
    ) -> ScoredContent:
        """Run all scoring stages and return a ScoredContent object."""
        combined_text = f"{title} {content}"

        scored = ScoredContent(
            title=title,
            content=content,
            url=url,
            source=source,
            author=author,
            published_at=published_at,
        )

        # Stage 1: Production relevance
        scored.production_score = self._calculate_production_relevance(combined_text)

        # Stage 2: Executive positioning
        scored.executive_score = self._calculate_executive_score(combined_text)

        # Stage 3: Content type classification and multiplier
        scored.content_type = self._classify_content_type(combined_text, url)
        scored.type_multiplier = CONTENT_TYPE_MULTIPLIERS.get(
            scored.content_type, 1.0
        )

        # Keyword matching
        scored.keyword_score = self._calculate_keyword_score(combined_text)
        scored.matched_keywords = self._find_matched_keywords(combined_text)
        scored.matched_categories = self._find_matched_categories(combined_text)

        # Freshness
        scored.freshness_multiplier = self._calculate_freshness(published_at)

        # Final composite score (business-applied weighting)
        base_score = (
            scored.production_score * 0.30
            + scored.executive_score * 0.35
            + scored.keyword_score * 0.35
        )
        scored.final_score = round(
            base_score * scored.type_multiplier * scored.freshness_multiplier, 2
        )

        return scored

    def filter_and_rank(
        self,
        items: list[dict],
        max_results: int = 20,
    ) -> list[ScoredContent]:
        """Score, filter, and rank a list of content items.

        Each item dict should have at least 'title' and 'content' keys.
        Optional: 'url', 'source', 'author'.
        """
        scored_items = []
        for item in items:
            scored = self.score(
                title=item.get("title", ""),
                content=item.get("content", ""),
                url=item.get("url", ""),
                source=item.get("source", ""),
                author=item.get("author", ""),
                published_at=item.get("published_at"),
            )
            if scored.final_score >= self.min_score_threshold:
                scored_items.append(scored)

        scored_items.sort(key=lambda x: x.final_score, reverse=True)
        return scored_items[:max_results]

    # ------------------------------------------------------------------
    # Freshness penalty
    # ------------------------------------------------------------------
    def _calculate_freshness(self, published_at: Optional[str]) -> float:
        """Return a freshness multiplier in [0.1, 1.0].

        Penalises 25% per month after the first month.
        Missing or unparseable dates default to 1.0 (no penalty).
        """
        if not published_at:
            return 1.0

        from src.utils.helpers import parse_published_date, months_ago

        dt = parse_published_date(published_at)
        if dt is None:
            return 1.0

        age = months_ago(dt)
        return round(min(1.0, max(0.1, 1.0 - (age - 1) * 0.25)), 4)

    # ------------------------------------------------------------------
    # Stage 1: Production-Relevance Scoring
    # ------------------------------------------------------------------
    def _calculate_production_relevance(self, text: str) -> float:
        text_lower = text.lower()
        score = 0.0

        # Production keywords (high weight)
        for keyword, weight in PRODUCTION_KEYWORDS.items():
            if keyword.lower() in text_lower:
                score += weight

        # Research keywords (lower weight)
        for keyword, weight in RESEARCH_KEYWORDS.items():
            if keyword.lower() in text_lower:
                score += weight

        # Business impact keywords (boosted weight)
        for keyword, weight in BUSINESS_KEYWORDS.items():
            if keyword.lower() in text_lower:
                score += weight

        # Implementation indicators
        for keyword, weight in IMPLEMENTATION_KEYWORDS.items():
            if keyword.lower() in text_lower:
                score += weight

        # Framework-specific weights (PyTorch >> TensorFlow)
        for framework, weight in FRAMEWORK_WEIGHTS.items():
            if framework.lower() in text_lower:
                score += weight

        # Bonus: production + implementation combination
        has_production = any(
            k.lower() in text_lower for k in PRODUCTION_KEYWORDS
        )
        has_implementation = any(
            k.lower() in text_lower for k in IMPLEMENTATION_KEYWORDS
        )
        if has_production and has_implementation:
            score += 15

        # Bonus: business + production combination
        has_business = any(
            k.lower() in text_lower for k in BUSINESS_KEYWORDS
        )
        if has_business and has_production:
            score += 12

        # Penalty: pure theory without application
        has_theory = any(t.lower() in text_lower for t in THEORY_ONLY_INDICATORS)
        if has_theory and not has_production:
            score -= 10

        return max(0.0, score)

    # ------------------------------------------------------------------
    # Stage 2: Executive / Business Positioning Filter
    # ------------------------------------------------------------------
    def _calculate_executive_score(self, text: str) -> float:
        if not self.enable_executive_filter:
            return 0.0

        text_lower = text.lower()
        score = 0.0

        # Business outcomes (highest weight -- applied AI focus)
        for indicator in EXECUTIVE_BUSINESS_OUTCOMES:
            if indicator.lower() in text_lower:
                score += 6

        # Scale indicators
        for indicator in EXECUTIVE_SCALE_INDICATORS:
            if indicator.lower() in text_lower:
                score += 5

        # Leadership signals
        for signal in EXECUTIVE_LEADERSHIP_SIGNALS:
            if signal.lower() in text_lower:
                score += 4

        # Operational excellence
        for indicator in EXECUTIVE_OPERATIONAL_EXCELLENCE:
            if indicator.lower() in text_lower:
                score += 3

        # Team/organizational
        for indicator in EXECUTIVE_TEAM_ORG:
            if indicator.lower() in text_lower:
                score += 3

        return score

    # ------------------------------------------------------------------
    # Stage 3: Content Type Classification
    # ------------------------------------------------------------------
    def _classify_content_type(self, text: str, url: str = "") -> ContentType:
        text_lower = text.lower()

        # Production case study indicators
        case_study_patterns = [
            r"how we (?:built|scaled|deployed|migrated)",
            r"case study",
            r"lessons learned",
            r"in production at",
            r"our (?:journey|experience) with",
            r"post-?mortem",
            r"scaling .+ to .+ (?:users|requests|queries)",
        ]
        if any(re.search(p, text_lower) for p in case_study_patterns):
            return ContentType.PRODUCTION_CASE_STUDY

        # Infrastructure deep-dive
        infra_patterns = [
            r"architecture (?:of|for|behind)",
            r"deep dive",
            r"infrastructure",
            r"system design",
            r"technical design",
        ]
        infra_count = sum(1 for p in infra_patterns if re.search(p, text_lower))
        if infra_count >= 2:
            return ContentType.INFRA_DEEP_DIVE

        # Framework comparison
        comparison_patterns = [
            r"(?:vs\.?|versus|compared to|comparison)",
            r"which (?:one|framework|tool)",
            r"(?:pros|cons) of",
            r"benchmark(?:ing|s)?",
        ]
        if any(re.search(p, text_lower) for p in comparison_patterns):
            has_framework = any(
                kw.lower() in text_lower for kw in
                ("PyTorch", "TensorFlow", "JAX", "ONNX", "TensorRT",
                 "Ray", "vLLM", "LangChain", "LlamaIndex")
            )
            if has_framework:
                return ContentType.FRAMEWORK_COMPARISON

        # Research with code
        if ("github" in text_lower or "code" in text_lower or "repository" in text_lower):
            has_research = any(
                kw.lower() in text_lower for kw in RESEARCH_KEYWORDS
            )
            if has_research:
                return ContentType.RESEARCH_WITH_CODE

        # Technical tutorial
        tutorial_patterns = [
            r"tutorial", r"step[- ]by[- ]step", r"how to",
            r"getting started", r"guide", r"walkthrough",
        ]
        if any(re.search(p, text_lower) for p in tutorial_patterns):
            return ContentType.TECHNICAL_TUTORIAL

        # Pure research (no production indicators)
        has_research = any(kw.lower() in text_lower for kw in RESEARCH_KEYWORDS)
        has_production = any(kw.lower() in text_lower for kw in PRODUCTION_KEYWORDS)
        if has_research and not has_production:
            return ContentType.PURE_RESEARCH

        return ContentType.GENERAL

    # ------------------------------------------------------------------
    # Keyword scoring
    # ------------------------------------------------------------------
    def _calculate_keyword_score(self, text: str) -> float:
        text_lower = text.lower()
        score = 0.0

        for kw in HIGH_PRIORITY_KEYWORDS:
            if kw.lower() in text_lower:
                score += 5

        for kw in MEDIUM_PRIORITY_KEYWORDS:
            if kw.lower() in text_lower:
                score += 3

        for kw in LOW_PRIORITY_KEYWORDS:
            if kw.lower() in text_lower:
                score += 1

        return score

    def _find_matched_keywords(self, text: str, max_keywords: int = 15) -> list[str]:
        text_lower = text.lower()
        matched = []
        for kw in HIGH_PRIORITY_KEYWORDS | MEDIUM_PRIORITY_KEYWORDS | LOW_PRIORITY_KEYWORDS:
            if kw.lower() in text_lower:
                matched.append(kw)
                if len(matched) >= max_keywords:
                    break
        return matched

    def _find_matched_categories(self, text: str) -> list[str]:
        text_lower = text.lower()
        matched = []
        for cat in ALL_CATEGORIES:
            if any(kw.lower() in text_lower for kw in cat.keywords):
                matched.append(cat.name)
        return matched
