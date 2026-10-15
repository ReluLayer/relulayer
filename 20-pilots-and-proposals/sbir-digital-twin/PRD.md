# Product Requirements Document (PRD)
## ReluLayer™ Software-in-the-Loop Digital Twin for SBIR ARM26TX04-NV001 & PPA VI (RELU-001-PPA6)

> **Canonical entity identity:** `AtelierLogicGroup/00-governance/entity-identity.md`. Any edits to UEI, CAGE, NAICS, PSC, patent serials, or addresses must be synchronized with that file. The entity identifiers below are provided for convenience within this document.

**Entity Legal Name:** Atelier Logic Group LLC  
**DBA / Brand:** ReluLayer™  
**UEI:** G9WFN3AL69J3  
**CAGE Code:** 20JX8  
**Primary NAICS:** 541715 (Research and Development in Physical, Engineering, and Life Sciences)  
**Primary PSC:** AC11 (Defense R&D: Military Sciences / Advanced Development)  
**Official Email:** proposals@atelierlogicgroup.com  
**Physical Address & Residence:** 32 Normandy Dr, Kenner, LA 70065-2031 USA  
**Mailing Address:** Atelier Logic Group LLC, Ishmael Amin, 201 Saint Charles Ave, Ste 114 PMB 603, New Orleans, LA 70170 US  
**Sole Inventor:** Ishmael Ibrahim Amin  
**PPA V Serial No.:** 64/095,530 (Confirmation No. 5029 | Docket: RELU-001-PPA5)  
**PPA VI Attorney Docket:** RELU-001-PPA6  
**Document Version:** 2.0 (Red Team Certified)  
**Date:** 2026-08-01  

---

## 1. Executive Summary

`sbir-digital-twin` is the Software-in-the-Loop (SIL) and Hardware-in-the-Loop (HIL) benchmark suite for the ReluLayer Deterministic Bare-Metal Hardware Safety Kernel and Q16.16 Fixed-Point Projection Engine. The suite is engineered for **US Army SBIR Topic ARM26TX04-NV001** and supported by **USPTO Provisional Patent Application VI (RELU-001-PPA6)**.

The core innovation is an in-line physical data bus interception co-processor and active-set constraint projection mechanism that replaces static kill-switches with deterministic setpoint interdiction. Operating with a worst-case execution bound of **128 CPU cycles ($\approx 267\text{ ns}$ at 480 MHz)** and zero dynamic heap allocation ($0\text{ B}$ heap, linker `_sbrk` trapped to `ENOMEM`), ReluLayer projects unconstrained control vectors onto safe convex polytopes $\mathcal{S}_{v} = \{v \in \mathbb{R}^{3} \mid Av \le b\}$ while preserving the symplectic phase-space structure ($\det(J) = 1.0$).

This PRD governs the system architecture, embedded execution constraints, intellectual property portfolio, avionics certification alignment (DO-178C DAL A, MIL-STD-882E), real-world telemetry ingestion, and eight designed experiments (DOE-01 through DOE-08).

---

## 2. IP Portfolio, Section 101 Moat & USPTO Strategy

### 2.1 Sole Inventor & Ownership
- **Sole Inventor:** Ishmael Ibrahim Amin
- **Residence & Physical Address:** 32 Normandy Dr, Kenner, LA 70065-2031 USA
- **Assignee:** Atelier Logic Group LLC dba ReluLayer™
- **Official Proposals Email:** proposals@atelierlogicgroup.com (`.com` domain only)

### 2.2 Patent Portfolio & Section 101 Eligibility Defense Moat
This master specification incorporates by reference all prior provisional applications:
- **PPA I (64/021,087 | Filed March 30, 2026)**
- **PPA II (64/058,892 | Filed May 6, 2026)**
- **PPA III (64/063,132 | Filed May 11, 2026)**
- **PPA IV (64/067,735 | Filed May 17, 2026)**
- **PPA V (64/095,530 | Filed June 21, 2026 | Confirmation No. 5029)**
- **PPA VI (Attorney Docket: RELU-001-PPA6)**

