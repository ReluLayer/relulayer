# ReluLayer™

[![CI / Build & Test](https://github.com/relulayer/relulayer/actions/workflows/wheels.yml/badge.svg)](https://github.com/relulayer/relulayer/actions)
[![PyPI Version](https://img.shields.io/pypi/v/relulayer.svg?color=blue)](https://pypi.org/project/relulayer/)
[![Crates.io](https://img.shields.io/crates/v/relulayer.svg?color=orange)](https://crates.io/crates/relulayer)
[![Rust MSRV](https://img.shields.io/badge/rustc-1.75%2B-brightgreen.svg)](https://www.rust-lang.org)
[![License: MIT OR Apache-2.0](https://img.shields.io/badge/License-MIT%20OR%20Apache--2.0-yellow.svg)](LICENSE-APACHE)
[![Fast-Path Latency](https://img.shields.io/badge/Fast--Path%20Latency-0.199%20%CE%BCs-blueviolet)](https://github.com/relulayer/relulayer)

> **Deterministic Edge Governor & Real-Time Execution Gatekeeper for Physical Super Intelligence (SI), Autonomous Robotics, and High-Assurance Actuators.**

## Quickstart

### Pre-Compiled Universal Wheels (Recommended)

ReluLayer™ publishes pre-compiled binary wheels for Linux (`x86_64`, `aarch64`) and macOS (`arm64`, `x86_64`). No local Rust toolchain or C-compiler is required:

```bash
pip install --upgrade relulayer
```

Verify in Python:

```python
import relulayer
from relulayer import ReluBoundary

# Instantiate deterministic edge governor with stack-allocated bounds
boundary = ReluBoundary(
    max_velocity_rad_s=4.18,
    monotonic_window_size=64,
    hmac_key=b"0123456789abcdef0123456789abcdef"
)

# Fast-path verification (0.199 µs)
receipt = boundary.authorize_action(
    target_axis=0,
    requested_position=1.57,
    commanded_velocity=2.0
)
assert receipt.is_authorized
```

### Source Build Fallback (Embedded & Custom Targets)

For bare-metal microcontrollers (ARM Cortex-R52/M7, RISC-V), QNX, or VxWorks:

1. **Install Prerequisites**:

   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   pip install maturin
   ```

2. **Build `#![no_std]` Separation Kernel**:

   ```bash
   cargo build --release --no-default-features
   ```

3. **Install Local Development Bindings**:

   ```bash
   maturin develop --release
   ```

## Latency

Short tool calls take the sub-512-byte fast path. Larger payloads stream through 4 Kibibyte (KiB) stack windows up to a 64 KiB policy ceiling. The kernel does not allocate.

| Boundary | Latency |
| --- | --- |
| [ReluLayer micro-action fast path](#latency) | 0.199 µs |
| [Guardrails AI](https://github.com/guardrails-ai/guardrails) | 18.2 ms |
| [NVIDIA NeMo Guardrails](https://github.com/NVIDIA/NeMo-Guardrails) | 24.5 ms |

Host builds enable the `std` feature so tests and PyO3 can link the standard library. Production firmware builds disable `std` and compile as `#![no_std]` with `0` bytes of heap in the kernel.

## When to Use ReluLayer (Applicability Matrix)

ReluLayer is not a conversational text filter. It is an execution-level gatekeeper that proves an action was authorized and prevents it from being tampered with or replayed in the moment it crosses from planner to host.

- **Semantic Content Filters (Guardrails AI, NVIDIA NeMo):** Run secondary LLM calls or regex parsing to evaluate conversational text ($18\text{--}25\,\text{ms}$, dynamic heap memory). Use them for brand tone, PII redaction, and chatbot toxicity.
- **Execution-Level Gatekeepers (ReluLayer):** Intercept raw execution payloads (APIs, SQL, motor actuators) directly before execution ($0.199\,\mu\text{s}$, zero dynamic heap, anti-replay monotonicity). Use ReluLayer for tool calling, robotics control loops, and mission-critical actions.

| Use Case Scenario | Use ReluLayer? | Why / Why Not |
| :--- | :--- | :--- |
| **Agent Tool Calling (Databases, APIs, Shells)** | **YES** | Proves the tool execution request was authorized by an upstream planner and hasn't suffered mid-flight TOCTOU tampering. |
| **Robotics & Drones (Actuator Motor Demands)** | **YES** | Real-time control loops run at $400\text{--}1000\,\text{Hz}$ ($1{,}000\text{--}2{,}500\,\mu\text{s}$ frame budget). A $0.199\,\mu\text{s}$ interceptor fits inside the loop; a $20\,\text{ms}$ LLM filter would crash the drone. |
| **High-Frequency Trading & FinTech Actions** | **YES** | Sub-microsecond validation of trade parameters and monotonic sequence ordering to prevent duplicate or replayed transactions. |
| **Chatbot Brand Voice & Tone Moderation** | **NO** | ReluLayer does not analyze conversational sentiment or linguistic style. Use Guardrails AI or NeMo here. |
| **Prompt Injection / Text Jailbreak Detection** | **NO** | ReluLayer protects the *action execution interface*, not the prompt parsing phase. Pair an input guardrail on text with ReluLayer on execution. |

## Examples & Cookbook

For copy-pasteable, runnable recipes covering TOCTOU-safe database tool calling, distributed replay prevention, and high-frequency robotics motor governance, see [`COOKBOOK.md`](COOKBOOK.md).

## Formal verification

`relulayer-proofs` contains AWS Kani harnesses that prove streaming HMAC equivalence and replay monotonicity by mathematical induction over the hasher state. The harnesses compile only under `cfg(kani)`.

## Build

```bash
cargo test --workspace
```

PyO3 needs a local CPython. If the dynamic linker cannot find `libpython`, prefix the test command with the interpreter's library directory:

```bash
LD_LIBRARY_PATH="$(python3 -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))'):$LD_LIBRARY_PATH" cargo test --workspace
```

## License

Licensed under either of

- Apache License, Version 2.0 ([LICENSE-APACHE](LICENSE-APACHE))
- Massachusetts Institute of Technology (MIT) license ([LICENSE-MIT](LICENSE-MIT))

at your option.
