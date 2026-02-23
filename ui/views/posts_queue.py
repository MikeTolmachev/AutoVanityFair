"""
Posts Queue page.

Review, approve, edit, reject, publish, and repost generated posts.
After publishing, optionally posts a first comment with the source article link.
"""

import json
import streamlit as st
from typing import Optional

from src.core.config_manager import LinkedInConfig
from src.database.crud import PostCRUD, InteractionLogCRUD, ContentLibraryCRUD
from ui.components.editor import render_editor


def render_posts_queue(
    post_crud: PostCRUD,
    log_crud: Optional[InteractionLogCRUD] = None,
    linkedin_config: Optional[LinkedInConfig] = None,
    content_crud: Optional[ContentLibraryCRUD] = None,
):
    st.header("Posts Queue")

    # Check for edit mode
    if "editing_post" in st.session_state:
        post = post_crud.get(st.session_state.editing_post)
        if post:
            render_editor(
                content=post["content"],
                item_id=post["id"],
                item_type="post",
                on_save=lambda pid, content: (
                    post_crud.update_content(pid, content),
                    st.session_state.pop("editing_post", None),
                ),
            )
            return

    # Status filter
    status_filter = st.selectbox(
        "Filter by status",
        ["draft", "approved", "published", "rejected"],
        index=0,
        key="posts_status_filter",
    )

    posts = post_crud.list_by_status(status_filter)

    if not posts:
        st.info(f"No {status_filter} posts found.")
        return

    st.caption(f"Showing {len(posts)} {status_filter} posts")

    for post in posts:
        _render_post_card(post, post_crud, log_crud, linkedin_config, content_crud)


def _render_post_card(
    post: dict,
    post_crud: PostCRUD,
    log_crud: Optional[InteractionLogCRUD],
    linkedin_config: Optional[LinkedInConfig],
    content_crud: Optional[ContentLibraryCRUD],
):
    with st.container(border=True):
        col_meta, col_status = st.columns([3, 1])
        with col_meta:
            st.caption(
                f"Strategy: **{post.get('strategy', 'N/A')}** | "
                f"Created: {post.get('created_at', 'N/A')}"
            )
        with col_status:
            status = post.get("status", "draft")
            color = {
                "draft": "blue", "approved": "green",
                "published": "violet", "rejected": "red",
            }.get(status, "gray")
            st.markdown(f":{color}[{status.upper()}]")

        st.markdown(post.get("content", ""))
        st.caption(f"{len(post.get('content', ''))} characters")

        # Show source article link if available
        source_url = _get_source_url(post, content_crud)
        if source_url:
            st.caption(f"Source: {source_url}")

        if post.get("rag_sources"):
            with st.expander("RAG Sources"):
                st.text(post["rag_sources"])

        # --- Actions based on status ---
        if status == "draft":
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("Approve", key=f"approve_{post['id']}", type="primary"):
                    post_crud.update_status(post["id"], "approved")
                    st.rerun()
            with col2:
                if st.button("Reject", key=f"reject_{post['id']}"):
                    post_crud.update_status(post["id"], "rejected", reason="Rejected in UI")
                    st.rerun()
            with col3:
                if st.button("Edit", key=f"edit_{post['id']}"):
                    st.session_state.editing_post = post["id"]
                    st.rerun()

        elif status == "approved":
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button(
                    "Publish to LinkedIn",
                    key=f"publish_{post['id']}",
                    type="primary",
                ):
                    _publish_post(post, post_crud, log_crud, linkedin_config, content_crud)
            with col2:
                if st.button("Edit", key=f"edit_approved_{post['id']}"):
                    st.session_state.editing_post = post["id"]
                    st.rerun()
            with col3:
                if st.button("Reject", key=f"reject_approved_{post['id']}"):
                    post_crud.update_status(post["id"], "rejected", reason="Rejected in UI")
                    st.rerun()

        elif status == "published":
            col1, col2 = st.columns([1, 3])
            with col1:
                if st.button("Repost", key=f"repost_{post['id']}"):
                    post_crud.update_status(post["id"], "approved")
                    if log_crud:
                        log_crud.log("repost", details=f"Post #{post['id']} reset to approved for reposting")
                    st.rerun()
            with col2:
                published_at = post.get("published_at", "")
                if post.get("linkedin_url"):
                    st.caption(f"Published: {published_at} | [View on LinkedIn]({post['linkedin_url']})")
                else:
                    st.caption(f"Published: {published_at}")

        elif status == "rejected":
            if st.button("Move back to draft", key=f"undraft_{post['id']}"):
                post_crud.update_status(post["id"], "draft")
                st.rerun()


