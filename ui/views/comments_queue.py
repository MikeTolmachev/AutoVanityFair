"""
Comments Queue page.

Generate comments grounded in past published posts,
search LinkedIn for posts to comment on, review/approve/publish.
"""

import streamlit as st
from typing import Optional

from src.core.config_manager import AIConfig, LinkedInConfig
from src.database.crud import CommentCRUD, PostCRUD, FeedItemCRUD
from ui.components.editor import render_editor


def render_comments_queue(
    comment_crud: CommentCRUD,
    post_crud: Optional[PostCRUD] = None,
    feed_crud: Optional[FeedItemCRUD] = None,
    ai_config: Optional[AIConfig] = None,
    linkedin_config: Optional[LinkedInConfig] = None,
):
    st.header("Comments")

    tab_generate, tab_queue = st.tabs(["Generate Comments", "Review Queue"])

    with tab_generate:
        _render_generate_tab(comment_crud, post_crud, feed_crud, ai_config, linkedin_config)

    with tab_queue:
        _render_queue_tab(comment_crud, linkedin_config)


# ---------------------------------------------------------------------------
# Generate tab
# ---------------------------------------------------------------------------
def _render_generate_tab(
    comment_crud: CommentCRUD,
    post_crud: Optional[PostCRUD],
    feed_crud: Optional[FeedItemCRUD],
    ai_config: Optional[AIConfig],
    linkedin_config: Optional[LinkedInConfig],
):
    # Past published posts as RAG context
    past_posts = []
    if post_crud:
        past_posts = post_crud.list_by_status("published", limit=20)

    if past_posts:
        with st.expander(f"Your published posts used as context ({len(past_posts)})", expanded=False):
            for p in past_posts[:5]:
                st.caption(f"- {p['content'][:100]}...")
    else:
        st.info("No published posts yet. Publish some posts first so the AI can match your voice and expertise.")

    st.divider()

    # --- Source selection ---
    st.markdown("##### Find a post to comment on")
    source_mode = st.radio(
        "Source",
        ["Smart Search", "Manual LinkedIn Search", "From saved feeds", "Paste manually"],
        horizontal=True,
        key="comment_source_mode",
    )

    target_content = ""
    target_author = ""
    target_url = ""

    if source_mode == "Smart Search":
        target_content, target_author, target_url = _render_smart_search(
            past_posts, ai_config, linkedin_config,
        )

    elif source_mode == "Manual LinkedIn Search":
        target_content, target_author, target_url = _render_linkedin_search(linkedin_config)

    elif source_mode == "From saved feeds":
        target_content, target_author, target_url = _render_feed_picker(feed_crud)

    else:  # Manual
        target_author = st.text_input("Post author", key="manual_author")
        target_content = st.text_area("Post content", height=120, key="manual_content")
        target_url = st.text_input("Post URL (LinkedIn URL to comment on)", key="manual_url")

    st.divider()

    if st.button(
        "Generate Comment",
        type="primary",
        use_container_width=True,
        disabled=(not target_content or ai_config is None),
    ):
        _generate_comment(
            target_content=target_content,
            target_author=target_author,
            target_url=target_url,
            past_posts=past_posts,
            comment_crud=comment_crud,
            ai_config=ai_config,
        )


# ---------------------------------------------------------------------------
# Smart Search: LLM extracts keywords -> LinkedIn search -> score & rank
# ---------------------------------------------------------------------------
def _render_smart_search(
    past_posts: list[dict],
    ai_config: Optional[AIConfig],
    linkedin_config: Optional[LinkedInConfig],
) -> tuple[str, str, str]:
    """Auto-generate search queries from past posts, search LinkedIn, rank results."""
    if not past_posts:
        st.warning("Publish some posts first. Smart Search uses your posts to generate search queries.")
        return "", "", ""
    if not ai_config:
        st.warning("AI config not available.")
        return "", "", ""

    if st.button("Find posts to comment on", type="primary", use_container_width=True, key="smart_search_btn"):
        _run_smart_search(past_posts, ai_config, linkedin_config)

    # Show ranked results
    ranked = st.session_state.get("smart_search_ranked", [])
    if not ranked:
        st.caption("Click the button above. The system will: extract keywords from your posts (Nano) -> search LinkedIn -> score & rank results -> show top matches.")
        return "", "", ""

    st.success(f"Found {len(ranked)} posts matching your expertise")

    for i, item in enumerate(ranked):
        with st.container(border=True):
            col_info, col_score = st.columns([4, 1])
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

            if st.button("Select this post", key=f"smart_pick_{i}"):
                st.session_state.smart_selected = item
                st.rerun()

    selected = st.session_state.get("smart_selected")
    if selected:
        return selected["content"], selected["author"], selected.get("url", "")

    return "", "", ""


