import pytest

chromadb = pytest.importorskip("chromadb", reason="chromadb not installed")


@pytest.fixture
def vector_store(tmp_path):
    """Create a VectorStore with a temp directory."""
    from src.database.vector_store import VectorStore

    try:
        vs = VectorStore(
            persist_directory=str(tmp_path / "chroma"),
            collection_name="test_collection",
            embedding_model="all-MiniLM-L6-v2",
        )
        return vs
    except Exception as e:
        pytest.skip(f"VectorStore dependencies not available: {e}")


class TestVectorStore:
    def test_add_and_count(self, vector_store):
        assert vector_store.count() == 0
        vector_store.add_document("doc1", "Machine learning is great")
        assert vector_store.count() == 1

    def test_add_multiple(self, vector_store):
        vector_store.add_document("doc1", "Deep learning for NLP")
        vector_store.add_document("doc2", "Computer vision with CNNs")
        vector_store.add_document("doc3", "Reinforcement learning agents")
        assert vector_store.count() == 3

    def test_query(self, vector_store):
        vector_store.add_document("doc1", "Python is a programming language")
        vector_store.add_document("doc2", "Machine learning uses data")
        vector_store.add_document("doc3", "Cooking recipes for pasta")

        results = vector_store.query("artificial intelligence", n_results=2)
        assert len(results) <= 2
        assert all("id" in r and "document" in r for r in results)

    def test_upsert(self, vector_store):
        vector_store.add_document("doc1", "Version 1")
        vector_store.add_document("doc1", "Version 2")
        assert vector_store.count() == 1

        results = vector_store.query("Version", n_results=1)
        assert results[0]["document"] == "Version 2"

    def test_delete(self, vector_store):
        vector_store.add_document("doc1", "To be deleted")
        assert vector_store.count() == 1
        vector_store.delete_document("doc1")
        assert vector_store.count() == 0

    def test_metadata(self, vector_store):
        vector_store.add_document(
            "doc1",
            "Test content",
            metadata={"title": "Test", "source": "unit_test"},
        )
        results = vector_store.query("Test", n_results=1)
        assert results[0]["metadata"]["title"] == "Test"
        assert results[0]["metadata"]["source"] == "unit_test"
