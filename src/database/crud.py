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

    def set_asset(self, post_id: int, asset_path: str, asset_type: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE posts SET asset_path = ?, asset_type = ?, updated_at = datetime('now') WHERE id = ?",
                (asset_path, asset_type, post_id),
            )

    def clear_asset(self, post_id: int) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE posts SET asset_path = NULL, asset_type = NULL, updated_at = datetime('now') WHERE id = ?",
                (post_id,),
            )


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
        personal_thoughts: Optional[str] = None,
    ) -> int:
        with self.db.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO content_library (title, content, source, tags, personal_thoughts) VALUES (?, ?, ?, ?, ?)",
                (title, content, source, json.dumps(tags) if tags else None, personal_thoughts),
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

    def update_personal_thoughts(self, doc_id: int, thoughts: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE content_library SET personal_thoughts = ?, updated_at = datetime('now') WHERE id = ?",
                (thoughts, doc_id),
            )

    def update_generated_post(self, doc_id: int, title: str, post: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE content_library SET generated_title = ?, generated_post = ?, updated_at = datetime('now') WHERE id = ?",
                (title, post, doc_id),
            )


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

    def get_liked_items(self, limit: int = 100) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT fi.* FROM feed_items fi
                   JOIN user_feedback uf ON fi.id = uf.feed_item_id
                   WHERE uf.feedback = 'liked'
                   ORDER BY fi.final_score DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_by_hash(self, item_hash: str) -> Optional[dict]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM feed_items WHERE item_hash = ?", (item_hash,)
            ).fetchone()
            return dict(row) if row else None


class FeedbackCRUD:
    def __init__(self, db: Database):
        self.db = db

    def set_feedback(self, feed_item_id: int, item_hash: str, feedback: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO user_feedback (feed_item_id, item_hash, feedback)
                   VALUES (?, ?, ?)
                   ON CONFLICT(feed_item_id) DO UPDATE SET
                    feedback = excluded.feedback,
                    created_at = datetime('now')""",
                (feed_item_id, item_hash, feedback),
            )

    def get_feedback(self, feed_item_id: int) -> Optional[str]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT feedback FROM user_feedback WHERE feed_item_id = ?",
                (feed_item_id,),
            ).fetchone()
            return row["feedback"] if row else None

    def get_feedback_map(self) -> dict[str, str]:
        """Return {item_hash: feedback} for all feedback entries."""
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT item_hash, feedback FROM user_feedback"
            ).fetchall()
            return {r["item_hash"]: r["feedback"] for r in rows}

    def get_all_feedback_with_features(self) -> list[dict]:
        """Return feedback joined with feed item features for training."""
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT fi.*, uf.feedback
                   FROM user_feedback uf
                   JOIN feed_items fi ON fi.id = uf.feed_item_id"""
            ).fetchall()
            return [dict(r) for r in rows]

    def get_liked_item_hashes(self) -> set[str]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT item_hash FROM user_feedback WHERE feedback = 'liked'"
            ).fetchall()
            return {r["item_hash"] for r in rows}

    def count_feedback(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT feedback, COUNT(*) as cnt FROM user_feedback GROUP BY feedback"
            ).fetchall()
            return {r["feedback"]: r["cnt"] for r in rows}

    def get_published_item_hashes(self) -> set[str]:
        """Return item_hashes of feed items that were used for publishing.

        A feed item is considered "used for publishing" when a matching
        content_library entry (joined on URL) has a generated_post.
        """
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT fi.item_hash
                   FROM feed_items fi
                   JOIN content_library cl
                     ON fi.url != '' AND fi.url = cl.source
                   WHERE cl.generated_post IS NOT NULL
                     AND cl.generated_post != ''"""
            ).fetchall()
            return {r["item_hash"] for r in rows}

    def get_all_training_data(self) -> list[dict]:
        """Return feedback + published-item data for reranker training.

        Includes explicit user feedback AND feed items used for publishing
        (treated as positive signal).
        """
        with self.db.connect() as conn:
            # Explicit feedback
            rows = conn.execute(
                """SELECT fi.*, uf.feedback
                   FROM user_feedback uf
                   JOIN feed_items fi ON fi.id = uf.feed_item_id"""
            ).fetchall()
            result = [dict(r) for r in rows]

            # Published items without explicit feedback (implicit positive)
            existing_hashes = {r["item_hash"] for r in result}
            pub_rows = conn.execute(
                """SELECT fi.*, 'liked' AS feedback
                   FROM feed_items fi
                   JOIN content_library cl
                     ON fi.url != '' AND fi.url = cl.source
                   WHERE cl.generated_post IS NOT NULL
                     AND cl.generated_post != ''"""
            ).fetchall()
            for r in pub_rows:
                row = dict(r)
                if row["item_hash"] not in existing_hashes:
                    result.append(row)

            return result
