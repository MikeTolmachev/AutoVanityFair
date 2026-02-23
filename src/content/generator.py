import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from src.core.config_manager import AIConfig

logger = logging.getLogger("openlinkedin.generator")


def _is_retryable(exc: BaseException) -> bool:
    """Only retry on transient errors (rate limits, server errors), not 400/404."""
    # OpenAI errors
    try:
        from openai import RateLimitError, APIConnectionError, InternalServerError
        if isinstance(exc, (RateLimitError, APIConnectionError, InternalServerError)):
            return True
    except ImportError:
        pass
    # Anthropic errors
    try:
        from anthropic import RateLimitError as AnthropicRateLimit
        from anthropic import APIConnectionError as AnthropicConnError
        from anthropic import InternalServerError as AnthropicServerErr
        if isinstance(exc, (AnthropicRateLimit, AnthropicConnError, AnthropicServerErr)):
            return True
    except ImportError:
        pass
    return False


_retry_policy = retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=2, max=30),
    reraise=True,
)


@dataclass
class GenerationResult:
    content: str
    model: str
    provider: str
    tokens_used: int = 0
    confidence: Optional[float] = None


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> GenerationResult:
        ...

    @abstractmethod
    def generate_with_confidence(
        self, system_prompt: str, user_prompt: str
    ) -> GenerationResult:
        """Generate content and return with a confidence score (0-1)."""
        ...

    def generate_fast(self, system_prompt: str, user_prompt: str) -> GenerationResult:
        """Generate using a cheap/fast model. Falls back to main model."""
        return self.generate(system_prompt, user_prompt)


class OpenAIProvider(AIProvider):
    def __init__(self, config: AIConfig):
        from openai import OpenAI

        self.client = OpenAI(api_key=config.openai.api_key)
        self.model = config.openai.model
        self.fast_model = config.openai.fast_model
        self.max_tokens = config.openai.max_tokens
        self.temperature = config.openai.temperature

    @_retry_policy
    def generate(self, system_prompt: str, user_prompt: str) -> GenerationResult:
        try:
            return self._generate_chat(system_prompt, user_prompt)
        except Exception as e:
            # If chat endpoint fails with a model-not-supported error, try responses API
            err_str = str(e).lower()
            if "not a chat model" in err_str or "not supported" in err_str:
                logger.info("Model %s not supported on chat endpoint, trying responses API", self.model)
                return self._generate_responses(system_prompt, user_prompt)
            raise

    def _generate_chat(self, system_prompt: str, user_prompt: str) -> GenerationResult:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        return GenerationResult(
            content=response.choices[0].message.content.strip(),
            model=self.model,
            provider="openai",
            tokens_used=response.usage.total_tokens if response.usage else 0,
        )

    def _generate_responses(self, system_prompt: str, user_prompt: str) -> GenerationResult:
        """Use the OpenAI Responses API for models that don't support chat completions."""
        response = self.client.responses.create(
            model=self.model,
            instructions=system_prompt,
            input=user_prompt,
        )
        return GenerationResult(
            content=response.output_text.strip(),
            model=self.model,
            provider="openai",
            tokens_used=(
                response.usage.total_tokens if response.usage else 0
            ),
        )

    @_retry_policy
    def generate_with_confidence(
        self, system_prompt: str, user_prompt: str
    ) -> GenerationResult:
        confidence_prompt = (
            user_prompt
            + "\n\nAfter your response, on a new line write CONFIDENCE: followed by "
            "a number between 0.0 and 1.0 indicating how confident you are in the "
            "quality and relevance of your response."
        )
        try:
            result = self._generate_chat(system_prompt, confidence_prompt)
        except Exception as e:
            err_str = str(e).lower()
            if "not a chat model" in err_str or "not supported" in err_str:
                result = self._generate_responses(system_prompt, confidence_prompt)
            else:
                raise
        content, confidence = _parse_confidence(result.content)
        return GenerationResult(
            content=content,
            model=self.model,
            provider="openai",
            tokens_used=result.tokens_used,
            confidence=confidence,
        )

    @_retry_policy
    def generate_fast(self, system_prompt: str, user_prompt: str) -> GenerationResult:
        """Use the fast/cheap model (e.g. nano) for simple extraction tasks."""
        model = self.fast_model or self.model
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=512,
                temperature=0.3,
            )
            return GenerationResult(
                content=response.choices[0].message.content.strip(),
                model=model,
                provider="openai",
                tokens_used=response.usage.total_tokens if response.usage else 0,
            )
        except Exception as e:
            err_str = str(e).lower()
            if "not a chat model" in err_str or "not supported" in err_str:
                response = self.client.responses.create(
                    model=model,
                    instructions=system_prompt,
                    input=user_prompt,
                )
                return GenerationResult(
                    content=response.output_text.strip(),
                    model=model,
                    provider="openai",
                    tokens_used=response.usage.total_tokens if response.usage else 0,
                )
            raise


class AnthropicProvider(AIProvider):
    def __init__(self, config: AIConfig):
        from anthropic import Anthropic

        self.client = Anthropic(api_key=config.anthropic.api_key)
        self.model = config.anthropic.model
        self.max_tokens = config.anthropic.max_tokens
        self.temperature = config.anthropic.temperature

    @_retry_policy
    def generate(self, system_prompt: str, user_prompt: str) -> GenerationResult:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return GenerationResult(
            content=response.content[0].text.strip(),
            model=self.model,
            provider="anthropic",
            tokens_used=response.usage.input_tokens + response.usage.output_tokens,
        )

    @_retry_policy
    def generate_with_confidence(
        self, system_prompt: str, user_prompt: str
    ) -> GenerationResult:
        confidence_prompt = (
            user_prompt
            + "\n\nAfter your response, on a new line write CONFIDENCE: followed by "
            "a number between 0.0 and 1.0 indicating how confident you are in the "
            "quality and relevance of your response."
        )
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": confidence_prompt}],
        )
        raw = response.content[0].text.strip()
        content, confidence = _parse_confidence(raw)
        return GenerationResult(
            content=content,
            model=self.model,
            provider="anthropic",
            tokens_used=response.usage.input_tokens + response.usage.output_tokens,
            confidence=confidence,
        )


def _parse_confidence(text: str) -> tuple[str, float]:
    """Extract confidence score from generated text."""
    lines = text.strip().split("\n")
    confidence = 0.5
    content_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("CONFIDENCE:"):
            try:
                confidence = float(stripped.split(":", 1)[1].strip())
                confidence = max(0.0, min(1.0, confidence))
            except (ValueError, IndexError):
                pass
        else:
            content_lines.append(line)
    return "\n".join(content_lines).strip(), confidence


def create_ai_provider(config: AIConfig) -> AIProvider:
    """Factory function to create the configured AI provider."""
    if config.provider == "anthropic":
        logger.info("Using Anthropic provider (model: %s)", config.anthropic.model)
        return AnthropicProvider(config)
    else:
        logger.info("Using OpenAI provider (model: %s)", config.openai.model)
        return OpenAIProvider(config)
