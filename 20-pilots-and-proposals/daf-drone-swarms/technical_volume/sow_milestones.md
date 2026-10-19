# Statement of Work & Milestone Deliverables

**Topic:** `DAF26BX06-DV026` — Ground and Air Launched Drone Swarms Create a Self-Protecting Perimeter Using Autonomous AI  
**Contractor:** Atelier Logic Group LLC dba ReluLayer™  
**Contract No.:** DAF26BX06-DV026 (Pending)  
**CAGE:** `20JX8` | **UEI:** `G9WFN3AL69J3`  
**Physical Address:** 32 Normandy Drive, Kenner, LA 70065  
**Mailing Address:** 201 Saint Charles Ave., Ste 114 PMB 603, New Orleans, LA 70170  
**Primary URLs:** https://relulayer.ai | https://atelierlogicgroup.com  
**Public Dual-Use Repositories:** https://github.com/ReluLayer/relulayer | https://pypi.org/project/relulayer/  
**Period of Performance:** 12 months  
**Contract Type:** Direct-to-Phase II SBIR

---

## Executive Summary

This Statement of Work (SOW) describes the 12-month Phase II execution plan for maturing ReluLayer from integrated simulation and host-verified autopilot interceptor to a flight-release-ready, multi-agent swarm safety governor. Work is organized into four 3-month milestones, each with defined deliverables, acceptance criteria, and risk mitigations.

---

## Milestone 1: Multi-Agent SITL Swarm Integration (Months 1–3)

**Objective:** Demonstrate that ReluLayer preserves swarm perimeter integrity in high-fidelity software-in-the-loop (SITL) simulation with 50+ autonomous drones.

### Technical Activities
- Port the PX4 mixer interceptor into a PX4 SITL module compatible with Gazebo and NVIDIA Isaac Sim.
- Implement a perimeter-defense scenario: ground- and air-launched drones form a self-protecting boundary around a high-value asset.
- Introduce RF degradation, GPS spoofing, and adversarial saturation commands to stress the safety boundary.
- Log every boundary activation, per-channel clip event, and latency sample.

### Deliverables
- `D1.1` SITL integration package with build instructions.
- `D1.2` 50-drone Gazebo / Isaac Sim demonstration video and log archive.
- `D1.3` Empirical report: latency distribution, bound-violation count, cascade-collision rate with and without ReluLayer.

### Acceptance Criteria
- 50+ drones maintain perimeter spacing for 10-minute missions under saturation.
- Zero bound violations on any actuator channel.
- Average per-frame latency remains < 1 µs in SITL.

---

## Milestone 2: Multivariable 4-D Coupled Polytope Solver on Pixhawk 6X (Months 4–6)

**Objective:** Extend the scalar active-set solver to a coupled 4-D polytope solver that simultaneously enforces roll, pitch, yaw, and thrust limits on the flight hardware.

### Technical Activities
- Generalize the active-set kernel to handle coupled linear constraints across four actuator/moment dimensions.
- Implement rotor-out / partial-airframe-loss reconfiguration: when a motor failure is detected, the interceptor recomputes the active set on the surviving 3-D moment polytope by dropping the lost channel from $A u \le b$ and tightening the remaining thrust/moment constraints so the degraded airframe remains flyable without central coordination.
- Maintain `#![no_std]`, zero-heap allocation, and deterministic WCET.
- Update AWS Kani proof harnesses to cover the 4-D coupled solver.
- Deploy the solver on Pixhawk 6X hardware-in-the-loop (HIL) benches.

### Deliverables
- `D2.1` Updated `relulayer-core` with 4-D coupled polytope solver.
- `D2.2` Renewed Kani proof matrix (4/4 proofs passing).
- `D2.3` HIL benchmark report on Pixhawk 6X: WCET, Flash/RAM footprint, and latency histogram.

### Acceptance Criteria
- 4-D solver executes within 1 µs worst-case on STM32H7.
- Flash footprint remains < 1 KiB.
- All Kani proofs pass; no panics or divisions by zero reachable.

---

## Milestone 3: Live-Fly Captive Ground Tests and Outdoor Swarm Demonstrations (Months 7–9)

**Objective:** Validate ReluLayer on actual airframes during captive ground tests and outdoor swarm flights under GPS-denied perimeter breach scenarios.

### Technical Activities
- Install ReluLayer on 10–15 small UAS airframes (quadrotor and/or VTOL configurations), consistent with the cost-volume airframe allocation and the DSIP Q&A ≥10-agent minimum.
- Execute captive ground tests with motors spinning under commanded saturation.
- Conduct outdoor swarm flights at an approved test range, including GPS-denied segments induced by jamming or indoor transition.
- Demonstrate degraded-mode perimeter recovery after simulated single-motor failure on one swarm member; log the reconfigured constraint polytope and the zero bound-violation outcome.
- Capture flight logs, video, and safety telemetry.

### Deliverables
- `D3.1` Flight-test plan and range-safety package.
- `D3.2` Captive ground test report with 0 bound violations.
- `D3.3` Outdoor swarm flight demo report (10–15 airframes) with video and log archive.

