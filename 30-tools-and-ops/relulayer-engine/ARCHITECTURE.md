# ReluLayer™ Architecture — 9-Layer Engineering Model

**Version:** 1.0  
**Applies to:** ReluLayer™ product line (kernel, digital twin, engine, and GTM tooling)  
**Entity:** Atelier Logic Group LLC dba ReluLayer™ — see `Organizations/AtelierLogicGroup/00-governance/entity-identity.md` for canonical identifiers.  
**Principle:** *Deterministic layers validate probabilistic layers. Probabilistic layers never control physical actuators.*

---

## 1. Purpose

This document defines the canonical 9-layer engineering model for ReluLayer™. It is stricter than a generic 14-layer AI best-practice stack because it is built for a dual-use product: high-assurance embedded safety kernels, defense SBIR deliverables, and enterprise AI governance tooling.

The model is designed to be:

- **Auditable:** every layer has an explicit interface and a deterministic boundary.
- **Air-gap friendly:** the safety-critical path does not depend on cloud APIs.
- **Composable:** a layer can be replaced without collapsing the stack.
- **SBIR-traceable:** each layer maps to a Volume II technical section or a DO-178C software level.

---

## 2. The 9 layers

### Layer 1 — Infrastructure & Compute

**Purpose:** Provide the hardware, container, network, and GPU envelope.

**Belongs here:**

- Docker Compose, NVIDIA Container Toolkit, CUDA 12.8 base image.
- GPU reservation and VRAM hygiene (`VRAMManager`).
- Build targets: `x86_64` dev host, `thumbv7em-none-eabihf` for STM32H7, `aarch64` for Jetson/Apple.
- CI/CD pipelines (Gitea act_runner, GitHub Actions).

**Does NOT belong here:**

- Business logic, prompt templates, or model weights.

**Directory:**

```text
Organizations/ReluLayer/10-kernel/infrastructure/
Organizations/ReluLayer/30-tools-and-ops/relulayer-engine/infrastructure/
```

**Interface:**

```text
Layer 2 consumes: containerized services, GPU allocation, network policy.
```

---

### Layer 2 — Security & Compliance

**Purpose:** Enforce the trust boundary before any data or model is touched.

**Belongs here:**

- CMMC Level 1 / FCI safeguarding.
- SQLCipher encryption keys, HKDF-SHA256 key derivation.
- Hardware attestation (PUF, Secure Enclave).
- Code-signing, SBOM generation, dependency audit.
- Air-gap and zero-egress policy enforcement.
- `governance:anti-genai` and lineage validators, if they exist as real CI gates.

**Does NOT belong here:**

- Model inference logic, UI components, or proposal documents.

**Directory:**

```text
Organizations/ReluLayer/10-kernel/security/
Organizations/ReluLayer/30-tools-and-ops/relulayer-engine/security/
```

**Interface:**

```text
Layer 3, 5, 6, and 7 call Layer 2 for identity, encryption, attestation, and egress checks.
```

**Note:** This is the largest gap in the previous 7-layer model. For defense buyers, this layer must be visible and testable.

---

### Layer 3 — Data & Ingestion

**Purpose:** Ingest, validate, version, and normalize raw inputs.

**Belongs here:**

- File ingestion (PDF, CSV, DOCX, telemetry).
- Schema validation, ETL, and lineage tracking.
- Telemetry datasets (`trajair_outdoor_flight.csv`, `nanobench_swarm_formation.csv`).
- SIL/HIL scenario loaders.

**Does NOT belong here:**

- LLM reasoning, prompt engineering, or UI rendering.

**Directory:**

```text
Organizations/ReluLayer/20-pilots-and-proposals/sbir-digital-twin/data/
Organizations/ReluLayer/30-tools-and-ops/relulayer-engine/data/
```

**Interface:**

```text
Outputs normalized, schema-bound records to Layer 4 and Layer 6.
```

---

### Layer 4 — Knowledge & Context

**Purpose:** Transform normalized data into the context that models and tools consume.

**Belongs here:**

- Vector store, RAG, semantic search.
- `context_string` preparation.
- Template metadata and prompt assembly.
- Domain-specific context boundaries (e.g., “only use this PPA section”).

**Does NOT belong here:**

- Raw model weights, DSPy module logic, or final UI state.

**Directory:**

```text
Organizations/ReluLayer/30-tools-and-ops/relulayer-engine/knowledge/
```

**Interface:**

```text
Consumes records from Layer 3. Produces context_string and template metadata to Layer 5 and Layer 6.
```

---

### Layer 5 — Models & Prompt Engineering

**Purpose:** Host, route, and constrain probabilistic models.

**Belongs here:**

- LLM routing configuration (Ollama model IDs, API base URLs, local-only endpoints).
- DSPy Signatures and Modules.
- Prompt templates, context-window management.
- Model selection logic (e.g., which model handles which extraction task).

**Does NOT belong here:**

- Deterministic execution, tool implementation, or safety-critical decisions.

**Directory:**

