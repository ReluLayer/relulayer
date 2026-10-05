# ReluLayer Engine: The General-Purpose Deterministic AI Orchestrator

ReluLayer Engine is a **locally hosted** orchestration platform that keeps probabilistic LLM steps behind typed contracts (DSPy) while **deterministic Python** owns data extraction, asset generation, and document assembly. It targets **high-stakes outputs** where handoffs must be structured, observable, and repeatable—especially on a single high-end workstation GPU.

The product vision and workflows are summarized in [`docs/PRD.md`](docs/PRD.md); day-to-day engineering constraints live in [`.cursorrules`](.cursorrules) and [`ARCHITECTURE.md`](ARCHITECTURE.md).

## The 9-Layer Blueprint

| Layer | Directory | Function |
| :--- | :--- | :--- |
| **1 — Infrastructure & Compute** | `infrastructure/` | Compute envelope: CUDA-aware Docker image, Compose with GPU reservations, VRAM hygiene utilities (`VRAMManager`). |
| **2 — Security & Compliance** | `security/` | Encryption, attestation, egress policy, SBOM, and compliance artifacts. |
| **3 — Data & Ingestion** | `data/` | Ingestion, ETL, schema validation, and raw telemetry normalization. |
| **4 — Knowledge & Context** | `knowledge/` | RAG, context preparation, `context_string` assembly, and template metadata. |
| **5 — Models & Prompt Engineering** | `models/` | LLM routing configuration (e.g. Ollama model IDs, API base URLs) and DSPy Signatures/Modules. |
| **6 — Orchestration & Agents** | `orchestration/` | FastAPI-facing logic, agent workflows, multi-step loops, and the shared `RateLimiter`. |
| **7 — Tools & Application Logic** | `tools/` | Deterministic execution plane: PPTX assembly, raster/SVG/ICO assets, pandas-driven transforms—**no LLM imports**. |
| **8 — Evaluation, Experimentation & Governance** | `evaluation/` | Assertions, audit logging, DoE harness (`evaluation/experiments/`), real-data validation, ROC/Markov analysis, hallucination detection, smoke tests, and the `audit.py` runner. |
| **9 — Frontend & Analytics** | `frontend/` | Glass-box UI: React / Vite / TypeScript, Tailwind, Axios—trace-heavy presentation of runs and errors. |

Together, these layers enforce a **deterministic boundary**: models propose structured JSON and schemas; **tools** and **knowledge** never call LLMs directly.

## Hardware Mandate

- **GPU:** NVIDIA **RTX 5090** (Blackwell architecture, **32 GB** VRAM) as the reference deployment for local inference and optional GPU-assisted tooling.
- **CUDA:** **12.8** runtime alignment with the CUDA base image used in `infrastructure/Dockerfile` (NVIDIA CUDA 12.8 on Ubuntu 22.04).
- **Host OS:** **WSL2** with **Ubuntu** is the expected development path; production-style runs use **Docker** with the **NVIDIA Container Toolkit** so Compose can attach **all** GPUs to the backend service.
- **VRAM policy:** Orchestration and GPU-touching paths should clear caches after heavy work (`torch.cuda.empty_cache()` via `VRAMManager`) so long sessions do not drift into OOM on a single-GPU box.

Ollama and optional image models (e.g. Stable Diffusion) are assumed to run **on the host** or adjacent to the stack; the Compose file wires **`OLLAMA_HOST`** (default `http://host.docker.internal:11434`) for containerized backends.

## The Audit Protocol

ReluLayer treats the repository as a **zero-drift** workspace: layer folders, DSPy usage, VRAM rules, RateLimiter usage, and the deterministic **`tools/`** boundary are checked mechanically.

From the **repository root**:

```bash
python3 evaluation/audit.py
```

- Verifies that all **nine** mandated top-level directories exist and flags unexpected or junk-style top-level folders.
- Scans **`orchestration/`** for raw prompt anti-patterns and DSPy surface usage.
- Ensures **`tools/`** and **`orchestration/`** files that import **PyTorch** also call **`VRAMManager.clear()`** where required.
- Forbids LLM client imports under **`tools/`** (e.g. DSPy, Ollama SDKs).

The process exits with a **non-zero** status if **critical** violations are found—suitable for **CI/CD** gates. Warnings alone do not fail the build.

## Quick Start

1. **GPU backend container** (from repo root):

   ```bash
   docker compose -f infrastructure/docker-compose.yml up -d
   ```

   Ensure the NVIDIA driver, Container Toolkit, and Docker Compose v2 GPU support match your WSL/Linux setup.

2. **Local smoke check** (Python 3.12+ recommended; run with dependencies installed, e.g. in the same environment as your IDE or container):

   ```bash
   python3 evaluation/smoke_test.py
   ```

   This runs `evaluation/audit.py` and imports core Layer 3–6 modules. It does **not** start Ollama or require a live GPU for the import path.

For application-level API startup, point **`PYTHONPATH`** at the repo root (or `/app` inside the container) so packages such as `orchestration` and `knowledge` resolve correctly.

## Security and Data Sovereignty

**All LLM reasoning is intended to run locally** via **Ollama** (and similarly local inference stacks for optional vision or diffusion workloads). No cloud inference is required for the core architecture: prompts and payloads stay on your machine under your policy, supporting **data sovereignty** and air-gapped deployments when paired with offline model artifacts and images.

Third-party libraries (e.g. LiteLLM inside DSPy) should still be configured so that **production** traffic targets **local** endpoints only unless you explicitly opt in to external providers.

---

*Aesthetic note:* the product targets a **Glass Box** audit experience—dark, monospace-forward UI with high observability of traces and failures end to end.
