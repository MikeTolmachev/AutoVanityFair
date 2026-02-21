import logging
from typing import Optional

import chromadb
from chromadb.config import Settings

logger = logging.getLogger("openlinkedin.vector_store")


class VectorStore:
    """ChromaDB wrapper using sentence-transformers for embeddings."""

    def __init__(
        self,
        persist_directory: str = "data/chroma",
        collection_name: str = "content_library",
        embedding_model: str = "all-MiniLM-L6-v2",
    ):
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.embedding_model = embedding_model

        self._client = chromadb.Client(
            Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=persist_directory,
                anonymized_telemetry=False,
            )
        )

        # Use sentence-transformers embedding function
        from chromadb.utils import embedding_functions

        self._ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=embedding_model
        )

        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=self._ef,
        )
        logger.info(
            "VectorStore initialized: collection=%s, docs=%d",
            collection_name,
            self._collection.count(),
        )

    def add_document(
        self,
        doc_id: str,
        text: str,
        metadata: Optional[dict] = None,
    ) -> None:
        self._collection.upsert(
            ids=[doc_id],
            documents=[text],
            metadatas=[metadata or {}],
        )

    def query(
        self,
        query_text: str,
        n_results: int = 3,
    ) -> list[dict]:
        results = self._collection.query(
            query_texts=[query_text],
            n_results=min(n_results, self._collection.count() or 1),
        )
        docs = []
        for i in range(len(results["ids"][0])):
            docs.append(
                {
                    "id": results["ids"][0][i],
                    "document": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else None,
                }
            )
        return docs

    def delete_document(self, doc_id: str) -> None:
        self._collection.delete(ids=[doc_id])

    def count(self) -> int:
        return self._collection.count()
