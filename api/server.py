"""
OpenLinkedIn -- FastAPI REST backend.

Serves the JSON API at /api/* and the web frontend from /web/.
"""

import hmac
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

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
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

from src.core.config_manager import ConfigManager  # noqa: E402
from src.core.safety_monitor import SafetyMonitor  # noqa: E402
from src.database.models import Database  # noqa: E402
from src.database.crud import (  # noqa: E402
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
        if not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], API_TOKEN):
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


class AssetGenerateBody(BaseModel):
    prompt: str
    aspect_ratio: Optional[str] = "1:1"
    style: Optional[str] = None


# ---------------------------------------------------------------------------
# LinkedIn publish helper (shared by posts + comments)
# ---------------------------------------------------------------------------


def _get_linkedin_session():
    """Create a LinkedInSession from config. Raises HTTPException if not configured."""
    config: ConfigManager = _get("config")
    lc = config.linkedin
    if not lc.email:
        raise HTTPException(400, "LinkedIn credentials not configured. Set LINKEDIN_EMAIL and LINKEDIN_PASSWORD in .env")
    from src.automation.session_manager import LinkedInSession
    return LinkedInSession(
        email=lc.email,
        password=lc.password,
        headless=lc.headless,
        slow_mo=lc.slow_mo,
        profile_dir=lc.browser_profile_dir,
    )


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
    content_crud: ContentLibraryCRUD = _get("content_crud")
    posts = crud.list_by_status(status, limit=limit)
    # Parse rag_sources JSON strings and resolve source URLs
    for p in posts:
        if p.get("rag_sources") and isinstance(p["rag_sources"], str):
            try:
                p["rag_sources"] = json.loads(p["rag_sources"])
            except (json.JSONDecodeError, TypeError):
                pass
        # Resolve source article URL from rag_sources
        p["source_url"] = None
        if p.get("rag_sources") and isinstance(p["rag_sources"], list) and p["rag_sources"]:
            try:
                doc = content_crud.get(int(p["rag_sources"][0]))
                if doc and doc.get("source"):
                    p["source_url"] = doc["source"]
            except (ValueError, TypeError):
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
    except Exception:
        logger.exception("Request failed")
        raise HTTPException(500, "Internal server error")


@app.post("/api/posts/{post_id}/publish")
async def publish_post(post_id: int):
    """Publish an approved post to LinkedIn via browser automation."""
    post_crud: PostCRUD = _get("post_crud")
    log_crud: InteractionLogCRUD = _get("log_crud")
    content_crud: ContentLibraryCRUD = _get("content_crud")

    post = post_crud.get(post_id)
    if not post:
        raise HTTPException(404, "Post not found")
    if post["status"] != "approved":
        raise HTTPException(400, "Post must be approved before publishing")

    session = _get_linkedin_session()

    # Look up source URL for first-comment
    source_url = None
    if post.get("rag_sources"):
        try:
            import json as _json
            sources = _json.loads(post["rag_sources"]) if isinstance(post["rag_sources"], str) else post["rag_sources"]
            if sources and isinstance(sources, list):
                doc = content_crud.get(int(sources[0]))
                if doc and doc.get("source"):
                    source_url = doc["source"]
        except (ValueError, TypeError):
            pass

    try:
        import asyncio
        from src.automation.linkedin_bot import LinkedInBot
        from src.core.safety_monitor import SafetyMonitor

        async def _do():
            async with session:
                bot = LinkedInBot(session, safety_monitor=SafetyMonitor(
                    hourly_limit=100, daily_limit=100, weekly_limit=500,
                ))
                await bot.login()
                asset = post.get("asset_path") or ""
                if asset and not os.path.exists(asset):
                    asset = ""
                post_content = post["content"]
                if source_url:
                    post_content += f"\n\n{source_url}"
                published = await bot.publish_post(post_content, asset_path=asset)
                if not published:
                    return False, None
                post_url = await bot.get_my_latest_post_url()
                if source_url:
                    comment_text = f"Source article: {source_url}"
                    await session.wait(5)
                    if post_url:
                        commented = await bot.publish_comment(post_url, comment_text)
                    else:
                        commented = await bot.comment_on_own_latest_post(comment_text)
                    if not commented:
                        logger.warning("Failed to post source comment for post #%s", post_id)
                return True, post_url

        success, post_url = await asyncio.to_thread(asyncio.run, _do())
        if success:
            post_crud.update_status(post_id, "published")
            if post_url:
                post_crud.set_linkedin_url(post_id, post_url)
            detail = f"Post #{post_id} published via web UI"
            if source_url:
                detail += " + source link comment"
            log_crud.log("publish_post", details=detail)
            return {"ok": True, "linkedin_url": post_url}
        else:
            raise HTTPException(502, "Publishing failed. Check browser for CAPTCHA or errors.")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Request failed")
        raise HTTPException(500, "Internal server error")


