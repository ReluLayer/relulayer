#!/usr/bin/env python3
"""Base classes for Design of Experiments (DoE) in the ReluLayer engine."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class DatasetSpec:
    """Specification for a real-world validation dataset stored in Layer 3."""

    path: Path
    """Path to the dataset file (CSV, JSONL, or JSON)."""

    def __post_init__(self):
        if isinstance(self.path, str):
            self.path = Path(self.path)

    input_field: str = "input"
    """Field name that contains the model input / prompt context."""

    expected_field: str = "expected"
    """Field name that contains the ground-truth output or label."""

    id_field: str | None = None
    """Optional field name for a stable record identifier."""

    def load(self) -> list[dict[str, Any]]:
        """Load records from the dataset file."""
        if not self.path.is_file():
            raise FileNotFoundError(f"Dataset not found: {self.path}")

        suffix = self.path.suffix.lower()
        with self.path.open("r", encoding="utf-8") as f:
            if suffix == ".json":
                data = json.load(f)
                if not isinstance(data, list):
                    raise ValueError("JSON dataset must be a list of records")
                return data
            if suffix == ".jsonl":
                return [json.loads(line) for line in f if line.strip()]
            if suffix in {".csv", ".tsv"}:
                delimiter = "\t" if suffix == ".tsv" else ","
                return list(csv.DictReader(f, delimiter=delimiter))

        raise ValueError(f"Unsupported dataset format: {suffix}")


@dataclass
class Prediction:
    """One prediction against a single dataset record."""

    record_id: str | int
    input: Any
    expected: Any
    actual: Any
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DoEResult:
    """Aggregated result of an experiment run."""

    experiment_name: str
    predictions: list[Prediction]
    metrics: dict[str, float] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_name": self.experiment_name,
            "parameters": self.parameters,
            "metrics": self.metrics,
            "artifacts": self.artifacts,
            "predictions": [
                {
                    "record_id": p.record_id,
                    "input": p.input,
                    "expected": p.expected,
                    "actual": p.actual,
                    "metadata": p.metadata,
                }
                for p in self.predictions
            ],
        }


class Experiment:
    """
    A Design of Experiments (DoE) run that evaluates a callable against a real dataset.

    The callable may be a model, a DSPy program, an orchestration workflow, or any
    deterministic/probabilistic function that maps an input to an output. Layer 8
    is responsible for measuring the behavior, not for defining the model itself.
    """

    def __init__(
        self,
        name: str,
        dataset: DatasetSpec,
        predictor: Callable[[Any], Any],
        *,
        parameters: dict[str, Any] | None = None,
    ):
        self.name = name
        self.dataset = dataset
        self.predictor = predictor
        self.parameters = parameters or {}

    def run(self, max_records: int | None = None) -> DoEResult:
        """Run the predictor over the dataset and return a DoEResult."""
        records = self.dataset.load()
        if max_records is not None:
            records = records[:max_records]

        predictions: list[Prediction] = []
        for idx, record in enumerate(records):
            record_id = (
                record.get(self.dataset.id_field)
                if self.dataset.id_field
                else idx
            )
            inp = record.get(self.dataset.input_field)
            expected = record.get(self.dataset.expected_field)
            actual = self.predictor(inp)
            predictions.append(
                Prediction(
                    record_id=record_id or idx,
                    input=inp,
                    expected=expected,
                    actual=actual,
                )
            )

        return DoEResult(
            experiment_name=self.name,
            predictions=predictions,
            parameters=self.parameters,
        )
