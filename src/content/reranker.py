"""
CatBoost ML reranker for feed content.

Uses user feedback (like/dislike) to train a classifier that reranks
feed items. The existing rule-based scores (production, executive, keyword)
serve as input features rather than being replaced.

Falls back to rule-based scoring when insufficient training data exists.
"""

import json
import logging
import os

from src.content.content_filter import ScoredContent
from src.content.embeddings import DEFAULT_DIMENSIONALITY

logger = logging.getLogger("openlinkedin.reranker")

EMBEDDING_DIM = DEFAULT_DIMENSIONALITY
EMBEDDING_FEATURE_NAMES = [f"emb_{i}" for i in range(EMBEDDING_DIM)]

FEATURE_NAMES = [
    "production_score",
    "executive_score",
    "keyword_score",
    "type_multiplier",
    "freshness_multiplier",
    "title_length",
    "content_length",
    "num_matched_keywords",
    "num_matched_categories",
    "has_url",
    "rule_based_score",
] + EMBEDDING_FEATURE_NAMES

CAT_FEATURE_NAMES = [
    "content_type",
    "source",
]

ALL_FEATURE_NAMES = FEATURE_NAMES + CAT_FEATURE_NAMES


class FeedReranker:
    """CatBoost-based feed content reranker with cold-start fallback."""

    def __init__(
        self,
        model_path: str = "data/reranker_model.cbm",
        min_training_samples: int = 20,
    ):
        self.model_path = model_path
        self.min_training_samples = min_training_samples
        self._model = None
        self._stats: dict = {}
        self._load_model()

    def _load_model(self) -> None:
        """Load a previously trained model from disk if it exists."""
        if not os.path.exists(self.model_path):
            return
        try:
            from catboost import CatBoostClassifier

            self._model = CatBoostClassifier()
            self._model.load_model(self.model_path)
            # Load stats if saved alongside model
            stats_path = self.model_path + ".stats.json"
            if os.path.exists(stats_path):
                with open(stats_path) as f:
                    self._stats = json.load(f)
            logger.info("Loaded reranker model from %s", self.model_path)
        except Exception as e:
            logger.warning("Failed to load reranker model: %s", e)
            self._model = None

    @property
    def is_trained(self) -> bool:
        return self._model is not None

    def extract_features(self, item: ScoredContent) -> dict:
        """Extract feature dict from a ScoredContent item."""
        return item.to_feature_dict()

    def extract_features_from_db_row(self, row: dict) -> dict:
        """Extract feature dict from a database feed_items row."""
        d = {
            "production_score": row.get("production_score", 0.0),
            "executive_score": row.get("executive_score", 0.0),
            "keyword_score": row.get("keyword_score", 0.0),
            "type_multiplier": 1.0,  # not stored in DB, default
            "freshness_multiplier": 1.0,
            "title_length": len(row.get("title", "").split()),
            "content_length": len(row.get("content", "").split()),
            "num_matched_keywords": len(
                json.loads(row["matched_keywords"])
                if row.get("matched_keywords")
                else []
            ),
            "num_matched_categories": len(
                json.loads(row["matched_categories"])
                if row.get("matched_categories")
                else []
            ),
            "has_url": 1 if row.get("url") else 0,
            "rule_based_score": row.get("final_score", 0.0),
            "content_type": row.get("content_type", "general"),
            "source": row.get("source_name", ""),
        }
        # Parse stored embedding or zero-fill
        emb = [0.0] * EMBEDDING_DIM
        if row.get("embedding"):
            try:
                emb = json.loads(row["embedding"])
            except (json.JSONDecodeError, TypeError):
                pass
        for i in range(EMBEDDING_DIM):
            d[f"emb_{i}"] = emb[i] if i < len(emb) else 0.0
        return d

    def train(
        self,
        training_data: list[dict],
        feedback_map: dict[str, str],
    ) -> dict:
        """Train the reranker on feedback data with cross-validation.

        Args:
            training_data: List of DB rows from feed_items joined with feedback.
            feedback_map: {item_hash: 'liked'|'disliked'} mapping.

        Returns:
            Dict with training and cross-validation metrics.
        """
        import random
        from catboost import CatBoostClassifier, Pool

        # Build feature matrix and labels
        features = []
        labels = []
        for row in training_data:
            item_hash = row.get("item_hash", "")
            fb = row.get("feedback") or feedback_map.get(item_hash)
            if fb not in ("liked", "disliked"):
                continue
            feat = self.extract_features_from_db_row(row)
            features.append(feat)
            labels.append(1 if fb == "liked" else 0)

        if len(labels) < self.min_training_samples:
            return {
                "status": "insufficient_data",
                "samples": len(labels),
                "min_required": self.min_training_samples,
            }

        feature_matrix = [[row[f] for f in ALL_FEATURE_NAMES] for row in features]
        cat_indices = [ALL_FEATURE_NAMES.index(c) for c in CAT_FEATURE_NAMES]

        # --- Cross-validation ---
        n_folds = min(5, len(labels))
        indices = list(range(len(labels)))
        random.seed(42)
        random.shuffle(indices)

        cv_accuracies = []
        cv_precisions = []
        cv_recalls = []
        cv_f1s = []
        fold_size = len(indices) // n_folds

        for fold in range(n_folds):
            val_start = fold * fold_size
            val_end = val_start + fold_size if fold < n_folds - 1 else len(indices)
            val_idx = indices[val_start:val_end]
            train_idx = indices[:val_start] + indices[val_end:]

            if not val_idx or not train_idx:
                continue

            train_X = [feature_matrix[i] for i in train_idx]
            train_y = [labels[i] for i in train_idx]
            val_X = [feature_matrix[i] for i in val_idx]
            val_y = [labels[i] for i in val_idx]

            # Skip folds with single-class training data
            if len(set(train_y)) < 2:
                continue

            fold_model = CatBoostClassifier(
                iterations=200,
                depth=4,
                learning_rate=0.1,
                loss_function="Logloss",
                verbose=0,
                auto_class_weights="Balanced",
            )

            train_pool = Pool(
                train_X, label=train_y,
                feature_names=ALL_FEATURE_NAMES,
                cat_features=cat_indices,
            )
            val_pool = Pool(
                val_X, label=val_y,
                feature_names=ALL_FEATURE_NAMES,
                cat_features=cat_indices,
            )
            fold_model.fit(train_pool, eval_set=val_pool)

            preds = fold_model.predict(val_pool).flatten().tolist()
            tp = sum(1 for p, a in zip(preds, val_y) if p == 1 and a == 1)
            fp = sum(1 for p, a in zip(preds, val_y) if p == 1 and a == 0)
            fn = sum(1 for p, a in zip(preds, val_y) if p == 0 and a == 1)
            correct = sum(1 for p, a in zip(preds, val_y) if p == a)

            accuracy = correct / len(val_y)
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

            cv_accuracies.append(accuracy)
            cv_precisions.append(precision)
            cv_recalls.append(recall)
            cv_f1s.append(f1)

            logger.info(
                "CV fold %d/%d: accuracy=%.3f precision=%.3f recall=%.3f f1=%.3f",
                fold + 1, n_folds, accuracy, precision, recall, f1,
            )

        cv_metrics = {}
        if cv_accuracies:
            cv_metrics = {
                "folds": n_folds,
                "accuracy": round(sum(cv_accuracies) / len(cv_accuracies), 4),
                "precision": round(sum(cv_precisions) / len(cv_precisions), 4),
                "recall": round(sum(cv_recalls) / len(cv_recalls), 4),
                "f1": round(sum(cv_f1s) / len(cv_f1s), 4),
            }
            logger.info("CV mean: %s", cv_metrics)

        # --- Train final model on ALL data ---
        full_pool = Pool(
            feature_matrix,
            label=labels,
            feature_names=ALL_FEATURE_NAMES,
            cat_features=cat_indices,
        )

        model = CatBoostClassifier(
            iterations=200,
            depth=4,
            learning_rate=0.1,
            loss_function="Logloss",
            verbose=0,
            auto_class_weights="Balanced",
        )
        model.fit(full_pool)

        # Save model
        os.makedirs(os.path.dirname(self.model_path) or ".", exist_ok=True)
        model.save_model(self.model_path)
        self._model = model

        # Compute stats
        liked_count = sum(labels)
        disliked_count = len(labels) - liked_count
        importance = dict(
            zip(ALL_FEATURE_NAMES, model.get_feature_importance().tolist())
        )
        importance = dict(
            sorted(importance.items(), key=lambda x: x[1], reverse=True)
        )

        self._stats = {
            "status": "trained",
            "total_samples": len(labels),
            "liked": liked_count,
            "disliked": disliked_count,
            "cross_validation": cv_metrics,
            "feature_importance": importance,
        }

        # Persist stats
        stats_path = self.model_path + ".stats.json"
        with open(stats_path, "w") as f:
            json.dump(self._stats, f, indent=2)

        logger.info(
            "Reranker trained on %d samples (%d liked, %d disliked)",
            len(labels),
            liked_count,
            disliked_count,
        )
        return self._stats

    def rerank(self, items: list[ScoredContent]) -> list[ScoredContent]:
        """Rerank items using ML model predictions.

        Falls back to rule-based final_score ordering if model is not trained.
        """
        if not self.is_trained or not items:
            return sorted(items, key=lambda x: x.final_score, reverse=True)

        try:
            from catboost import Pool

            feature_dicts = [self.extract_features(item) for item in items]
            feature_matrix = [
                [row[f] for f in ALL_FEATURE_NAMES] for row in feature_dicts
            ]
            cat_indices = [ALL_FEATURE_NAMES.index(c) for c in CAT_FEATURE_NAMES]

            pool = Pool(
                feature_matrix,
                feature_names=ALL_FEATURE_NAMES,
                cat_features=cat_indices,
            )
            probas = self._model.predict_proba(pool)

            # Use P(liked) as the ML score, scale to 0-100
            for item, proba in zip(items, probas):
                ml_score = proba[1] * 100  # P(liked=1)
                item.final_score = round(ml_score, 2)

            items.sort(key=lambda x: x.final_score, reverse=True)
            return items

        except Exception as e:
            logger.warning("Reranker prediction failed, using rule-based: %s", e)
            return sorted(items, key=lambda x: x.final_score, reverse=True)

    def rescore_db_rows(self, rows: list[dict]) -> list[tuple[int, float]]:
        """Score DB rows with the trained model. Returns list of (id, new_score)."""
        if not self.is_trained or not rows:
            return []
        try:
            from catboost import Pool

            feature_dicts = [self.extract_features_from_db_row(r) for r in rows]
            feature_matrix = [
                [row[f] for f in ALL_FEATURE_NAMES] for row in feature_dicts
            ]
            cat_indices = [ALL_FEATURE_NAMES.index(c) for c in CAT_FEATURE_NAMES]
            pool = Pool(
                feature_matrix,
                feature_names=ALL_FEATURE_NAMES,
                cat_features=cat_indices,
            )
            probas = self._model.predict_proba(pool)
            results = []
            for row, proba in zip(rows, probas):
                ml_score = round(proba[1] * 100, 2)
                results.append((row["id"], ml_score))
            return results
        except Exception as e:
            logger.warning("Rescore failed: %s", e)
            return []

    def get_stats(self) -> dict:
        """Return model statistics."""
        if not self._stats:
            return {
                "status": "not_trained",
                "model_exists": os.path.exists(self.model_path),
            }
        return self._stats
