import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.database.vector_store import VectorStore

logger = logging.getLogger("openlinkedin.rag")


class RAGEngine:
    """Queries VectorStore and builds context strings for content generation."""

    def __init__(
        self,
        vector_store: "VectorStore",
        similarity_threshold: float = 0.65,
        max_context_docs: int = 3,
    ):
        self.vector_store = vector_store
        self.similarity_threshold = similarity_threshold
        self.max_context_docs = max_context_docs

    def get_context(self, query: str) -> Optional[str]:
        """Query the knowledge base and return formatted context string."""
        if self.vector_store.count() == 0:
            logger.debug("Vector store is empty, no context available")
            return None

        results = self.vector_store.query(query, n_results=self.max_context_docs)
        relevant = [
            r for r in results
            if r["distance"] is not None and r["distance"] < (1 - self.similarity_threshold)
        ]

        if not relevant:
            logger.debug("No results above similarity threshold for query: %s", query[:50])
            return None

        context_parts = []
        for r in relevant:
            title = r["metadata"].get("title", "Source")
            context_parts.append(f"[{title}]: {r['document']}")

        context = "\n\n".join(context_parts)
        logger.info("RAG context built from %d documents", len(relevant))
        return context

    def get_strategy(self, query: str) -> str:
        """Determine if we have enough context for a grounded response."""
        context = self.get_context(query)
        if context:
            return "grounded"
        return "generic"

    def get_context_with_sources(self, query: str) -> tuple[Optional[str], list[str]]:
        """Return context string and list of source IDs."""
        if self.vector_store.count() == 0:
            return None, []

        results = self.vector_store.query(query, n_results=self.max_context_docs)
        relevant = [
            r for r in results
            if r["distance"] is not None and r["distance"] < (1 - self.similarity_threshold)
        ]

        if not relevant:
            return None, []

        context_parts = []
        sources = []
        for r in relevant:
            title = r["metadata"].get("title", "Source")
            context_parts.append(f"[{title}]: {r['document']}")
            sources.append(r["id"])

        return "\n\n".join(context_parts), sources