@app.post("/api/posts/{post_id}/asset/generate-image")
def generate_post_image(post_id: int, body: AssetGenerateBody):
    """Generate an image with Imagen and attach to post."""
    config: ConfigManager = _get("config")
    post_crud: PostCRUD = _get("post_crud")
    vc = config.vertex_ai
    if not vc.project_id:
        raise HTTPException(400, "Set GCP_PROJECT_ID in .env to enable Vertex AI")
    prompt = body.prompt
    if body.style:
        prompt = f"{prompt}. Render in the visual style of {body.style}."
    try:
        from src.content.asset_generator import AssetGenerator
        gen = AssetGenerator(
            project_id=vc.project_id,
            location=vc.location,
            imagen_model=vc.imagen_model,
        )
        path = gen.generate_image(prompt, aspect_ratio=body.aspect_ratio or "1:1")
        post_crud.set_asset(post_id, path, "image")
        return {"ok": True, "path": path, "type": "image"}
    except Exception:
        logger.exception("Request failed")
        raise HTTPException(500, "Internal server error")


@app.post("/api/posts/{post_id}/asset/generate-video")
def generate_post_video(post_id: int, body: AssetGenerateBody):
    """Generate a video with Veo and attach to post."""
    config: ConfigManager = _get("config")
    post_crud: PostCRUD = _get("post_crud")
    vc = config.vertex_ai
    if not vc.project_id:
        raise HTTPException(400, "Set GCP_PROJECT_ID in .env to enable Vertex AI")
    try:
        from src.content.asset_generator import AssetGenerator
        gen = AssetGenerator(
            project_id=vc.project_id,
            location=vc.location,
            veo_model=vc.veo_model,
        )
        path = gen.generate_video(body.prompt, aspect_ratio=body.aspect_ratio or "16:9")
        post_crud.set_asset(post_id, path, "video")
        return {"ok": True, "path": path, "type": "video"}
    except Exception:
        logger.exception("Request failed")
        raise HTTPException(500, "Internal server error")


@app.delete("/api/posts/{post_id}/asset")
def remove_post_asset(post_id: int):
    post_crud: PostCRUD = _get("post_crud")
    post_crud.clear_asset(post_id)
    return {"ok": True}


class AssetPromptBody(BaseModel):
    style: Optional[str] = None


@app.post("/api/posts/{post_id}/generate-asset-prompt")
def generate_asset_prompt(post_id: int, body: AssetPromptBody = AssetPromptBody()):
    """Use the fast model (nano) to generate an Imagen/Veo prompt from post content."""
    config: ConfigManager = _get("config")
    post_crud: PostCRUD = _get("post_crud")

    post = post_crud.get(post_id)
    if not post:
        raise HTTPException(404, "Post not found")

    style_instruction = ""
    if body.style:
        style_instruction = (
            f" The image MUST be rendered in the distinctive visual style of {body.style} — "
            f"adopt their palette, brushwork, composition, and artistic sensibility. "
            f"Make the style unmistakable while keeping the content professional."
        )

    try:
        from src.content.generator import create_ai_provider

        ai = create_ai_provider(config.ai)
        result = ai.generate_fast(
            "You are a visual prompt engineer for Nano Banana / Gemini image models. "
            "Generate a narrative scene description — NOT a keyword list. "
            "Start with a strong verb (Generate, Create, Photograph, Render). "
            "Follow this formula: [Subject] + [Action/Pose] + [Location/Context] + [Composition] + [Style/Lighting]. "
            "Use positive framing — describe what IS in the scene, never what isn't (e.g. 'empty street' not 'no cars'). "
            "Control the camera: specify camera type (e.g. Fujifilm for authentic color science), "
            "lens, angle, depth of field (e.g. 'low-angle shot, shallow depth of field f/1.8, wide-angle lens'). "
            "Design the lighting explicitly (e.g. 'three-point softbox setup', 'golden hour backlighting', "
            "'chiaroscuro lighting with harsh high contrast'). "
            "Define color grading and film stock (e.g. 'cinematic muted teal tones', 'shot on medium-format analog film, pronounced grain'). "
            "Emphasize materiality and texture of objects (e.g. 'brushed aluminum', 'navy blue tweed', 'minimalist ceramic'). "
            "If text appears in the image, enclose exact words in quotes and specify font style. "
            "The result must look like a Fortune 500 corporate presentation or top-tier business publication. "
            "Clean, modern, executive-level aesthetic. No cartoons, clip-art, or stock-photo cliches."
            f"{style_instruction} "
            "Output ONLY the prompt, nothing else. Keep it under 120 words.",
            f"Generate a visual prompt for this LinkedIn post:\n\n{post['content'][:1500]}",
        )
        return {"prompt": result.content, "model": result.model}
    except Exception:
        logger.exception("Request failed")
        raise HTTPException(500, "Internal server error")


