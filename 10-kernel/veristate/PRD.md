# Product Requirement Document (PRD): Project VeriState

> **Canonical entity identity:** `AtelierLogicGroup/00-governance/entity-identity.md`. Any edits to UEI, CAGE, NAICS, PSC, patent serials, or addresses must be synchronized with that file.

**Classification:** Enterprise Internal / Proprietary
**Target Environment:** Enterprise Apple Platform (iOS / macOS Ecosystem) & Local Workspace Dev/Test (WSL2 Linux)
**Version:** 3.2.0 (Asynchronous Core, Stateless Singletons, & High-Throughput Edge Architecture)

---

## 1. Executive Summary & Core Mission
Project VeriState is an enterprise-grade, edge-deterministic state-enforcement system designed to eliminate transactional fraud, data corruption, and verification hallucinations within high-consequence field asset operations (e.g., insurance adjustments, engineering surveys, asset integrity inspections).

The system replaces passive digital entry forms with cryptographically signed, hardware-attested, and spatially verified transaction manifests. Trust is enforced deterministically by cryptographic and geometric proofs at the edge, removing any dependency on runtime cloud connectivity or operator compliance. 

Version 3.2.0 architecture establishes an ultra-low latency, decoupled processing framework. It introduces a global thread-safe state singleton within the native execution core to prevent key-derivation thrashing, and utilizes a multi-threaded presentation engine powered by Dart background Isolates. This completely insulates the host application's user interface from native cryptographic calculations and physical flash-storage disk write overhead, maintaining a fluid rendering profile during intensive data-ingestion workloads.

## 2. Core Architectural Pillars & Invariants
- **Determinism over Probability:** All analytical and verification logic in the primary trust path must rely on pure mathematical, text-matching, or cryptographic algorithms. Probabilistic outputs from AI models are strictly banned from entering the validation, persistence, or serialization tracks. 
- **Edge-Local & Disconnected-First:** All validation, ledger storage, cryptographic transformations, and synchronization preparation must execute entirely on the target device hardware without requiring external cloud orchestration.
- **Transactional Outbox Isolation:** Local writes must never synchronously depend on network execution or external process invocation. Data capture commits atomically to the local relational cache and an internal synchronization queue simultaneously.
- **In-Database Cryptographic Lineage:** Relational entries must retain structural, tamper-evident lineage independent of the transport layout using row-level cryptographic hash-chaining ($H_n = \text{SHA-256}(F_n \mathbin{\Vert} H_{n-1})$).
- **Zero-Trust Memory Boundaries:** The native Rust core owns all unmanaged allocation lifetimes across the foreign function interface (FFI) boundary. It utilizes strict C-ABI structures to eliminate pointer leaks, integer underflow wraparounds, or memory corruption on the host container. All crossed memory pointer records must be instantly unpacked into pure immutable Dart models and explicitly freed via audited native destructors.
- **Persistent Runtime Singletons:** The unmanaged FFI gateway must preserve expensive cryptographic contexts and connection environments inside global, thread-safe `OnceLock<Mutex<T>>` abstractions. Re-initializing database file decryption keys or running KDF routines on a per-call basis is strictly prohibited.
- **Asynchronous Presentation Isolation:** The host user interface thread must operate with zero blocking FFI friction. All unmanaged transaction execution blocks exceeding a $2.0\text{ ms}$ processing footprint must be explicitly offloaded to independent background OS threads (Dart Isolates) to guarantee a consistent $120\text{Hz}$ UI frame budget ($8.33\text{ ms}$ max latency per frame).

## 3. High-Integrity Technical Architecture

### 3.1 Compilation & Deployment Matrix
- **Native Performance Core (`veristate-core`):** Written in Standard Native Rust (Edition 2024, Runtime Rust 1.90+). 
- **Multi-Target Cross-Compilation Profiles:**
  - Local Dev/Verification: `x86_64-unknown-linux-gnu` / `x86_64-pc-windows-gnu` / `x86_64-linux-android`
  - Enterprise Target Environment: `aarch64-apple-ios`, `aarch64-apple-darwin`, and `aarch64-linux-android` compiled, bundled, and wrapped as high-integrity native components.
- **Automated Mobile Toolchain Integration:** Target cross-compilation is orchestrated entirely via `compile_android.sh`, targeting `arm64-v8a` (production field silicon) and `x86_64` (workspace emulation layouts) using `cargo-ndk`. Binaries are stripped, optimized (~7.5 MB per `.so` shared object), and directly deposited into the presentation container's internal JNI link folders (`flutter_shell/android/app/src/main/jniLibs`).
- **Presentation Layer Container (`flutter_shell`):** Compiled natively on the targeted host machine (macOS/iOS for production; Windows/Linux workstations via loopback and emulation tools for local testing). Interacts with the native performance core through zero-copy Dart-FFI unmanaged pointer addresses.

