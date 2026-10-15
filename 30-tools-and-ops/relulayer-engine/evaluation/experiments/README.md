# ReluLayer Engine — Design of Experiments (DoE) Harness

This directory implements **Layer 8 — Evaluation, Experimentation & Governance** for the ReluLayer engine. It runs models, prompts, architectures, and tool chains against **real-world datasets** and produces statistical evidence that can be committed to the repository.

## Goals

- Compare model/prompt variants against ground-truth data, not synthetic hand-waves.
- Detect hallucinations by comparing model outputs against source context or expected answers.
- Support rigorous statistical techniques: **ROC/AUC**, **Markov Chain state-transition analysis**, confusion matrices, and any other method justified by the problem domain.
- Make experiments reproducible: every result is a JSON artifact with parameters, metrics, and predictions.

## Layer 8 boundary rules

- **Datasets live in Layer 3** (`data/`). The DoE harness loads them by path; it does not store raw data here.
- **Predictors are injected**, not defined here. The harness calls a model, DSPy program, or deterministic function as a black box.
- **Results are written to Layer 8** (`evaluation/experiments/results/` by convention) and should be version-controlled or archived according to the project retention policy.
- **No LLM client imports** in the core metrics modules. Statistical analysis is deterministic.

## Quick start

### 1. Prepare a real dataset in Layer 3

```text
ReluLayer/30-tools-and-ops/relulayer-engine/data/
└── example_deck_classifier.jsonl
```

Each record needs at least an `input` and an `expected` field:

```json
{"input": "Extract the CEO from this pitch deck.", "expected": "Jane Doe", "context": "..."}
```

### 2. Write a predictor

A predictor is any callable that takes a single input and returns a prediction. For classification, it can return a label. For generative tasks, it can return a string.

```python
# evaluation/experiments/example_predictor.py
def predict(input_text: str) -> str:
    # In a real experiment this calls a DSPy module or local model.
    return "Jane Doe"
```

### 3. Define an experiment config

```yaml
# evaluation/experiments/example_experiment.yaml
name: example_deck_classifier
predictor: evaluation.experiments.example_predictor:predict
dataset:
  path: data/example_deck_classifier.jsonl
  input_field: input
  expected_field: expected
parameters:
  model: qwen2.5:14b
  temperature: 0.0
```

### 4. Run the experiment

```bash
python3 -m evaluation.experiments.runner evaluation/experiments/example_experiment.yaml
```

Results are written to `example_deck_classifier_results.json` with metrics, predictions, and any ROC/Markov artifacts.

## Modules

| Module | Purpose |
|--------|---------|
| `design.py` | `Experiment`, `DatasetSpec`, `DoEResult`, `Prediction` base classes |
| `metrics.py` | Classification metrics, hallucination score, token overlap |
| `roc.py` | ROC curve and AUC computation |
| `markov.py` | First-order Markov chain analysis for state transitions |
| `runner.py` | CLI and programmatic entry points |

## Statistical methods

The harness is intentionally pluggable. Use whichever method is justified by the validation question:

- **Binary classification:** ROC/AUC, precision, recall, F1, confusion matrix.
- **State transition analysis:** Markov chain transition matrix and steady-state distribution.
- **Generation / extraction:** exact match, token overlap, hallucination score.
- **Future additions:** confidence intervals, bootstrap resampling, paired t-tests, Bayesian model comparison.

## Notes on hallucination detection

The default `hallucination_score` is a simple token-overlap heuristic: words in the prediction that do not appear in the reference count as hallucinated. Replace it with an embedding-based or entailment-based scorer for production work by passing a custom `label_fn` or by wrapping the predictor to return a metadata score.