> **Section 101 "Alice Corp." Defense Moat (Section 1.6 Disclaimer):**  
> PPA VI expressly disclaims vertical-specific business or natural language rules. All incoming workloads across all filings are treated purely as abstract multi-dimensional state vectors, physical bus signals, and polyhedral safety manifolds. Subject-matter eligibility under 35 U.S.C. § 101 is tied directly to physical hardware operations: in-line co-processor bus interception (AXI4-Stream, PCIe, GPIO), memory-mapped enforcement register 114 override, electronic inhibit line assertion, sub-microsecond timing determinism, and zero-heap C-runtime system call stubs.

### 2.3 Split-Brain / Bifurcated Hardware Architecture
- **Primary AI Compute Node:** NVIDIA Jetson Orin System-on-Module executing probabilistic perception, mission planning, and constraint calculation under Linux.
- **Freestanding Safety Co-Processor:** STM32H743 / Pixhawk 6X executing `#![no_std]` Rust micro-kernel (326-byte core footprint) that intercepts Memory-Mapped Enforcement Register 114 beneath the OS kernel to enforce safety manifolds even under main compute compromise or OS latency jitter.

### 2.4 Trademark Strategy
- **Primary Mark:** RELULAYER
- **Target Classification:**
  - **Class 9:** Bare-metal safety hypervisors; embedded safety controllers; avionics-grade deterministic middleware.
  - **Class 42:** Cyber-physical safety verification; defense engineering R&D; SIL/HIL autonomy benchmarking.

---

## 3. System Architecture, Embedded Limits & Compliance

### 3.1 SWaP-C Payload Budget
- **Co-processor Board Target Mass:** $\approx 350\text{ g}$
- **Total Co-processor Payload Weight:** $< 2.0\text{ lbs}$
- **Power Envelope:** Bounded and deterministic; zero FPU or heap allocator invocation in the safety-critical path.

### 3.2 Target Hardware & Compilation Flags
- **Microcontroller Target:** STM32H743BIT6 on Pixhawk 6X carrier @ 480 MHz ARM Cortex-M7 core.
- **Compiler Options:** `-mcpu=cortex-m7 -mthumb -mfloat-abi=hard -mfpu=fpv5-d16`
- **Execution Performance:** 128 cycles worst-case latency bound ($\approx 267\text{ ns}$ at 480 MHz); $0.00\%$ bit-level output variance across 1,000 HIL iterations.

### 3.3 Static Memory Footprint & Zero-Heap Boundary
- **Flash Footprint:** $27,364\text{ B}$ (contains vector table, 326-byte kernel core, Q16.16 projection engine, and linker metadata).
- **Static RAM Footprint:** $67,628\text{ B}$ (comprising global state, $64\text{ KB}$ pre-allocated stack, and $0\text{ B}$ dynamic heap).
- **Dynamic Heap:** $0\text{ B}$. Enforced by `_sbrk` stub in `hil/syscalls.c` returning `(void *)-1` with `errno = ENOMEM`. Satisfies **RTCA DO-178C Design Assurance Level A (DAL A)** memory-determinism requirements.
- **Fault Handling:** Reverts aircraft to trim conditions upon fault/timeout and logs error codes to a non-volatile sentinel region pursuant to **MIL-STD-882E**.
- **Cybersecurity:** Complies with **CMMC Level 1** Federal Contract Information (FCI) safeguarding protocols.

### 3.4 Kinematic Envelope (Group 1/2 UAS)
| Parameter | Value |
|-----------|-------|
| Maximum velocity $v_{\max}$ | $83.33\text{ m/s}$ ($\approx 300\text{ km/h}$) |
| Maximum acceleration $a_{\max}$ | $30.0\text{ m/s}^2$ |
| Maximum body rotation rate $\omega_{\max}$ | $5.0\text{ rad/s}$ |
| Actuator lag $\Delta t_{\text{actuator}}$ | $50\text{ ms}$ |

---

## 4. Real-World Telemetry Ingestion Strategy

### 4.1 Telemetry Datasets
Real flight logs stream through `relulayer_py` (PyO3 0.23+ smart pointers) into the SIL Monte Carlo harness:
- `data/trajair_outdoor_flight.csv`: Outdoor trajectory log under wind shear and turbulent gusts.
- `data/nanobench_swarm_formation.csv`: Indoor 6-DOF motion-capture swarm dataset representing close-proximity formation flight.

