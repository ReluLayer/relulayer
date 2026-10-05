#!/usr/bin/env python3
"""DoE runner utilities and a lightweight CLI for the ReluLayer Engine."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Any

from .design import DatasetSpec, DoEResult, Experiment
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


def _load_predictor(spec: str):
    """
    Load a predictor callable from a module path.

    Examples:
        my_module.predict
        my_package.my_module:my_function
    """
    if ":" in spec:
        module_path, attr_path = spec.split(":", 1)
    else:
        parts = spec.split(".")
        module_path = ".".join(parts[:-1])
        attr_path = parts[-1]

    module = importlib.import_module(module_path)
    obj = module
    for attr in attr_path.split("."):
        obj = getattr(obj, attr)
    if not callable(obj):
        raise ValueError(f"Predictor spec {spec!r} does not resolve to a callable")
    return obj


def _resolve_scores(predictions: list[Any]) -> list[float] | None:
    """Try to extract float scores from prediction metadata for ROC analysis."""
    scores: list[float] = []
    for p in predictions:
        score = p.metadata.get("score")
        if score is None or not isinstance(score, (int, float)):
            return None
        scores.append(float(score))
    return scores


def evaluate(
    result: DoEResult, *, positive_label: Any | None = None
) -> DoEResult:
    """Compute standard metrics and attach them to a DoEResult."""
    expected = [p.expected for p in result.predictions]
    actual = [p.actual for p in result.predictions]

    # Exact match and token overlap work for any task.
    result.metrics["exact_match"] = exact_match(expected, actual)
    result.metrics["mean_token_overlap"] = sum(
        token_overlap(e, a) for e, a in zip(expected, actual)
    ) / max(len(expected), 1)

    # Hallucination score against expected/ground truth.
    result.metrics["mean_hallucination_score"] = sum(
        hallucination_score(a, e) for e, a in zip(expected, actual)
    ) / max(len(expected), 1)

    # Binary classification metrics only when labels are genuinely binary
    # or when the caller explicitly asks for a positive label.
    labels = set(expected) | set(actual)
    if positive_label is not None or labels <= {True, False, "true", "false", "yes", "no", "1", "0", 1, 0}:
        pos_label = positive_label if positive_label is not None else True
        try:
            cm = confusion_matrix(expected, actual, positive_label=pos_label)
            result.metrics["precision"] = precision(expected, actual, positive_label=pos_label)
            result.metrics["recall"] = recall(expected, actual, positive_label=pos_label)
            result.metrics["f1"] = f1_score(expected, actual, positive_label=pos_label)
            result.metrics["accuracy"] = accuracy(expected, actual)
            result.metrics["tp"] = float(cm["tp"])
            result.metrics["tn"] = float(cm["tn"])
            result.metrics["fp"] = float(cm["fp"])
            result.metrics["fn"] = float(cm["fn"])
        except Exception:
            pass

    # ROC/AUC if predictions carry continuous scores in metadata.
    scores = _resolve_scores(result.predictions)
    if scores is not None and (positive_label is not None or labels <= {True, False}):
        try:
            fpr, tpr, thresholds = roc_curve(expected, scores, positive_label=positive_label or True)
            result.metrics["auc_roc"] = auc_roc(fpr, tpr)
            result.artifacts["roc"] = {
                "fpr": fpr,
                "tpr": tpr,
                "thresholds": thresholds,
            }
        except Exception:
            pass

    # Markov transition analysis if labels are discrete states.
    try:
        sequences = extract_label_sequence(actual)
        if sequences and any(len(seq) > 1 for seq in sequences):
            model = MarkovModel().fit(sequences)
            result.artifacts["markov_transition_matrix"] = model.transition_matrix()
            result.artifacts["markov_steady_state"] = model.steady_state()
    except Exception:
        pass

    return result


def run_experiment_from_config(config: dict[str, Any]) -> DoEResult:
    """Run an experiment defined by a plain dict config."""
    dataset = DatasetSpec(
        path=Path(config["dataset"]["path"]),
        input_field=config["dataset"].get("input_field", "input"),
        expected_field=config["dataset"].get("expected_field", "expected"),
        id_field=config["dataset"].get("id_field"),
    )
    predictor = _load_predictor(config["predictor"])
    experiment = Experiment(
        name=config["name"],
        dataset=dataset,
        predictor=predictor,
        parameters=config.get("parameters", {}),
    )
    result = experiment.run(max_records=config.get("max_records"))
    return evaluate(result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a ReluLayer DoE experiment")
    parser.add_argument("config", type=Path, help="Path to YAML or JSON experiment config")
    parser.add_argument("--output", "-o", type=Path, help="Path to write results JSON")
    parser.add_argument(
        "--max-records", type=int, default=None, help="Limit number of dataset records"
    )
    args = parser.parse_args()

    config_text = args.config.read_text(encoding="utf-8")
    if args.config.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:
            raise ImportError("PyYAML is required for YAML configs") from exc
        config = yaml.safe_load(config_text)
    else:
        config = json.loads(config_text)

    if args.max_records is not None:
        config["max_records"] = args.max_records

    result = run_experiment_from_config(config)
    output = args.output or Path(f"{result.experiment_name}_results.json")
    output.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    print(f"Results written to {output}")
    print(json.dumps(result.metrics, indent=2))


if __name__ == "__main__":
    main()
