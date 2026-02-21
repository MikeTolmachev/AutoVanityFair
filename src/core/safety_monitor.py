import logging
import time
import threading
from dataclasses import dataclass, field
from typing import Optional

from src.core.rate_limiter import RateLimiter

logger = logging.getLogger("openlinkedin.safety")


@dataclass
class SafetyMonitor:
    """Wraps multiple rate limiters and tracks error rates."""

    hourly_limit: int = 8
    daily_limit: int = 30
    weekly_limit: int = 150
    error_rate_threshold: float = 0.3
    error_window_seconds: int = 3600
    cooldown_minutes: int = 30

    _hourly: RateLimiter = field(init=False)
    _daily: RateLimiter = field(init=False)
    _weekly: RateLimiter = field(init=False)
    _errors: list[float] = field(default_factory=list, init=False, repr=False)
    _successes: list[float] = field(default_factory=list, init=False, repr=False)
    _cooldown_until: Optional[float] = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        self._hourly = RateLimiter(self.hourly_limit, 3600)
        self._daily = RateLimiter(self.daily_limit, 86400)
        self._weekly = RateLimiter(self.weekly_limit, 604800)

    def can_act(self) -> bool:
        with self._lock:
            now = time.time()
            if self._cooldown_until and now < self._cooldown_until:
                logger.warning("In cooldown until %.0f", self._cooldown_until)
                return False

            if not self._hourly.can_act():
                logger.warning("Hourly limit reached")
                return False
            if not self._daily.can_act():
                logger.warning("Daily limit reached")
                return False
            if not self._weekly.can_act():
                logger.warning("Weekly limit reached")
                return False

            if self._current_error_rate() > self.error_rate_threshold:
                logger.warning(
                    "Error rate %.2f exceeds threshold %.2f, entering cooldown",
                    self._current_error_rate(),
                    self.error_rate_threshold,
                )
                self._cooldown_until = now + self.cooldown_minutes * 60
                return False

            return True

    def record_action(self) -> None:
        """Record a successful action."""
        with self._lock:
            now = time.time()
            self._hourly.record()
            self._daily.record()
            self._weekly.record()
            self._successes.append(now)

    def record_error(self) -> None:
        """Record a failed action."""
        with self._lock:
            now = time.time()
            self._hourly.record()
            self._daily.record()
            self._weekly.record()
            self._errors.append(now)

    def _prune_window(self, timestamps: list[float], now: float) -> list[float]:
        cutoff = now - self.error_window_seconds
        return [t for t in timestamps if t > cutoff]

    def _current_error_rate(self) -> float:
        now = time.time()
        self._errors = self._prune_window(self._errors, now)
        self._successes = self._prune_window(self._successes, now)
        total = len(self._errors) + len(self._successes)
        if total == 0:
            return 0.0
        return len(self._errors) / total

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "hourly_remaining": self._hourly.remaining(),
                "daily_remaining": self._daily.remaining(),
                "weekly_remaining": self._weekly.remaining(),
                "error_rate": round(self._current_error_rate(), 3),
                "in_cooldown": (
                    self._cooldown_until is not None
                    and time.time() < self._cooldown_until
                ),
            }
