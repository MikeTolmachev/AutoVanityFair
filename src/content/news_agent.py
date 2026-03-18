"""
Agentic news research via last30days plugin.

Replaces the RSS feed system with multi-platform search (Reddit, X, YouTube,
HN, TikTok, Bluesky, etc.), using topics auto-derived from published posts
and liked feed items.
"""

import hashlib
import json
import logging
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.content.content_filter import ContentFilter
from src.database.crud import FeedItemCRUD, ContentLibraryCRUD
from src.database.models import Database

logger = logging.getLogger("openlinkedin.news_agent")


def _find_skill_root() -> str:
    """Locate the last30days script."""
    path = os.path.join(
        os.path.expanduser("~"),
        ".claude", "plugins", "marketplaces",
        "last30days-skill", "scripts", "last30days.py",
    )
    if not os.path.isfile(path):
        raise FileNotFoundError(f"last30days script not found at {path}")
    return path


def extract_topics(db: Database, config, n: int = 5) -> list[str]:
    """Derive search topics from published posts and liked feed items.

    Falls back to HIGH_PRIORITY_KEYWORDS if no history exists.
    """
    from src.content.generator import create_ai_provider

    post_texts: list[str] = []
    liked_texts: list[str] = []

    # Collect recent published posts (last 30 days)
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT content FROM posts
               WHERE status = 'published'
                 AND published_at >= datetime('now', '-30 days')
               ORDER BY published_at DESC LIMIT 20""",
        ).fetchall()
        for r in rows:
            post_texts.append(r["content"][:500])

    # Collect liked feed items
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT fi.title, fi.content FROM feed_items fi
               JOIN user_feedback uf ON fi.id = uf.feed_item_id
               WHERE uf.feedback = 'liked'
               ORDER BY uf.created_at DESC LIMIT 20""",
        ).fetchall()
        for r in rows:
            liked_texts.append(f"{r['title']}. {r['content'][:200]}")

    if not post_texts and not liked_texts:
        from src.content.keyword_taxonomy import HIGH_PRIORITY_KEYWORDS
        sample = list(HIGH_PRIORITY_KEYWORDS)[:n]
        logger.info("No history found, using fallback topics: %s", sample)
        return sample

    sections = []
    if post_texts:
        sections.append("## MY PUBLISHED LINKEDIN POSTS:\n" + "\n---\n".join(post_texts))
    if liked_texts:
        sections.append("## ARTICLES I LIKED:\n" + "\n---\n".join(liked_texts))

    context = "\n\n".join(sections)

    prompt = (
        "You are a research assistant for an AI/ML executive who publishes thought leadership on LinkedIn.\n\n"
        "Below are their recent published posts and liked articles. Analyze the SPECIFIC technical themes, "
        "technologies, frameworks, and research directions they cover.\n\n"
        f"{context}\n\n"
        "Based on this content, generate exactly {n} search queries that would find NEW related content "
        "on Reddit, Hacker News, and tech blogs. Each query should:\n"
        "- Target the specific technical niche from their posts (e.g. 'LLM inference optimization', "
        "'vision language model efficiency', 'on-device ML Apple Neural Engine')\n"
        "- Be 2-6 words, specific enough to return relevant results\n"
        "- Cover different themes from their portfolio — don't repeat the same angle\n"
        "- Focus on what would make good follow-up content for their audience\n\n"
        "Return ONLY a JSON array of strings. No explanation."
    ).format(n=n)

    try:
        ai = create_ai_provider(config.ai)
        result = ai.generate(
            system_prompt="You analyze content themes and generate targeted search queries. Return ONLY a JSON array of strings.",
            user_prompt=prompt,
        )
        text = result.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        topics = json.loads(text)
        if isinstance(topics, list):
            return [str(t) for t in topics[:n]]
    except Exception:
        logger.exception("Topic extraction failed, using fallback")

    from src.content.keyword_taxonomy import HIGH_PRIORITY_KEYWORDS
    return list(HIGH_PRIORITY_KEYWORDS)[:n]


def _research_topic(topic: str, script_path: str, timeout: int = 300) -> list[dict]:
    """Run last30days for a single topic and return parsed items."""
    cmd = [
        "python3", script_path,
        topic,
        "--emit=json",
    ]
    logger.info("Researching topic: %s", topic)

    # Inherit env and fix Python 3.14 SSL cert issue on macOS
    env = dict(os.environ)
    try:
        import certifi
        env.setdefault("SSL_CERT_FILE", certifi.where())
    except ImportError:
        pass

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        if proc.returncode != 0:
            logger.warning("last30days failed for '%s': %s", topic, proc.stderr[:500])
            return []

        data = json.loads(proc.stdout)
        items = []
        # The output may be a dict with platform keys or a list
        if isinstance(data, dict):
            for platform, platform_items in data.items():
                if isinstance(platform_items, list):
                    for item in platform_items:
                        item["_platform"] = platform
                        item["_topic"] = topic
                        items.append(item)
        elif isinstance(data, list):
            for item in data:
                item["_topic"] = topic
                items.append(item)

        logger.info("Topic '%s': found %d items", topic, len(items))
        return items

    except subprocess.TimeoutExpired:
        logger.warning("Timeout researching topic: %s", topic)
        return []
    except (json.JSONDecodeError, Exception):
        logger.exception("Failed to parse research output for: %s", topic)
        return []


