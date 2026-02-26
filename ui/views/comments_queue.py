"""
Comments Queue page.

Search LinkedIn by topic filters, generate comments,
build voice profile from past comments over time.
"""

import streamlit as st
from typing import Optional

from src.core.config_manager import AIConfig, LinkedInConfig
from src.database.crud import CommentCRUD, PostCRUD, FeedItemCRUD, SearchFeedbackCRUD
from ui.components.editor import render_editor

# Predefined topic filters for LinkedIn search
TOPIC_FILTERS = {
    "GenAI": ["generative AI", "GenAI applications", "GenAI enterprise"],
    "LLM": ["large language models", "LLM deployment", "LLM fine-tuning"],
    "AI Agents": ["AI agents", "agentic AI", "autonomous agents"],
    "MLOps": ["MLOps", "ML infrastructure", "model deployment"],
    "AI Strategy": ["AI strategy", "AI transformation", "enterprise AI"],
    "Computer Vision": ["computer vision", "image recognition", "multimodal AI"],
    "Data Engineering": ["data engineering", "data pipeline", "data platform"],
    "AI Ethics": ["responsible AI", "AI ethics", "AI governance"],
}


def render_comments_queue(
    comment_crud: CommentCRUD,
    post_crud: Optional[PostCRUD] = None,
    feed_crud: Optional[FeedItemCRUD] = None,
    ai_config: Optional[AIConfig] = None,
    linkedin_config: Optional[LinkedInConfig] = None,
    search_feedback_crud: Optional[SearchFeedbackCRUD] = None,
):
    st.header("Comments")

    tab_generate, tab_queue = st.tabs(["Generate Comments", "Review Queue"])

    with tab_generate:
        _render_generate_tab(comment_crud, ai_config, linkedin_config, search_feedback_crud)

    with tab_queue:
        _render_queue_tab(comment_crud, linkedin_config)


# ---------------------------------------------------------------------------
# Generate tab
# ---------------------------------------------------------------------------
def _render_generate_tab(
    comment_crud: CommentCRUD,
    ai_config: Optional[AIConfig],
    linkedin_config: Optional[LinkedInConfig],
    search_feedback_crud: Optional[SearchFeedbackCRUD],
):
    total_comments = comment_crud.count_total()

    # Show context source info
    if total_comments > 0:
        past_comments = comment_crud.get_recent(limit=20)
        with st.expander(f"Your previous comments used as voice context ({min(total_comments, 20)})", expanded=False):
            for c in past_comments[:5]:
                st.caption(f"- {c['comment_content'][:100]}...")
    else:
        st.info("No comments yet. Your first comments will establish your voice. Future comments will match that style automatically.")

    st.divider()

    # --- Topic filter search ---
    st.markdown("##### Find posts to comment on")
    _render_topic_search(
        comment_crud=comment_crud,
        ai_config=ai_config,
        linkedin_config=linkedin_config,
        search_feedback_crud=search_feedback_crud,
    )


