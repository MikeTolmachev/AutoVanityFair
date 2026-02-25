"""
Feed Aggregator UI page.

View and manage RSS/API feeds, browse aggregated content with relevance scores,
provide like/dislike feedback, and train an ML reranker to personalise results.
"""

import streamlit as st

from src.content.rss_aggregator import RSSAggregator, ALL_FEEDS, FeedSource
from src.content.content_filter import ContentFilter, ContentType
from src.content.reranker import FeedReranker
from src.database.crud import ContentLibraryCRUD, FeedItemCRUD, FeedbackCRUD
from src.utils.helpers import parse_published_date, months_ago


def render_feed_aggregator(
    content_crud: ContentLibraryCRUD,
    feed_crud: FeedItemCRUD,
    feedback_crud: FeedbackCRUD,
    vector_store=None,
):
    """Page: RSS/API feed aggregation and content filtering."""
    st.header("Feed Aggregator")
    st.caption("Aggregate production-focused AI content from RSS feeds and APIs")

    # Initialize aggregator and reranker in session state
    if "aggregator" not in st.session_state:
        st.session_state.aggregator = RSSAggregator()
    aggregator: RSSAggregator = st.session_state.aggregator

    if "reranker" not in st.session_state:
        st.session_state.reranker = FeedReranker()
    reranker: FeedReranker = st.session_state.reranker

    # Load feedback map into session (cached per session)
    if "feedback_map" not in st.session_state:
        st.session_state.feedback_map = feedback_crud.get_feedback_map()

    # --- Feed Sources Overview ---
    with st.expander("Feed Sources", expanded=False):
        _render_feed_sources(aggregator)

    # --- ML Model Info ---
    with st.expander("ML Reranker", expanded=False):
        _render_reranker_panel(reranker, feedback_crud)

    st.divider()

    # --- Fetch Controls ---
    col_fetch, col_filter, col_max, col_liked = st.columns([2, 2, 1, 1])

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
            max_value=500,
            value=100,
            step=10,
            key="feed_max_results",
        )

    with col_liked:
        tagged_only = st.toggle("Tagged Only", value=False, key="feed_tagged_only")

    if st.button("Fetch & Score Content", type="primary", use_container_width=True):
        aggregator.content_filter.min_score_threshold = min_score
        with st.status("Fetching feeds...", expanded=True) as status:
            st.write("Fetching RSS feeds and APIs...")
            scored_items = aggregator.fetch_and_filter(
                priorities=priorities,
                max_results=max_results,
            )

            # Persist to DB for training data
            for item in scored_items:
                feed_crud.upsert(
                    item_hash=_item_hash(item),
                    title=item.title,
                    content=item.content,
                    url=item.url,
                    source_name=item.source,
                    source_category=_guess_category(item.source),
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

            # ML rerank if model is available
            if reranker.is_trained:
                st.write("Reranking with ML model...")
                scored_items = reranker.rerank(scored_items)

            st.session_state.scored_feed_items = scored_items
            status.update(
                label=f"Fetched and scored {len(scored_items)} items"
                + (" (ML reranked)" if reranker.is_trained else ""),
                state="complete",
            )

    st.divider()

    # --- Display Results ---
    scored_items = st.session_state.get("scored_feed_items", [])

    feedback_map = st.session_state.feedback_map
    if tagged_only:
        # Show only items that have feedback (liked or disliked)
        if scored_items:
            scored_items = [
                item for item in scored_items
                if _item_hash(item) in feedback_map
            ]
        else:
            # Load tagged items from DB directly
            liked_rows = feed_crud.get_liked_items(limit=max_results)
            if liked_rows:
                st.info(f"Showing {len(liked_rows)} tagged items from history.")
                for i, row in enumerate(liked_rows):
                    _render_db_item(row, i, feedback_crud, content_crud, vector_store)
                return
    else:
        # Default: show only unlabeled items (no feedback yet)
        if scored_items:
            scored_items = [
                item for item in scored_items
                if _item_hash(item) not in feedback_map
            ]

    if not scored_items:
        st.info("Click 'Fetch & Score Content' to aggregate feeds.")
        return

    st.subheader(f"Showing {len(scored_items)} Results")

    # Summary metrics
    feedback_counts = feedback_crud.count_feedback()
    col1, col2, col3, col4, col5, col6 = st.columns(6)
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
    with col5:
        st.metric("Liked", feedback_counts.get("liked", 0))
    with col6:
        st.metric("Disliked", feedback_counts.get("disliked", 0))

    st.divider()

    # Content cards
    for i, item in enumerate(scored_items):
        _render_scored_item(item, i, content_crud, feed_crud, feedback_crud, vector_store)


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


def _render_reranker_panel(reranker: FeedReranker, feedback_crud: FeedbackCRUD):
    """Render ML reranker status and retrain controls."""
    stats = reranker.get_stats()
    feedback_counts = feedback_crud.count_feedback()

    col1, col2, col3 = st.columns(3)
    with col1:
        status_text = "Trained" if reranker.is_trained else "Not trained"
        st.metric("Model Status", status_text)
    with col2:
        total_fb = sum(feedback_counts.values())
        st.metric("Total Feedback", total_fb)
    with col3:
        st.metric(
            "Min Required",
            f"{total_fb}/{reranker.min_training_samples}",
        )

    if reranker.is_trained and stats.get("feature_importance"):
        st.caption("**Top Feature Importance:**")
        importance = stats["feature_importance"]
        top_features = list(importance.items())[:5]
        for feat, imp in top_features:
            st.text(f"  {feat}: {imp:.1f}")

    if st.button("Retrain Model", key="retrain_btn"):
        training_data = feedback_crud.get_all_training_data()
        feedback_map = feedback_crud.get_feedback_map()
        # Add published items as implicit likes
        published_hashes = feedback_crud.get_published_item_hashes()
        for h in published_hashes:
            if h not in feedback_map:
                feedback_map[h] = "liked"
        result = reranker.train(training_data, feedback_map)
        if result.get("status") == "trained":
            pub_count = len(published_hashes - set(feedback_crud.get_feedback_map().keys()))
            msg = (
                f"Model trained on {result['total_samples']} samples "
                f"({result['liked']} liked, {result['disliked']} disliked)"
            )
            if pub_count > 0:
                msg += f" incl. {pub_count} from published posts"
            st.success(msg)
        elif result.get("status") == "insufficient_data":
            st.warning(
                f"Need at least {result['min_required']} feedback items "
                f"(have {result['samples']}). Keep rating items!"
            )
        else:
            st.error(f"Training failed: {result}")


def _render_scored_item(
    item,
    index: int,
    content_crud: ContentLibraryCRUD,
    feed_crud: FeedItemCRUD,
    feedback_crud: FeedbackCRUD,
    vector_store=None,
):
    """Render a single scored content item with feedback controls."""
    item_hash = _item_hash(item)
    current_feedback = st.session_state.feedback_map.get(item_hash)

    # Container border color hint via emoji prefix
    feedback_prefix = ""
    if current_feedback == "liked":
        feedback_prefix = "[LIKED] "
    elif current_feedback == "disliked":
        feedback_prefix = "[DISLIKED] "

    with st.container(border=True):
        # Header row
        col_title, col_score = st.columns([4, 1])
        with col_title:
            st.markdown(f"**{feedback_prefix}{item.title}**")

            # Rich metadata line
            meta_parts = [f"Source: {item.source}"]
            meta_parts.append(f"Type: {item.content_type.value}")

            if item.author:
                meta_parts.append(f"Author: {item.author}")

            if item.published_at:
                dt = parse_published_date(item.published_at)
                if dt:
                    age = months_ago(dt)
                    if age < 1:
                        age_str = f"{int(age * 30)}d ago"
                    else:
                        age_str = f"{age:.0f}mo ago"
                    meta_parts.append(age_str)

            meta_parts.append(f"Multiplier: {item.type_multiplier}x")

            if item.freshness_multiplier < 1.0:
                meta_parts.append(f"Freshness: {item.freshness_multiplier}x")

            st.caption(" | ".join(meta_parts))

        with col_score:
            score_color = (
                "green" if item.final_score >= 30
                else "orange" if item.final_score >= 15
                else "red"
            )
            label = "ML" if st.session_state.reranker.is_trained else "Rule"
            st.markdown(f":{score_color}[**{item.final_score:.1f}**] `{label}`")

        # Score breakdown
        with st.expander("Score Details"):
            col_a, col_b, col_c, col_d = st.columns(4)
            with col_a:
                st.caption(f"Production: {item.production_score:.1f}")
            with col_b:
                st.caption(f"Executive: {item.executive_score:.1f}")
            with col_c:
                st.caption(f"Keyword: {item.keyword_score:.1f}")
            with col_d:
                st.caption(f"Freshness: {item.freshness_multiplier}x")

            if item.matched_keywords:
                st.caption(f"Keywords: {', '.join(item.matched_keywords[:10])}")
            if item.matched_categories:
                st.caption(f"Categories: {', '.join(item.matched_categories)}")

        # Content preview
        preview = item.content[:500] + "..." if len(item.content) > 500 else item.content
        st.text(preview)

        # Actions row: like, dislike, save, link
        col_like, col_dislike, col_save, col_link = st.columns([1, 1, 1, 3])

        with col_like:
            like_label = "Liked" if current_feedback == "liked" else "Like"
            like_type = "primary" if current_feedback == "liked" else "secondary"
            if st.button(
                like_label,
                key=f"like_{index}",
                type=like_type,
                use_container_width=True,
            ):
                _save_feedback(item, item_hash, "liked", feed_crud, feedback_crud)
                st.rerun()

        with col_dislike:
            dislike_label = "Disliked" if current_feedback == "disliked" else "Dislike"
            dislike_type = "primary" if current_feedback == "disliked" else "secondary"
            if st.button(
                dislike_label,
                key=f"dislike_{index}",
                type=dislike_type,
                use_container_width=True,
            ):
                _save_feedback(item, item_hash, "disliked", feed_crud, feedback_crud)
                st.rerun()

        with col_save:
            if st.button(
                "Save to Library",
                key=f"save_feed_{index}",
                type="secondary",
                use_container_width=True,
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


def _render_db_item(
    row: dict,
    index: int,
    feedback_crud: FeedbackCRUD,
    content_crud: ContentLibraryCRUD,
    vector_store=None,
):
    """Render a feed item from a DB row (used for liked-only view)."""
    with st.container(border=True):
        col_title, col_score = st.columns([4, 1])
        with col_title:
            st.markdown(f"**[LIKED] {row['title']}**")
            meta_parts = [f"Source: {row.get('source_name', '')}"]
            if row.get("content_type"):
                meta_parts.append(f"Type: {row['content_type']}")
            if row.get("author"):
                meta_parts.append(f"Author: {row['author']}")
            st.caption(" | ".join(meta_parts))
        with col_score:
            st.markdown(f":green[**{row.get('final_score', 0):.1f}**]")

        preview = row.get("content", "")
        if len(preview) > 500:
            preview = preview[:500] + "..."
        st.text(preview)

        col_save, col_link = st.columns([1, 3])
        with col_save:
            if st.button("Save to Library", key=f"save_liked_{index}"):
                doc_id = content_crud.add(
                    title=row["title"],
                    content=row.get("content", ""),
                    source=row.get("url") or row.get("source_name", ""),
                    tags=[row.get("content_type", ""), row.get("source_name", "")],
                )
                st.success(f"Saved as document #{doc_id}")
        with col_link:
            if row.get("url"):
                st.caption(f"[Open article]({row['url']})")


def _save_feedback(
    item,
    item_hash: str,
    feedback: str,
    feed_crud: FeedItemCRUD,
    feedback_crud: FeedbackCRUD,
):
    """Save user feedback for a feed item."""
    # Ensure the item exists in the DB
    db_row = feed_crud.get_by_hash(item_hash)
    if db_row:
        feed_item_id = db_row["id"]
    else:
        feed_item_id = feed_crud.upsert(
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

    feedback_crud.set_feedback(feed_item_id, item_hash, feedback)
    st.session_state.feedback_map[item_hash] = feedback


def _item_hash(item) -> str:
    """Get or compute item hash from a ScoredContent item."""
    import hashlib

    raw = f"{item.title}{item.url}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _guess_category(source_name: str) -> str:
    """Guess category from source name (for DB storage)."""
    from src.content.rss_aggregator import ALL_FEEDS

    for feed in ALL_FEEDS:
        if feed.name == source_name:
            return feed.category
    return ""
