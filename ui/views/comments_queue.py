import streamlit as st

from src.database.crud import CommentCRUD
from ui.components.queue_card import render_comment_card
from ui.components.editor import render_editor


def render_comments_queue(comment_crud: CommentCRUD):
    """Page: Review comments with confidence scores and strategy labels."""
    st.header("Comments Queue")

    # Check for edit mode
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
        render_comment_card(
            comment,
            on_approve=lambda cid: (
                comment_crud.update_status(cid, "approved"),
                st.rerun(),
            ),
            on_reject=lambda cid: (
                comment_crud.update_status(cid, "rejected", reason="Rejected in UI"),
                st.rerun(),
            ),
            on_edit=lambda cid: (
                st.session_state.update({"editing_comment": cid}),
                st.rerun(),
            ),
        )