### 4.2 EKF Noise Overlay
All simulated flight scenarios overlay real telemetry with a simulated Extended Kalman Filter (EKF) position estimation error of **$\pm 0.35\text{ m}$** to benchmark boundary projection robustness under state uncertainty.

---

## 5. Designed Experiments (DOE-01 through DOE-08)

### DOE-01: Reaction Latency Jitter
- **Objective:** Verify that Q16.16 projection latency remains strictly bounded under 128 CPU cycles ($\approx 267\text{ ns}$).
- **Metric:** Worst-case execution time (WCET) in cycles, 99th-percentile cycle jitter.
- **Success Criterion:** Max latency $\le 128$ cycles; $0.00\%$ bit-level output variance across 1,000 HIL iterations.

### DOE-02: Geofence Boundary Breach Distance
- **Objective:** Quantify minimum lateral distance maintained from a polyhedral boundary under EKF position noise.
- **Metric:** Signed distance to boundary at closest approach ($\text{m}$).
- **Success Criterion:** $0.00\text{ m}$ breach target under $\pm 0.35\text{ m}$ EKF drift; all candidate breaches projected to feasible set boundary.

### DOE-03: Airframe Survival Rate
- **Objective:** Measure percentage of simulated flight episodes recovering from injected anomalous actuator commands.
- **Metric:** Recovered episodes / total episodes.
- **Success Criterion:** $100\%$ recovery for all tested anomaly classes within the kinematic envelope.

### DOE-04: HPM Bit-Flip Detection & Symplectic Audit
- **Objective:** Benchmark reaction time to High-Powered Microwave (HPM) bit-flips violating symplectic phase-space invariants.
- **Metric:** Time from $|\det(J) - 1.0| > \epsilon_{\text{tol}}$ to fallback assertion ($\mu\text{s}$).
- **Success Criterion:** Rejection within 1 control cycle; fallback vector issued; $\det(J)$ preserved at $65,536 \pm 65$ in Q16.16.

### DOE-05: Inter-Agent Swarm Collision Rate
- **Objective:** Evaluate collision probability for $N=16$ agents operating under $50\text{ ms}$ actuator lag.
- **Metric:** Collisions per episode across Monte Carlo runs.
- **Success Criterion:** Zero collisions under nominal swarm density; graceful speed reduction under bottleneck stress.

### DOE-06: Cascading Anomaly Containment
- **Objective:** Ensure single-agent sensor corruption does not propagate fleet-wide.
- **Metric:** Containment time; fleet recovery rate.
- **Success Criterion:** Fault containment within 1 control cycle ($267\text{ ns}$); $100\%$ of unaffected agents maintain mission trajectories.

### DOE-07: Mesh Packet Loss Resiliency
- **Objective:** Validate swarm interdiction performance under $40\%$ RF packet loss.
- **Metric:** Mission completion rate, position consensus error, collision rate.
- **Success Criterion:** Zero collisions and safe separation maintained despite $40\%$ packet drop.

### DOE-08: High-Density Bottleneck Squeeze
- **Objective:** Stress-test projection engine in a high-density flight corridor with conflicting setpoint vectors.
- **Metric:** Projection throughput (projections/s), deadlock-free traversal rate.
- **Success Criterion:** Zero deadlocks; deterministic execution time maintained across all active-set transitions.

---

## 6. Document Generation & Build Standards

### 6.1 Package Structure & Page Budget
- **Specification Document (`ppa6.pdf`):** Exactly **12 pages**.
- **Drawing Suite (`ppa6_drawings.pdf`):** Exactly **11 pages** (37 CFR 1.84 compliant, $1.0\text{ in}$ top/left margins, 1 figure per page).
- **Master Filing Package (`ppa6_master_filing.pdf`):** Exactly **23 pages** ($12 + 11$).

### 6.2 Python Scripting & Regex Rules
To prevent build crashes and backslash escape errors during document compilation:
- **Rule 1:** NEVER pass LaTeX backslash strings (e.g., `\subsection`, `\mathcal`, `\item`) directly into Python `re.sub()` replacement string parameters.
- **Rule 2:** ALWAYS wrap `re.sub()` replacement strings in a `lambda` function: `re.sub(pattern, lambda m: r"...", text)`.
- **Rule 3:** ALWAYS maintain `ppa6.tex.bak` pre-flight backups before modifying source files.