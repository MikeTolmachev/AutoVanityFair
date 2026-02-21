import streamlit as st


def render_post_card(post: dict, on_approve=None, on_reject=None, on_edit=None):
    """Render a post review card with approve/reject/edit buttons."""
    with st.container(border=True):
        col_meta, col_status = st.columns([3, 1])
        with col_meta:
            st.caption(
                f"Strategy: **{post.get('strategy', 'N/A')}** | "
                f"Created: {post.get('created_at', 'N/A')}"
            )
        with col_status:
            status = post.get("status", "draft")
            color = {"draft": "blue", "approved": "green", "published": "violet", "rejected": "red"}.get(status, "gray")
            st.markdown(f":{color}[{status.upper()}]")

        st.markdown(post.get("content", ""))

        if post.get("rag_sources"):
            with st.expander("RAG Sources"):
                st.text(post["rag_sources"])

        if status in ("draft", "approved"):
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("Approve", key=f"approve_post_{post['id']}", type="primary"):
                    if on_approve:
                        on_approve(post["id"])
            with col2:
                if st.button("Reject", key=f"reject_post_{post['id']}"):
                    if on_reject:
                        on_reject(post["id"])
            with col3:
                if st.button("Edit", key=f"edit_post_{post['id']}"):
                    if on_edit:
                        on_edit(post["id"])


def render_comment_card(comment: dict, on_approve=None, on_reject=None, on_edit=None):
    """Render a comment review card."""
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
            color = {"draft": "blue", "approved": "green", "published": "violet", "rejected": "red"}.get(status, "gray")
            st.markdown(f":{color}[{status.upper()}]")

        if comment.get("target_post_content"):
            with st.expander("Target Post"):
                st.caption(f"By: {comment.get('target_post_author', 'Unknown')}")
                st.text(comment["target_post_content"][:300])

        st.markdown(f"**Comment:** {comment.get('comment_content', '')}")

        if status in ("draft", "approved"):
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("Approve", key=f"approve_comment_{comment['id']}", type="primary"):
                    if on_approve:
                        on_approve(comment["id"])
            with col2:
                if st.button("Reject", key=f"reject_comment_{comment['id']}"):
                    if on_reject:
                        on_reject(comment["id"])
            with col3:
                if st.button("Edit", key=f"edit_comment_{comment['id']}"):
                    if on_edit:
                        on_edit(comment["id"])