@app.post("/api/posts/{post_id}/asset/upload")
async def upload_post_asset(post_id: int, request: Request):
    """Upload an image or video file and attach to post."""
    post_crud: PostCRUD = _get("post_crud")

    post = post_crud.get(post_id)
    if not post:
        raise HTTPException(404, "Post not found")

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        raise HTTPException(400, "Expected multipart/form-data")

    try:
        form = await request.form()
        file = form.get("file")
        if not file:
            raise HTTPException(400, "No file uploaded")

        filename = file.filename or "upload"
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ("png", "jpg", "jpeg", "mp4", "webp"):
            raise HTTPException(400, "Supported formats: png, jpg, jpeg, mp4, webp")

        asset_type = "video" if ext == "mp4" else "image"
        os.makedirs("data/assets", exist_ok=True)
        save_path = f"data/assets/post_{post_id}.{ext}"

        content = await file.read()
        with open(save_path, "wb") as f:
            f.write(content)

        post_crud.set_asset(post_id, save_path, asset_type)
        return {"ok": True, "path": save_path, "type": asset_type}
    except HTTPException:
        raise
    except Exception:
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


@app.post("/api/comments/reject-all")
def reject_all_comments():
    """Reject all draft + approved comments in one call."""
    crud: CommentCRUD = _get("comment_crud")
    log_crud: InteractionLogCRUD = _get("log_crud")
    count = crud.reject_all()
    log_crud.log("reject_all_comments", details=f"Rejected {count} comments")
    return {"rejected": count}


@app.get("/api/comments/ranked")
def list_ranked_comments(limit: int = Query(default=50, ge=1, le=500)):
    """Return draft + approved comments ranked by target post relevance score."""
    crud: CommentCRUD = _get("comment_crud")

    drafts = crud.list_by_status("draft", limit=limit)
    approved = crud.list_by_status("approved", limit=limit)
    comments = drafts + approved

    try:
        from src.content.content_filter import ContentFilter
        content_filter = ContentFilter(min_score_threshold=0)

        for c in comments:
            if c.get("target_post_content"):
                scored = content_filter.score(
                    title="",
                    content=c["target_post_content"],
                    author=c.get("target_post_author") or "",
                    published_at=c.get("created_at"),
                )
                c["relevance_score"] = scored.final_score
            else:
                c["relevance_score"] = 0.0

        comments.sort(key=lambda c: c["relevance_score"], reverse=True)
    except Exception:
        logger.exception("Failed to score comments, returning unsorted")
        for c in comments:
            c["relevance_score"] = 0.0

    return comments[:limit]


@app.post("/api/comments/approve-all")
def approve_all_draft_comments():
    crud: CommentCRUD = _get("comment_crud")
    drafts = crud.list_by_status("draft")
    for c in drafts:
        crud.update_status(c["id"], "approved")
    return {"ok": True, "count": len(drafts)}


@app.post("/api/comments/regenerate-drafts")
def regenerate_draft_comments():
    """Regenerate all draft and approved comments using the current prompt."""
    config: ConfigManager = _get("config")
    crud: CommentCRUD = _get("comment_crud")
    log_crud: InteractionLogCRUD = _get("log_crud")

    try:
        from src.content.generator import create_ai_provider
        from src.content.comment_generator import CommentGenerator

        ai = create_ai_provider(config.ai)
        generator = CommentGenerator(ai_provider=ai)

        # Gather draft + approved comments that have target post content
        drafts = crud.list_by_status("draft")
        approved = crud.list_by_status("approved")
        to_regenerate = [
            c for c in drafts + approved
            if c.get("target_post_content")
        ]

        if not to_regenerate:
            return {"ok": True, "regenerated": 0, "message": "No comments with target post content to regenerate"}

        # Use recent published comments for voice matching
        past_comments = [
            c for c in crud.get_recent(limit=20)
            if c.get("status") == "published"
        ]

        regenerated = 0
        for comment in to_regenerate:
            result = generator.generate(
                post_content=comment["target_post_content"],
                post_author=comment.get("target_post_author") or "Unknown",
                post_url=comment.get("target_post_url") or "",
                past_comments=past_comments,
            )
            crud.update_content(comment["id"], result["content"])
            regenerated += 1

        log_crud.log("regenerate_comments", details=f"Regenerated {regenerated} comments")
        return {"ok": True, "regenerated": regenerated}
    except Exception:
        logger.exception("Request failed")
        raise HTTPException(500, "Internal server error")


