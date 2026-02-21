import os
import sys
import tempfile

import pytest

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.database.models import Database
from src.database.crud import PostCRUD, CommentCRUD, InteractionLogCRUD, ContentLibraryCRUD
from src.content.generator import AIProvider, GenerationResult


class MockAIProvider(AIProvider):
    """Mock AI provider for testing."""

    def __init__(self, response: str = "Mock generated content.", confidence: float = 0.8):
        self._response = response
        self._confidence = confidence

    def generate(self, system_prompt: str, user_prompt: str) -> GenerationResult:
        return GenerationResult(
            content=self._response,
            model="mock-model",
            provider="mock",
            tokens_used=100,
        )

    def generate_with_confidence(
        self, system_prompt: str, user_prompt: str
    ) -> GenerationResult:
        return GenerationResult(
            content=self._response,
            model="mock-model",
            provider="mock",
            tokens_used=100,
            confidence=self._confidence,
        )


@pytest.fixture
def tmp_db(tmp_path):
    """Create an in-memory-like SQLite database in a temp directory."""
    db_path = str(tmp_path / "test.db")
    return Database(db_path)


@pytest.fixture
def post_crud(tmp_db):
    return PostCRUD(tmp_db)


@pytest.fixture
def comment_crud(tmp_db):
    return CommentCRUD(tmp_db)


@pytest.fixture
def log_crud(tmp_db):
    return InteractionLogCRUD(tmp_db)


@pytest.fixture
def content_crud(tmp_db):
    return ContentLibraryCRUD(tmp_db)


@pytest.fixture
def mock_ai():
    return MockAIProvider()


@pytest.fixture
def mock_ai_long():
    return MockAIProvider(
        response="A" * 200 + " This is a longer mock post for validation testing."
    )
