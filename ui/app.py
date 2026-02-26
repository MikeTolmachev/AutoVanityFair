"""
OpenLinkedIn -- Streamlit UI main entry point.
"""

import os
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st

from src.core.config_manager import ConfigManager
from src.core.safety_monitor import SafetyMonitor
from src.database.models import Database
from src.database.crud import PostCRUD, CommentCRUD, InteractionLogCRUD, ContentLibraryCRUD, FeedItemCRUD, FeedbackCRUD, SearchFeedbackCRUD
from src.content.generator import create_ai_provider
from src.content.post_generator import PostGenerator
from src.content.validators import ContentValidator
from ui.components.stats_widget import render_sidebar_stats
from ui.views.posts_queue import render_posts_queue
from ui.views.comments_queue import render_comments_queue
from ui.views.analytics import render_analytics
from ui.views.content_library import render_content_library
from ui.views.settings import render_settings
from ui.views.feed_aggregator import render_feed_aggregator

st.set_page_config(
    page_title="OpenLinkedIn",
    page_icon="🔗",
    layout="wide",
)


@st.cache_resource
def get_config():
    return ConfigManager()


@st.cache_resource
def get_database(_config):
    return Database(_config.paths.database)


@st.cache_resource
def get_safety_monitor(_config):
    return SafetyMonitor(
        hourly_limit=_config.safety.hourly_action_limit,
        daily_limit=_config.safety.daily_action_limit,
        weekly_limit=_config.safety.weekly_action_limit,
        error_rate_threshold=_config.safety.error_rate_threshold,
        error_window_seconds=_config.safety.error_window_seconds,
        cooldown_minutes=_config.safety.cooldown_minutes,
    )


def get_vector_store(config):
    """Lazy-load vector store (heavy dependency)."""
    try:
        from src.database.vector_store import VectorStore

        return VectorStore(
            persist_directory=config.paths.chroma_persist,
            collection_name=config.rag.collection_name,
            embedding_model=config.rag.embedding_model,
        )
    except Exception as e:
        st.sidebar.warning(f"Vector store unavailable: {e}")
        return None


def main():
    config = get_config()
    db = get_database(config)
    safety = get_safety_monitor(config)

    post_crud = PostCRUD(db)
    comment_crud = CommentCRUD(db)
    log_crud = InteractionLogCRUD(db)
    content_crud = ContentLibraryCRUD(db)
    feed_crud = FeedItemCRUD(db)
    feedback_crud = FeedbackCRUD(db)
    search_feedback_crud = SearchFeedbackCRUD(db)

    # Sidebar
    st.sidebar.title("OpenLinkedIn")
    render_sidebar_stats(
        post_counts=post_crud.count_by_status(),
        comment_today=comment_crud.count_published_today(),
        safety_stats=safety.get_stats(),
    )

    # Quick actions
    st.sidebar.divider()
    st.sidebar.subheader("Quick Actions")

    if st.sidebar.button("Generate New Post", use_container_width=True):
        with st.sidebar.status("Generating post..."):
            try:
                ai = create_ai_provider(config.ai)
                generator = PostGenerator(ai_provider=ai)
                result = generator.generate(
                    topic="AI and technology trends",
                    strategy="thought_leadership",
                )
                post_id = post_crud.create(
                    content=result["content"],
                    strategy=result["strategy"],
                    rag_sources=result["rag_sources"],
                )
                log_crud.log("generate_post", details=f"Post #{post_id} generated")
                st.sidebar.success(f"Post #{post_id} created!")
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Generation failed: {e}")

    # Tab navigation -- ordered by workflow
    tab_feeds, tab_library, tab_posts, tab_comments, tab_analytics, tab_settings = st.tabs([
        "1. Feed Aggregator",
        "2. Content Library",
        "3. Posts Queue",
        "4. Comments",
        "Analytics",
        "Settings",
    ])

    with tab_feeds:
        vs = get_vector_store(config)
        render_feed_aggregator(
            content_crud,
            feed_crud=feed_crud,
            feedback_crud=feedback_crud,
            vector_store=vs,
        )

    with tab_library:
        vs = get_vector_store(config)
        render_content_library(
            content_crud,
            vector_store=vs,
            post_crud=post_crud,
            ai_config=config.ai,
        )

    with tab_posts:
        render_posts_queue(
            post_crud,
            log_crud=log_crud,
            linkedin_config=config.linkedin,
            content_crud=content_crud,
            vertex_ai_config=config.vertex_ai,
        )

    with tab_comments:
        render_comments_queue(
            comment_crud,
            ai_config=config.ai,
            linkedin_config=config.linkedin,
            search_feedback_crud=search_feedback_crud,
        )

    with tab_analytics:
        render_analytics(post_crud, comment_crud, log_crud)

    with tab_settings:
        render_settings(config)


if __name__ == "__main__":
    main()
