# ReluLayer™ Product Repository

**Entity:** Atelier Logic Group LLC dba ReluLayer™  
**CAGE:** `20JX8`  
**UEI:** `G9WFN3AL69J3`  
**Purpose:** Deep-tech product source code, proposals, and operational tooling for the ReluLayer™ deterministic safety kernel and related systems.

> **Canonical entity identity:** `AtelierLogicGroup/00-governance/entity-identity.md`. All entity identifiers (UEI, CAGE, NAICS, PSC, patent serials, addresses) should be synchronized with that file.

This directory is the consolidated home for all ReluLayer™ product work. It is separate from `AtelierLogicGroup/`, which holds services, GTM, and advisory work.

---

## Structure

```text
ReluLayer/
├── 00-product-strategy/          # PRDs, roadmaps, market analysis
├── 10-kernel/                      # Safety kernel, digital twin, core product
├── 20-pilots-and-proposals/        # SBIR, STTR, pilot evidence, patent support
├── 30-tools-and-ops/               # Internal tools, orchestration, dashboards
└── 40-archive/                     # Legacy experiments, retired work
```

### 10-kernel

The core product stack:

- `relulayer-kernel-rs/` — `#![no_std]` Rust workspace (core, FFI, Python bindings).
- `relulayer-digital-twin/` — Software-in-the-loop and hardware-in-the-loop verification.
- `veristate/` — Edge-deterministic state enforcement and cryptographic transaction lineage.
- `relulayer-website/` — Product-facing technical site and demos.

### 20-pilots-and-proposals

Customer-facing and government-facing artifacts:

- `sbir-digital-twin/` — SBIR ARM26TX04-NV001 and related proposal packages.
- `sbir-gtm-websites/` — Public-facing web presence (corporate + product hub) and dual-domain Astro deployment.
- `atelier-defense-vault/` — Submission packages, patent support, and confidential review packs.

### 30-tools-and-ops

Internal tools used to build and operate the product:

- `relulayer-engine/` — General-purpose deterministic AI orchestration engine.
- `otto-aviation/` — MCP client prototype for Otto Aviation research and engagement.
- `prompt2ppt/` — Prompt-to-PPTX asset generation tool.

See `30-tools-and-ops/relulayer-engine/ARCHITECTURE.md` for the canonical 9-layer engineering model.

### 40-archive

Cold storage for legacy experiments and retired projects. This material is retained for reference but is not actively maintained.

- `relulayer-sandbox/` — Legacy experimental workspace.
- `relulayer-sovereign-shield/` — Retired sovereign shield work.

---

## Principles

1. **Deterministic layers validate probabilistic layers.** Probabilistic AI never directly controls physical actuators.
2. **Products are version-controlled.** Every directory under `10-kernel/`, `20-pilots-and-proposals/`, and `30-tools-and-ops/` should be a git repository.
3. **No cloud dependency for safety-critical paths.** The kernel and digital twin must run offline.
4. **Auditability.** Every layer has a defined interface and produces traceable evidence.
5. **Separate product from services.** GTM decks, client work, and helper apps live in `AtelierLogicGroup/`, not here.

## Path conventions

Cross-references in this tree use workspace-root-relative paths (e.g., `Organizations/AtelierLogicGroup/00-governance/entity-identity.md`). For Cursor rules and scripts to resolve these automatically, initialize the repository at the `ReluLayer/` level or create a symlink/copy of the referenced file inside the project root. If you initialize smaller repositories per project, adjust the relative paths accordingly.

---

## Related

- `../AtelierLogicGroup/` — Services, GTM, advisory, and helper apps.
- `../shared-standards/brand/BRANDING.md` — Shared brand and color tokens.
