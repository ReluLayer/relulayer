"""Benchmark the ReluLayer Python governor in a tight simulation loop."""

import time
import numpy as np
from relulayer import Governor


def main() -> None:
    rng = np.random.default_rng(seed=42)
    commands = rng.uniform(low=-25.0, high=25.0, size=100_000).astype(np.float32)

    gov = Governor(min_bound=-12.0, max_bound=12.0)

    # Warm-up to avoid first-call initialization noise.
    for _ in range(1_000):
        gov.project(0.0)

    start = time.perf_counter()
    for u in commands:
        gov.project(float(u))
    elapsed = time.perf_counter() - start

    avg_us = (elapsed / len(commands)) * 1_000_000.0

    # Vectorized sanity check on the full batch.
    safe = gov.project_batch(commands.tolist())
    min_val = min(safe)
    max_val = max(safe)

    print(f"Total elapsed: {elapsed:.6f} s")
    print(f"Iterations: {len(commands)}")
    print(f"Average per-step latency: {avg_us:.6f} µs")
    print(f"Min output value: {min_val}")
    print(f"Max output value: {max_val}")

    assert avg_us < 1.0, f"Average latency {avg_us:.6f} µs exceeds 1 µs budget"
    assert min_val >= -12.0, f"Lower-bound violation: {min_val}"
    assert max_val <= 12.0, f"Upper-bound violation: {max_val}"
    print("All assertions passed.")


if __name__ == "__main__":
    main()
