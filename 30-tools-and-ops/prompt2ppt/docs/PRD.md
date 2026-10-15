**Role:** Chief Enterprise Architect
**Task:** Draft the comprehensive Product Requirements Document (PRD) for the ReluLayer Engine.

**Context:** Read the `.cursorrules` file to understand the project's identity, tech stack, and strict architectural constraints. 

**Instructions:**
Draft a formal, enterprise-grade PRD in this `PRD.md` file. Include the following sections:
1. **Executive Summary:** The $2.5B Federal Obligation mandate, municipal chaos resolution, and zero-clawback resilience.
2. **System Architecture:** Detail the implementation of the 7 Layers of AI Engineering.
3. **Core Workflows:** - *Workflow A (ETL Plane):* Ingesting municipal CSVs/PDFs -> DSPy Schema Extraction -> OR-Tools execution.
   - *Workflow B (GTM Plane):* Ingesting briefs -> DSPy Art Director / Content generation -> Stable Diffusion 3.5 -> PPTX compilation with Template RAG.
4. **Hardware & Infrastructure constraints:** Local RTX 5090, WSL, Docker, VRAM optimization.
5. **Success Metrics & Programmatic Auditing:** How we measure hallucination rates (must be 0% at the execution layer) and performance.