```text
Organizations/ReluLayer/30-tools-and-ops/relulayer-engine/models/
```

**Critical rule:**

```text
Models only emit typed JSON, schemas, or structured text. They never directly call tools, write files, or send commands to actuators.
```

**Interface:**

```text
Consumes context from Layer 4. Outputs structured proposals to Layer 6.
```

---

### Layer 6 — Orchestration & Agents

**Purpose:** Coordinate deterministic and probabilistic steps into a verifiable workflow.

**Belongs here:**

- FastAPI-facing orchestration.
- DSPy program assembly.
- Workflow state machines.
- Multi-step agent loops with stop conditions.
- Rate limiting and retry policy (see `orchestration/rate_limiter.py`).

**Does NOT belong here:**

- LLM internals (Layer 5), raw tool logic (Layer 7), or UI rendering (Layer 9).

**Directory:**

```text
Organizations/ReluLayer/30-tools-and-ops/relulayer-engine/orchestration/
```

**Interface:**

```text
Consumes structured output from Layer 5. Dispatches deterministic work to Layer 7. Logs every decision to Layer 8.
```

---

### Layer 7 — Tools & Application Logic

**Purpose:** Execute deterministic, auditable operations.

**Belongs here:**

- PPTX assembly, PDF generation, image/SVG/ICO asset generation.
- Pandas-driven transforms, data extraction, numerical computation.
- C ABI/FFI bridge to the ReluLayer kernel.
- Document compilation (LaTeX, Typst).
- External API calls that are not LLM inference (e.g., SBIR.gov scraping).

**Does NOT belong here:**

- LLM client imports (DSPy, Ollama SDK, OpenAI SDK).
- Safety-critical actuator commands (those belong in the kernel).

**Directory:**

```text
Organizations/ReluLayer/30-tools-and-ops/relulayer-engine/tools/
Organizations/ReluLayer/20-pilots-and-proposals/sbir-digital-twin/scripts/
```

**Critical rule:**

```text
Tools never import LLM clients. They receive typed inputs from Layer 6 and produce deterministic outputs.
```

**Interface:**

```text
Receives typed tasks from Layer 6. Returns deterministic results and side-effect logs to Layer 6 and Layer 8.
```

---

### Layer 8 — Evaluation, Experimentation & Governance

**Purpose:** Validate outputs, run Design of Experiments (DoE), detect hallucinations, and maintain audit lineage.

**Belongs here:**

- DSPy assertions and quality gates.
- Audit logging, `audit.py`.
- **Design of Experiments (DoE) harness:** repeatable experiments that compare models, prompts, architectures, or tool chains against real-world datasets.
- Statistical validation techniques: Markov Chain state-transition analysis, ROC/AUC curves, confidence intervals, hypothesis testing, and any other method justified by the problem domain.
- Real-data benchmarks and regression suites (not only synthetic tests).
- Hallucination and drift detection by comparing generated outputs against ground truth, source documents, or structured embeddings.
- Bitemporal ledger (`valid_time`, `transaction_time`, `payload_sha256`).
- HIL/SIL benchmarks, DO-178C traceability, MIL-STD-882E safe-state verification.
- Compliance report generation.

**Does NOT belong here:**

- Model weights, UI code, raw ingestion, or the datasets themselves (those live in Layer 3).

**Directory:**

```text
Organizations/ReluLayer/30-tools-and-ops/relulayer-engine/evaluation/
Organizations/ReluLayer/30-tools-and-ops/relulayer-engine/evaluation/experiments/   # DoE harness
Organizations/ReluLayer/20-pilots-and-proposals/sbir-digital-twin/results/
```

**Interface:**

```text
Consumes execution traces from Layers 6 and 7, plus real datasets from Layer 3. Outputs pass/fail verdicts, statistical evidence, experiment artifacts, audit records, and compliance evidence.
```

---

### Layer 9 — Frontend & Analytics

**Purpose:** Present the system to humans and expose business-facing features.

**Belongs here:**

- React/Vite/TypeScript UI.
- Dashboards, analytics, explainability views.
- Lead-capture forms, SBLO portal, capability statement pages.
- Public marketing sites (`atelierlogicgroup.com`, `relulayer.ai`).

**Does NOT belong here:**

- Model inference, tool execution, or kernel logic.

**Directory:**

```text
Organizations/ReluLayer/30-tools-and-ops/relulayer-engine/frontend/
Organizations/ReluLayer/20-pilots-and-proposals/sbir-digital-twin/pitch-deck/
Organizations/AtelierLogicGroup/02-gtm-and-sales/websites/
```

**Interface:**

```text
Consumes read-only traces and results from Layer 8. Sends user requests to Layer 6.
```

---

## 3. Mapping from the previous 7-layer model

