"""
OpenLinkedIn -- FastAPI REST backend.

Serves the JSON API at /api/* and the web frontend from /web/.
"""

import hashlib
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger("openlinkedin.api")

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
# Set OPENLINKEDIN_API_TOKEN in .env to require bearer-token auth on all
# /api/* endpoints.  When the variable is empty or unset, auth is disabled
# (convenient for local development).
# ---------------------------------------------------------------------------

API_TOKEN: Optional[str] = os.environ.get("OPENLINKEDIN_API_TOKEN", "").strip() or None

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.config_manager import ConfigManager
from src.core.safety_monitor import SafetyMonitor
from src.database.models import Database
from src.database.crud import (
    PostCRUD,
    CommentCRUD,
    InteractionLogCRUD,
    ContentLibraryCRUD,
    FeedItemCRUD,
    FeedbackCRUD,
    SearchFeedbackCRUD,
)

# ---------------------------------------------------------------------------
# Shared state (initialized on startup)
# ---------------------------------------------------------------------------
_state: dict = {}


def _get(key: str):
    return _state[key]


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = ConfigManager()
    db = Database(config.paths.database)
    safety = SafetyMonitor(
        hourly_limit=config.safety.hourly_action_limit,
        daily_limit=config.safety.daily_action_limit,
        weekly_limit=config.safety.weekly_action_limit,
        error_rate_threshold=config.safety.error_rate_threshold,
        error_window_seconds=config.safety.error_window_seconds,
        cooldown_minutes=config.safety.cooldown_minutes,
    )

    _state.update(
        config=config,
        db=db,
        safety=safety,
        post_crud=PostCRUD(db),
        comment_crud=CommentCRUD(db),
        log_crud=InteractionLogCRUD(db),
        content_crud=ContentLibraryCRUD(db),
        feed_crud=FeedItemCRUD(db),
        feedback_crud=FeedbackCRUD(db),
        search_feedback_crud=SearchFeedbackCRUD(db),
    )
    yield
    _state.clear()


