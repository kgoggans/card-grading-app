"""
ML Model for Card Grade Prediction

GradientBoostingRegressor trained on per-category CV scores (front + back)
to predict PSA grade. Falls back gracefully when insufficient training data.
"""

import os
import json
import numpy as np
from datetime import datetime

try:
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    from sklearn.model_selection import cross_val_score
    import joblib
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(_DIR, 'training_data', 'gb_model.pkl')
MODEL_META_PATH = os.path.join(_DIR, 'training_data', 'gb_model_meta.json')

MIN_SAMPLES_FOR_ML = 10

# PSA grade → midpoint on 100-1000 scale
_GRADE_TO_SCORE = {
    10.0: 970, 9.0: 925, 8.5: 875, 8.0: 825,
    7.5: 775, 7.0: 725, 6.5: 675, 6.0: 625, 5.5: 575,
    5.0: 525, 4.5: 475, 4.0: 425, 3.5: 375, 3.0: 325,
    2.5: 275, 2.0: 225, 1.5: 175, 1.0: 125
}

_VALID_PSA_GRADES = sorted(_GRADE_TO_SCORE.keys())


def build_feature_vector(front_scores: dict, back_scores: dict) -> np.ndarray:
    """
    Build 12-element feature vector from per-side category scores (100-1000 scale).
    Features: front 4 categories + back 4 categories + abs differences = 12 total.
    """
    cats = ['corners', 'edges', 'surface', 'centering']
    front = [float(front_scores.get(c, 500)) for c in cats]
    back  = [float(back_scores.get(c, 500))  for c in cats]
    diffs = [abs(f - b) for f, b in zip(front, back)]
    return np.array(front + back + diffs, dtype=np.float32)


def _snap_to_valid_grade(raw: float) -> float:
    """Round raw prediction to nearest valid PSA grade."""
    return min(_VALID_PSA_GRADES, key=lambda g: abs(g - raw))


class CardGradingModel:
    """Wrapper around a sklearn Pipeline (scaler + GBR)."""

    def __init__(self):
        self._pipeline = None
        self._meta: dict = {}
        self._load()

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #

    def _load(self):
        if not _SKLEARN_AVAILABLE:
            return
        try:
            if os.path.exists(MODEL_PATH):
                self._pipeline = joblib.load(MODEL_PATH)
            if os.path.exists(MODEL_META_PATH):
                with open(MODEL_META_PATH) as f:
                    self._meta = json.load(f)
        except Exception:
            self._pipeline = None
            self._meta = {}

    def _save(self):
        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        joblib.dump(self._pipeline, MODEL_PATH)
        with open(MODEL_META_PATH, 'w') as f:
            json.dump(self._meta, f, indent=2)

    # ------------------------------------------------------------------ #
    # Training                                                             #
    # ------------------------------------------------------------------ #

    def train(self, samples: list) -> dict:
        """
        Train on samples = list of (front_scores_dict, back_scores_dict, psa_grade_float)
        or (front_scores_dict, back_scores_dict, psa_grade_float, weight_float).
        Personal scans should pass weight=5.0; eBay imports default to weight=1.0.
        Returns meta dict with accuracy info or raises ValueError.
        """
        if not _SKLEARN_AVAILABLE:
            raise ValueError("scikit-learn is not installed. Run: pip install scikit-learn joblib")

        X_list, y_list, w_list = [], [], []
        for entry in samples:
            try:
                if len(entry) == 4:
                    front_scores, back_scores, psa_grade, weight = entry
                else:
                    front_scores, back_scores, psa_grade = entry
                    weight = 1.0
                X_list.append(build_feature_vector(front_scores, back_scores))
                y_list.append(float(psa_grade))
                w_list.append(float(weight))
            except Exception:
                continue

        if len(X_list) < MIN_SAMPLES_FOR_ML:
            raise ValueError(
                f"Need at least {MIN_SAMPLES_FOR_ML} valid samples (have {len(X_list)}). "
                "Keep adding labeled cards and try again."
            )

        X = np.array(X_list)
        y = np.array(y_list)
        w = np.array(w_list)

        pipeline = Pipeline([
            ('scaler', StandardScaler()),
            ('gbr', GradientBoostingRegressor(
                n_estimators=300,
                learning_rate=0.04,
                max_depth=4,
                subsample=0.8,
                min_samples_leaf=2,
                validation_fraction=0.1 if len(X) >= 20 else None,
                n_iter_no_change=20 if len(X) >= 20 else None,
                random_state=42,
            ))
        ])

        # Cross-validation when possible
        cv_mae = None
        if len(X) >= 20:
            n_folds = min(5, len(X) // 4)
            cv_scores = cross_val_score(
                pipeline, X, y, cv=n_folds,
                scoring='neg_mean_absolute_error'
            )
            cv_mae = float(-cv_scores.mean())

        pipeline.fit(X, y, gbr__sample_weight=w)
        self._pipeline = pipeline

        train_pred = pipeline.predict(X)
        train_mae = float(np.mean(np.abs(train_pred - y)))

        # Grade-level accuracy (within ±0.5 grade)
        correct = sum(1 for p, t in zip(train_pred, y)
                      if abs(_snap_to_valid_grade(p) - t) <= 0.5)
        grade_acc = round(100.0 * correct / len(y), 1)

        self._meta = {
            'n_samples':          len(X),
            'train_mae':          round(train_mae, 3),
            'cv_mae':             round(cv_mae, 3) if cv_mae is not None else None,
            'grade_accuracy_pct': grade_acc,
            'trained_at':         datetime.utcnow().isoformat(),
        }

        self._save()
        return dict(self._meta)

    # ------------------------------------------------------------------ #
    # Prediction                                                           #
    # ------------------------------------------------------------------ #

    def predict(self, front_scores: dict, back_scores: dict) -> tuple:
        """
        Predict PSA grade from category scores.
        Returns (snapped_grade: float, raw_prediction: float) or raises ValueError.
        """
        if self._pipeline is None:
            raise ValueError("Model not trained yet")

        features = build_feature_vector(front_scores, back_scores).reshape(1, -1)
        raw = float(self._pipeline.predict(features)[0])
        raw = max(1.0, min(10.0, raw))
        return _snap_to_valid_grade(raw), round(raw, 2)

    # ------------------------------------------------------------------ #
    # Status                                                               #
    # ------------------------------------------------------------------ #

    @property
    def is_trained(self) -> bool:
        return self._pipeline is not None

    def status(self) -> dict:
        return {
            'is_trained':         self.is_trained,
            'sklearn_available':  _SKLEARN_AVAILABLE,
            'n_samples':          self._meta.get('n_samples', 0),
            'train_mae':          self._meta.get('train_mae'),
            'cv_mae':             self._meta.get('cv_mae'),
            'grade_accuracy_pct': self._meta.get('grade_accuracy_pct'),
            'trained_at':         self._meta.get('trained_at'),
        }


# Module-level singleton (loaded once at import time)
_model_instance = None  # CardGradingModel singleton


def get_model():
    global _model_instance
    if _model_instance is None:
        _model_instance = CardGradingModel()
    return _model_instance


def reload_model():
    """Force a reload from disk (call after training completes)."""
    global _model_instance
    _model_instance = CardGradingModel()
    return _model_instance
