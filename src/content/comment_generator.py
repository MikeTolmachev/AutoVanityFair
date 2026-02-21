import logging
from typing import Optional

from src.content.generator import AIProvider
from src.content.prompts import COMMENT_SYSTEM_PROMPT, COMMENT_TEMPLATES
from src.content.rag_engine import RAGEngine
from src.content.validators import ContentValidator

logger = logging.getLogger("openlinkedin.comment_generator")

MAX_RETRIES = 2


class CommentGenerator:
    """Orchestrates RAG + AI + confidence scoring for comments."""

    def __init__(
        self,
        ai_provider: AIProvider,
        rag_engine: Optional[RAGEngine] = None,
        validator: Optional[ContentValidator] = None,
    ):
        self.ai = ai_provider
        self.rag = rag_engine
        self.validator = validator or ContentValidator()

    def generate(
        self,
        post_content: str,
        post_author: str = "Unknown",
        post_url: str = "",
    ) -> dict:
        """Generate a comment with strategy selection and confidence scoring.

        Returns dict with keys: content, strategy, confidence, rag_sources, validation
        """
        strategy = "generic"
        rag_context = ""
        rag_sources: list[str] = []

        if self.rag:
            context, sources = self.rag.get_context_with_sources(post_content)
            if context:
                strategy = "grounded"
                rag_context = context
                rag_sources = sources

        template = COMMENT_TEMPLATES[strategy]
        user_prompt = template.format(
            author=post_author,
            post_content=post_content,
            rag_context=rag_context,
        )

        result = None
        validation = None

        for attempt in range(MAX_RETRIES + 1):
            result = self.ai.generate_with_confidence(
                COMMENT_SYSTEM_PROMPT, user_prompt
            )
            validation = self.validator.validate_comment(result.content)

            if validation.valid:
                break

            logger.warning(
                "Comment validation failed (attempt %d/%d): %s",
                attempt + 1,
                MAX_RETRIES + 1,
                validation.errors,
            )
            user_prompt += (
                "\n\nPrevious attempt had issues: "
                + "; ".join(validation.errors)
                + ". Please fix these issues."
            )

        return {
            "content": result.content,
            "strategy": strategy,
            "confidence": result.confidence or 0.5,
            "rag_sources": rag_sources,
            "validation": validation,
            "generation_result": result,
        }
