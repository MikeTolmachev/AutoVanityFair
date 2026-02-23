import os
import sqlite3
import logging
from contextlib import contextmanager
from typing import Generator

logger = logging.getLogger("openlinkedin.database")

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    strategy TEXT DEFAULT 'thought_leadership',
    status TEXT DEFAULT 'draft' CHECK(status IN ('draft','approved','published','rejected')),
    rag_sources TEXT,
    linkedin_url TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    published_at TEXT,
    rejection_reason TEXT
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_post_url TEXT NOT NULL,
    target_post_author TEXT,
    target_post_content TEXT,
    comment_content TEXT NOT NULL,
    strategy TEXT DEFAULT 'generic' CHECK(strategy IN ('grounded','generic')),
    confidence REAL DEFAULT 0.0,
    status TEXT DEFAULT 'draft' CHECK(status IN ('draft','approved','published','rejected')),
    rag_sources TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    published_at TEXT,
    rejection_reason TEXT
);

CREATE TABLE IF NOT EXISTS interaction_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT NOT NULL,
    target_url TEXT,
    status TEXT DEFAULT 'success',
    details TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS content_library (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT,
    tags TEXT,
    personal_thoughts TEXT,
    generated_title TEXT,
    generated_post TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS feed_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_hash TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    url TEXT,
    source_name TEXT,
    source_category TEXT,
    author TEXT,
    published_at TEXT,
    production_score REAL DEFAULT 0.0,
    executive_score REAL DEFAULT 0.0,
    keyword_score REAL DEFAULT 0.0,
    final_score REAL DEFAULT 0.0,
    content_type TEXT,
    matched_keywords TEXT,
    matched_categories TEXT,
    saved_to_library INTEGER DEFAULT 0,
    fetched_at TEXT DEFAULT (datetime('now'))
);
"""


class Database:
    """SQLite connection manager with schema initialization."""

    def __init__(self, db_path: str = "data/openlinkedin.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)
            logger.info("Database schema initialized at %s", self.db_path)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Add columns that may be missing on older databases."""
        existing = {
            row[1]
            for row in conn.execute("PRAGMA table_info(content_library)").fetchall()
        }
        migrations = {
            "personal_thoughts": "ALTER TABLE content_library ADD COLUMN personal_thoughts TEXT",
            "generated_title": "ALTER TABLE content_library ADD COLUMN generated_title TEXT",
            "generated_post": "ALTER TABLE content_library ADD COLUMN generated_post TEXT",
            "updated_at": "ALTER TABLE content_library ADD COLUMN updated_at TEXT",
        }
        for col, sql in migrations.items():
            if col not in existing:
                conn.execute(sql)

    @contextmanager
    def connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