app = FastAPI(title="OpenLinkedIn API", lifespan=lifespan)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Require bearer token for /api/* routes when OPENLINKEDIN_API_TOKEN is set."""
    if API_TOKEN and request.url.path.startswith("/api/"):
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != API_TOKEN:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API token"})
    return await call_next(request)

# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------


class StatusUpdate(BaseModel):
    status: str
    reason: Optional[str] = None


class ContentUpdate(BaseModel):
    content: str


class LibraryAdd(BaseModel):
    title: str
    content: str
    source: Optional[str] = None
    tags: Optional[list[str]] = None
    personal_thoughts: Optional[str] = None


class ThoughtsUpdate(BaseModel):
    thoughts: str


class FeedbackBody(BaseModel):
    feedback: str  # "liked" or "disliked"


class FeedSaveBody(BaseModel):
    title: str
    content: str
    url: Optional[str] = None
    source_name: Optional[str] = None
    content_type: Optional[str] = None


class GeneratePostBody(BaseModel):
    topic: Optional[str] = "AI and technology trends"
    strategy: Optional[str] = "thought_leadership"


# ---------------------------------------------------------------------------
# Dashboard / Stats
# ---------------------------------------------------------------------------


@app.get("/api/stats")
def get_stats():
    post_crud: PostCRUD = _get("post_crud")
    comment_crud: CommentCRUD = _get("comment_crud")
    safety: SafetyMonitor = _get("safety")
    feed_crud: FeedItemCRUD = _get("feed_crud")
    content_crud: ContentLibraryCRUD = _get("content_crud")
    feedback_crud: FeedbackCRUD = _get("feedback_crud")

    post_counts = post_crud.count_by_status()
    feedback_counts = feedback_crud.count_feedback()

    return {
        "posts": post_counts,
        "total_posts": sum(post_counts.values()),
        "comments_today": comment_crud.count_published_today(),
        "total_comments": comment_crud.count_total(),
        "feed_items": feed_crud.count(),
        "library_docs": content_crud.count(),
        "feedback": feedback_counts,
        "safety": safety.get_stats(),
    }


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------


@app.get("/api/posts")
def list_posts(status: str = "draft", limit: int = Query(default=50, ge=1, le=500)):
    crud: PostCRUD = _get("post_crud")
    posts = crud.list_by_status(status, limit=limit)
    # Parse rag_sources JSON strings
    for p in posts:
        if p.get("rag_sources") and isinstance(p["rag_sources"], str):
            try:
                p["rag_sources"] = json.loads(p["rag_sources"])
            except (json.JSONDecodeError, TypeError):
                pass
    return posts


@app.get("/api/posts/{post_id}")
def get_post(post_id: int):
    crud: PostCRUD = _get("post_crud")
    post = crud.get(post_id)
    if not post:
        raise HTTPException(404, "Post not found")
    return post


@app.put("/api/posts/{post_id}/status")
def update_post_status(post_id: int, body: StatusUpdate):
    crud: PostCRUD = _get("post_crud")
    log_crud: InteractionLogCRUD = _get("log_crud")
    if body.status not in ("draft", "approved", "published", "rejected"):
        raise HTTPException(400, "Invalid status")
    crud.update_status(post_id, body.status, reason=body.reason)
    log_crud.log("update_post_status", details=f"Post #{post_id} -> {body.status}")
    return {"ok": True}


@app.put("/api/posts/{post_id}/content")
def update_post_content(post_id: int, body: ContentUpdate):
    crud: PostCRUD = _get("post_crud")
    crud.update_content(post_id, body.content)
    return {"ok": True}


@app.post("/api/posts/generate")
def generate_post(body: GeneratePostBody):
    config: ConfigManager = _get("config")
    crud: PostCRUD = _get("post_crud")
    log_crud: InteractionLogCRUD = _get("log_crud")
    try:
        from src.content.generator import create_ai_provider
        from src.content.post_generator import PostGenerator

        ai = create_ai_provider(config.ai)
        generator = PostGenerator(ai_provider=ai)
        result = generator.generate(topic=body.topic, strategy=body.strategy)
        post_id = crud.create(
            content=result["content"],
            strategy=result["strategy"],
            rag_sources=result["rag_sources"],
        )
        log_crud.log("generate_post", details=f"Post #{post_id} generated via web UI")
        return {"id": post_id, "content": result["content"], "strategy": result["strategy"]}
    except Exception as e:
        logger.exception("Request failed")
        raise HTTPException(500, "Internal server error")


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


@app.get("/api/comments")
def list_comments(status: str = "draft", limit: int = Query(default=50, ge=1, le=500)):
    crud: CommentCRUD = _get("comment_crud")
    return crud.list_by_status(status, limit=limit)


@app.get("/api/comments/{comment_id}")
def get_comment(comment_id: int):
    crud: CommentCRUD = _get("comment_crud")
    comment = crud.get(comment_id)
    if not comment:
        raise HTTPException(404, "Comment not found")
    return comment


@app.put("/api/comments/{comment_id}/status")
def update_comment_status(comment_id: int, body: StatusUpdate):
    crud: CommentCRUD = _get("comment_crud")
    if body.status not in ("draft", "approved", "published", "rejected"):
        raise HTTPException(400, "Invalid status")
    crud.update_status(comment_id, body.status, reason=body.reason)
    return {"ok": True}


@app.put("/api/comments/{comment_id}/content")
def update_comment_content(comment_id: int, body: ContentUpdate):
    crud: CommentCRUD = _get("comment_crud")
    crud.update_content(comment_id, body.content)
    return {"ok": True}


@app.post("/api/comments/approve-all")
def approve_all_draft_comments():
    crud: CommentCRUD = _get("comment_crud")
    drafts = crud.list_by_status("draft")
    for c in drafts:
        crud.update_status(c["id"], "approved")
    return {"ok": True, "count": len(drafts)}


# ---------------------------------------------------------------------------
# Content Library
# ---------------------------------------------------------------------------


@app.get("/api/library")
def list_library(limit: int = Query(default=100, ge=1, le=500)):
    crud: ContentLibraryCRUD = _get("content_crud")
    docs = crud.list_all(limit=limit)
    for d in docs:
        if d.get("tags") and isinstance(d["tags"], str):
            try:
                d["tags"] = json.loads(d["tags"])
            except (json.JSONDecodeError, TypeError):
                pass
    return docs


@app.get("/api/library/{doc_id}")
def get_library_doc(doc_id: int):
    crud: ContentLibraryCRUD = _get("content_crud")
    doc = crud.get(doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.get("tags") and isinstance(doc["tags"], str):
        try:
            doc["tags"] = json.loads(doc["tags"])
        except (json.JSONDecodeError, TypeError):
            pass
    return doc


@app.post("/api/library")
def add_library_doc(body: LibraryAdd):
    crud: ContentLibraryCRUD = _get("content_crud")
    doc_id = crud.add(
        title=body.title,
        content=body.content,
        source=body.source,
        tags=body.tags,
        personal_thoughts=body.personal_thoughts,
    )
    return {"id": doc_id}


@app.delete("/api/library/{doc_id}")
def delete_library_doc(doc_id: int):
    crud: ContentLibraryCRUD = _get("content_crud")
    crud.delete(doc_id)
    return {"ok": True}


@app.put("/api/library/{doc_id}/thoughts")
def update_thoughts(doc_id: int, body: ThoughtsUpdate):
    crud: ContentLibraryCRUD = _get("content_crud")
    crud.update_personal_thoughts(doc_id, body.thoughts)
    return {"ok": True}


@app.post("/api/library/{doc_id}/generate")
def generate_post_from_library(doc_id: int):
    config: ConfigManager = _get("config")
    crud: ContentLibraryCRUD = _get("content_crud")

    doc = crud.get(doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")

    try:
        from src.content.generator import create_ai_provider
        from src.content.prompts import LIBRARY_POST_SYSTEM_PROMPT, LIBRARY_POST_TEMPLATE

        ai = create_ai_provider(config.ai)

        thoughts_section = ""
        if doc.get("personal_thoughts") and doc["personal_thoughts"].strip():
            thoughts_section = f"\nMy personal thoughts / angle:\n{doc['personal_thoughts'].strip()}\n"

        user_prompt = LIBRARY_POST_TEMPLATE.format(
            article_title=doc["title"],
            article_source=doc.get("source") or "N/A",
            article_content=doc["content"][:2000],
            personal_thoughts_section=thoughts_section,
        )

        result = ai.generate(LIBRARY_POST_SYSTEM_PROMPT, user_prompt)
        raw = result.content

        title = ""
        body = raw
        if "TITLE:" in raw:
            after_title = raw.split("TITLE:", 1)[1]
            if "---" in after_title:
                title_part, body = after_title.split("---", 1)
                title = title_part.strip()
                body = body.strip()
            else:
                lines = after_title.strip().split("\n", 1)
                title = lines[0].strip()
                body = lines[1].strip() if len(lines) > 1 else ""

        crud.update_generated_post(doc_id, title, body)
        return {"title": title, "body": body, "tokens_used": result.tokens_used}
    except Exception as e:
        logger.exception("Request failed")
        raise HTTPException(500, "Internal server error")


@app.post("/api/library/{doc_id}/to-queue")
def send_to_post_queue(doc_id: int):
    content_crud: ContentLibraryCRUD = _get("content_crud")
    post_crud: PostCRUD = _get("post_crud")

    doc = content_crud.get(doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    if not doc.get("generated_post"):
        raise HTTPException(400, "No generated post to send")

    post_id = post_crud.create(
        content=doc["generated_post"],
        strategy="thought_leadership",
        rag_sources=[str(doc["id"])],
    )
    return {"post_id": post_id}


# ---------------------------------------------------------------------------
# Feed
# ---------------------------------------------------------------------------


@app.get("/api/feed")
def list_feed_items(
    min_score: float = 0.0,
    limit: int = Query(default=100, ge=1, le=500),
    source: Optional[str] = None,
):
    feed_crud: FeedItemCRUD = _get("feed_crud")
    feedback_crud: FeedbackCRUD = _get("feedback_crud")

    if source:
        items = feed_crud.get_by_source(source, limit=limit)
    else:
        items = feed_crud.get_top_scored(limit=limit, min_score=min_score)

    feedback_map = feedback_crud.get_feedback_map()

    for item in items:
        h = item.get("item_hash", "")
        item["feedback"] = feedback_map.get(h)
        if item.get("matched_keywords") and isinstance(item["matched_keywords"], str):
            try:
                item["matched_keywords"] = json.loads(item["matched_keywords"])
            except (json.JSONDecodeError, TypeError):
                pass
        if item.get("matched_categories") and isinstance(item["matched_categories"], str):
            try:
                item["matched_categories"] = json.loads(item["matched_categories"])
            except (json.JSONDecodeError, TypeError):
                pass

    return items


@app.get("/api/feed/sources")
def feed_source_counts():
    feed_crud: FeedItemCRUD = _get("feed_crud")
    return feed_crud.count_by_source()


@app.post("/api/feed/fetch")
def fetch_feeds(
    min_score: float = 10.0,
    max_results: int = 100,
    priorities: Optional[str] = None,
):
    """Fetch RSS feeds, score, and persist. priorities is comma-separated like '1,2'."""
    config: ConfigManager = _get("config")
    feed_crud: FeedItemCRUD = _get("feed_crud")
    content_crud: ContentLibraryCRUD = _get("content_crud")

    try:
        from src.content.rss_aggregator import RSSAggregator
        from src.content.content_filter import ContentFilter

        content_filter = ContentFilter(min_score_threshold=min_score)
        aggregator = RSSAggregator(
            content_filter=content_filter,
            fetch_timeout=config.aggregation.fetch_timeout,
            max_items_per_feed=config.aggregation.max_items_per_feed,
        )

        prio_list = None
        if priorities:
            prio_list = [int(p.strip()) for p in priorities.split(",")]

        scored = aggregator.fetch_and_filter(
            priorities=prio_list,
            max_results=max_results,
        )

        persisted = 0
        for item in scored:
            item_hash = hashlib.sha256(f"{item.title}{item.url}".encode()).hexdigest()[:16]
            feed_crud.upsert(
                item_hash=item_hash,
                title=item.title,
                content=item.content,
                url=item.url,
                source_name=item.source,
                author=item.author,
                published_at=item.published_at,
                production_score=item.production_score,
                executive_score=item.executive_score,
                keyword_score=item.keyword_score,
                final_score=item.final_score,
                content_type=item.content_type.value,
                matched_keywords=item.matched_keywords,
                matched_categories=item.matched_categories,
            )
            if item.final_score >= config.aggregation.auto_save_threshold:
                content_crud.add(
                    title=item.title,
                    content=item.content,
                    source=item.url or item.source,
                    tags=[item.content_type.value],
                )
            persisted += 1

        return {"fetched": len(scored), "persisted": persisted}
    except Exception as e:
        logger.exception("Request failed")
        raise HTTPException(500, "Internal server error")


@app.post("/api/feed/{item_id}/feedback")
def set_feed_feedback(item_id: int, body: FeedbackBody):
    feed_crud: FeedItemCRUD = _get("feed_crud")
    feedback_crud: FeedbackCRUD = _get("feedback_crud")

    if body.feedback not in ("liked", "disliked"):
        raise HTTPException(400, "feedback must be 'liked' or 'disliked'")

    # Look up item_hash from ID
    with feed_crud.db.connect() as conn:
        row = conn.execute("SELECT item_hash FROM feed_items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Feed item not found")

    feedback_crud.set_feedback(item_id, row["item_hash"], body.feedback)
    return {"ok": True}


@app.post("/api/feed/save")
def save_feed_to_library(body: FeedSaveBody):
    content_crud: ContentLibraryCRUD = _get("content_crud")
    doc_id = content_crud.add(
        title=body.title,
        content=body.content,
        source=body.url or body.source_name or "",
        tags=[body.content_type or "", body.source_name or ""],
    )
    return {"id": doc_id}


# ---------------------------------------------------------------------------
# Reranker
# ---------------------------------------------------------------------------


@app.post("/api/feed/retrain")
def retrain_reranker():
    feedback_crud: FeedbackCRUD = _get("feedback_crud")
    try:
        from src.content.reranker import FeedReranker

        reranker = FeedReranker()
        training_data = feedback_crud.get_all_training_data()
        feedback_map = feedback_crud.get_feedback_map()
        published_hashes = feedback_crud.get_published_item_hashes()
        for h in published_hashes:
            if h not in feedback_map:
                feedback_map[h] = "liked"
        result = reranker.train(training_data, feedback_map)
        return result
    except Exception as e:
        logger.exception("Request failed")
        raise HTTPException(500, "Internal server error")


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


@app.get("/api/analytics")
def get_analytics():
    post_crud: PostCRUD = _get("post_crud")
    comment_crud: CommentCRUD = _get("comment_crud")
    log_crud: InteractionLogCRUD = _get("log_crud")

    post_counts = post_crud.count_by_status()
    total_posts = sum(post_counts.values())
    published = post_counts.get("published", 0)

    return {
        "posts": {
            "total": total_posts,
            "by_status": post_counts,
            "published": published,
            "approval_rate": f"{published / total_posts:.0%}" if total_posts > 0 else "N/A",
        },
        "comments": {
            "today": comment_crud.count_published_today(),
            "total": comment_crud.count_total(),
        },
        "actions_7d": log_crud.count_by_action(days=7),
        "recent_activity": log_crud.get_recent(limit=30),
    }


# ---------------------------------------------------------------------------
# Settings (read-only)
# ---------------------------------------------------------------------------


def _mask_email(email: str) -> str:
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    masked = local[0] + "***" if local else "***"
    return f"{masked}@{domain}"


@app.get("/api/settings")
def get_settings():
    config: ConfigManager = _get("config")
    ai = config.ai
    api_key = ai.openai.api_key if ai.provider == "openai" else ai.anthropic.api_key
    key_status = "Configured" if api_key and len(api_key) > 4 else "Not set"
    model = ai.openai.model if ai.provider == "openai" else ai.anthropic.model

    return {
        "ai": {
            "provider": ai.provider,
            "model": model,
            "api_key_status": key_status,
        },
        "scheduling": {
            "timezone": config.scheduling.timezone,
            "posts_cron_hour": config.scheduling.posts.cron_hour,
            "posts_max_per_day": config.scheduling.posts.max_per_day,
            "comments_interval": config.scheduling.comments.interval_hours,
            "comments_active_hours": f"{config.scheduling.comments.active_start_hour}-{config.scheduling.comments.active_end_hour}",
            "comments_max_per_day": config.scheduling.comments.max_per_day,
        },
        "safety": {
            "hourly": config.safety.hourly_action_limit,
            "daily": config.safety.daily_action_limit,
            "weekly": config.safety.weekly_action_limit,
            "error_threshold": config.safety.error_rate_threshold,
            "cooldown_minutes": config.safety.cooldown_minutes,
        },
        "linkedin": {
            "email": _mask_email(config.linkedin.email) if config.linkedin.email else "Not configured",
            "headless": config.linkedin.headless,
        },
    }


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


@app.get("/api/logs")
def get_logs(limit: int = Query(default=50, ge=1, le=200)):
    log_crud: InteractionLogCRUD = _get("log_crud")
    return log_crud.get_recent(limit=limit)


# ---------------------------------------------------------------------------
# Frontend serving
# ---------------------------------------------------------------------------

WEB_DIR = os.path.join(os.path.dirname(__file__), "..", "web")


@app.get("/")
def serve_index():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


# Mount static files last so API routes take priority
if os.path.isdir(WEB_DIR):
    app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")
