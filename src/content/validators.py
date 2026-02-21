import logging
import re
from dataclasses import dataclass

logger = logging.getLogger("openlinkedin.validators")

PLACEHOLDER_PATTERNS = [
    r"\[your\s+\w+\]",
    r"\[company\]",
    r"\[name\]",
    r"\[insert\s+\w+\]",
    r"\[fill\s+in\]",
    r"<your\s+\w+>",
    r"\[TODO\]",
    r"\[PLACEHOLDER\]",
]


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]


class ContentValidator:
    """Validates generated content for quality and safety."""

    def __init__(
        self,
        min_post_length: int = 100,
        max_post_length: int = 3000,
        min_comment_length: int = 20,
        max_comment_length: int = 500,
    ):
        self.min_post_length = min_post_length
        self.max_post_length = max_post_length
        self.min_comment_length = min_comment_length
        self.max_comment_length = max_comment_length

    def validate_post(self, content: str) -> ValidationResult:
        errors = []
        if len(content) < self.min_post_length:
            errors.append(f"Post too short ({len(content)} < {self.min_post_length} chars)")
        if len(content) > self.max_post_length:
            errors.append(f"Post too long ({len(content)} > {self.max_post_length} chars)")
        errors.extend(self._check_placeholders(content))
        errors.extend(self._check_duplicates(content))
        return ValidationResult(valid=len(errors) == 0, errors=errors)

    def validate_comment(self, content: str) -> ValidationResult:
        errors = []
        if len(content) < self.min_comment_length:
            errors.append(f"Comment too short ({len(content)} < {self.min_comment_length} chars)")
        if len(content) > self.max_comment_length:
            errors.append(f"Comment too long ({len(content)} > {self.max_comment_length} chars)")
        errors.extend(self._check_placeholders(content))
        return ValidationResult(valid=len(errors) == 0, errors=errors)

    def _check_placeholders(self, content: str) -> list[str]:
        errors = []
        for pattern in PLACEHOLDER_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                errors.append(f"Contains placeholder text matching: {pattern}")
        return errors

    def _check_duplicates(self, content: str) -> list[str]:
        """Check for repeated paragraphs within the same content."""
        errors = []
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        seen = set()
        for p in paragraphs:
            if p in seen:
                errors.append("Contains duplicate paragraph")
                break
            seen.add(p)
        return errors
