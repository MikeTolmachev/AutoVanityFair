"""Gemini text-embedding-004 wrapper for feed item embeddings."""

import logging

logger = logging.getLogger("openlinkedin.embeddings")

EMBEDDING_MODEL = "text-embedding-004"
DEFAULT_DIMENSIONALITY = 32


def get_embeddings(
    texts: list[str],
    project_id: str,
    location: str = "us-central1",
    dimensionality: int = DEFAULT_DIMENSIONALITY,
) -> list[list[float]]:
    """Compute embeddings for a list of texts using Gemini text-embedding-004.

    Returns a list of float vectors (one per input text).
    On API failure, returns zero vectors so the pipeline never breaks.
    """
    if not texts:
        return []

    zero = [0.0] * dimensionality

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            vertexai=True,
            project=project_id,
            location=location,
        )

        # API supports batch natively but cap at 100 per call
        all_embeddings: list[list[float]] = []
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            # Truncate very long texts to avoid token limits
            batch = [t[:8000] if len(t) > 8000 else t for t in batch]
            result = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=batch,
                config=types.EmbedContentConfig(
                    output_dimensionality=dimensionality,
                ),
            )
            for emb in result.embeddings:
                all_embeddings.append(list(emb.values))

        logger.info("Computed %d embeddings (dim=%d)", len(all_embeddings), dimensionality)
        return all_embeddings

    except Exception:
        logger.exception("Embedding API failed, returning zero vectors")
        return [zero] * len(texts)


def embedding_text(title: str, content: str) -> str:
    """Combine title + content into a single string for embedding."""
    return f"{title}\n{content[:2000]}" if content else title
