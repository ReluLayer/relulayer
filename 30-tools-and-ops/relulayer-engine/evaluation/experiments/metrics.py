#!/usr/bin/env python3
"""Standard DoE metrics for the ReluLayer Engine evaluation layer."""

from __future__ import annotations

from collections import Counter
from typing import Any


def _to_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return set(value.lower().split())
    if isinstance(value, (list, tuple, set)):
        return {str(v).lower() for v in value}
    return {str(value).lower()}


def confusion_matrix(
    expected: list[Any], actual: list[Any], positive_label: Any = True
) -> dict[str, int]:
    """Return TP, TN, FP, FN counts for a binary classification task."""
    tp = tn = fp = fn = 0
    for e, a in zip(expected, actual):
        e_pos = e == positive_label
        a_pos = a == positive_label
        if e_pos and a_pos:
            tp += 1
        elif not e_pos and not a_pos:
            tn += 1
        elif not e_pos and a_pos:
            fp += 1
        else:
            fn += 1
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn}


def precision(expected: list[Any], actual: list[Any], positive_label: Any = True) -> float:
    cm = confusion_matrix(expected, actual, positive_label)
    denom = cm["tp"] + cm["fp"]
    return cm["tp"] / denom if denom else 0.0


def recall(expected: list[Any], actual: list[Any], positive_label: Any = True) -> float:
    cm = confusion_matrix(expected, actual, positive_label)
    denom = cm["tp"] + cm["fn"]
    return cm["tp"] / denom if denom else 0.0


def f1_score(expected: list[Any], actual: list[Any], positive_label: Any = True) -> float:
    p = precision(expected, actual, positive_label)
    r = recall(expected, actual, positive_label)
    denom = p + r
    return 2 * p * r / denom if denom else 0.0


def accuracy(expected: list[Any], actual: list[Any]) -> float:
    if not expected:
        return 0.0
    return sum(1 for e, a in zip(expected, actual) if e == a) / len(expected)


def hallucination_score(prediction: Any, reference: Any) -> float:
    """
    Return a hallucination score in [0, 1] where 1 means the prediction is
    entirely unsupported by the reference.

    This default implementation uses a simple token-overlap heuristic. Replace it
    with an embedding-based or entailment-based scorer for production use.
    """
    pred_set = _to_set(prediction)
    ref_set = _to_set(reference)
    if not pred_set:
        return 0.0
    unsupported = pred_set - ref_set
    return len(unsupported) / len(pred_set)


def token_overlap(prediction: Any, reference: Any) -> float:
    """Jaccard-style token overlap between prediction and reference."""
    pred_set = _to_set(prediction)
    ref_set = _to_set(reference)
    if not pred_set and not ref_set:
        return 1.0
    union = pred_set | ref_set
    if not union:
        return 0.0
    return len(pred_set & ref_set) / len(union)


def exact_match(expected: list[Any], actual: list[Any]) -> float:
    if not expected:
        return 0.0
    return sum(1 for e, a in zip(expected, actual) if e == a) / len(expected)
