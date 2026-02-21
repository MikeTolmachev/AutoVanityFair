#!/usr/bin/env python3
"""
OpenLinkedIn CLI entry point.

Usage:
    python main.py run          Start the scheduler daemon
    python main.py ui           Launch the Streamlit UI
    python main.py setup        Initialize directories and database
    python main.py generate-post [topic]   Generate a single post
"""

import argparse
import os
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))


def cmd_setup(args):
    """Create directories, initialize DB, validate config."""
    from src.core.config_manager import ConfigManager
    from src.database.models import Database
    from src.utils.logging_config import setup_logging

    print("Running setup...")

    config = ConfigManager()
    setup_logging(config.paths.logs)

    # Create directories
    dirs = [
        config.paths.logs,
        os.path.dirname(config.paths.database),
        config.linkedin.browser_profile_dir,
        config.paths.chroma_persist,
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        print(f"  Directory: {d}")

    # Initialize database
    db = Database(config.paths.database)
    print(f"  Database: {config.paths.database}")

    # Validate config
    print(f"  AI Provider: {config.ai.provider}")
    print(f"  Timezone: {config.scheduling.timezone}")
    print(f"  LinkedIn email: {config.linkedin.email or 'NOT SET'}")

    api_key = (
        config.ai.openai.api_key
        if config.ai.provider == "openai"
        else config.ai.anthropic.api_key
    )
    if api_key:
        print(f"  API key: {api_key[:8]}...")
    else:
        print("  WARNING: API key not set!")

    print("\nSetup complete!")


def cmd_run(args):
    """Start the scheduler daemon."""
    from src.core.config_manager import ConfigManager
    from src.core.safety_monitor import SafetyMonitor
    from src.core.scheduler import ContentScheduler
    from src.database.models import Database
    from src.database.crud import PostCRUD, CommentCRUD, InteractionLogCRUD
    from src.content.generator import create_ai_provider
    from src.content.post_generator import PostGenerator
    from src.content.comment_generator import CommentGenerator
    from src.utils.logging_config import setup_logging

    config = ConfigManager()
    logger = setup_logging(config.paths.logs)
    db = Database(config.paths.database)
    safety = SafetyMonitor(
        hourly_limit=config.safety.hourly_action_limit,
        daily_limit=config.safety.daily_action_limit,
        weekly_limit=config.safety.weekly_action_limit,
    )

    post_crud = PostCRUD(db)
    comment_crud = CommentCRUD(db)
    log_crud = InteractionLogCRUD(db)

    ai = create_ai_provider(config.ai)
    post_gen = PostGenerator(ai_provider=ai)
    comment_gen = CommentGenerator(ai_provider=ai)

    def on_post():
        if post_crud.count_published_today() >= config.scheduling.posts.max_per_day:
            logger.info("Daily post limit reached, skipping")
            return
        result = post_gen.generate(topic="AI and technology", strategy="thought_leadership")
        post_id = post_crud.create(
            content=result["content"],
            strategy=result["strategy"],
            rag_sources=result["rag_sources"],
        )
        log_crud.log("generate_post", details=f"Post #{post_id} generated via scheduler")
        logger.info("Post #%d generated and queued for approval", post_id)

    def on_comment():
        if comment_crud.count_published_today() >= config.scheduling.comments.max_per_day:
            logger.info("Daily comment limit reached, skipping")
            return
        result = comment_gen.generate(
            post_content="General AI discussion",
            post_author="Feed",
        )
        comment_id = comment_crud.create(
            target_post_url="",
            comment_content=result["content"],
            strategy=result["strategy"],
            confidence=result["confidence"],
            rag_sources=result["rag_sources"],
        )
        log_crud.log("generate_comment", details=f"Comment #{comment_id} generated")
        logger.info("Comment #%d generated and queued", comment_id)

    scheduler = ContentScheduler(config.scheduling, safety)
    scheduler.set_post_callback(on_post)
    scheduler.set_comment_callback(on_comment)

    def shutdown(signum, frame):
        logger.info("Shutting down scheduler...")
        scheduler.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    scheduler.start()
    print("Scheduler running. Press Ctrl+C to stop.")
    logger.info("Scheduler daemon started")

    while True:
        time.sleep(60)


def cmd_ui(args):
    """Launch the Streamlit UI."""
    ui_path = os.path.join(os.path.dirname(__file__), "ui", "app.py")
    subprocess.run(["streamlit", "run", ui_path, "--server.headless", "true"])


def cmd_generate_post(args):
    """Generate a single post."""
    from src.core.config_manager import ConfigManager
    from src.database.models import Database
    from src.database.crud import PostCRUD
    from src.content.generator import create_ai_provider
    from src.content.post_generator import PostGenerator

    config = ConfigManager()
    db = Database(config.paths.database)
    post_crud = PostCRUD(db)

    ai = create_ai_provider(config.ai)
    generator = PostGenerator(ai_provider=ai)

    topic = args.topic or "AI and technology trends"
    strategy = args.strategy or "thought_leadership"

    print(f"Generating {strategy} post about: {topic}")
    result = generator.generate(topic=topic, strategy=strategy)

    post_id = post_crud.create(
        content=result["content"],
        strategy=result["strategy"],
        rag_sources=result["rag_sources"],
    )

    print(f"\nPost #{post_id} created (status: draft)")
    print(f"Validation: {'PASS' if result['validation'].valid else 'FAIL'}")
    if not result["validation"].valid:
        print(f"  Errors: {result['validation'].errors}")
    print(f"\n--- Content ---\n{result['content']}\n")


def cmd_fetch_feeds(args):
    """Fetch and score content from RSS/API feeds."""
    from src.core.config_manager import ConfigManager
    from src.database.models import Database
    from src.database.crud import FeedItemCRUD, ContentLibraryCRUD
    from src.content.rss_aggregator import RSSAggregator
    from src.content.content_filter import ContentFilter

    config = ConfigManager()
    db = Database(config.paths.database)
    feed_crud = FeedItemCRUD(db)
    content_crud = ContentLibraryCRUD(db)

    content_filter = ContentFilter(
        min_score_threshold=args.min_score or config.aggregation.min_relevance_score,
    )
    aggregator = RSSAggregator(
        content_filter=content_filter,
        fetch_timeout=config.aggregation.fetch_timeout,
        max_items_per_feed=config.aggregation.max_items_per_feed,
    )

    priorities = [int(p) for p in args.priorities.split(",")] if args.priorities else config.aggregation.default_priorities

    print(f"Fetching feeds (priorities: {priorities})...")
    scored = aggregator.fetch_and_filter(
        priorities=priorities,
        max_results=args.max_results,
    )

    print(f"\nTop {len(scored)} results:\n")
    for i, item in enumerate(scored, 1):
        print(f"  {i:2d}. [{item.final_score:5.1f}] {item.title[:70]}")
        print(f"      Source: {item.source} | Type: {item.content_type.value}")

        # Persist to DB
        import hashlib
        item_hash = hashlib.sha256(f"{item.title}{item.url}".encode()).hexdigest()[:16]
        feed_crud.upsert(
            item_hash=item_hash,
            title=item.title,
            content=item.content,
            url=item.url,
            source_name=item.source,
            production_score=item.production_score,
            executive_score=item.executive_score,
            keyword_score=item.keyword_score,
            final_score=item.final_score,
            content_type=item.content_type.value,
            matched_keywords=item.matched_keywords,
            matched_categories=item.matched_categories,
        )

        # Auto-save high-scoring items to content library
        if item.final_score >= config.aggregation.auto_save_threshold:
            content_crud.add(
                title=item.title,
                content=item.content,
                source=item.url or item.source,
                tags=[item.content_type.value],
            )
            print(f"      >> Auto-saved to content library (score >= {config.aggregation.auto_save_threshold})")

    print(f"\n{len(scored)} items scored and persisted.")


def main():
    parser = argparse.ArgumentParser(description="OpenLinkedIn CLI")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("setup", help="Initialize directories and database")
    subparsers.add_parser("run", help="Start the scheduler daemon")
    subparsers.add_parser("ui", help="Launch Streamlit UI")

    gen_parser = subparsers.add_parser("generate-post", help="Generate a post")
    gen_parser.add_argument("topic", nargs="?", default=None, help="Post topic")
    gen_parser.add_argument(
        "--strategy",
        choices=["thought_leadership", "model_review", "pov"],
        default="thought_leadership",
    )

    feed_parser = subparsers.add_parser("fetch-feeds", help="Fetch and score RSS/API feeds")
    feed_parser.add_argument(
        "--priorities",
        default=None,
        help="Comma-separated priorities (e.g., 1,2). Default: from config",
    )
    feed_parser.add_argument(
        "--max-results",
        type=int,
        default=20,
        help="Maximum results to return",
    )
    feed_parser.add_argument(
        "--min-score",
        type=float,
        default=None,
        help="Minimum relevance score threshold",
    )

    args = parser.parse_args()

    if args.command == "setup":
        cmd_setup(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "ui":
        cmd_ui(args)
    elif args.command == "generate-post":
        cmd_generate_post(args)
    elif args.command == "fetch-feeds":
        cmd_fetch_feeds(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