# ---------------------------------------------------------------------------
# Topic-based search: pick topics -> search LinkedIn -> rank -> generate
# ---------------------------------------------------------------------------
def _render_topic_search(
    comment_crud: CommentCRUD,
    ai_config: Optional[AIConfig],
    linkedin_config: Optional[LinkedInConfig],
    search_feedback_crud: Optional[SearchFeedbackCRUD] = None,
):
    if not ai_config:
        st.warning("AI config not available.")
        return

    # Topic selection
    selected_topics = st.multiselect(
        "Select topics",
        list(TOPIC_FILTERS.keys()),
        default=["GenAI", "LLM"],
        key="comment_topics",
    )

    # Optional custom query
    custom_query = st.text_input(
        "Or add a custom search term",
        placeholder="e.g. RAG pipeline, AI in healthcare",
        key="custom_search_query",
    )

    if st.button("Find posts to comment on", type="primary", use_container_width=True, key="smart_search_btn"):
        queries = []
        for topic in selected_topics:
            queries.extend(TOPIC_FILTERS[topic])
        if custom_query.strip():
            queries.append(custom_query.strip())
        if not queries:
            st.warning("Select at least one topic or enter a custom search term.")
            return
        _run_topic_search(queries, ai_config, linkedin_config, comment_crud)

    # Show ranked results
    ranked = st.session_state.get("smart_search_ranked", [])
    if not ranked:
        st.caption("Select topics above and click the button. The system will search LinkedIn and rank results by commenting potential.")
        return

    st.success(f"Found {len(ranked)} posts. Select posts to generate comments for:")

    # Initialize selection state
    if "smart_selections" not in st.session_state:
        st.session_state.smart_selections = {}

    # Select/deselect all
    col_all, col_none, col_count = st.columns([1, 1, 2])
    with col_all:
        if st.button("Select All", key="smart_sel_all"):
            st.session_state.smart_selections = {i: True for i in range(len(ranked))}
            st.rerun()
    with col_none:
        if st.button("Deselect All", key="smart_desel_all"):
            st.session_state.smart_selections = {}
            st.rerun()
    with col_count:
        n_selected = sum(1 for v in st.session_state.smart_selections.values() if v)
        st.caption(f"{n_selected} / {len(ranked)} selected")

    # Render each result with a checkbox
    for i, item in enumerate(ranked):
        with st.container(border=True):
            col_check, col_info, col_score = st.columns([0.5, 4, 1])
            with col_check:
                checked = st.checkbox(
                    "sel",
                    value=st.session_state.smart_selections.get(i, False),
                    key=f"smart_chk_{i}",
                    label_visibility="collapsed",
                )
                st.session_state.smart_selections[i] = checked
            with col_info:
                st.markdown(f"**{item['author']}**")
                st.text(item["content"][:300])
                if item.get("url"):
                    st.caption(item["url"])
            with col_score:
                score = item.get("relevance_score", 0)
                color = "green" if score >= 8 else "orange" if score >= 6 else "gray"
                st.markdown(f":{color}[**{score}/10**]")
                if item.get("reason"):
                    st.caption(item["reason"])

    # --- Generate button for selected posts ---
    selections = st.session_state.get("smart_selections", {})
    selected_posts = [ranked[i] for i, v in selections.items() if v and i < len(ranked)]
    selected_indices = {i for i, v in selections.items() if v and i < len(ranked)}

    if selected_posts:
        st.divider()
        if st.button(
            f"Generate Comments for {len(selected_posts)} Selected Posts",
            type="primary",
            use_container_width=True,
            key="batch_generate_btn",
        ):
            # Store selection feedback
            if search_feedback_crud:
                queries = st.session_state.get("smart_search_queries", [])
                search_feedback_crud.record_batch(
                    search_queries=queries,
                    ranked_results=ranked,
                    selected_indices=selected_indices,
                )

            # Use past comments as context (not past posts)
            past_comments = comment_crud.get_recent(limit=20)

            _batch_generate_comments(
                selected_posts=selected_posts,
                past_comments=past_comments,
                comment_crud=comment_crud,
                ai_config=ai_config,
            )
    else:
        st.divider()
        st.caption("Select one or more posts above, then click Generate.")


