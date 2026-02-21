"""
Feed Aggregator UI page.

View and manage RSS/API feeds, browse aggregated content with relevance scores,
and push high-scoring items into the content generation pipeline.
"""

import streamlit as st

from src.content.rss_aggregator import RSSAggregator, ALL_FEEDS, FeedSource
from src.content.content_filter import ContentFilter, ContentType
from src.database.crud import ContentLibraryCRUD


def render_feed_aggregator(
    content_crud: ContentLibraryCRUD,
    vector_store=None,
):
    """Page: RSS/API feed aggregation and content filtering."""
    st.header("Feed Aggregator")
    st.caption("Aggregate production-focused AI content from RSS feeds and APIs")

    # Initialize aggregator in session state
    if "aggregator" not in st.session_state:
        st.session_state.aggregator = RSSAggregator()
    aggregator: RSSAggregator = st.session_state.aggregator

    # --- Feed Sources Overview ---
    with st.expander("Feed Sources", expanded=False):
        _render_feed_sources(aggregator)

    st.divider()

    # --- Fetch Controls ---
    col_fetch, col_filter, col_max = st.columns([2, 2, 1])

    with col_fetch:
        priority_options = {
            "All Priorities": None,
            "P1: Production AI & MLOps": [1],
            "P2: Engineering Research": [2],
            "P3: Infrastructure & Deployment": [3],
            "P4: Community & Discussion": [4],
            "P1 + P2 (Recommended)": [1, 2],
        }
        selected_priority = st.selectbox(
            "Feed Priority",
            list(priority_options.keys()),
            index=5,
            key="feed_priority_select",
        )
        priorities = priority_options[selected_priority]

    with col_filter:
        min_score = st.slider(
            "Min Relevance Score",
            min_value=0.0,
            max_value=50.0,
            value=10.0,
            step=2.5,
            key="feed_min_score",
        )

    with col_max:
        max_results = st.number_input(
            "Max Results",
            min_value=5,
            max_value=100,
            value=20,
            step=5,
            key="feed_max_results",
        )

    if st.button("Fetch & Score Content", type="primary", use_container_width=True):
        aggregator.content_filter.min_score_threshold = min_score
        with st.status("Fetching feeds...", expanded=True) as status:
            st.write("Fetching RSS feeds and APIs...")
            scored_items = aggregator.fetch_and_filter(
                priorities=priorities,
                max_results=max_results,
            )
            st.session_state.scored_feed_items = scored_items
            status.update(
                label=f"Fetched and scored {len(scored_items)} items",
                state="complete",
            )

    st.divider()

    # --- Display Results ---
    scored_items = st.session_state.get("scored_feed_items", [])

    if not scored_items:
        st.info("Click 'Fetch & Score Content' to aggregate feeds.")
        return

    st.subheader(f"Top {len(scored_items)} Results")

    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        avg_score = sum(i.final_score for i in scored_items) / len(scored_items)
        st.metric("Avg Score", f"{avg_score:.1f}")
    with col2:
        prod_case_studies = sum(
            1 for i in scored_items
            if i.content_type == ContentType.PRODUCTION_CASE_STUDY
        )
        st.metric("Case Studies", prod_case_studies)
    with col3:
        sources = set(i.source for i in scored_items)
        st.metric("Sources", len(sources))
    with col4:
        high_score = sum(1 for i in scored_items if i.final_score >= 30)
        st.metric("High Score (30+)", high_score)

    st.divider()

    # Content cards
    for i, item in enumerate(scored_items):
        _render_scored_item(item, i, content_crud, vector_store)


def _render_feed_sources(aggregator: RSSAggregator):
    """Render the feed sources table."""
    stats = aggregator.get_source_stats()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Feeds", stats["total_feeds"])
    with col2:
        st.metric("Enabled", stats["enabled_feeds"])
    with col3:
        st.metric("Cached", stats["cached_feeds"])

    for priority in [1, 2, 3, 4]:
        feeds = aggregator.get_feeds_by_priority(priority)
        if feeds:
            st.caption(f"**Priority {priority}** ({len(feeds)} feeds)")
            for feed in feeds:
                st.text(f"  {'[ON]' if feed.enabled else '[OFF]'} {feed.name} -- {feed.category}")


def _render_scored_item(
    item,
    index: int,
    content_crud: ContentLibraryCRUD,
    vector_store=None,
):
    """Render a single scored content item."""
    with st.container(border=True):
        # Header row
        col_title, col_score = st.columns([4, 1])
        with col_title:
            st.markdown(f"**{item.title}**")
            st.caption(
                f"Source: {item.source} | "
                f"Type: {item.content_type.value} | "
                f"Multiplier: {item.type_multiplier}x"
            )
        with col_score:
            score_color = (
                "green" if item.final_score >= 30
                else "orange" if item.final_score >= 15
                else "red"
            )
            st.markdown(f":{score_color}[**{item.final_score:.1f}**]")

        # Score breakdown
        with st.expander("Score Details"):
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.caption(f"Production: {item.production_score:.1f}")
            with col_b:
                st.caption(f"Executive: {item.executive_score:.1f}")
            with col_c:
                st.caption(f"Keyword: {item.keyword_score:.1f}")

            if item.matched_keywords:
                st.caption(f"Keywords: {', '.join(item.matched_keywords[:8])}")
            if item.matched_categories:
                st.caption(f"Categories: {', '.join(item.matched_categories)}")

        # Content preview
        preview = item.content[:300] + "..." if len(item.content) > 300 else item.content
        st.text(preview)

        # Actions
        col_save, col_link = st.columns([1, 3])
        with col_save:
            if st.button(
                "Save to Library",
                key=f"save_feed_{index}",
                type="secondary",
            ):
                doc_id = content_crud.add(
                    title=item.title,
                    content=item.content,
                    source=item.url or item.source,
                    tags=[item.content_type.value, item.source],
                )
                if vector_store:
                    vector_store.add_document(
                        doc_id=str(doc_id),
                        text=item.content,
                        metadata={"title": item.title, "source": item.source},
                    )
                st.success(f"Saved as document #{doc_id}")
        with col_link:
            if item.url:
                st.caption(f"[Open article]({item.url})")