@app.post("/api/comments/{comment_id}/publish")
async def publish_comment(comment_id: int):
    """Publish a single approved comment to LinkedIn."""
    crud: CommentCRUD = _get("comment_crud")
    log_crud: InteractionLogCRUD = _get("log_crud")

    comment = crud.get(comment_id)
    if not comment:
        raise HTTPException(404, "Comment not found")
    if comment["status"] != "approved":
        raise HTTPException(400, "Comment must be approved before publishing")
    if not comment.get("target_post_url"):
        raise HTTPException(400, "No target post URL")

    session = _get_linkedin_session()

    try:
        import asyncio
        from src.automation.linkedin_bot import LinkedInBot
        from src.core.safety_monitor import SafetyMonitor

        async def _do():
            async with session:
                bot = LinkedInBot(session, safety_monitor=SafetyMonitor(
                    hourly_limit=100, daily_limit=100, weekly_limit=500,
                ))
                await bot.login()
                return await bot.publish_comment(
                    comment["target_post_url"],
                    comment["comment_content"],
                )

        success = await asyncio.to_thread(asyncio.run, _do())
        if success:
            crud.update_status(comment_id, "published")
            log_crud.log("publish_comment", details=f"Comment #{comment_id} published via web UI")
            return {"ok": True}
        else:
            raise HTTPException(502, "Publishing failed. Check browser for CAPTCHA or errors.")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Request failed")
        raise HTTPException(500, "Internal server error")


@app.post("/api/comments/publish-approved")
async def publish_all_approved_comments():
    """Batch publish all approved comments with target URLs in a single browser session."""
    crud: CommentCRUD = _get("comment_crud")
    log_crud: InteractionLogCRUD = _get("log_crud")

    approved = crud.list_by_status("approved")
    publishable = [c for c in approved if c.get("target_post_url")]
    if not publishable:
        return {"ok": True, "published": 0, "failed": 0, "message": "No publishable comments"}

    session = _get_linkedin_session()

    try:
        import asyncio
        from src.automation.linkedin_bot import LinkedInBot
        from src.core.safety_monitor import SafetyMonitor

        async def _do_batch():
            async with session:
                bot = LinkedInBot(session, safety_monitor=SafetyMonitor(
                    hourly_limit=100, daily_limit=100, weekly_limit=500,
                ))
                await bot.login()
                published = 0
                failed = 0
                for c in publishable:
                    try:
                        ok = await bot.publish_comment(
                            c["target_post_url"],
                            c["comment_content"],
                        )
                        if ok:
                            crud.update_status(c["id"], "published")
                            published += 1
                        else:
                            failed += 1
                    except Exception:
                        failed += 1
                    await session.wait(3)
                return published, failed

        published, failed = await asyncio.to_thread(asyncio.run, _do_batch())
        log_crud.log("batch_publish_comments", details=f"{published} published, {failed} failed")
        return {"ok": True, "published": published, "failed": failed}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Request failed")
        raise HTTPException(500, "Internal server error")


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


