import time
import threading
from dataclasses import dataclass, field


@dataclass
class RateLimiter:
    """Token-bucket style rate limiter with a sliding window."""

    max_actions: int
    window_seconds: int
    _timestamps: list[float] = field(default_factory=list, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        self._timestamps = [t for t in self._timestamps if t > cutoff]

    def can_act(self) -> bool:
        with self._lock:
            self._prune(time.time())
            return len(self._timestamps) < self.max_actions

    def record(self) -> None:
        with self._lock:
            self._timestamps.append(time.time())

    def remaining(self) -> int:
        with self._lock:
            self._prune(time.time())
            return max(0, self.max_actions - len(self._timestamps))

    def reset(self) -> None:
        with self._lock:
            self._timestamps.clear()

    @property
    def count(self) -> int:
        with self._lock:
            self._prune(time.time())
            return len(self._timestamps)
