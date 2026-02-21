#!/usr/bin/env python3
"""
Seed the content library / RAG knowledge base with sample documents.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.config_manager import ConfigManager
from src.database.models import Database
from src.database.crud import ContentLibraryCRUD

SAMPLE_DOCS = [
    {
        "title": "LLM Fine-Tuning Best Practices",
        "content": (
            "Fine-tuning large language models requires careful data preparation. "
            "Key considerations include: data quality over quantity, balanced training "
            "examples, proper evaluation metrics, and avoiding catastrophic forgetting. "
            "LoRA and QLoRA have made fine-tuning accessible on consumer hardware."
        ),
        "source": "internal knowledge",
        "tags": ["llm", "fine-tuning", "ai"],
    },
    {
        "title": "RAG Architecture Patterns",
        "content": (
            "Retrieval-Augmented Generation combines the strengths of retrieval systems "
            "and generative models. Effective RAG requires: chunking strategies that "
            "preserve context, embedding models matched to your domain, hybrid search "
            "(vector + keyword), and careful prompt engineering to ground responses."
        ),
        "source": "internal knowledge",
        "tags": ["rag", "architecture", "ai"],
    },
    {
        "title": "AI Agent Frameworks Comparison",
        "content": (
            "Modern AI agent frameworks like LangGraph, CrewAI, and AutoGen each take "
            "different approaches. LangGraph offers graph-based orchestration with fine "
            "control. CrewAI simplifies multi-agent collaboration. AutoGen focuses on "
            "conversational agents. Choice depends on use case complexity and control needs."
        ),
        "source": "internal knowledge",
        "tags": ["agents", "frameworks", "ai"],
    },
]


def main():
    config = ConfigManager()
    db = Database(config.paths.database)
    content_crud = ContentLibraryCRUD(db)

    # Optionally seed vector store too
    vector_store = None
    try:
        from src.database.vector_store import VectorStore

        vector_store = VectorStore(
            persist_directory=config.paths.chroma_persist,
            collection_name=config.rag.collection_name,
            embedding_model=config.rag.embedding_model,
        )
    except Exception as e:
        print(f"Vector store not available: {e}")

    print("Seeding content library...\n")
    for doc in SAMPLE_DOCS:
        doc_id = content_crud.add(
            title=doc["title"],
            content=doc["content"],
            source=doc["source"],
            tags=doc["tags"],
        )
        print(f"  Added: {doc['title']} (#{doc_id})")

        if vector_store:
            vector_store.add_document(
                doc_id=str(doc_id),
                text=doc["content"],
                metadata={"title": doc["title"], "source": doc["source"]},
            )

    print(f"\nSeeded {len(SAMPLE_DOCS)} documents.")
    if vector_store:
        print(f"Vector store count: {vector_store.count()}")


if __name__ == "__main__":
    main()
