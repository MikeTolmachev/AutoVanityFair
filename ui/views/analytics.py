import streamlit as st

from src.database.crud import PostCRUD, CommentCRUD, InteractionLogCRUD


def render_analytics(
    post_crud: PostCRUD,
    comment_crud: CommentCRUD,
    log_crud: InteractionLogCRUD,
):
    """Page: Charts and stats for posts, comments, and actions."""
    st.header("Analytics")

    # Summary metrics
    col1, col2, col3 = st.columns(3)
    post_counts = post_crud.count_by_status()
    total_posts = sum(post_counts.values())

    with col1:
        st.metric("Total Posts", total_posts)
    with col2:
        published = post_counts.get("published", 0)
        rate = f"{published / total_posts:.0%}" if total_posts > 0 else "N/A"
        st.metric("Published", published, help=f"Approval rate: {rate}")
    with col3:
        st.metric("Comments Today", comment_crud.count_published_today())

    st.divider()

    # Post status breakdown
    st.subheader("Post Status Breakdown")
    if post_counts:
        st.bar_chart(post_counts)
    else:
        st.info("No post data yet.")

    st.divider()

    # Action counts
    st.subheader("Actions (Last 7 Days)")
    action_counts = log_crud.count_by_action(days=7)
    if action_counts:
        st.bar_chart(action_counts)
    else:
        st.info("No actions recorded.")

    st.divider()

    # Recent activity log
    st.subheader("Recent Activity")
    recent = log_crud.get_recent(limit=20)
    if recent:
        for entry in recent:
            status_icon = "ok" if entry["status"] == "success" else "x"
            st.caption(
                f":{status_icon}: [{entry['created_at']}] "
                f"**{entry['action_type']}** "
                f"{entry.get('target_url', '') or ''} "
                f"-- {entry.get('details', '') or ''}"
            )
    else:
        st.info("No activity recorded yet.")