def _run_smart_search(
    past_posts: list[dict],
    ai_config: AIConfig,
    linkedin_config: Optional[LinkedInConfig],
):
    """Full pipeline: extract queries -> search LinkedIn -> rank."""
    with st.status("Smart Search running...", expanded=True) as status:
        try:
            from src.content.generator import create_ai_provider
            from src.content.prompts import EXTRACT_SEARCH_QUERIES_PROMPT, RANK_SEARCH_RESULTS_PROMPT

            ai = create_ai_provider(ai_config)

            # Step 1: Extract search queries from past posts using fast model
            posts_text = "\n\n".join(
                f"Post {i+1}: {p['content'][:300]}"
                for i, p in enumerate(past_posts[:10])
            )

            st.write("Step 1: Extracting keywords from your posts (fast model)...")
            queries_result = ai.generate_fast(
                "You extract LinkedIn search queries from text. Return only the queries, one per line.",
                EXTRACT_SEARCH_QUERIES_PROMPT.format(posts_text=posts_text),
            )
            queries = [q.strip() for q in queries_result.content.strip().split("\n") if q.strip()]
            queries = queries[:5]
            st.write(f"Generated queries: **{', '.join(queries)}**")

            if not queries:
                status.update(label="No queries generated", state="error")
                return

            # Step 2: Search LinkedIn for each query
            if not linkedin_config or not linkedin_config.email:
                st.error("LinkedIn credentials needed for search.")
                return

            import asyncio
            from src.automation.session_manager import LinkedInSession
            from src.automation.linkedin_bot import LinkedInBot
            from src.core.safety_monitor import SafetyMonitor

            st.write("Step 2: Searching LinkedIn...")

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
                    for query in queries:
                        results = await bot.search_posts(query, max_results=5)
                        for r in results:
                            if r.content and r.url not in seen_urls:
                                all_results.append(r)
                                seen_urls.add(r.url)
                        await session.wait(1)
                    return all_results

            raw_results = asyncio.run(_do_searches())
            st.write(f"Found **{len(raw_results)}** unique posts across {len(queries)} queries")

            if not raw_results:
                status.update(label="No posts found", state="error")
                return

            # Step 3: Rank with LLM
            st.write("Step 3: Ranking posts by relevance to your expertise (fast model)...")
            expertise_summary = "\n".join(
                f"- {p['content'][:150]}" for p in past_posts[:5]
            )
            posts_list = "\n\n".join(
                f"[{i}] {r.author}: {r.content[:200]}"
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
                st.info("LLM found no posts worth commenting on.")
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
                            "relevance_score": score,
                            "reason": reason,
                        })

            ranked.sort(key=lambda x: x["relevance_score"], reverse=True)
            st.session_state.smart_search_ranked = ranked
            st.session_state.pop("smart_selected", None)

            status.update(label=f"Found {len(ranked)} relevant posts!", state="complete")
            st.rerun()

        except Exception as e:
            status.update(label="Smart Search failed", state="error")
            st.error(f"Error: {e}")
            import traceback
            st.code(traceback.format_exc())


