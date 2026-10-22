# ReluLayer™

[![CI / Build & Test](https://github.com/relulayer/relulayer/actions/workflows/wheels.yml/badge.svg)](https://github.com/relulayer/relulayer/actions)
[![PyPI Version](https://img.shields.io/pypi/v/relulayer.svg?color=blue)](https://pypi.org/project/relulayer/)
[![Rust MSRV](https://img.shields.io/badge/rustc-1.75%2B-brightgreen.svg)](https://www.rust-lang.org)
[![License: MIT OR Apache-2.0](https://img.shields.io/badge/License-MIT%20OR%20Apache--2.0-yellow.svg)](LICENSE-APACHE)
[![Fast-Path Latency](https://img.shields.io/badge/Fast--Path%20Latency-0.199%20%CE%BCs-blueviolet)](https://github.com/relulayer/relulayer)

> **Deterministic Edge Governor & Real-Time Execution Gatekeeper for Software Agent Workflows and Simulation Testbeds.**

> ⚠️ **IMPORTANT NOTICE & SAFETY-CRITICAL USAGE RESTRICTION:**
>
> `relulayer` is distributed solely as an experimental evaluation and development framework for software-level agent governance, simulation, and architectural prototyping. This package is **NOT CERTIFIED FOR SAFETY-CRITICAL, HIGH-CONSEQUENCE, OR LIFE-CRITICAL SYSTEMS**. Direct integration with safety-critical hardware or external control systems requires ReluLayer™ Certified Kernels and a separate commercial agreement. The authors and Atelier Logic Group LLC disclaim all liability for property damage, personal injury, or regulatory violations resulting from unauthorized integration.

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

# Instantiate a deterministic agent governor for simulation / testbed use
boundary = ReluBoundary(
    max_rate=4.18,
    monotonic_window_size=64,
    hmac_key=b"0123456789abcdef0123456789abcdef"
)

# Fast-path software authorization check (0.199 µs)
receipt = boundary.authorize_action(
    channel=0,
    setpoint=1.57,
    delta=2.0
)
assert receipt.is_authorized
```

### Source Build Fallback

For local development and custom host targets:

1. **Install Prerequisites**:

   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   pip install maturin
   ```

2. **Build Local Development Bindings**:

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

Host builds enable the `std` feature so tests and PyO3 can link the standard library. Validated safety-critical deployments require ReluLayer™ Certified Kernels compiled as `#![no_std]` with `0` bytes of heap; that hardened target is not included in this open-source distribution.

## When to Use ReluLayer (Applicability Matrix)

ReluLayer is not a conversational text filter. It is a software-level execution gatekeeper that proves an action was authorized and prevents it from being tampered with or replayed in the moment it crosses from planner to execution environment in a simulation or testbed.

- **Semantic Content Filters (Guardrails AI, NVIDIA NeMo):** Run secondary LLM calls or regex parsing to evaluate conversational text ($18\text{--}25\,\text{ms}$, dynamic heap memory). Use them for brand tone, PII redaction, and chatbot toxicity.
- **Execution-Level Gatekeepers (ReluLayer):** Intercept software execution payloads (APIs, SQL, simulated control commands) directly before execution in a sandboxed environment ($0.199\,\mu\text{s}$, zero dynamic heap, anti-replay monotonicity). Use ReluLayer for tool calling, simulated autonomy control loops, and mission-critical software actions.

| Use Case Scenario | Use ReluLayer? | Why / Why Not |
| :--- | :--- | :--- |
| **Agent Tool Calling (Databases, APIs, Shells)** | **YES** | Proves the tool execution request was authorized by an upstream planner and hasn't suffered in-transit TOCTOU tampering. Always run in a sandbox or testbed first. |
| **Autonomy & Control-Loop Simulation** | **YES** | Validate control-loop commands and monotonic sequencing in simulation ($400\text{--}1000\,\text{Hz}$ notional frame budget). A $0.199\,\mu\text{s}$ check fits inside the software loop. |
| **High-Frequency Trading & FinTech Simulation** | **YES** | Sub-microsecond validation of trade parameters and monotonic sequence ordering in backtesting and simulation environments. |
| **Safety-Critical Hardware or External Control Systems** | **NO** | This open-source package is not certified for high-consequence or life-critical systems. Contact ReluLayer™ for certified kernel options. |
| **Chatbot Brand Voice & Tone Moderation** | **NO** | ReluLayer does not analyze conversational sentiment or linguistic style. Use Guardrails AI or NeMo here. |
| **Prompt Injection / Text Jailbreak Detection** | **NO** | ReluLayer protects the *action execution interface*, not the prompt parsing phase. Pair an input guardrail on text with ReluLayer on execution. |

## Examples & Cookbook

For copy-pasteable, runnable recipes covering TOCTOU-safe database tool calling, distributed replay prevention, and high-frequency simulation governance, see [`COOKBOOK.md`](COOKBOOK.md).

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

---

## Enterprise & High-Assurance Evaluation

ReluLayer™ is designed for teams building deterministic runtime assurance into
software agent and autonomy stacks. The open-source distribution provides a
simulation-first execution gatekeeper; validated safety-critical deployments are
supported through ReluLayer™ Certified Kernels and separate enterprise
licensing.

### Regulatory Safety Standards Alignment — Simulation & Architectural Prototyping

The open-source `relulayer` package is **not certified** to any of the standards
below. Its architecture is informed by the runtime-assurance principles reflected
in those standards and is intended for simulation, testing, and architectural
prototyping only. CPython execution cannot provide certified real-time
determinism.

| Standard | Target Domain | ReluLayer™ Architectural Alignment for Simulation | Notional Target for Certified Editions |
| :--- | :--- | :--- | :--- |
| **DO-178C / DO-330** | Avionics | Zero dynamic allocations (`#![no_std]`), static stack-depth goals ($< 4\,\text{KB}$), deterministic execution bounds ($0.199\,\mu\text{s}$). | Design Assurance Level (DAL) A/B — *Certified Safety Edition only* |
| **IEC 61508** | Industrial Automation | Monotonic counter tracking preventing Time-of-Check to Time-of-Use (TOCTOU) exploits, bounded state-machine validation. | SIL 3 / SIL 4 — *Certified Safety Edition only* |
| **Common Criteria** | Secure Infrastructure | Cryptographically sealed HMAC-SHA256 action receipts, microkernel MILS separation architecture. | EAL 6+ Augmentation — *Certified Safety Edition only* |
| **ISO 26262** | Autonomous Vehicles & ADAS | Real-time torque and steering kinematic boundary concepts, bus-level command isolation outside userland OS. | ASIL D — *Certified Safety Edition only* |

---

### Inbound Engagement Protocol: Enterprise Design Partners

We partner with software agent developers, systems integrators, and
critical infrastructure operators who need verified, tamper-evident execution
control. Design partners receive engineering co-development for simulation
hardening and, separately, certified production deployments:

```
[Inbound Intake]
       │
       ▼
[Architecture & Threat Model Review] ────► 1-Week Analysis of Planner-to-Execution Data Flow
       │
       ▼
[Simulation Integration Harness] ────────► Software-in-the-Loop (SIL) Testbed & Benchmarks
       │
       ▼
[Validated Hardware-in-the-Loop Testbed] ► Latency, Jitter, & Fault-Injection Verification
       │
       ▼
[Certified Production Deployment] ─────────► ReluLayer™ Safety Edition License & Qualification Data
```

1. **Architecture & Threat Model Review**: Audit the planner-to-execution data
   flow in your software stack. We identify TOCTOU race conditions,
   non-deterministic latency spikes, and unauthorized command injection surfaces.
2. **Simulation Integration Harness**: Tailored integration for your simulation
   environment, including software-in-the-loop (SIL) benchmarks and replay
   monotonicity validation.
3. **Validated Hardware-in-the-Loop (HIL) Testbed**: For certified editions,
   rigorous edge-injection testing under saturation workloads on validated
   target hardware.

To initiate an architectural evaluation under Mutual NDA, contact:
**Atelier Logic Group LLC dba ReluLayer™** — `ishmael.amin@outlook.com`

---

### Safety & Compliance Roadmap (2026–2027)

ReluLayer™ follows an open-core roadmap. The open-source package provides
simulation and architectural-prototyping artifacts; certified qualification data
packs are delivered through the commercial Safety Edition.

```
       Q4 2026                        Q1 2027                        Q2 2027                        Q3 2027
┌──────────────────────┐      ┌──────────────────────┐      ┌──────────────────────┐      ┌──────────────────────┐
│  Simulation Hardening  │      │  Kani & Creusot SV   │      │  IEC 61508 Pre-Cert  │      │ DO-178C DAL A Pack   │
│  & Testbed Alignment   │ ────►│  Mathematical Proofs │ ────►│  Functional Safety   │ ────►│ Avionics Tool Qual   │
│                        │      │  Zero-Panic Baseline │      │  SIL 3/4 Artifacts   │      │ PSAC / TOR Bundles   │
└──────────────────────┘      └──────────────────────┘      └──────────────────────┘      └──────────────────────┘
```

- **Q4 2026 (Simulation Hardening & Testbed Alignment)**:
  - Hardening of the software-level agent governor for deterministic behavior in simulation and SIL environments.
  - Delivery of open-core monotonic sequencing kernel suitable for research and prototyping hosts.
- **Q1 2027 (Formal Static Verification Proofs)**:
  - Integration of model checking and formal verification toolchains (Kani Rust Verifier, Creusot).
  - Mathematical verification of zero-panic invariant states, absence of arithmetic overflow, and bounded stack consumption ($< 4\,\text{KB}$).
- **Q2 2027 (IEC 61508 SIL 3/4 Functional Safety Package)** — *Safety Edition*:
  - Third-party assessment of failure modes, effects, and diagnostic analysis (FMEDA).
  - Production of deterministic hazard mitigation matrices for industrial automation workcells.
- **Q3 2027 (DO-178C Tool Qualification Data Packs)** — *Safety Edition*:
  - Release of ReluLayer™ Safety Edition documentation: Plan for Software Aspects of Certification (PSAC), Software Tool Qualification Plan (STQP), and Tool Operational Requirements (TOR).

## License

Licensed under either of

- Apache License, Version 2.0 ([LICENSE-APACHE](LICENSE-APACHE))
- Massachusetts Institute of Technology (MIT) license ([LICENSE-MIT](LICENSE-MIT))

at your option.

### Patent Rights Notice

Copyright (c) 2026 Atelier Logic Group LLC dba ReluLayer™. All Rights Reserved.

This open-source release grants a license solely to the software code and Python
interfaces expressly contained in this repository distribution. Nothing in this
license shall be construed as granting, either expressly, by implication, or by
estoppel, any patent license or right to practice, make, have made, use, sell,
or offer for sale any inventions, architectures, methods, or apparatus disclosed
or claimed in USPTO Provisional Patent Application Serial Nos. 64/127,611 and
64/124,094. See [PATENTS.md](PATENTS.md) for the complete reservation.
