import streamlit as st


def render_sidebar_stats(post_counts: dict, comment_today: int, safety_stats: dict):
    """Render sidebar metrics."""
    st.sidebar.header("Dashboard")

    st.sidebar.metric("Posts in Queue", post_counts.get("draft", 0))
    st.sidebar.metric("Posts Approved", post_counts.get("approved", 0))
    st.sidebar.metric("Posts Published", post_counts.get("published", 0))
    st.sidebar.metric("Comments Today", comment_today)

    st.sidebar.divider()
    st.sidebar.subheader("Safety Limits")

    hourly = safety_stats.get("hourly_remaining", "?")
    daily = safety_stats.get("daily_remaining", "?")
    weekly = safety_stats.get("weekly_remaining", "?")

    st.sidebar.caption(f"Hourly remaining: **{hourly}**")
    st.sidebar.caption(f"Daily remaining: **{daily}**")
    st.sidebar.caption(f"Weekly remaining: **{weekly}**")

    error_rate = safety_stats.get("error_rate", 0)
    if error_rate > 0.2:
        st.sidebar.warning(f"Error rate: {error_rate:.1%}")
    else:
        st.sidebar.caption(f"Error rate: **{error_rate:.1%}**")

    if safety_stats.get("in_cooldown"):
        st.sidebar.error("System in cooldown mode")