def _render_linkedin_search(linkedin_config: Optional[LinkedInConfig]) -> tuple[str, str, str]:
    """Manual LinkedIn search."""
    query = st.text_input(
        "Search LinkedIn posts",
        placeholder="e.g. AI deployment production MLOps",
        key="linkedin_search_query",
    )

    if st.button("Search", key="linkedin_search_btn") and query:
        if not linkedin_config or not linkedin_config.email:
            st.error("LinkedIn credentials not configured.")
            return "", "", ""

        with st.status("Searching LinkedIn...", expanded=True):
            try:
                import asyncio
                from src.automation.session_manager import LinkedInSession
                from src.automation.linkedin_bot import LinkedInBot
                from src.core.safety_monitor import SafetyMonitor

                async def _do_search():
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
                        return await bot.search_posts(query, max_results=10)

                results = asyncio.run(_do_search())
                st.session_state.linkedin_search_results = [
                    {"author": r.author, "content": r.content, "url": r.url}
                    for r in results if r.content
                ]
                st.success(f"Found {len(st.session_state.linkedin_search_results)} posts")
            except Exception as e:
                st.error(f"Search failed: {e}")

    results = st.session_state.get("linkedin_search_results", [])
    if results:
        options = {}
        for i, r in enumerate(results):
            label = f"{r['author'][:30]}: {r['content'][:70]}..."
            options[label] = r

        selected_label = st.selectbox("Pick a post", list(options.keys()), key="li_search_pick")
        selected = options[selected_label]

        with st.container(border=True):
            st.markdown(f"**{selected['author']}**")
            st.text(selected["content"][:400])
            if selected.get("url"):
                st.caption(selected["url"])

        return selected["content"], selected["author"], selected.get("url", "")

    return "", "", ""


def _render_feed_picker(feed_crud: Optional[FeedItemCRUD]) -> tuple[str, str, str]:
    """Pick from saved feed articles."""
    feed_posts = []
    if feed_crud:
        feed_posts = feed_crud.get_top_scored(limit=20, min_score=5.0)

    if not feed_posts:
        st.info("No feed articles available. Fetch feeds in the Feed Aggregator tab first.")
        return "", "", ""

    options = {
        f"[{fp['final_score']:.0f}] {fp['title'][:80]}": fp
        for fp in feed_posts
    }
    selected_label = st.selectbox("Select a feed article", list(options.keys()), key="comment_feed_sel")
    selected = options[selected_label]

    with st.container(border=True):
        st.markdown(f"**{selected['title']}**")
        st.caption(f"Source: {selected.get('source_name', 'N/A')}")
        st.text(selected.get("content", "")[:400])
        if selected.get("url"):
            st.caption(f"[Open article]({selected['url']})")

    return selected.get("content", ""), selected.get("source_name", "Unknown"), selected.get("url", "")


def _generate_comment(
    target_content: str,
    target_author: str,
    target_url: str,
    past_posts: list[dict],
    comment_crud: CommentCRUD,
    ai_config: AIConfig,
):
    with st.status("Generating comment...", expanded=True) as status:
        try:
            from src.content.generator import create_ai_provider
            from src.content.prompts import COMMENT_SYSTEM_PROMPT, COMMENT_TEMPLATES

            ai = create_ai_provider(ai_config)

            past_posts_context = ""
            if past_posts:
                snippets = [f"- {p['content'][:200]}" for p in past_posts[:10]]
                past_posts_context = "Your past published LinkedIn posts:\n" + "\n".join(snippets)

            strategy = "grounded" if past_posts_context else "generic"
            template = COMMENT_TEMPLATES[strategy]

            user_prompt = template.format(
                author=target_author,
                post_content=target_content[:1500],
                past_posts_context=past_posts_context,
                rag_context="",
            )

            model = ai_config.openai.model if ai_config.provider == "openai" else ai_config.anthropic.model
            st.write(f"Strategy: **{strategy}** | Model: **{model}**")

            result = ai.generate_with_confidence(COMMENT_SYSTEM_PROMPT, user_prompt)

            comment_id = comment_crud.create(
                target_post_url=target_url,
                comment_content=result.content,
                target_post_author=target_author,
                target_post_content=target_content[:500],
                strategy=strategy,
                confidence=result.confidence or 0.5,
            )

            status.update(label=f"Comment #{comment_id} generated!", state="complete")
            st.rerun()

        except Exception as e:
            status.update(label="Generation failed", state="error")
            st.error(f"LLM API error: {e}")
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
