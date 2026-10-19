# ReluLayer™ Product Requirements Document (PRD)

**Version:** 0.2.0  
**Status:** Authoritative baseline — synchronized across the public mirror and the internal monorepo  
**Applies to:**
- `/home/iamin/Dist/relulayer-oss` (public GitHub mirror)
- `/home/iamin/Organizations/ReluLayer` (primary monorepo)

**Author / Provenance:** `ishmaelamin <ishmael.amin@outlook.com>`  
**Entity:** Atelier Logic Group LLC dba ReluLayer™ — CAGE `20JX8`, UEI `G9WFN3AL69J3`  
**Date:** 2026-10-19

> **Classification:** Engineering baseline. This document is the single source of truth for product positioning, architectural invariants, and development governance. When this PRD conflicts with any other guidance, this PRD prevails.

---

## 1. Executive Summary & Category Framing

ReluLayer™ is a deterministic **Edge Governor** and **Execution Gatekeeper** for autonomous AI agent reasoning, LLM tool calling, and Physical Super Intelligence (Physical SI) actuator loops.

Probabilistic foundation models and Vision-Language-Action (VLA) networks plan; ReluLayer™ proves and permits the resulting physical execution request in the moment it crosses from planner to host. The kernel is written in pure `#![no_std]` Rust, uses zero dynamic heap allocations on the hot path, and binds every authorized action to a replay-resistant HMAC-SHA256 receipt with a monotonic anti-replay counter.

Core value proposition:

- **Sub-microsecond authorization:** 0.199 µs micro-action fast path on modern silicon.
- **TOCTOU elimination:** caller payloads are snapshot or streamed through fixed-size stack buffers before HMAC verification begins.
- **Deterministic memory envelope:** no allocator in the safety-critical path; bounded stack usage stays below 1 KB.
- **Physical SI alignment:** prevents kinetic destruction, actuator runaway, and unauthorized tool execution without relying on a second probabilistic model.

---

## 2. Core Problem Statement & Competitive Benchmark

### 2.1 Problem Statement

Autonomous agents and physical robots increasingly combine probabilistic planners with real-time actuators. The planner may be safe, but the execution interface is vulnerable to:

- **Time-of-Check to Time-of-Use (TOCTOU) mutation** of the action buffer between policy approval and host execution.
- **Replay attacks** that re-issue previously valid motor commands or financial transactions.
- **Latency inflation** from secondary LLM filters that cannot meet 400–1000 Hz control-loop budgets.

ReluLayer™ intercepts the raw execution payload (motor command, SQL query, API call, financial instruction) directly before execution and proves it is authorized and untampered.

### 2.2 Competitive Latency Comparison

| Boundary / Filter | Latency | Notes |
| :--- | :--- | :--- |
| **ReluLayer™ micro-action fast path** | **0.199 µs** | `#![no_std]`, zero heap, HMAC-SHA256 |
| Guardrails AI | 18.2 ms | Conversational / content filter; secondary LLM or regex pass |
| NVIDIA NeMo Guardrails | 24.5 ms | Conversational guardrails; cloud or local LLM inference |

ReluLayer™ is not a replacement for conversational content filters. It is an execution-level gatekeeper that operates on raw bytes, not natural language.

---

## 3. System Architecture & Technical Specifications

### 3.1 Workspace Topology

The product is developed in a dual-repo model:

- **Public mirror (`~/Dist/relulayer-oss`)** — open-core community edition.
- **Primary monorepo (`~/Organizations/ReluLayer`)** — superset that contains the public crates plus commercial, certification, and pilot modules.

#### Public mirror workspace members (`Cargo.toml`)

| Crate | Path | Responsibility |
| :--- | :--- | :--- |
| `relulayer-security` | `crates/relulayer-security` | `#![no_std]` boundary interceptor; HMAC-SHA256, replay window, TOCTOU-safe snapshot/streaming |
| `relulayer-ffi` | `crates/relulayer-ffi` | C-ABI opaque-handle wrapper for the boundary interceptor |
| `relulayer-py` (`_relulayer`) | `crates/relulayer-py` | PyO3 0.23+ Python bindings (`ReluBoundary`, `ReluReceipt`, `ReluViolation`) |
| `relulayer-proofs` | `crates/relulayer-proofs` | AWS Kani bounded-model-checking proofs for streaming and replay invariants |

#### Monorepo-only extensions (`~/Organizations/ReluLayer`)

