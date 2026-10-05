#!/usr/bin/env python3
"""ROC/AUC analysis for binary classification experiments."""

from __future__ import annotations

from typing import Any


def roc_curve(
    labels: list[Any], scores: list[float], positive_label: Any = True
) -> tuple[list[float], list[float], list[float]]:
    """
    Compute the ROC curve.

    Returns:
        fpr: list of false-positive rates
        tpr: list of true-positive rates
        thresholds: list of thresholds corresponding to each point
    """
    if len(labels) != len(scores):
        raise ValueError("labels and scores must have the same length")
    if not labels:
        return [], [], []

    pairs = sorted(
        ((1 if label == positive_label else 0, score) for label, score in zip(labels, scores)),
        key=lambda x: x[1],
        reverse=True,
    )

    pos_count = sum(1 for label, _ in pairs if label == 1)
    neg_count = len(pairs) - pos_count

    if pos_count == 0 or neg_count == 0:
        return [0.0, 1.0], [0.0, 1.0], [pairs[0][1] if pairs else 0.0]

    tpr = 0.0
    fpr = 0.0
    fprs: list[float] = [0.0]
    tprs: list[float] = [0.0]
    thresholds: list[float] = [pairs[0][1] + 1e-9]

    prev_score = None
    for label, score in pairs:
        if prev_score is not None and score != prev_score:
            fprs.append(fpr / neg_count)
            tprs.append(tpr / pos_count)
            thresholds.append(prev_score)
        if label == 1:
            tpr += 1
        else:
            fpr += 1
        prev_score = score

    fprs.append(fpr / neg_count)
    tprs.append(tpr / pos_count)
    thresholds.append(prev_score if prev_score is not None else 0.0)

    return fprs, tprs, thresholds


def auc_roc(fpr: list[float], tpr: list[float]) -> float:
    """Compute the area under the ROC curve using the trapezoidal rule."""
    if len(fpr) != len(tpr) or len(fpr) < 2:
        return 0.0

    area = 0.0
    for i in range(1, len(fpr)):
        width = fpr[i] - fpr[i - 1]
        height = (tpr[i] + tpr[i - 1]) / 2.0
        area += width * height
    return area
