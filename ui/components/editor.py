import streamlit as st


def render_editor(
    content: str,
    item_id: int,
    item_type: str = "post",
    on_save=None,
):
    """Inline content editor with preview."""
    st.subheader(f"Edit {item_type.title()} #{item_id}")

    edited = st.text_area(
        "Content",
        value=content,
        height=200,
        key=f"editor_{item_type}_{item_id}",
    )

    col_preview, col_stats = st.columns([2, 1])
    with col_preview:
        with st.expander("Preview", expanded=True):
            st.markdown(edited)
    with col_stats:
        st.caption(f"Characters: {len(edited)}")
        st.caption(f"Words: {len(edited.split())}")

    col_save, col_cancel = st.columns(2)
    with col_save:
        if st.button("Save", key=f"save_{item_type}_{item_id}", type="primary"):
            if on_save:
                on_save(item_id, edited)
                st.success("Saved!")
    with col_cancel:
        if st.button("Cancel", key=f"cancel_{item_type}_{item_id}"):
            st.rerun()