| Crate / Component | Path | Responsibility |
| :--- | :--- | :--- |
| `relulayer-core` | `10-kernel/relulayer-core` | Scalar and 4-D multivariable active-set QP solver; bare-metal math primitives |
| `relulayer-safety` | `crates/relulayer-safety` | Commercial Safety Edition: formal verification harnesses and DO-178C qualification artifacts |
| `relulayer-fleet` | `crates/relulayer-fleet` | Multi-agent monotonic arbitration and enterprise key management |
| `veristate` | `10-kernel/veristate` | Enterprise state-enforcement and hardware-attested transaction ledger (separate program of record) |
| `bridges/px4-mixer` | `bridges/px4-mixer` | C++17 PX4 Autopilot mixer barrier using the ReluLayer active-set C ABI |
| `20-pilots-and-proposals` | `20-pilots-and-proposals/*` | SBIR / D2P2 pilot packages and digital-twin benchmarks |

### 3.2 Build Profiles & Memory Invariants

- **Default host:** `std` feature enabled for tests and PyO3.
- **Production firmware:** `#![no_std]`, `panic = "abort"`, `lto = true`, `opt-level = 3`.
- **Zero dynamic heap allocations** on the authorization path; `_sbrk` traps to `ENOMEM` on embedded targets.
- **Stack ceiling:** < 1 KB for any single authorization call.
  - Micro-action fast path: ≤ 512 bytes stack snapshot.
  - Standard snapshot path: 4 KiB stack chunk.
  - Streaming path: 4 KiB sliding window for payloads up to 64 KiB total policy ceiling.

### 3.3 Boundary Interceptor Contract

- Action identifiers and payloads are raw `bytes` (`&[u8]` / `PyBytes`).
- Receipt serialization: `nonce(12) + timestamp(8) + counter(8) + HMAC-SHA256 tag(32) = 60 bytes`.
- Verification failure raises `ValueError` (Python) or returns a negative FFI code; it never returns a boolean that could be ignored.
- Monotonic counter must strictly increase per authorization scope.
- Nonce window rejects nonce reuse inside the configured replay window.

### 3.4 Mathematical Bound Enforcement — 4-D Active-Set QP

`relulayer-core` solves the strictly convex projection QP:

\[
\min_{u \in \mathbb{R}^4} \frac{1}{2} \|u - u_{\text{raw}}\|^2
\quad \text{s.t.} \quad u_{\min} \le u \le u_{\max}, \; A u \le b
\]

- \(u \in \mathbb{R}^4\) actuator / effector channels.
- \(p \le 4\) linear inequality rows.
- Hard iteration ceiling \(k \le 20\) active-set iterations plus a deterministic Phase-I feasibility step.
- All working memory is stack-allocated via fixed-size arrays.
- Measured scalar-channel host latency: ≈ 26.11 ns; 4-D solver stays well below microsecond budgets.

---

## 4. Current Status & Milestone Achievements

### Sprint 1 — PyO3 Bridge & Stateful FFI (`v0.1.x`)

- Stateful `ReluInterceptor` opaque-handle pattern in `relulayer-ffi`.
- Persistent `ReluBoundary` in `relulayer-py` to eliminate replay vulnerabilities.
- Measured Python binding overhead: 42.1 ns.

### Sprint 2 — PX4 Autopilot Mixer Barrier (`v0.2.0`)

- C++17 drop-in barrier between PX4 control allocator and ESC outputs (`bridges/px4-mixer`).
- Active-set scalar projection with hard-clamp fallback.
- Host benchmark: 27,666 clamps enforced, 0 bound breaches, average per-frame latency < 1.0 µs.

### Sprint 3 — DAF Direct-to-Phase II Proposal Package

- Federal reference: Air Force SBIR D2P2 Topic `DAF26BX06-DV026`.
- DO-333 formal proof tables and traceability artifacts.
- SITL/Renode STM32H743 / Pixhawk 6X bare-metal target harness.

### Sprint 4 — 4-D Multivariable Active-Set Solver (`v0.2.0-multivar-4d`)

- `relulayer-core` 4-D QP kernel with Phase-I cyclic projection and Phase-II primal-feasible active-set method.
- C ABI `relulayer_solve_multivar_4d` for flight-controller integration.
- Kani proof scaffolding extended to multivariable invariants.

### Live Publication

- PyPI package `relulayer` at `v0.2.0` with pre-compiled wheels for:
  - Linux `x86_64`
  - Linux `aarch64`
  - macOS `macos-14` Apple Silicon
  - macOS cross-compiled Intel `x86_64`

