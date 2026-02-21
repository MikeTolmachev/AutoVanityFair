import pytest

from tests.conftest import MockAIProvider
from src.content.post_generator import PostGenerator
from src.content.comment_generator import CommentGenerator
from src.content.validators import ContentValidator, ValidationResult
from src.content.generator import _parse_confidence


class TestParseConfidence:
    def test_extracts_confidence(self):
        text = "Here is my response.\nCONFIDENCE: 0.85"
        content, conf = _parse_confidence(text)
        assert content == "Here is my response."
        assert conf == 0.85

    def test_no_confidence_line(self):
        text = "Just a response with no confidence."
        content, conf = _parse_confidence(text)
        assert content == "Just a response with no confidence."
        assert conf == 0.5  # default

    def test_clamps_confidence(self):
        text = "Response\nCONFIDENCE: 1.5"
        _, conf = _parse_confidence(text)
        assert conf == 1.0

        text2 = "Response\nCONFIDENCE: -0.5"
        _, conf2 = _parse_confidence(text2)
        assert conf2 == 0.0


class TestContentValidator:
    def test_valid_post(self):
        v = ContentValidator(min_post_length=10, max_post_length=500)
        result = v.validate_post("This is a valid post content that is long enough.")
        assert result.valid
        assert result.errors == []

    def test_post_too_short(self):
        v = ContentValidator(min_post_length=100)
        result = v.validate_post("Short")
        assert not result.valid
        assert any("too short" in e for e in result.errors)

    def test_post_too_long(self):
        v = ContentValidator(max_post_length=10)
        result = v.validate_post("This is way too long for the limit.")
        assert not result.valid
        assert any("too long" in e for e in result.errors)

    def test_placeholder_detection(self):
        v = ContentValidator(min_post_length=5)
        result = v.validate_post("Hello [Your Name], welcome to [Company]!")
        assert not result.valid
        assert any("placeholder" in e.lower() for e in result.errors)

    def test_valid_comment(self):
        v = ContentValidator(min_comment_length=10, max_comment_length=300)
        result = v.validate_comment("Great point about the new architecture!")
        assert result.valid

    def test_comment_too_short(self):
        v = ContentValidator(min_comment_length=50)
        result = v.validate_comment("Nice!")
        assert not result.valid


class TestPostGenerator:
    def test_generates_post(self, mock_ai_long):
        gen = PostGenerator(ai_provider=mock_ai_long)
        result = gen.generate(topic="AI trends", strategy="thought_leadership")

        assert "content" in result
        assert result["strategy"] == "thought_leadership"
        assert result["rag_sources"] == []
        assert result["validation"] is not None

    def test_generate_with_different_strategies(self, mock_ai_long):
        gen = PostGenerator(ai_provider=mock_ai_long)

        for strategy in ["thought_leadership", "model_review", "pov"]:
            result = gen.generate(topic="test", strategy=strategy)
            assert result["strategy"] == strategy


class TestCommentGenerator:
    def test_generates_comment(self):
        mock = MockAIProvider(
            response="This is a thoughtful comment about the topic.",
            confidence=0.9,
        )
        gen = CommentGenerator(ai_provider=mock)
        result = gen.generate(
            post_content="AI is transforming industries.",
            post_author="Jane",
        )

        assert "content" in result
        assert result["strategy"] == "generic"
        assert result["confidence"] == 0.9

    def test_comment_strategy_without_rag(self):
        mock = MockAIProvider(response="A valid comment that is long enough to pass.")
        gen = CommentGenerator(ai_provider=mock, rag_engine=None)
        result = gen.generate(
            post_content="Some post",
            post_author="Author",
        )
        assert result["strategy"] == "generic"