def _run_topic_search(
    queries: list[str],
    ai_config: AIConfig,
    linkedin_config: Optional[LinkedInConfig],
    comment_crud: Optional[CommentCRUD] = None,
):
    """Search LinkedIn with topic queries and rank results."""
    with st.status("Searching...", expanded=True) as status:
        try:
            from src.content.generator import create_ai_provider
            from src.content.prompts import RANK_SEARCH_RESULTS_PROMPT

            ai = create_ai_provider(ai_config)

            # Store queries for feedback
            st.session_state.smart_search_queries = queries
            st.write(f"Searching for: **{', '.join(queries[:5])}**" + (f" (+{len(queries)-5} more)" if len(queries) > 5 else ""))

            # Search LinkedIn
            if not linkedin_config or not linkedin_config.email:
                st.error("LinkedIn credentials needed for search.")
                return

            import asyncio
            from src.automation.session_manager import LinkedInSession
            from src.automation.linkedin_bot import LinkedInBot
            from src.core.safety_monitor import SafetyMonitor

            st.write("Searching LinkedIn...")

            async def _do_searches():
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
                    all_results = []
                    seen_urls = set()
                    # Use at most 5 queries to avoid too many requests
                    for query in queries[:5]:
                        results = await bot.search_posts(query, max_results=5)
                        for r in results:
                            if r.content and r.url not in seen_urls:
                                all_results.append(r)
                                seen_urls.add(r.url)
                        await session.wait(1)
                    return all_results

            raw_results = asyncio.run(_do_searches())
            st.write(f"Found **{len(raw_results)}** posts via LinkedIn")

            # Google fallback
            if not raw_results:
                st.write("Trying Google fallback...")
                from src.automation.linkedin_bot import search_linkedin_via_google

                for query in queries[:5]:
                    google_results = search_linkedin_via_google(query, max_results=10)
                    for r in google_results:
                        raw_results.append(r)

                seen = set()
                deduped = []
                for r in raw_results:
                    key = r.url or r.content[:80]
                    if key not in seen:
                        seen.add(key)
                        deduped.append(r)
                raw_results = deduped
                st.write(f"Google fallback found **{len(raw_results)}** posts")

            if not raw_results:
                status.update(label="No posts found", state="error")
                return

            # Build expertise context from past comments (not posts)
            expertise_summary = "GenAI and AI technology professional"
            if comment_crud:
                past_comments = comment_crud.get_recent(limit=10)
                if past_comments:
                    expertise_summary = "\n".join(
                        f"- {c['comment_content'][:150]}" for c in past_comments[:5]
                    )

            # Rank with LLM
            st.write("Ranking posts by commenting potential...")
            posts_list = "\n\n".join(
                f"[{i}] {r.author} (posted: {r.published_at or 'unknown'}): {r.content[:200]}"
                for i, r in enumerate(raw_results)
            )
            rank_result = ai.generate_fast(
                "You rank LinkedIn posts by relevance. Follow the format exactly.",
                RANK_SEARCH_RESULTS_PROMPT.format(
                    expertise_summary=expertise_summary,
                    posts_list=posts_list,
                ),
            )

            # Parse ranking
            ranked = []
            if "NONE" in rank_result.content.upper():
                st.info("No posts worth commenting on found. Try different topics.")
            else:
                blocks = rank_result.content.split("---")
                for block in blocks:
                    block = block.strip()
                    if not block:
                        continue
                    idx = None
                    score = 0
                    reason = ""
                    for line in block.split("\n"):
                        line = line.strip()
                        if line.upper().startswith("INDEX:"):
                            try:
                                idx = int(line.split(":", 1)[1].strip())
                            except ValueError:
                                pass
                        elif line.upper().startswith("SCORE:"):
                            try:
                                score = int(line.split(":", 1)[1].strip())
                            except ValueError:
                                pass
                        elif line.upper().startswith("REASON:"):
                            reason = line.split(":", 1)[1].strip()
                    if idx is not None and 0 <= idx < len(raw_results):
                        r = raw_results[idx]
                        ranked.append({
                            "author": r.author,
                            "content": r.content,
                            "url": r.url,
                            "published_at": r.published_at,
                            "relevance_score": score,
                            "reason": reason,
                        })

            ranked.sort(key=lambda x: x["relevance_score"], reverse=True)
            st.session_state.smart_search_ranked = ranked
            st.session_state.smart_selections = {}

            status.update(label=f"Found {len(ranked)} posts to comment on!", state="complete")
            st.rerun()

        except Exception as e:
            status.update(label="Search failed", state="error")
            st.error(f"Error: {e}")
            import traceback
            st.code(traceback.format_exc())


