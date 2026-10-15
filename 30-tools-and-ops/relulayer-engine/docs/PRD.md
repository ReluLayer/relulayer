**Role:** Chief Enterprise Architect
**Task:** Draft the Product Requirements Document (PRD) for the ReluLayer Engine.

**Context:** Read the `.cursorrules` file to understand the project's identity, tech stack, and strict architectural constraints. This is a general-purpose foundational POC, not tied to a specific industry vertical yet.

**Instructions:**
Draft a formal PRD in this `PRD.md` file. Include the following sections:
1. **Executive Summary:** The goal of building a general-purpose AI orchestration engine that guarantees zero-hallucination handoffs between probabilistic LLMs and deterministic Python execution.
2. **System Architecture:** Detail the implementation of the 7 Layers of AI Engineering.
3. **Core Capabilities (Workflows):** - *Data Extraction (ETL):* Ingesting unstructured documents -> DSPy structured extraction -> validated JSON output.
   - *Multimodal Document Generation:* User prompt + reference files -> DSPy content/design agents -> Stable Diffusion visual anchors -> PPTX compilation with Template RAG.
4. **Hardware & Infrastructure constraints:** Local RTX 5090, WSL, Docker, VRAM optimization.
5. **Observability & Auditing:** How the system provides "Glass Box" traceability for every LLM decision and execution step.