### Acceptance Criteria
- All live-fly actuator commands remain inside configured limits.
- No loss-of-control events attributable to saturation.
- Swarm recovers perimeter integrity after GPS-denied breach injection.
- At least 10 airframes simultaneously governed in the outdoor demonstration.

---

## Milestone 4: DO-178C Level A / DO-333 Formal Methods Evidence Package (Months 10–12)

**Objective:** Deliver the formal verification artifacts required for Air Force flight release of ReluLayer as a safety-critical software component.

### Technical Activities
- Develop PSAC, SC, SAS, and SECI plans aligned with DO-178C Level A.
- Produce requirements-to-code-to-proof bidirectional traceability.
- Generate structural coverage analysis (MC/DC) and Kani formal-methods credits per DO-333.
- Package DO-178C/DO-333 lifecycle data for government review.

### Deliverables
- `D4.1` DO-178C Level A / DO-333 verification evidence package.
- `D4.2` Traceability matrix: requirements ↔ source ↔ tests ↔ proofs.
- `D4.3` Final technical report and transition recommendation.
- `D4.4` Production license and SBIR data-rights schedule.

### Acceptance Criteria
- Evidence package complete and internally consistent.
- All Level A objectives addressed or formally waived with rationale.
- Government reviewer concurrence on readiness for flight release.

---

## Milestone Schedule Summary

| Milestone | Months | Key Deliverable | Go/No-Go Gate |
|---|---|---|---|
| M1: SITL Swarm Integration | 1–3 | 50-drone Gazebo/Isaac Sim demo | Latency < 1 µs, 0 violations |
| M2: 4-D Coupled Solver HIL | 4–6 | Pixhawk 6X HIL benchmark | WCET < 1 µs, Kani 4/4 |
| M3: Live-Fly Demonstrations | 7–9 | 10–15 airframe outdoor demo | 0 saturation-related LOC events; ≥10 airframes simultaneously governed |
| M4: DO-178C/DO-333 Package | 10–12 | Flight-release evidence package | Government concurrence |

---

## Deliverable-to-DID Mapping

| ReluLayer Deliverable | DoD DID / Standard | Description |
|---|---|---|
| `D1.1` SITL integration package | DI-IPSC-81431 (SRS) / SITL artifacts | Simulation requirements and build package |
| `D1.2` 50-drone demo | — | Demonstration video and log archive |
| `D1.3` Empirical report | DI-MGMT-81336 (Test Report) | SITL test report |
| `D2.1` Updated `relulayer-core` | DI-IPSC-81432 (SDD) | Software design description |
| `D2.2` Kani proof matrix | DO-333 FM credits | Formal methods evidence |
| `D2.3` HIL benchmark report | DI-MGMT-81336 | HIL test report |
| `D3.1` Flight-test plan | DI-SAFT-81065 / D3.4 | System Safety Hazard Analysis / Range Safety Plan |
| `D3.2` Ground test report | DI-MGMT-81336 | Captive test report |
| `D3.3` Outdoor demo report | DI-MGMT-81336 | Flight demo report |
| `D4.1` Certification package | DO-178C Level A / DO-333 | Verification evidence package |
| `D4.2` Traceability matrix | DI-IPSC-81434 (SVCP) / custom | Requirements-to-code-to-proof matrix |
| `D4.3` Final technical report | DI-MGMT-81337 | Final report |
| `D4.4` License & data-rights schedule | DFARS 252.227-7018 | IP transition schedule |

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Range access delays for outdoor flights | Medium | Schedule | Begin range coordination in Month 1; have SITL-only acceptance path. |
| 4-D WCET growth on STM32H7 | Low | Technical | Bound iteration count at compile time; Kani proves WCET before hardware test. |
| Certification evidence reviewer findings | Medium | Schedule | Monthly informal reviews with AF technical POC; use DO-178C checklists from Month 1. |
| Open-source / proprietary boundary confusion | Low | IP | Maintain separate repositories and license headers; include SBIR Data Rights notice in every artifact. |

---

## Government Furnished Equipment / Information

None required. All development leverages commercially available Pixhawk 6X flight controllers, simulation environments, and ReluLayer proprietary software.

---

**SBIR DATA RIGHTS**

Contract No.: DAF26BX06-DV026 (Pending)  
Contractor Name: Atelier Logic Group LLC dba ReluLayer™  
Physical Address: 32 Normandy Drive, Kenner, LA 70065  
Mailing Address: 201 Saint Charles Ave., Ste 114 PMB 603, New Orleans, LA 70170  
CAGE: 20JX8 | UEI: G9WFN3AL69J3  
DFARS 252.227-7018  
Expiration of SBIR Data Rights Period: October 21, 2046

The Government's rights to use, modify, reproduce, release, perform, display, or disclose technical data or computer software marked with this legend are restricted during the period shown as provided in paragraph (b)(4) of the Rights in Noncommercial Technical Data and Computer Software--Small Business Innovation Research (SBIR) Program clause contained in the above identified contract. No restrictions apply after the expiration date shown above. Any reproduction of technical data, computer software, or portions thereof marked with this legend must also reproduce the markings.