### 3.2 Security Perimeter & Data Storage
- **Local Ledger Subsystem:** Embedded **SQLCipher** utilizing optimized, low-overhead transaction parameters to minimize physical storage controller constraints.
  - *Advanced Engine Tuning:* To maximize throughput, the database engine bypasses standard filesystem interaction patterns via explicit kernel-level optimization directives:
    ```sql
    PRAGMA journal_mode = WAL;
    PRAGMA synchronous = NORMAL;
    PRAGMA locking_mode = EXCLUSIVE;
    PRAGMA mmap_size = 268435456;  -- 256 MB Virtual Memory Map
    PRAGMA cache_size = -64000;    -- 64 MB Volatile RAM Cache Page Allocation
    PRAGMA temp_store = MEMORY;    -- Volatile RAM Temporary Table Storage
    ```
  - *EXCLUSIVE Locking Invariant:* Configuring `EXCLUSIVE` locking ensures the core engine retains file system control permanently, completely eliminating operating system file-lock dropping and reclaiming overhead during transaction `COMMIT` cycles.
  - *Testing Invariant Constraints:* Because SQLite in-memory databases (`:memory:`) bypass Write-Ahead Logging (WAL) state allocations, all test-harness vectors asserting database schema execution must initialize isolated, disk-backed ephemeral storage locations using temporary filesystem layout strategies (`std::env::temp_dir()`) to prevent state invariant verification crashes.
- **Row-Level Hash-Chaining:** The `findings` table enforces cryptographic tamper-evidence using a sequential SHA-256 chain calculation:
  $$H_n = \text{SHA-256}(F_n \mathbin{\Vert} H_{n-1})$$
- **Cryptographic Key Lifecycle:** Encryption keys are ephemeral and stored strictly within volatile RAM. The master seed required by **HKDF-SHA256** computation must be initialized and pulled directly from the target environment's hardware-backed Secure Enclave / Keychain Services, completely blocking memory-dump analysis vulnerabilities.
- **In-Process Git Transport Engine:** Remote ledger mirroring must bypass external shell command subprocess spawning (`std::process::Command`). All staging, index modification, object committing, and packing must execute entirely in-process using direct static linking against `libgit2` (via the `git2` crate).

---

## 4. Institutional Capability Targets
1. **Deterministic Structured Processing:** Extract canonical inspection entities from unstructured entry streams using a zero-allocation matching engine.
2. **Hardware-Anchored Key Derivation:** Execute volatile HKDF-SHA256 operations tied to native secure element keys.
3. **Atomic Outbox Persistence:** Maintain transactional atomic writes over a protected SQLCipher instance, routing every telemetry write through a unified relational table transaction block along with an outbound synchronization record.
4. **Asynchronous Edge Sync Subsystem:** An isolated background worker thread or Tokio task that polls the relational outbox table, serializes pending states to canonical flat JSON files, generates localized commits via `git2`, handles pushes over loopback SSH networks with exponential backoff, and marks records completed upon server confirmation.
5. **Multi-Threaded Presentation Routing:** Provide an asynchronous endpoint pipeline using the **Axum** framework backed by **Tokio** runtime executors. Shared relational structures cross multi-threaded asynchronous boundaries safely via scope-isolated transaction blocks guarded by an explicit mutual exclusion pointer wrapper (`std::sync::Mutex<StorageEngine>`), preventing cross-thread lock retention deadlocks.
6. **High-Throughput Ingestion Batching (Group Commit Pipeline):** Transition the ingestion core from synchronous single-write commitments to an in-memory transactional aggregation queue, processing multiple validated data payloads within a single disk synchronization barrier.
7. **Local Automated Database Retention & Pruning:** Enforce automated edge-cleaning background tasks to identify successfully synchronized outbox entities, safely purging historical ledger indices outside a configured operational retention envelope (e.g., 30 days) to prevent local storage degradation.

---

## 5. Implementation Status Matrix

| Module | Interface Boundary | Evaluation | Technical Progress Details |
| :--- | :--- | :--- | :--- |
| `nlp/parser.rs` | `TokenExtractionEngine::parse` | ✅ Pass | Zero-allocation, case-insensitive structural matching engine. Fully covered by unit validations. |
| `crypto.rs` | `EphemeralKeyEngine::derive_key` | ✅ Pass | HKDF-SHA256 primitive operational. Explicit signing wrappers pending production Keychain binding. |
| `storage.rs` | `StorageEngine` | ✅ Pass | Outbox schema integrated. Type-safe Serde serialization blocks unescaped injection parameters. Hardened with high-throughput engine tuning flags (`mmap`, `cache_size`, `EXCLUSIVE` locks). |
| `sync/worker.rs` | `GitSynchronizer` | ✅ Pass | Replaced legacy Git CLI subprocess loops with memory-safe, in-process asynchronous `git2` repository workers. Outbox record state transactions verified via loopback testing. |
| `server.rs` | `ApiServer::bootstrap` | ✅ Pass | Multi-threaded Axum infrastructure established on Tokio. Incorporates type-safe payload extraction (`IngestFindingRequest`) and thread-safe database locking. Covered by `TestServer` modules. |
| `ffi.rs` | Type-Safe C ABI Surface | ✅ Pass | Hardened boundary surface. Caches expensive `Orchestrator` structures inside a global `OnceLock<Mutex<T>>` singleton, completely eliminating connection and KDF bootstrap thrashing. Defensive length constraints handle integer underflow risks. |
| `attestation` | `AttestationVerifier::verify_token` | 🏗️ Progress | Structured skeletal infrastructure established. Enforces app identity tracking (`org.veristate.fieldapp`) and cryptographic SHA-256 base64url nonce verification (replay protection). Integrates a backward-compatible bridge for legacy FFI arrays. |
| `telemetry_coordinator.dart` | `TelemetryCoordinator::processIncomingStream` | ✅ Pass | Asynchronous, actor-model offloading implemented. Utilizes `Isolate.run()` to isolate the unmanaged FFI transition and native 5ms cryptographic load onto independent background CPU threads. |
| `main.dart` | `TelemetryMonitorDashboard` | ✅ Pass | Presentation monitor views re-architected to seamlessly capture asynchronous isolate states, introducing visual progress frames to track active native execution cycles. |