def _normalize_item(raw: dict) -> dict:
    """Normalize a last30days item into feed_items fields."""
    platform = raw.get("_platform", raw.get("platform", "web")).lower()
    topic = raw.get("_topic", "")

    title = raw.get("title", raw.get("text", ""))
    # For social posts, use first line as title
    if platform in ("x", "tiktok", "instagram", "bluesky", "truth", "truthsocial"):
        lines = title.split("\n")
        title = lines[0][:200] if lines else title[:200]

    content = raw.get("content", raw.get("text", raw.get("body", "")))
    url = raw.get("url", raw.get("link", ""))
    author = raw.get("author", raw.get("username", raw.get("handle", "")))
    published = raw.get("date", raw.get("published", raw.get("created_at", "")))

    # Build source_name with platform prefix
    source_name = raw.get("source", raw.get("subreddit", ""))
    if source_name:
        source_name = f"{platform.capitalize()} {source_name}"
    else:
        source_name = platform.capitalize()
        if author:
            source_name = f"{platform.capitalize()} @{author}"

    item_hash = hashlib.sha256(f"{title}{url}".encode()).hexdigest()[:16]

    return {
        "title": title,
        "content": content,
        "url": url,
        "source_name": source_name,
        "source_category": topic,
        "author": author,
        "published_at": published,
        "item_hash": item_hash,
    }


def run_research(
    topics: list[str],
    config,
    feed_crud: FeedItemCRUD,
    content_crud: ContentLibraryCRUD,
) -> dict:
    """Run multi-platform research for all topics and persist results."""
    script_path = _find_skill_root()
    content_filter = ContentFilter(min_score_threshold=0.0)

    # Research all topics in parallel
    all_raw: list[dict] = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            pool.submit(_research_topic, topic, script_path): topic
            for topic in topics
        }
        for future in as_completed(futures):
            topic = futures[future]
            try:
                items = future.result()
                all_raw.extend(items)
            except Exception:
                logger.exception("Research failed for topic: %s", topic)

    logger.info("Total raw items from research: %d", len(all_raw))

    # Normalize and deduplicate
    seen_hashes: set[str] = set()
    normalized: list[dict] = []
    for raw in all_raw:
        item = _normalize_item(raw)
        if not item["title"] or item["item_hash"] in seen_hashes:
            continue
        seen_hashes.add(item["item_hash"])
        normalized.append(item)

    # Score each item through ContentFilter
    scored_items: list[dict] = []
    for item in normalized:
        scored = content_filter.score(
            title=item["title"],
            content=item["content"],
            url=item["url"],
            source=item["source_name"],
            author=item["author"],
            published_at=item["published_at"],
        )
        item["production_score"] = scored.production_score
        item["executive_score"] = scored.executive_score
        item["keyword_score"] = scored.keyword_score
        item["final_score"] = scored.final_score
        item["content_type"] = scored.content_type.value
        item["matched_keywords"] = scored.matched_keywords
        item["matched_categories"] = scored.matched_categories
        scored_items.append(item)

    # Compute embeddings in batch
    embeddings: list[list[float]] = []
    vc = config.vertex_ai
    if vc.project_id and scored_items:
        from src.content.embeddings import get_embeddings, embedding_text
        texts = [embedding_text(it["title"], it["content"]) for it in scored_items]
        embeddings = get_embeddings(texts, project_id=vc.project_id, location="us-central1")

    # Persist to DB
    persisted = 0
    for idx, item in enumerate(scored_items):
        emb = embeddings[idx] if idx < len(embeddings) else None
        feed_crud.upsert(
            item_hash=item["item_hash"],
            title=item["title"],
            content=item["content"],
            url=item["url"],
            source_name=item["source_name"],
            source_category=item["source_category"],
            author=item["author"],
            published_at=item["published_at"],
            production_score=item["production_score"],
            executive_score=item["executive_score"],
            keyword_score=item["keyword_score"],
            final_score=item["final_score"],
            content_type=item["content_type"],
            matched_keywords=item["matched_keywords"],
            matched_categories=item["matched_categories"],
            embedding=emb,
        )

        # Auto-save high scorers to content library
        if item["final_score"] >= config.aggregation.auto_save_threshold:
            content_crud.add(
                title=item["title"],
                content=item["content"],
                source=item["url"] or item["source_name"],
                tags=[item["content_type"]],
            )
        persisted += 1

    return {
        "topics_searched": len(topics),
        "topics": topics,
        "items_found": len(all_raw),
        "items_unique": len(normalized),
        "items_persisted": persisted,
        "items_embedded": len(embeddings),
    }
