#!/usr/bin/env python3
"""Example predictor for demonstrating the DoE harness."""

from __future__ import annotations


def predict(input_text: str) -> str:
    """Stub predictor that echoes the input. Replace with a real model call."""
    return f"prediction_for:{input_text[:40]}"
