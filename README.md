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

---

## Enterprise & High-Assurance Evaluation

ReluLayer™ is engineered specifically for physical autonomy domains where probabilistic software failure risks kinetic destruction, actuator runaway, or loss of life. While probabilistic foundation models and Vision-Language-Action (VLA) networks handle high-level planning, ReluLayer™ operates as the deterministic, hardware-adjacent **Edge Governor** and **Execution Gatekeeper**.

### Regulatory Safety Standards Alignment

| Standard | Target Domain | ReluLayer™ Deterministic Enforcement Profile | Target Assurance Level |
| :--- | :--- | :--- | :--- |
| **DO-178C / DO-330** | Civil & Military Avionics | Zero dynamic allocations (`#![no_std]`), static stack-depth guarantees ($< 4\,\text{KB}$), deterministic execution bounds ($0.199\,\mu\text{s}$). | **Design Assurance Level (DAL) A/B** |
| **IEC 61508** | Industrial Autonomous Robotics | Monotonic counter tracking preventing Time-of-Check to Time-of-Use (TOCTOU) exploits, bounded state-machine validation. | **SIL 3 / SIL 4** |
| **Common Criteria** | Secure Defense Infrastructure | Cryptographically sealed HMAC-SHA256 action receipts, microkernel MILS separation architecture. | **EAL 6+ Augmentation** |
| **ISO 26262** | Autonomous Vehicles & ADAS | Real-time torque, steering kinematic boundaries, and bus-level command isolation outside userland OS. | **ASIL D** |

---

### Inbound Engagement Protocol: Enterprise Design Partners

We partner with autonomous vehicle OEMs, defense contractors, robotics integrators, and critical infrastructure operators requiring verified, tamper-evident execution control.

Design partners receive dedicated engineering co-development for mission-critical deployments:

```
[Inbound Intake]
       │
       ▼
[Architecture & Threat Model Review] ────► 1-Week Analysis of Actuator & Compute Bus
       │
       ▼
[Custom Hardware Integration Harness] ───► Board Support Package (BSP) for QNX, VxWorks, or FPGA
       │
       ▼
[Dedicated Hardware-in-the-Loop Testbed] ► Latency, Jitter, & Fault-Injection Verification
       │
       ▼
[Co-Developed Production Deployment] ───► ReluLayer™ Safety Edition License & Qualification Data
```

1. **Architecture & Threat Model Review**: Complete audit of your motion planner-to-actuator control loop. We identify TOCTOU race conditions, non-deterministic latency spikes, and unauthorized actuator command injection surfaces.
2. **Custom Hardware Integration Harness**: Tailored integration for mission-critical target environments, including bare-metal microcontrollers (ARM Cortex-R52/M7, RISC-V RV64GC), real-time operating systems (QNX Neutrino 7.1+, VxWorks 653), and low-latency PCIe/CAN-FD interfaces.
3. **Dedicated Hardware-in-the-Loop (HIL) Testbed**: Rigorous edge injection testing under saturation workloads. We prove absolute boundary enforcement down to $0.199\,\mu\text{s}$ authorization latency under hardware failure conditions.

To initiate an architectural evaluation under Mutual NDA, contact:
**Defense & Aerospace Solutions Group**: `ishmael.amin@outlook.com`
*Direct inquiries referencing Air Force SBIR D2P2 Topic `DAF26BX06-DV026` receive prioritized technical evaluation within 24 hours.*

---

### Safety & Compliance Roadmap (2026–2027)

ReluLayer™ follows an open-core, high-assurance roadmap designed to support civil certification and military airworthiness qualifications:

```
       Q4 2026                        Q1 2027                        Q2 2027                        Q3 2027
┌──────────────────────┐      ┌──────────────────────┐      ┌──────────────────────┐      ┌──────────────────────┐
│  Phase II SBIR D2P2  │      │  Kani & Creusot SV   │      │  IEC 61508 Pre-Cert  │      │ DO-178C DAL A Pack   │
│  Flight Verification │ ────►│  Mathematical Proofs │ ────►│  Functional Safety   │ ────►│ Avionics Tool Qual   │
│  Actuator Isolation  │      │  Zero-Panic Baseline │      │  SIL 3/4 Artifacts   │      │ PSAC / TOR Bundles   │
└──────────────────────┘      └──────────────────────┘      └──────────────────────┘      └──────────────────────┘
```

- **Q4 2026 (Air Force SBIR D2P2 Alignment — Topic `DAF26BX06-DV026`)**:
  - Demonstration of flight-critical actuator command isolation under contested electromagnetic interference and adversarial compute interception.
  - Delivery of zero-heap monotonic sequencing kernel running bare-metal on military-grade avionics compute blocks.
- **Q1 2027 (Formal Static Verification Proofs)**:
  - Integration of model checking and formal verification toolchains (Kani Rust Verifier, Creusot).
  - Mathematical verification of zero-panic invariant states, absence of arithmetic overflow, and bounded stack consumption ($< 4\,\text{KB}$).
- **Q2 2027 (IEC 61508 SIL 3/4 Functional Safety Package)**:
  - Third-party assessment of failure modes, effects, and diagnostic analysis (FMEDA).
  - Production of deterministic hazard mitigation matrices for industrial robotics workcells.
- **Q3 2027 (DO-178C Tool Qualification Data Packs)**:
  - Release of ReluLayer™ Safety Edition documentation: Plan for Software Aspects of Certification (PSAC), Software Tool Qualification Plan (STQP), and Tool Operational Requirements (TOR).

## License

Licensed under either of

- Apache License, Version 2.0 ([LICENSE-APACHE](LICENSE-APACHE))
- Massachusetts Institute of Technology (MIT) license ([LICENSE-MIT](LICENSE-MIT))

at your option.