| Previous 7-layer | New 9-layer | Change |
|---|---|---|
| 1. Infrastructure | 1. Infrastructure & Compute | No change |
| — | 2. Security & Compliance | **New dedicated layer** |
| 2. Models | 5. Models & Prompt Engineering | Renamed; prompt engineering made explicit |
| 3. Orchestration | 6. Orchestration & Agents | Renamed; agent coordination made explicit |
| 4. Memory | 3. Data & Ingestion + 4. Knowledge & Context | **Split** |
| 5. Tools | 7. Tools & Application Logic | Renamed; application boundary made explicit |
| 6. Evaluation | 8. Evaluation & Governance | Renamed; governance made explicit |
| 7. Frontend | 9. Frontend & Analytics | Renamed; analytics made explicit |

---

## 4. Cross-layer rules

1. **Deterministic boundary.** Layer 7 may call Layer 6 for structured input, but Layer 6 may not call Layer 7 inside an LLM prompt chain.
2. **No LLM imports in tools.** Layer 7 is forbidden from importing DSPy, Ollama, or OpenAI SDKs.
3. **Security is a vertical concern.** Layer 2 provides primitives; every other layer uses them. Security is not an afterthought in Layer 1.
4. **Audit is write-once.** Layer 8 logs are immutable. If a record is corrected, a new record is appended with a corrected `transaction_time`.
5. **UI is read-only for audit.** Layer 9 reads from Layer 8 but never writes to it directly.
6. **Air-gap path.** Layers 1–4, 7, and 8 can run without cloud access. Layer 5 and 6 default to local endpoints.

---

## 5. Directory structure under the consolidated model

```text
Organizations/
├── shared-standards/
│   ├── brand/BRANDING.md                # Shared brand tokens and visual identity
│   ├── engineering/                     # Engineering standards
│   ├── security/                        # Security and compliance standards
│   └── compliance/                      # Governance, legal, and audit standards
├── shared-assets/
│   ├── templates/                       # Reusable proposal, deck, and web templates
│   ├── fonts/                           # Approved typography files
│   ├── logos/                           # Logo files and wordmarks
│   └── icons/                           # Favicon and icon library
│
├── ReluLayer/
│   ├── 00-product-strategy/
│   │   └── PRD/
│   ├── 10-kernel/
│   │   ├── relulayer-kernel-rs/
│   │   │   ├── crates/
│   │   │   │   ├── relulayer-core/          # Layer 1 + 2 (bare-metal)
│   │   │   │   ├── relulayer-ffi/           # Layer 7 bridge
│   │   │   │   └── relulayer-py/            # Layer 7 Python bindings
│   │   │   ├── security/                    # Layer 2
│   │   │   └── infrastructure/              # Layer 1
│   │   ├── relulayer-digital-twin/
│   │   │   ├── data/                        # Layer 3
│   │   │   ├── knowledge/                   # Layer 4
│   │   │   ├── evaluation/                  # Layer 8
│   │   │   └── infrastructure/              # Layer 1
│   │   └── relulayer-website/
│   │       └── (Layer 9 product pages)
│   │
│   ├── 20-pilots-and-proposals/
│   │   ├── sbir-digital-twin/
│   │   │   ├── data/                        # Layer 3
│   │   │   ├── scripts/                     # Layer 7
│   │   │   ├── results/                     # Layer 8
│   │   │   └── proposal/                    # Layer 8 output
│   │   └── atelier-defense-vault/
│   │       └── (Layer 8 compliance evidence)
│   │
│   ├── 30-tools-and-ops/
│   │   ├── relulayer-engine/                # General orchestration engine
│   │   │   ├── infrastructure/              # Layer 1
│   │   │   ├── security/                    # Layer 2
│   │   │   ├── data/                        # Layer 3
│   │   │   ├── knowledge/                   # Layer 4
│   │   │   ├── models/                      # Layer 5
│   │   │   ├── orchestration/               # Layer 6
│   │   │   │   └── rate_limiter.py
│   │   │   ├── tools/                       # Layer 7
│   │   │   ├── evaluation/                  # Layer 8
│   │   │   │   ├── audit.py
│   │   │   │   ├── smoke_test.py
│   │   │   │   └── experiments/             # DoE harness (Layer 8)
│   │   │   └── frontend/                    # Layer 9
│   │   ├── otto-aviation/                   # Layer 7 MCP-client prototype
│   │   └── prompt2ppt/                      # Layer 7 prompt-to-PPTX tool
│   │
│   └── 40-archive/
│       └── relulayer-sandbox/
│           └── (legacy layers, frozen)
│
└── AtelierLogicGroup/
    ├── 00-governance/
    │   └── entity-identity.md
    ├── 01-services/
    │   └── sblo-dashboard/                  # Layer 9 proposal-management service
    ├── 02-gtm-and-sales/
    │   └── websites/                        # Layer 9 marketing sites
    └── 03-advisory/
        └── (advisory board materials)
```

---

## 6. Related files

- `../../README.md` — Overview of the consolidated `ReluLayer/` product space.
- `orchestration/rate_limiter.py` — Concrete API rate-limiting implementation for Layer 6.
- `~/Organizations/AtelierLogicGroup/README.md` — Services, GTM, and helper-app structure (sibling repository).