def _get_source_url(post: dict, content_crud: Optional[ContentLibraryCRUD]) -> Optional[str]:
    """Look up the source article URL from the post's rag_sources."""
    if not content_crud or not post.get("rag_sources"):
        return None
    try:
        sources = json.loads(post["rag_sources"])
        if sources and isinstance(sources, list):
            doc = content_crud.get(int(sources[0]))
            if doc and doc.get("source"):
                return doc["source"]
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return None


def _publish_post(
    post: dict,
    post_crud: PostCRUD,
    log_crud: Optional[InteractionLogCRUD],
    linkedin_config: Optional[LinkedInConfig],
    content_crud: Optional[ContentLibraryCRUD],
):
    """Publish post to LinkedIn, then post a first comment with the source link."""
    if not linkedin_config or not linkedin_config.email:
        st.error("LinkedIn credentials not configured. Set LINKEDIN_EMAIL and LINKEDIN_PASSWORD in .env")
        return

    source_url = _get_source_url(post, content_crud)

    with st.status("Publishing to LinkedIn...", expanded=True) as status:
        try:
            import asyncio
            from src.automation.session_manager import LinkedInSession
            from src.automation.linkedin_bot import LinkedInBot
            from src.core.safety_monitor import SafetyMonitor

            st.write(f"Account: **{linkedin_config.email}**")

            async def _do_publish():
                session = LinkedInSession(
                    email=linkedin_config.email,
                    password=linkedin_config.password,
                    headless=linkedin_config.headless,
                    slow_mo=linkedin_config.slow_mo,
                    profile_dir=linkedin_config.browser_profile_dir,
                )
                async with session:
                    bot = LinkedInBot(session, safety_monitor=SafetyMonitor(
                        hourly_limit=100, daily_limit=100, weekly_limit=500,
                    ))
                    await bot.login()
                    published = await bot.publish_post(post["content"])

                    if not published:
                        return False, None

                    # Find the URL of OUR latest post (not someone else's)
                    post_url = await bot.get_my_latest_post_url()

                    # Post first comment with source article link on OUR post
                    if source_url:
                        comment_text = f"Source article: {source_url}"
                        if post_url:
                            await session.wait(2)
                            await bot.publish_comment(post_url, comment_text)
                        else:
                            # Fallback: comment on own latest post without URL
                            await session.wait(2)
                            await bot.comment_on_own_latest_post(comment_text)

                    return True, post_url

            st.write("Launching browser...")
            success, post_url = asyncio.run(_do_publish())

            if success:
                post_crud.update_status(post["id"], "published")
                if post_url:
                    post_crud.set_linkedin_url(post["id"], post_url)
                if log_crud:
                    detail = f"Post #{post['id']} published"
                    if source_url:
                        detail += " + source link comment"
                    log_crud.log("publish_post", details=detail)
                status.update(label="Published!", state="complete")
                st.rerun()
            else:
                status.update(label="Publishing failed", state="error")
                st.error("Bot returned False. Check the browser window for CAPTCHA or error state.")

        except Exception as e:
            status.update(label="Publishing failed", state="error")
            st.error(f"Publish error: {e}")
            import traceback
            st.code(traceback.format_exc())
