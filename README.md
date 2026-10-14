# ReluLayer

ReluLayer is a Multiple Independent Levels of Security (MILS) separation kernel for autonomous Artificial Intelligence (AI) agent execution. Agent intent stays on one side of the boundary. An action crosses only after a replay-resistant Hash-based Message Authentication Code using SHA-256 (HMAC-SHA256) receipt is checked against a persistent interceptor. The kernel snapshots the caller buffer before verification, so a concurrent writer cannot change the payload mid-check.

The public wedge is four crates:

| Crate | Role |
| --- | --- |
| `relulayer-security` | `#![no_std]` authorization kernel |
| `relulayer-ffi` | Stateful Foreign Function Interface (FFI) exposing an ANSI C Application Binary Interface (C-ABI) (`ReluInterceptor` opaque handle) |
| `relulayer-py` | PyO3 bindings (Rust bindings for the Python interpreter) (`ReluBoundary`) |
| `relulayer-proofs` | Amazon Web Services (AWS) Kani induction harnesses |

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

## Python

```python
from relulayer_py import ReluBoundary

# Initialize the boundary with a 32-byte shared cryptographic secret
boundary = ReluBoundary(b"\x07" * 32)

action_id = b"execute_sql_query"
payload_data = b"SELECT * FROM user_records WHERE id = 42;"
nonce = b"123456789012"   # 12-byte unique cryptographic nonce
timestamp = 1728849600     # Unix epoch timestamp
counter = 1                # Strictly increasing sequence counter

# 1. Authority or Planner issues a signed action receipt
receipt = boundary.issue_receipt(nonce, timestamp, counter, action_id, payload_data)

# 2. Interceptor validates authenticity, payload integrity, and counter monotonicity
# Raises ValueError on invalid signature, corrupted payload, or replay attempt
try:
    boundary.intercept_and_authorize(action_id, payload_data, receipt)
    # Action confirmed untampered and non-replayed; safe to execute
    print("[+] Action authorized and verified.")
except ValueError as err:
    print(f"[-] Execution blocked: {err}")
```

`nonce` is 12 bytes. `counter` must increase strictly for the authorization scope. Each `ReluBoundary` keeps its own replay window. Instances are not thread-safe.

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
