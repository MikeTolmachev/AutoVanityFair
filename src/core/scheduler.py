"""
ContentScheduler -- APScheduler with CET timezone for posts and comments.
"""

import logging
from typing import Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.core.config_manager import SchedulingConfig
from src.core.safety_monitor import SafetyMonitor

logger = logging.getLogger("openlinkedin.scheduler")


class ContentScheduler:
    """Manages scheduled content generation and publishing."""

    def __init__(
        self,
        scheduling_config: SchedulingConfig,
        safety_monitor: SafetyMonitor,
    ):
        self.config = scheduling_config
        self.safety = safety_monitor
        self.scheduler = BackgroundScheduler(
            timezone=scheduling_config.timezone,
        )
        self._post_callback: Optional[Callable] = None
        self._comment_callback: Optional[Callable] = None

    def set_post_callback(self, callback: Callable) -> None:
        """Set the function called when it's time to generate/publish a post."""
        self._post_callback = callback

    def set_comment_callback(self, callback: Callable) -> None:
        """Set the function called when it's time to generate/publish a comment."""
        self._comment_callback = callback

    def _safe_post_callback(self) -> None:
        if not self.safety.can_act():
            logger.warning("Post generation skipped: safety limits reached")
            return
        if self._post_callback:
            try:
                self._post_callback()
            except Exception as e:
                logger.error("Post callback error: %s", e)
                self.safety.record_error()

    def _safe_comment_callback(self) -> None:
        if not self.safety.can_act():
            logger.warning("Comment generation skipped: safety limits reached")
            return
        if self._comment_callback:
            try:
                self._comment_callback()
            except Exception as e:
                logger.error("Comment callback error: %s", e)
                self.safety.record_error()

    def start(self) -> None:
        """Start the scheduler with configured triggers."""
        # Post generation: cron trigger during morning hours (CET)
        post_trigger = CronTrigger(
            hour=self.config.posts.cron_hour,
            minute=self.config.posts.cron_minute,
            timezone=self.config.timezone,
        )
        self.scheduler.add_job(
            self._safe_post_callback,
            trigger=post_trigger,
            id="post_generation",
            name="Generate LinkedIn Post",
            replace_existing=True,
        )

        # Comment generation: interval trigger during active hours (CET)
        comment_trigger = IntervalTrigger(
            hours=self.config.comments.interval_hours,
            timezone=self.config.timezone,
        )
        self.scheduler.add_job(
            self._safe_comment_callback,
            trigger=comment_trigger,
            id="comment_generation",
            name="Generate LinkedIn Comment",
            replace_existing=True,
        )

        self.scheduler.start()
        logger.info(
            "Scheduler started (timezone=%s, post_hours=%s, comment_interval=%dh)",
            self.config.timezone,
            self.config.posts.cron_hour,
            self.config.comments.interval_hours,
        )

    def stop(self) -> None:
        """Shutdown the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")

    def get_jobs(self) -> list[dict]:
        """Return info about scheduled jobs."""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": str(job.next_run_time) if job.next_run_time else None,
                    "trigger": str(job.trigger),
                }
            )
        return jobs

    @property
    def running(self) -> bool:
        return self.scheduler.running
