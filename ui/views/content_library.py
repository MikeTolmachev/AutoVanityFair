"""
Content Library page.

Browse documents saved from feeds, add personal thoughts,
and generate LinkedIn post drafts using the LLM API.
"""

import json
from typing import Optional

import streamlit as st

from src.core.config_manager import AIConfig
from src.database.crud import ContentLibraryCRUD, PostCRUD


def render_content_library(
    content_crud: ContentLibraryCRUD,
    vector_store=None,
    post_crud: Optional[PostCRUD] = None,
    ai_config: Optional[AIConfig] = None,
):
    st.header("Content Library")

    doc_count = content_crud.count()
    st.caption(f"{doc_count} documents | Save articles from the Feed Aggregator tab, then generate posts here.")

    # --- Detail view when a document is opened ---
    if "library_detail_id" in st.session_state:
        doc = content_crud.get(st.session_state.library_detail_id)
        if doc:
            _render_document_detail(doc, content_crud, post_crud, ai_config)
            return
        else:
            del st.session_state["library_detail_id"]

    if doc_count == 0:
        st.info("No documents yet. Go to the **Feed Aggregator** tab, fetch feeds, and click **Save to Library** on articles you like.")
        return

    # --- Document list ---
    docs = content_crud.list_all()
    for doc in docs:
        _render_document_card(doc, content_crud, vector_store)

    # --- Manual add (collapsed) ---
    with st.expander("Manually add a document"):
        _render_add_form(content_crud, vector_store)


def _render_document_card(doc: dict, content_crud: ContentLibraryCRUD, vector_store):
    with st.container(border=True):
        col_info, col_status, col_actions = st.columns([4, 1, 1])

        with col_info:
            st.markdown(f"**{doc['title']}**")
            meta = []
            if doc.get("source"):
                src = doc["source"]
                if len(src) > 60:
                    src = src[:57] + "..."
                meta.append(src)
            if doc.get("tags"):
                try:
                    meta.append(", ".join(json.loads(doc["tags"])))
                except (json.JSONDecodeError, TypeError):
                    pass
            if meta:
                st.caption(" | ".join(meta))

        with col_status:
            if doc.get("generated_post"):
                st.caption(":green[Draft ready]")
            elif doc.get("personal_thoughts"):
                st.caption(":blue[Has thoughts]")

        with col_actions:
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Open", key=f"open_{doc['id']}", use_container_width=True):
                    st.session_state.library_detail_id = doc["id"]
                    st.rerun()
            with c2:
                if st.button("Del", key=f"del_{doc['id']}", use_container_width=True):
                    content_crud.delete(doc["id"])
                    if vector_store:
                        vector_store.delete_document(str(doc["id"]))
                    st.rerun()


def _render_document_detail(
    doc: dict,
    content_crud: ContentLibraryCRUD,
    post_crud: Optional[PostCRUD],
    ai_config: Optional[AIConfig],
):
    """Document detail: article content, personal thoughts, generate post."""
    if st.button("< Back to list"):
        del st.session_state["library_detail_id"]
        st.rerun()

    st.subheader(doc["title"])
    if doc.get("source"):
        st.caption(f"Source: {doc['source']}")

    # ---- 1. Article content (read-only) ----
    st.markdown("##### Source Article")
    st.text_area(
        "article_ro",
        value=doc["content"],
        height=160,
        disabled=True,
        label_visibility="collapsed",
    )

    st.divider()

    # ---- 2. Personal thoughts ----
    st.markdown("##### Your Thoughts")
    st.caption("Write your perspective, experience, or opinion. The LLM will blend this with the article to create your post.")

    current_thoughts = doc.get("personal_thoughts") or ""
    thoughts_key = f"thoughts_{doc['id']}"
    thoughts = st.text_area(
        thoughts_key,
        value=current_thoughts,
        height=120,
        placeholder="e.g. We ran into the same issue when deploying our RAG pipeline -- the retrieval latency was the real bottleneck, not the LLM...",
        label_visibility="collapsed",
    )

    # Auto-save thoughts when changed
    if thoughts != current_thoughts:
        content_crud.update_personal_thoughts(doc["id"], thoughts)
        # Update local copy so generate uses latest
        doc = dict(doc)
        doc["personal_thoughts"] = thoughts

    st.divider()

    # ---- 3. Generate post ----
    st.markdown("##### LinkedIn Post Draft")

    if st.button(
        "Generate Post from Article + Thoughts",
        type="primary",
        use_container_width=True,
        disabled=(ai_config is None),
    ):
        if ai_config is None:
            st.error("AI config not available.")
        else:
            _generate_draft(doc, thoughts, content_crud, ai_config)

    # ---- 4. Show / edit generated draft ----
    if doc.get("generated_post"):
        if doc.get("generated_title"):
            st.markdown(f"**Suggested title:** {doc['generated_title']}")

        generated = doc["generated_post"]
        edited = st.text_area(
            "edit_draft",
            value=generated,
            height=220,
            label_visibility="collapsed",
        )
        st.caption(f"{len(edited)} characters | LinkedIn ideal: 200-1300")

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Send to Posts Queue", type="primary", use_container_width=True):
                if post_crud and edited.strip():
                    post_id = post_crud.create(
                        content=edited.strip(),
                        strategy="thought_leadership",
                        rag_sources=[str(doc["id"])],
                    )
                    st.success(f"Post #{post_id} added to queue for review!")
                elif not post_crud:
                    st.error("Post queue not available.")
                else:
                    st.warning("Post is empty.")
        with col2:
            if st.button("Regenerate", use_container_width=True):
                if ai_config:
                    _generate_draft(doc, thoughts, content_crud, ai_config)
        with col3:
            if edited != generated:
                if st.button("Save Edits", use_container_width=True):
                    content_crud.update_generated_post(
                        doc["id"],
                        doc.get("generated_title", ""),
                        edited,
                    )
                    st.success("Edits saved!")
                    st.rerun()
    else:
        st.info("Click the button above to generate a LinkedIn post draft using the LLM.")