@app.put("/api/library/{doc_id}/draft")
def update_draft(doc_id: int, body: dict):
    """Save edited draft content back to the library document."""
    crud: ContentLibraryCRUD = _get("content_crud")
    doc = crud.get(doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    content = body.get("content", "")
    if not content:
        raise HTTPException(400, "content is required")
    crud.update_generated_post(doc_id, doc.get("generated_title") or "", content)
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
    except Exception:
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
        # Fetch a larger pool so freshness decay can resurface newer items
        items = feed_crud.get_top_scored(limit=limit * 5, min_score=0)

    feedback_map = feedback_crud.get_feedback_map()

    # Recalculate freshness against current date so scores decay over time
    from datetime import timezone
    from src.utils.helpers import parse_published_date, utc_now

    now = utc_now()

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

        # Live freshness: 6% decay per day after 2-day grace period
        pub = item.get("published_at")
        dt = parse_published_date(pub) if pub else None
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            days_old = max(0.0, (now - dt).total_seconds() / 86400)
            freshness = round(min(1.0, max(0.1, 1.0 - max(0, days_old - 2) * 0.06)), 4)
        else:
            freshness = 1.0
        item["freshness_multiplier"] = freshness
        # Apply freshness decay to the stored final_score (may be ML-based or rule-based)
        item["final_score"] = round((item.get("final_score", 0) or 0) * freshness, 2)

    # Re-sort by live score, then apply limit and min_score filter
    items.sort(key=lambda x: x.get("final_score", 0), reverse=True)
    if min_score > 0:
        items = [i for i in items if i.get("final_score", 0) >= min_score]
    items = items[:limit]

    return items


@app.get("/api/feed/sources")
def feed_source_counts():
    feed_crud: FeedItemCRUD = _get("feed_crud")
    return feed_crud.count_by_source()


@app.post("/api/feed/topics")
def extract_research_topics(
    max_topics: int = Query(default=5, ge=1, le=10),
):
    """Extract search topics from published posts and liked items."""
    from src.content.news_agent import extract_topics

    config = _get("config")
    db = _get("db")

    try:
        topics = extract_topics(db, config, n=max_topics)
        return {"topics": topics}
    except Exception:
        logger.exception("Topic extraction failed")
        raise HTTPException(500, "Internal server error")


class ResearchRequest(BaseModel):
    topics: list[str]
    sources: list[str] | None = None


import threading as _threading  # noqa: E402
_research_lock = _threading.Lock()


@app.post("/api/feed/research")
def research_news(body: ResearchRequest):
    """Run agentic news research for the given topics."""
    import threading

    from src.content.news_agent import run_research

    if not body.topics:
        raise HTTPException(400, "topics list cannot be empty")

    if not _research_lock.acquire(blocking=False):
        raise HTTPException(429, "Research already in progress")

    config = _get("config")

    result_holder: list[dict] = []
    error_holder: list[Exception] = []

    def _run():
        try:
            result = run_research(
                topics=body.topics,
                config=config,
                feed_crud=_get("feed_crud"),
                content_crud=_get("content_crud"),
                sources=body.sources,
            )
            result_holder.append(result)
        except Exception as e:
            error_holder.append(e)

    try:
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=600)  # 10 min max

        if error_holder:
            logger.exception("Research failed: %s", error_holder[0])
            raise HTTPException(500, "Internal server error")
        if not result_holder:
            raise HTTPException(504, "Research timed out")

        return result_holder[0]
    finally:
        _research_lock.release()


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


@app.post("/api/feed/{item_id}/save")
def save_feed_item_to_library(item_id: int):
    """Save a feed item to the content library by its DB id."""
    feed_crud: FeedItemCRUD = _get("feed_crud")
    content_crud: ContentLibraryCRUD = _get("content_crud")
    item = feed_crud.get(item_id)
    if not item:
        raise HTTPException(404, "Feed item not found")
    doc_id = content_crud.add(
        title=item["title"],
        content=item.get("content", ""),
        source=item.get("url") or item.get("source_name", ""),
        tags=[item.get("content_type", ""), item.get("source_name", "")],
    )
    return {"id": doc_id}


# ---------------------------------------------------------------------------
# Reranker
# ---------------------------------------------------------------------------


@app.post("/api/feed/clear")
def clear_feed_items():
    """Delete all feed items and their feedback. Preserves content library."""
    db: Database = _get("db")
    try:
        with db.connect() as conn:
            conn.execute("DELETE FROM user_feedback")
            conn.execute("DELETE FROM feed_items")
        logger.info("Cleared all feed items and feedback")
        return {"status": "cleared"}
    except Exception:
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
    if ai.provider == "vertexai":
        model = ai.vertexai.model
        key_status = "Configured" if ai.vertexai.project_id else "Not set"
    elif ai.provider == "anthropic":
        model = ai.anthropic.model
        key_status = "Configured" if ai.anthropic.api_key and len(ai.anthropic.api_key) > 4 else "Not set"
    else:
        model = ai.openai.model
        key_status = "Configured" if ai.openai.api_key and len(ai.openai.api_key) > 4 else "Not set"

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


@app.get("/favicon.ico")
def favicon():
    path = os.path.join(WEB_DIR, "favicon.ico")
    if os.path.isfile(path):
        return FileResponse(path)
    from fastapi.responses import Response
    return Response(status_code=204)


# Mount static files last so API routes take priority
if os.path.isdir(WEB_DIR):
    app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")

# Serve generated assets (images/videos)
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)
app.mount("/api/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