---

## 6. Engineering Constraints & Operational Governance
- **TDD Requirement:** No functional adjustments can be merged into production source code files within `veristate-core` without first satisfying a strict RED-GREEN-REFACTOR lifecycle pass inside localized unit testing spaces. The active verification pipeline must pass a clean 29-out-of-29 test matrix matrix before staging.
- **Static Analysis Compliance:** All Rust implementation layers must run with zero compile warnings and fully satisfy strict compiler lint baselines: `#![deny(unsafe_code)]` must be preserved for all modules outside of thin, explicitly isolated FFI raw pointer transactions.

---

## 7. Project Management Framework (Epics & User Stories)

### Epic 1: High-Integrity Local Data & Storage Core
* **User Story 1.1: Embedded Relational Ledger Storage Integration**
    * *As a developer, I need to integrate an embedded SQLCipher instance running in WAL mode with normal sync profiles so that system writes are atomic and performance-optimized.* [✅ **Completed & Verified**]
* **User Story 1.2: Sequential Cryptographic Ledger Chaining**
    * *As a security compliance auditor, I need the findings table to implement an automated sequential SHA-256 hash chain on insert so that any unauthorized database row modification causes structural validation chain breaks.* [✅ **Completed & Verified**]
* **User Story 1.3: Ephemeral Secure Key Derivation**
    * *As a security engineer, I need volatile cryptographic master seeds pulled directly from the target environment's Secure Enclave or Keychain to fuel an HKDF-SHA256 engine in RAM so that file memory dumps yield no plaintext key signatures.* [✅ **Completed & Verified**]
* **User Story 1.4: Group Commit / High-Throughput Inbound Batching Pipeline**
    * *As a core developer, I need an in-memory transactional aggregation queue to bundle multiple telemetry writes inside a single database transaction context to entirely bypass physical drive IOPS bottlenecks.* [🏗️ **Planned / Next Milestone**]
* **User Story 1.5: Local Storage Automated Retention & Pruning Tasks**
    * *As a mobile platform engineer, I need an automated pruning background routine to delete completed outbox records and enforce a local data retention window so that device storage capacity does not degrade.* [🏗️ **Planned / Next Milestone**]

### Epic 2: Stateless Server API Layer (Axum & Tokio Core)
* **User Story 2.1: Multi-Threaded Axum Framework Bootstrap**
    * *As a backend developer, I need to configure an Axum engine backed by a Tokio asynchronous runtime to structure incoming data endpoints efficiently on our workstation infrastructure.* [✅ **Completed & Verified**]
* **User Story 2.2: Type-Safe Request Body Extraction & Deserialization**
    * *As an integration engineer, I need incoming mobile payloads validated via type-safe Serde structures inside Axum extractors to block unescaped string injection vectors completely.* [✅ **Completed & Verified**]

### Epic 3: Asynchronous Outbox Synchronization Subsystem
* **User Story 3.1: Atomic Relational Storage Outbox Engine**
    * *As a system architect, I need local mutation commands to execute concurrently inside a single transaction writing to both the operational table and the outbox queue schema so that local updates are completely insulated from network states.* [✅ **Completed & Verified**]
* **User Story 3.2: In-Process Asynchronous Git Queue Worker**
    * *As a DevOps lead, I need a background Tokio task to poll the outbox schema, serialize records to disk, and generate localized index commits entirely in-process via static linking to git2 to bypass external shell commands.* [✅ **Completed & Verified**]
* **User Story 3.3: Loopback Transport Edge Synchronization Routing & Deployment**
    * *As a platform operator, I need local git2 worker pools to push changes securely across port 2225 to Gitea using automatic retry intervals, and I need the native module to cross-compile into multi-architecture Android `.so` objects using an automated tooling script.* [✅ **Completed & Verified**]
* **User Story 3.4: Asynchronous Cross-Runtime Presentation Offloading**
    * *As a mobile user experience designer, I need the application's front-end shell to delegate unmanaged pointer execution blocks to an independent background OS thread using Dart Isolates so that the primary thread remains responsive at a fluent 120Hz rendering budget.* [✅ **Completed & Verified**]