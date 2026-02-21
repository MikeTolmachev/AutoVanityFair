import json

import streamlit as st

from src.database.crud import ContentLibraryCRUD


def render_content_library(
    content_crud: ContentLibraryCRUD,
    vector_store=None,
):
    """Page: Manage RAG knowledge base documents."""
    st.header("Content Library")

    # Stats
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Documents in DB", content_crud.count())
    with col2:
        if vector_store:
            st.metric("Embeddings", vector_store.count())
        else:
            st.metric("Embeddings", "N/A")

    st.divider()

    # Add new document
    st.subheader("Add Document")
    with st.form("add_document"):
        title = st.text_input("Title")
        content = st.text_area("Content", height=150)
        source = st.text_input("Source (optional)", placeholder="URL or reference")
        tags_str = st.text_input("Tags (comma-separated)", placeholder="ai, ml, llm")

        submitted = st.form_submit_button("Add to Library", type="primary")
        if submitted and title and content:
            tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else None
            doc_id = content_crud.add(
                title=title,
                content=content,
                source=source or None,
                tags=tags,
            )
            # Also add to vector store
            if vector_store:
                vector_store.add_document(
                    doc_id=str(doc_id),
                    text=content,
                    metadata={"title": title, "source": source or ""},
                )
            st.success(f"Document #{doc_id} added!")
            st.rerun()
        elif submitted:
            st.warning("Title and content are required.")

    st.divider()

    # List existing documents
    st.subheader("Existing Documents")
    docs = content_crud.list_all()

    if not docs:
        st.info("No documents in the library yet.")
        return

    for doc in docs:
        with st.container(border=True):
            col_title, col_actions = st.columns([3, 1])
            with col_title:
                st.markdown(f"**{doc['title']}**")
                if doc.get("source"):
                    st.caption(f"Source: {doc['source']}")
                if doc.get("tags"):
                    try:
                        tags = json.loads(doc["tags"])
                        st.caption(f"Tags: {', '.join(tags)}")
                    except (json.JSONDecodeError, TypeError):
                        pass
            with col_actions:
                if st.button("Delete", key=f"delete_doc_{doc['id']}"):
                    content_crud.delete(doc["id"])
                    if vector_store:
                        vector_store.delete_document(str(doc["id"]))
                    st.rerun()

            with st.expander("Content"):
                st.text(doc["content"][:500])
