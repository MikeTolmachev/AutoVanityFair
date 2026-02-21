import re
from datetime import datetime, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def cet_now() -> datetime:
    """Return current CET/CEST datetime."""
    return datetime.now(ZoneInfo("Europe/Berlin"))


def iso_timestamp() -> str:
    """Return current UTC time as ISO 8601 string."""
    return utc_now().isoformat()


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate text to max_length, appending suffix if truncated."""
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def is_valid_url(url: str) -> bool:
    """Check if a string is a valid HTTP(S) URL."""
    try:
        result = urlparse(url)
        return result.scheme in ("http", "https") and bool(result.netloc)
    except Exception:
        return False


def is_linkedin_url(url: str) -> bool:
    """Check if URL belongs to LinkedIn."""
    try:
        result = urlparse(url)
        return "linkedin.com" in result.netloc
    except Exception:
        return False


def sanitize_text(text: str) -> str:
    """Remove excessive whitespace and control characters."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def word_count(text: str) -> int:
    """Count words in text."""
    return len(text.split())
