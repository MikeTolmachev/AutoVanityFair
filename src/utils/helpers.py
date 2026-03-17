import logging
import re
import ssl
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

logger = logging.getLogger("openlinkedin.helpers")

USER_AGENT = (
    "Mozilla/5.0 (compatible; OpenLinkedIn/1.0; "
    "+https://github.com/openlinkedin)"
)


def fetch_url(url: str, timeout: int = 15) -> Optional[bytes]:
    """Fetch raw bytes from a URL."""
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except URLError as ssl_err:
            if "CERTIFICATE_VERIFY_FAILED" in str(ssl_err):
                logger.warning("SSL verify failed for %s, retrying without verification", url)
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urlopen(req, timeout=timeout, context=ctx) as resp:
                    return resp.read()
            raise
    except (URLError, OSError, TimeoutError) as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return None


def strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


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


# LinkedIn relative time pattern: "2w", "1mo", "3d", "5h", "1yr"
_LINKEDIN_RELATIVE_RE = re.compile(
    r"^\s*(\d+)\s*(mo|min|mi|yr|hr|w|d|h|m|s)\w*\s*$", re.IGNORECASE
)


def parse_published_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse a date string into a timezone-aware UTC datetime.

    Handles:
    - ISO 8601 (e.g. "2024-10-15T12:00:00Z")
    - RFC 2822 (e.g. "Tue, 15 Oct 2024 12:00:00 +0000")
    - LinkedIn relative strings ("2w", "1mo", "3d", "5h", "1yr")

    Returns None if the string is empty or unparseable.
    """
    if not date_str or not date_str.strip():
        return None

    date_str = date_str.strip()

    # Try LinkedIn relative time first (e.g. "2w", "1mo", "3d")
    m = _LINKEDIN_RELATIVE_RE.match(date_str)
    if m:
        amount = int(m.group(1))
        unit = m.group(2).lower()
        now = utc_now()
        if unit in ("s",):
            delta = amount
        elif unit in ("m", "mi", "min"):
            delta = amount * 60
        elif unit in ("h", "hr"):
            delta = amount * 3600
        elif unit == "d":
            delta = amount * 86400
        elif unit == "w":
            delta = amount * 7 * 86400
        elif unit == "mo":
            delta = amount * 30 * 86400
        elif unit == "yr":
            delta = amount * 365 * 86400
        else:
            return None
        from datetime import timedelta
        return now - timedelta(seconds=delta)

    # Try ISO 8601
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        pass

    # Try RFC 2822 (RSS pubDate format)
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError, IndexError):
        pass

    return None


def months_ago(dt: datetime, now: Optional[datetime] = None) -> float:
    """Return the fractional number of months between *dt* and *now*.

    Uses a 30-day month approximation.
    """
    if now is None:
        now = utc_now()
    # Ensure both are timezone-aware for comparison
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    delta_seconds = (now - dt).total_seconds()
    return max(0.0, delta_seconds / (30 * 86400))
