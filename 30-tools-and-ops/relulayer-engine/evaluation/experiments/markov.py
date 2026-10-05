#!/usr/bin/env python3
"""Markov chain analysis for state transitions in model outputs."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class MarkovModel:
    """First-order discrete Markov model over a finite state alphabet."""

    states: set[str] = field(default_factory=set)
    transitions: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    order: int = 1

    def fit(self, sequences: list[list[str]]) -> "MarkovModel":
        """Build a first-order transition matrix from a list of state sequences."""
        for seq in sequences:
            for state in seq:
                self.states.add(state)
            for i in range(len(seq) - self.order):
                current = seq[i]
                nxt = seq[i + self.order]
                self.transitions[current][nxt] += 1
        return self

    def transition_matrix(self) -> dict[str, dict[str, float]]:
        """Return normalized transition probabilities P(next | current)."""
        matrix: dict[str, dict[str, float]] = {}
        for state in self.states:
            counter = self.transitions.get(state, Counter())
            total = sum(counter.values())
            if total == 0:
                matrix[state] = {s: 1.0 / len(self.states) for s in self.states}
            else:
                matrix[state] = {s: counter.get(s, 0) / total for s in self.states}
        return matrix

    def steady_state(self, iterations: int = 1000) -> dict[str, float]:
        """Approximate the stationary distribution via power iteration."""
        if not self.states:
            return {}

        matrix = self.transition_matrix()
        distribution = {state: 1.0 / len(self.states) for state in self.states}

        for _ in range(iterations):
            new_distribution: dict[str, float] = {state: 0.0 for state in self.states}
            for state in self.states:
                prob = distribution[state]
                if prob == 0.0:
                    continue
                for next_state, transition_prob in matrix[state].items():
                    new_distribution[next_state] += prob * transition_prob
            distribution = new_distribution

        return distribution

    def sequence_log_likelihood(self, sequence: list[str]) -> float:
        """Return the log-likelihood of a state sequence under the learned model."""
        matrix = self.transition_matrix()
        log_likelihood = 0.0
        for i in range(len(sequence) - self.order):
            current = sequence[i]
            nxt = sequence[i + self.order]
            prob = matrix.get(current, {}).get(nxt, 0.0)
            log_likelihood += -1000.0 if prob == 0.0 else math.log(prob)
        return log_likelihood


def extract_label_sequence(
    predictions: list[Any],
    label_fn: Callable[[Any], str | list[str]] | None = None,
) -> list[list[str]]:
    """
    Convert predictions into a list of state label sequences.

    `label_fn` should accept a prediction and return a string label or a list of
    string labels. If None, the prediction itself is cast to a string.
    """
    if label_fn is None:
        label_fn = str

    sequences: list[list[str]] = []
    for p in predictions:
        label = label_fn(p)
        if isinstance(label, list):
            sequences.append([str(x) for x in label])
        else:
            sequences.append([str(label)])
    return sequences
