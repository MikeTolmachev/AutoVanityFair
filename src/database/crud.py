import json
import logging
from typing import Optional

from src.database.models import Database

logger = logging.getLogger("openlinkedin.crud")


class PostCRUD:
    def __init__(self, db: Database):
        self.db = db

    def create(
        self,
        content: str,
        strategy: str = "thought_leadership",
        rag_sources: Optional[list[str]] = None,
    ) -> int:
        with self.db.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO posts (content, strategy, rag_sources) VALUES (?, ?, ?)",
                (content, strategy, json.dumps(rag_sources) if rag_sources else None),
            )
            return cursor.lastrowid

    def get(self, post_id: int) -> Optional[dict]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
            return dict(row) if row else None

    def list_by_status(self, status: str, limit: int = 50) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM posts WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def update_status(
        self, post_id: int, status: str, reason: Optional[str] = None
    ) -> None:
        with self.db.connect() as conn:
            if status == "rejected" and reason:
                conn.execute(
                    "UPDATE posts SET status = ?, rejection_reason = ?, updated_at = datetime('now') WHERE id = ?",
                    (status, reason, post_id),
                )
            elif status == "published":
                conn.execute(
                    "UPDATE posts SET status = ?, published_at = datetime('now'), updated_at = datetime('now') WHERE id = ?",
                    (status, post_id),
                )
            else:
                conn.execute(
                    "UPDATE posts SET status = ?, updated_at = datetime('now') WHERE id = ?",
                    (status, post_id),
                )

    def update_content(self, post_id: int, content: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE posts SET content = ?, updated_at = datetime('now') WHERE id = ?",
                (content, post_id),
            )

    def set_linkedin_url(self, post_id: int, url: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE posts SET linkedin_url = ? WHERE id = ?",
                (url, post_id),
            )

    def count_by_status(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM posts GROUP BY status"
            ).fetchall()
            return {r["status"]: r["cnt"] for r in rows}

    def count_published_today(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM posts WHERE status = 'published' AND date(published_at) = date('now')"
            ).fetchone()
            return row["cnt"]


class CommentCRUD:
    def __init__(self, db: Database):
        self.db = db

    def create(
        self,
        target_post_url: str,
        comment_content: str,
        target_post_author: Optional[str] = None,
        target_post_content: Optional[str] = None,
        strategy: str = "generic",
        confidence: float = 0.0,
        rag_sources: Optional[list[str]] = None,
    ) -> int:
        with self.db.connect() as conn:
            cursor = conn.execute(
                """INSERT INTO comments
                   (target_post_url, comment_content, target_post_author, target_post_content,
                    strategy, confidence, rag_sources)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    target_post_url,
                    comment_content,
                    target_post_author,
                    target_post_content,
                    strategy,
                    confidence,
                    json.dumps(rag_sources) if rag_sources else None,
                ),
            )
            return cursor.lastrowid

    def get(self, comment_id: int) -> Optional[dict]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM comments WHERE id = ?", (comment_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_by_status(self, status: str, limit: int = 50) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM comments WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def update_status(
        self, comment_id: int, status: str, reason: Optional[str] = None
    ) -> None:
        with self.db.connect() as conn:
            if status == "rejected" and reason:
                conn.execute(
                    "UPDATE comments SET status = ?, rejection_reason = ?, updated_at = datetime('now') WHERE id = ?",
                    (status, reason, comment_id),
                )
            elif status == "published":
                conn.execute(
                    "UPDATE comments SET status = ?, published_at = datetime('now'), updated_at = datetime('now') WHERE id = ?",
                    (status, comment_id),
                )
            else:
                conn.execute(
                    "UPDATE comments SET status = ?, updated_at = datetime('now') WHERE id = ?",
                    (status, comment_id),
                )

    def update_content(self, comment_id: int, content: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE comments SET comment_content = ?, updated_at = datetime('now') WHERE id = ?",
                (content, comment_id),
            )

    def count_published_today(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM comments WHERE status = 'published' AND date(published_at) = date('now')"
            ).fetchone()
            return row["cnt"]


class InteractionLogCRUD:
    def __init__(self, db: Database):
        self.db = db

    def log(
        self,
        action_type: str,
        target_url: Optional[str] = None,
        status: str = "success",
        details: Optional[str] = None,
    ) -> int:
        with self.db.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO interaction_log (action_type, target_url, status, details) VALUES (?, ?, ?, ?)",
                (action_type, target_url, status, details),
            )
            return cursor.lastrowid

    def get_recent(self, limit: int = 50) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM interaction_log ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def count_by_action(self, days: int = 7) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT action_type, COUNT(*) as cnt FROM interaction_log
                   WHERE created_at >= datetime('now', ? || ' days')
                   GROUP BY action_type""",
                (f"-{days}",),
            ).fetchall()
            return {r["action_type"]: r["cnt"] for r in rows}


class ContentLibraryCRUD:
    def __init__(self, db: Database):
        self.db = db

    def add(
        self,
        title: str,
        content: str,
        source: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> int:
        with self.db.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO content_library (title, content, source, tags) VALUES (?, ?, ?, ?)",
                (title, content, source, json.dumps(tags) if tags else None),
            )
            return cursor.lastrowid

    def get(self, doc_id: int) -> Optional[dict]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM content_library WHERE id = ?", (doc_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_all(self, limit: int = 100) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM content_library ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def delete(self, doc_id: int) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM content_library WHERE id = ?", (doc_id,))

    def count(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM content_library").fetchone()
            return row["cnt"]


class FeedItemCRUD:
    def __init__(self, db: Database):
        self.db = db

    def upsert(
        self,
        item_hash: str,
        title: str,
        content: str = "",
        url: str = "",
        source_name: str = "",
        source_category: str = "",
        author: str = "",
        published_at: Optional[str] = None,
        production_score: float = 0.0,
        executive_score: float = 0.0,
        keyword_score: float = 0.0,
        final_score: float = 0.0,
        content_type: str = "",
        matched_keywords: Optional[list[str]] = None,
        matched_categories: Optional[list[str]] = None,
    ) -> int:
        with self.db.connect() as conn:
            cursor = conn.execute(
                """INSERT INTO feed_items
                   (item_hash, title, content, url, source_name, source_category,
                    author, published_at, production_score, executive_score,
                    keyword_score, final_score, content_type,
                    matched_keywords, matched_categories)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(item_hash) DO UPDATE SET
                    final_score = excluded.final_score,
                    fetched_at = datetime('now')""",
                (
                    item_hash,
                    title,
                    content,
                    url,
                    source_name,
                    source_category,
                    author,
                    published_at,
                    production_score,
                    executive_score,
                    keyword_score,
                    final_score,
                    content_type,
                    json.dumps(matched_keywords) if matched_keywords else None,
                    json.dumps(matched_categories) if matched_categories else None,
                ),
            )
            return cursor.lastrowid

    def get_top_scored(self, limit: int = 20, min_score: float = 0.0) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT * FROM feed_items
                   WHERE final_score >= ?
                   ORDER BY final_score DESC LIMIT ?""",
                (min_score, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_by_source(self, source_name: str, limit: int = 20) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM feed_items WHERE source_name = ? ORDER BY final_score DESC LIMIT ?",
                (source_name, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_saved(self, item_id: int) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE feed_items SET saved_to_library = 1 WHERE id = ?",
                (item_id,),
            )

    def count(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM feed_items").fetchone()
            return row["cnt"]

    def count_by_source(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT source_name, COUNT(*) as cnt FROM feed_items GROUP BY source_name"
            ).fetchall()
            return {r["source_name"]: r["cnt"] for r in rows}
