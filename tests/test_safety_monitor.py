import time

import pytest

from src.core.rate_limiter import RateLimiter
from src.core.safety_monitor import SafetyMonitor


class TestRateLimiter:
    def test_can_act_within_limit(self):
        rl = RateLimiter(max_actions=3, window_seconds=60)
        assert rl.can_act()
        rl.record()
        rl.record()
        assert rl.can_act()
        rl.record()
        assert not rl.can_act()

    def test_remaining(self):
        rl = RateLimiter(max_actions=5, window_seconds=60)
        assert rl.remaining() == 5
        rl.record()
        rl.record()
        assert rl.remaining() == 3

    def test_reset(self):
        rl = RateLimiter(max_actions=2, window_seconds=60)
        rl.record()
        rl.record()
        assert not rl.can_act()
        rl.reset()
        assert rl.can_act()
        assert rl.remaining() == 2

    def test_count(self):
        rl = RateLimiter(max_actions=10, window_seconds=60)
        rl.record()
        rl.record()
        rl.record()
        assert rl.count == 3


class TestSafetyMonitor:
    def test_can_act_initially(self):
        sm = SafetyMonitor(hourly_limit=5, daily_limit=10, weekly_limit=50)
        assert sm.can_act()

    def test_hourly_limit(self):
        sm = SafetyMonitor(hourly_limit=2, daily_limit=100, weekly_limit=500)
        sm.record_action()
        sm.record_action()
        assert not sm.can_act()

    def test_error_rate_threshold(self):
        sm = SafetyMonitor(
            hourly_limit=100,
            daily_limit=100,
            weekly_limit=500,
            error_rate_threshold=0.3,
            error_window_seconds=3600,
            cooldown_minutes=1,
        )
        # 4 errors, 1 success = 80% error rate
        for _ in range(4):
            sm.record_error()
        sm.record_action()

        assert not sm.can_act()

    def test_get_stats(self):
        sm = SafetyMonitor(hourly_limit=5, daily_limit=10, weekly_limit=50)
        sm.record_action()
        sm.record_action()

        stats = sm.get_stats()
        assert stats["hourly_remaining"] == 3
        assert stats["daily_remaining"] == 8
        assert stats["weekly_remaining"] == 48
        assert stats["error_rate"] == 0.0
        assert stats["in_cooldown"] is False

    def test_cooldown_after_errors(self):
        sm = SafetyMonitor(
            hourly_limit=100,
            daily_limit=100,
            weekly_limit=500,
            error_rate_threshold=0.3,
            cooldown_minutes=1,
        )
        for _ in range(5):
            sm.record_error()

        # First call triggers cooldown
        assert not sm.can_act()

        stats = sm.get_stats()
        assert stats["in_cooldown"] is True