def _batch_generate_comments(
    selected_posts: list[dict],
    past_comments: list[dict],
    comment_crud: CommentCRUD,
    ai_config: AIConfig,
):
    """Generate comments for multiple selected posts in batch."""
    with st.status(f"Generating comments for {len(selected_posts)} posts...", expanded=True) as status:
        try:
            from src.content.generator import create_ai_provider
            from src.content.prompts import COMMENT_SYSTEM_PROMPT, COMMENT_TEMPLATES

            ai = create_ai_provider(ai_config)

            # Build context from past comments
            past_context = ""
            if past_comments:
                snippets = [f"- {c['comment_content'][:200]}" for c in past_comments[:10]]
                past_context = "Your previous LinkedIn comments:\n" + "\n".join(snippets)

            strategy = "grounded" if past_context else "generic"
            template = COMMENT_TEMPLATES[strategy]
            generated = 0

            for i, post in enumerate(selected_posts):
                st.write(f"[{i+1}/{len(selected_posts)}] Generating for: {post['author'][:30]} - {post['content'][:50]}...")

                user_prompt = template.format(
                    author=post.get("author", "Unknown"),
                    post_content=post.get("content", "")[:1500],
                    past_context=past_context,
                    rag_context="",
                )

                result = ai.generate_with_confidence(COMMENT_SYSTEM_PROMPT, user_prompt)

                comment_crud.create(
                    target_post_url=post.get("url", ""),
                    comment_content=result.content,
                    target_post_author=post.get("author", ""),
                    target_post_content=post.get("content", "")[:500],
                    strategy=strategy,
                    confidence=result.confidence or 0.5,
                )
                generated += 1

            status.update(label=f"Generated {generated} comments! Go to Review Queue.", state="complete")
            st.session_state.smart_selections = {}
            st.rerun()

        except Exception as e:
            status.update(label="Batch generation failed", state="error")
            st.error(f"Error: {e}")
            import traceback
            st.code(traceback.format_exc())


# ---------------------------------------------------------------------------
# Queue tab
# ---------------------------------------------------------------------------
def _render_queue_tab(
    comment_crud: CommentCRUD,
    linkedin_config: Optional[LinkedInConfig],
):
    if "editing_comment" in st.session_state:
        comment = comment_crud.get(st.session_state.editing_comment)
        if comment:
            render_editor(
                content=comment["comment_content"],
                item_id=comment["id"],
                item_type="comment",
                on_save=lambda cid, content: (
                    comment_crud.update_content(cid, content),
                    st.session_state.pop("editing_comment", None),
                ),
            )
            return

    status_filter = st.selectbox(
        "Filter by status",
        ["draft", "approved", "published", "rejected"],
        index=0,
        key="comments_status_filter",
    )

    comments = comment_crud.list_by_status(status_filter)

    if not comments:
        st.info(f"No {status_filter} comments found.")
        return

    st.caption(f"Showing {len(comments)} {status_filter} comments")

    # Batch action buttons
    if status_filter == "draft" and comments:
        if st.button("Approve All Drafts", key="approve_all_drafts", type="primary"):
            for c in comments:
                comment_crud.update_status(c["id"], "approved")
            st.rerun()

    if status_filter == "approved" and comments:
        publishable = [c for c in comments if c.get("target_post_url")]
        if publishable:
            if st.button(
                f"Publish All Approved ({len(publishable)})",
                key="publish_all_approved",
                type="primary",
            ):
                _batch_publish_comments(publishable, comment_crud, linkedin_config)
        else:
            st.caption("No approved comments have a target URL to publish to.")

    for comment in comments:
        _render_comment_card(comment, comment_crud, linkedin_config)