---

## 5. The 3-Phase Go-To-Market Strategy

### Phase 1 — Maximizing Usage Count (Active Execution)

- Zero-build pip installs: `pip install relulayer`.
- Open-core permissive dual licensing: MIT OR Apache-2.0.
- Benchmark push and reference recipes in `COOKBOOK.md`.
- Public GitHub CI matrix (Rust + Python 3.12).

### Phase 2 — Enterprise Design Partners (Bridge Phase)

- 2–3 OEM pilots across robotics, UAS swarms, and high-frequency trading.
- Co-funded safety-certification packs.
- Requirements gathering for DO-178C Level A, IEC 61508 SIL 3/4, ISO 26262 ASIL-D, and Common Criteria EAL 6+.

### Phase 3 — Monetization & Commercial Distribution

- **Community Edition:** open-core kernel, PyO3 bindings, permissive license.
- **Commercial ReluLayer™ Safety Edition:** certified binaries, qualification kits, indemnification, dedicated support.
- **Control Plane:** SaaS and on-prem fleet key management and policy orchestration.
- **Hardware OEM dual-licensing:** BSP integrations for QNX, VxWorks, FreeRTOS, and bare-metal ARM/RISC-V.

---

## 6. Regulatory & Safety Standards Alignment

| Standard | Domain | ReluLayer™ Deterministic Enforcement Profile | Target Assurance |
| :--- | :--- | :--- | :--- |
| DO-178C / DO-330 | Civil & military avionics | `#![no_std]`, zero dynamic allocation, static stack-depth guarantees | DAL A / B |
| IEC 61508 | Industrial autonomous robotics | Monotonic counter TOCTOU prevention, bounded state-machine validation | SIL 3 / SIL 4 |
| ISO 26262 | Autonomous vehicles & ADAS | Real-time torque/steering boundaries, bus-level command isolation | ASIL D |
| Common Criteria | Secure defense infrastructure | HMAC-SHA256 receipts, MILS separation architecture | EAL 6+ |

---

## 7. SCM, Audit Hygiene & Development Governance

### 7.1 Author Provenance

- All commits in this repository must be attributed to:
  ```text
  ishmaelamin <ishmael.amin@outlook.com>
  ```
- `Co-authored-by: Cursor`, `Co-authored-by: GitHub Copilot`, or any bot attribution trailer is strictly prohibited.

### 7.2 Dual-Repository Parity

- Every modification in `~/Dist/relulayer-oss` must be mirrored to `~/Organizations/ReluLayer` (and vice-versa) for files that exist in both workspaces.
- The public mirror contains only the open-core wedge; the monorepo is the superset. Do not copy proprietary monorepo content into the public mirror.

### 7.3 Commit Hygiene

- Use [Conventional Commits](https://www.conventionalcommits.org/):
  - `docs(prd): ...`
  - `feat(core): ...`
  - `fix(security): ...`
  - `ci(actions): ...`
- Stage explicit paths only; `git add .`, `git add -A`, and `git add *` are forbidden.
- Keep `target/`, `node_modules/`, `.venv/`, build artifacts, and transient caches out of the index.

### 7.4 Architectural Non-Negotiables

- `#![no_std]` first for all safety-critical crates.
- Zero dynamic heap allocations on hot paths.
- Bounded stack allocations < 1 KB per authorization call.
- Sub-microsecond latency ceiling for the fast path.
- PyO3 action identifiers and payloads are raw `bytes`; verification raises on failure.

### 7.5 Nomenclature & Branding

- Product name is **ReluLayer™**.
- Categories are **Edge Governor** and **Execution Gatekeeper**.
- Federal / defense references use **Physical Super Intelligence (Physical SI)**.
- Do not anthropomorphize the kernel: avoid "reflexes", "thoughts", "instincts", or "believes".

---

## 8. Related Documents

- `README.md` — Quickstart, latency matrix, and applicability matrix.
- `COOKBOOK.md` — Runnable integration recipes (agent tool calling, replay prevention, robotics governor).
- `ENTERPRISE_EVAL.md` — Inbound engagement protocol for OEM and defense design partners.
- `cursor_oss_release_prompt.md` / `cursor_post_push_automation_prompt.md` — Historical release-automation prompts (reference only).
- `Organizations/AtelierLogicGroup/00-governance/entity-identity.md` — Canonical entity identifiers (UEI, CAGE, NAICS, PSC, patent serials).

---

*End of PRD — authoritative baseline for ReluLayer™ v0.2.0.*
