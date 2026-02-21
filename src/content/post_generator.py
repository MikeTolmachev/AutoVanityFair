import logging
from typing import Optional

from src.content.generator import AIProvider, GenerationResult
from src.content.prompts import POST_SYSTEM_PROMPT, POST_TEMPLATES
from src.content.rag_engine import RAGEngine
from src.content.validators import ContentValidator, ValidationResult

logger = logging.getLogger("openlinkedin.post_generator")

MAX_RETRIES = 2


class PostGenerator:
    """Orchestrates RAG context + AI generation + validation for posts."""

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
        topic: str,
        strategy: str = "thought_leadership",
    ) -> dict:
        """Generate a post with RAG grounding and validation.

        Returns dict with keys: content, strategy, rag_sources, validation, generation_result
        """
        template = POST_TEMPLATES.get(strategy, POST_TEMPLATES["thought_leadership"])

        rag_context = ""
        rag_sources: list[str] = []
        if self.rag:
            context, sources = self.rag.get_context_with_sources(topic)
            if context:
                rag_context = f"Relevant context from knowledge base:\n{context}"
                rag_sources = sources

        user_prompt = template.format(topic=topic, rag_context=rag_context)

        result: Optional[GenerationResult] = None
        validation: Optional[ValidationResult] = None

        for attempt in range(MAX_RETRIES + 1):
            result = self.ai.generate(POST_SYSTEM_PROMPT, user_prompt)
            validation = self.validator.validate_post(result.content)

            if validation.valid:
                break

            logger.warning(
                "Post validation failed (attempt %d/%d): %s",
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
            "rag_sources": rag_sources,
            "validation": validation,
            "generation_result": result,
        }
