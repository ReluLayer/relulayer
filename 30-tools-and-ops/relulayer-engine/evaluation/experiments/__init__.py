"""ReluLayer Engine — Design of Experiments (DoE) harness (Layer 8)."""

from __future__ import annotations

from .design import DatasetSpec, DoEResult, Experiment, Prediction
from .markov import MarkovModel, extract_label_sequence
from .metrics import (
    accuracy,
    confusion_matrix,
    exact_match,
    f1_score,
    hallucination_score,
    precision,
    recall,
    token_overlap,
)
from .roc import auc_roc, roc_curve
from .runner import evaluate, run_experiment_from_config

__all__ = [
    "accuracy",
    "auc_roc",
    "confusion_matrix",
    "DatasetSpec",
    "DoEResult",
    "exact_match",
    "evaluate",
    "Experiment",
    "extract_label_sequence",
    "f1_score",
    "hallucination_score",
    "MarkovModel",
    "precision",
    "Prediction",
    "recall",
    "roc_curve",
    "run_experiment_from_config",
    "token_overlap",
]
