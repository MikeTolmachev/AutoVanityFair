import streamlit as st

from src.database.crud import PostCRUD
from ui.components.queue_card import render_post_card
from ui.components.editor import render_editor


def render_posts_queue(post_crud: PostCRUD):
    """Page: Review/approve/edit/reject generated posts."""
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
        render_post_card(
            post,
            on_approve=lambda pid: (
                post_crud.update_status(pid, "approved"),
                st.rerun(),
            ),
            on_reject=lambda pid: (
                post_crud.update_status(pid, "rejected", reason="Rejected in UI"),
                st.rerun(),
            ),
            on_edit=lambda pid: (
                st.session_state.update({"editing_post": pid}),
                st.rerun(),
            ),
        )
