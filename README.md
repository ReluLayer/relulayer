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

## Python

```python
from relulayer_py import ReluBoundary

boundary = ReluBoundary(b"\x07" * 32)
receipt = boundary.issue_receipt(nonce, timestamp, counter, action, payload)
boundary.intercept_and_authorize(action, payload, receipt)
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