def _generate_draft(
    doc: dict,
    thoughts: str,
    content_crud: ContentLibraryCRUD,
    ai_config: AIConfig,
):
    """Call the LLM API to generate a post from article + personal thoughts."""
    with st.status("Calling LLM API...", expanded=True) as status:
        try:
            from src.content.generator import create_ai_provider
            from src.content.prompts import (
                LIBRARY_POST_SYSTEM_PROMPT,
                LIBRARY_POST_TEMPLATE,
            )

            st.write(f"Provider: **{ai_config.provider}**")
            model = (
                ai_config.openai.model
                if ai_config.provider == "openai"
                else ai_config.anthropic.model
            )
            st.write(f"Model: **{model}**")

            ai = create_ai_provider(ai_config)

            thoughts_section = ""
            if thoughts and thoughts.strip():
                thoughts_section = f"\nMy personal thoughts / angle:\n{thoughts.strip()}\n"

            user_prompt = LIBRARY_POST_TEMPLATE.format(
                article_title=doc["title"],
                article_source=doc.get("source") or "N/A",
                article_content=doc["content"][:2000],
                personal_thoughts_section=thoughts_section,
            )

            st.write("Generating...")
            result = ai.generate(LIBRARY_POST_SYSTEM_PROMPT, user_prompt)
            raw = result.content
            st.write(f"Tokens used: **{result.tokens_used}**")

            # Parse TITLE: ... --- body
            title = ""
            body = raw
            if "TITLE:" in raw:
                after_title = raw.split("TITLE:", 1)[1]
                if "---" in after_title:
                    title_part, body = after_title.split("---", 1)
                    title = title_part.strip()
                    body = body.strip()
                else:
                    lines = after_title.strip().split("\n", 1)
                    title = lines[0].strip()
                    body = lines[1].strip() if len(lines) > 1 else ""

            content_crud.update_generated_post(doc["id"], title, body)
            status.update(label="Draft generated!", state="complete")
            st.rerun()

        except Exception as e:
            status.update(label="Generation failed", state="error")
            st.error(f"LLM API error: {e}")
            import traceback
            st.code(traceback.format_exc())


def _render_add_form(content_crud: ContentLibraryCRUD, vector_store):
    """Manual document add form (collapsed by default)."""
    with st.form("add_document"):
        title = st.text_input("Title")
        content = st.text_area("Content", height=120)
        source = st.text_input("Source (optional)")
        tags_str = st.text_input("Tags (comma-separated)")
        thoughts = st.text_area("Your thoughts (optional)", height=80)

        if st.form_submit_button("Add to Library"):
            if title and content:
                tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else None
                doc_id = content_crud.add(
                    title=title, content=content,
                    source=source or None, tags=tags,
                    personal_thoughts=thoughts or None,
                )
                if vector_store:
                    vector_store.add_document(
                        doc_id=str(doc_id), text=content,
                        metadata={"title": title, "source": source or ""},
                    )
                st.success(f"Document #{doc_id} added!")
                st.rerun()
            else:
                st.warning("Title and content are required.")