def _render_comment_card(
    comment: dict,
    comment_crud: CommentCRUD,
    linkedin_config: Optional[LinkedInConfig],
):
    with st.container(border=True):
        col_meta, col_status = st.columns([3, 1])
        with col_meta:
            st.caption(
                f"Strategy: **{comment.get('strategy', 'N/A')}** | "
                f"Confidence: **{comment.get('confidence', 0):.0%}** | "
                f"Created: {comment.get('created_at', 'N/A')}"
            )
        with col_status:
            status = comment.get("status", "draft")
            color = {
                "draft": "blue", "approved": "green",
                "published": "violet", "rejected": "red",
            }.get(status, "gray")
            st.markdown(f":{color}[{status.upper()}]")

        if comment.get("target_post_content"):
            with st.expander("Target Post"):
                st.caption(f"By: {comment.get('target_post_author', 'Unknown')}")
                st.text(comment["target_post_content"][:300])
                if comment.get("target_post_url"):
                    st.caption(comment["target_post_url"])

        st.markdown(f"**Comment:** {comment.get('comment_content', '')}")

        if status == "draft":
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("Approve", key=f"ac_{comment['id']}", type="primary"):
                    comment_crud.update_status(comment["id"], "approved")
                    st.rerun()
            with col2:
                if st.button("Reject", key=f"rc_{comment['id']}"):
                    comment_crud.update_status(comment["id"], "rejected", reason="Rejected in UI")
                    st.rerun()
            with col3:
                if st.button("Edit", key=f"ec_{comment['id']}"):
                    st.session_state.editing_comment = comment["id"]
                    st.rerun()

        elif status == "approved":
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("Publish to LinkedIn", key=f"pc_{comment['id']}", type="primary"):
                    _publish_comment(comment, comment_crud, linkedin_config)
            with col2:
                if st.button("Edit", key=f"eca_{comment['id']}"):
                    st.session_state.editing_comment = comment["id"]
                    st.rerun()
            with col3:
                if st.button("Reject", key=f"rca_{comment['id']}"):
                    comment_crud.update_status(comment["id"], "rejected", reason="Rejected in UI")
                    st.rerun()

        elif status == "published":
            if st.button("Repost", key=f"repost_c_{comment['id']}"):
                comment_crud.update_status(comment["id"], "approved")
                st.rerun()


def _publish_comment(
    comment: dict,
    comment_crud: CommentCRUD,
    linkedin_config: Optional[LinkedInConfig],
):
    if not linkedin_config or not linkedin_config.email:
        st.error("LinkedIn credentials not configured.")
        return
    if not comment.get("target_post_url"):
        st.error("No target post URL. You need a LinkedIn post URL to comment on.")
        return

    with st.status("Publishing comment...", expanded=True) as status:
        try:
            import asyncio
            from src.automation.session_manager import LinkedInSession
            from src.automation.linkedin_bot import LinkedInBot
            from src.core.safety_monitor import SafetyMonitor

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
                    return await bot.publish_comment(
                        comment["target_post_url"],
                        comment["comment_content"],
                    )

            success = asyncio.run(_do_publish())
            if success:
                comment_crud.update_status(comment["id"], "published")
                status.update(label="Published!", state="complete")
                st.rerun()
            else:
                status.update(label="Failed", state="error")
                st.error("Bot could not publish the comment.")
        except Exception as e:
            status.update(label="Failed", state="error")
            st.error(f"Publish error: {e}")
            import traceback
            st.code(traceback.format_exc())


def _batch_publish_comments(
    comments: list[dict],
    comment_crud: CommentCRUD,
    linkedin_config: Optional[LinkedInConfig],
):
    """Publish multiple approved comments in a single browser session."""
    if not linkedin_config or not linkedin_config.email:
        st.error("LinkedIn credentials not configured.")
        return

    with st.status(f"Publishing {len(comments)} comments...", expanded=True) as status:
        try:
            import asyncio
            from src.automation.session_manager import LinkedInSession
            from src.automation.linkedin_bot import LinkedInBot
            from src.core.safety_monitor import SafetyMonitor

            async def _do_batch():
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
                    published = 0
                    failed = 0
                    for c in comments:
                        try:
                            ok = await bot.publish_comment(
                                c["target_post_url"],
                                c["comment_content"],
                            )
                            if ok:
                                comment_crud.update_status(c["id"], "published")
                                published += 1
                            else:
                                failed += 1
                        except Exception as e:
                            failed += 1
                        await session.wait(3)
                    return published, failed

            published, failed = asyncio.run(_do_batch())
            label = f"Published {published}/{len(comments)} comments"
            if failed:
                label += f" ({failed} failed)"
            status.update(label=label, state="complete" if published > 0 else "error")
            st.rerun()

        except Exception as e:
            status.update(label="Batch publish failed", state="error")
            st.error(f"Error: {e}")
            import traceback
            st.code(traceback.format_exc())
