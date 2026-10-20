# Direct-to-Phase II Feasibility Volume

**Topic:** `DAF26BX06-DV026` — Ground and Air Launched Drone Swarms Create a Self-Protecting Perimeter Using Autonomous AI  
**Company:** Atelier Logic Group LLC dba ReluLayer™  
**CAGE:** `20JX8` | **UEI:** `G9WFN3AL69J3`  
**Submission Deadline:** October 21, 2026  
**Primary URLs:** https://relulayer.ai | https://atelierlogicgroup.com  
**Public Dual-Use Repositories:** https://github.com/ReluLayer/relulayer | https://pypi.org/project/relulayer/  
**Contract No.:** DAF26BX06-DV026 (Pending)  

---

## Abstract

This Feasibility Volume demonstrates prior Phase I equivalency for AFWERX Direct-to-Phase II topic `DAF26BX06-DV026`. ReluLayer™ is a deterministic, sub-microsecond physical safety governor for autonomous drone swarms. It executes entirely at the flight-control edge, requires no inter-vehicle RF coordination for boundary enforcement, and is already integrated with both Python reinforcement-learning simulation pipelines and the PX4 autopilot C++ mixer. Empirical results from Sprints 1, 2, and 4 show sub-microsecond latency on both the Python bridge and PX4 mixer paths, 30.93 ns host solve latency for the 4-D coupled QP, and zero bound violations under deliberate saturation. The scalar per-channel governor entry point (`relulayer_solve_active_set`) compiles to a 54-byte Thumb-2 instruction footprint; the 4-D coupled QP solver is a larger, separately compiled module and is the subject of the host benchmark. The combined kernel is architected for DO-178C Level A / DO-333 certification.

---

## Section 1: Problem Statement & Swarm Vulnerability

Ground- and air-launched autonomous swarms executing self-protecting perimeter defense are asked to make aggressive, coordinated maneuvers under contested electromagnetic conditions. Aggressive AI-driven controllers naturally command actuator demands that approach or exceed physical limits. In a swarm, the consequences extend beyond a single airframe:

1. **Dynamic actuator saturation:** A commanded roll/pitch/yaw/thrust mix can demand motor PWM values beyond the ESC envelope. When saturated open-loop, one rotor starves while another over-commands, producing unmodeled torque and rapid attitude divergence.
2. **Mid-air vehicle desync:** Without a deterministic, independent safety boundary, two drones responding to the same perceived threat may simultaneously command limit excursions in coupled directions, breaking the geometric spacing the swarm controller assumed.
3. **Catastrophic cascade collisions:** A single saturated drone that loses altitude or yaw stability can cross into a neighbor's keep-out sphere; the neighbor's evasive maneuver may then saturate *its* actuators, turning a localized limit breach into a multi-vehicle cascade.

Existing swarm architectures rely heavily on centralized planners or inter-agent RF coordination. Under jamming, multipath, or reduced data-rate links, the safety margin collapses. ReluLayer addresses this by embedding a formally bounded, zero-heap, zero-communication safety governor directly at the edge of every drone's autopilot.

### Air-Drop Deployment & Swarm Scale Compliance (Oct 4 DSIP Q&A)

The ReluLayer-governed swarm is designed explicitly for the air-launched operational envelope defined in the **October 4, 2026 DSIP Q&A**:

- **Vehicle Gross Weight:** Each drone remains bounded at **< 50 lb (< 22.7 kg)**, inclusive of airframe, Pixhawk 6X flight computer, battery, and deployment latching hardware.
- **Air-Drop Deployment Kinetics:** Selected test envelope points are bounded strictly within **3,000–10,000 ft MSL** and **130–200 KIAS** airspeed.
- **Host Aircraft Relationship:** The host platform (C-130J via un-modified paratroop doors/ramp) departs immediately post-release. ReluLayer independently arrests post-drop freefall trajectories and establishes swarm operations with **zero co-flight period** and **zero reliance on host RF**.
- **Minimum Swarm Scale:** The architecture is designed for **≥ 10 simultaneous heterogeneous agents**, with SITL demonstrations already supporting **50+ agents** with distributed sensor allocation across airframes.

---

## Section 2: Empirical Simulation Proof (Sprint 1 Results)

Sprint 1 exposed the high-assurance Rust core to Python via PyO3 so that reinforcement-learning and physics-simulation environments can enforce actuator limits on every action before it reaches the simulated plant.

### Architecture

The Python package `relulayer` exposes a `Governor` class whose `project()` method calls the `#![no_std]` active-set projection core through a C-compatible dynamic library. The hot path performs no dynamic heap allocation, no `unwrap` panics, and no Python object creation per call.

### Test Harness

A benchmark harness streamed 100,000 randomized `float32` actuator commands uniformly distributed in `[-25.0, +25.0]` through a governor configured to `[-12.0, +12.0]`. The loop was executed on a host workstation using the release Maturin build.

**Host benchmark configuration:** AMD Ryzen 9 5900X @ 3.7 GHz (fixed-performance power profile), Rust 1.81, Maturin 1.7, release profile `opt-level=3, lto=true`, Ubuntu 22.04 LTS. Numbers are host reference latencies for the PyO3 bridge, not the STM32H7 flight-computer WCET.

### Results

| Metric | Value |
|---|---|
| Iterations | 100,000 |
| Average round-trip latency | **42.1 ns** (0.0421 µs) |
| Latency budget | < 1.0 µs |
| Boundary violations | **0** |
| Dynamic heap allocations on hot path | **0** |

The result satisfies the < 1 µs simulation-loop budget by more than an order of magnitude.

---

## Section 3: Empirical Autopilot Proof (Sprint 2 Results)

Sprint 2 integrated ReluLayer between the PX4 control allocator and the ESC outputs using a C++17 mixer interceptor. The interceptor receives a 4-channel normalized motor-demand array and returns a bounded array in which each channel is projected through the active-set C-ABI core.

### Test Harness

A 10,000-frame host test at 400 Hz generated quadrotor-like roll, pitch, yaw, and thrust trajectories, added random noise, and deliberately injected saturation events by commanding one motor to `u = 1.8` in approximately 10% of frames. Extreme negative commands were also injected at the midpoint of the run. Every frame was timed with a high-resolution clock, and every output channel was checked against `[0.05, 0.95]`.

**Host benchmark configuration:** same AMD Ryzen 9 5900X workstation; the interceptor was exercised as a C-ABI call from a host harness emulating the PX4 400 Hz actuator pipeline. The 26.11 ns figure is the per-frame C-ABI overhead on the host; the STM32H7 WCET is reported separately in §5.

### Results

| Metric | Value |
|---|---|
| Frames processed | 10,000 |
| Sample rate | 400 Hz (2.5 ms frame budget) |
| Average per-frame intercept latency | **26.11 ns** (0.0261 µs) |
| Latency as fraction of frame budget | **< 0.001%** |
| Deliberate saturation injections | ≈ 1,000 |
| Channel clip events | **27,666** |
| Bound violations outside `[0.05, 0.95]` | **0** |

Even under deliberate over-saturation, every channel remained inside the commanded flight envelope.

---

## Section 4: Sprint 4 — Multivariable 4-D Coupled QP Solver & Zero-Heap Discipline

Sprint 4 extended the scalar active-set boundary to a coupled four-channel polytope solver required for thrust-limited, geometrically constrained swarm allocation.

### Problem Formulation

The 4-D QP projects a raw actuator demand $u_{\text{raw}} \in \mathbb{R}^4$ onto the feasible set defined by per-channel bounds and a coupled linear inequality such as a total-thrust ceiling:

$$
\min_u \frac{1}{2} \|u - u_{\text{raw}}\|_2^2
\quad \text{s.t.} \quad
u_{\min} \le u \le u_{\max},
\quad \sum_{i=1}^4 u_i \le T_{\max}
$$

### Empirical Benchmark

A host-side Monte Carlo harness generated 1,000 randomized 4-D demand vectors and solved each instance through the C-ABI entry point.

**Host benchmark configuration:** same workstation as Sprints 1 and 2; the 30.93 ns figure is the average host-side solve latency of the 4-D coupled active-set QP. The scalar per-channel flight-hardware entry point is bounded at 128 cycles / 267 ns on STM32H7; the 4-D coupled QP flight-hardware WCET will be measured and bounded in Phase II.

| Metric | Value |
|---|---|
| Test vectors | 1,000 |
| Decision dimension | $u \in \mathbb{R}^4$ |
| Coupled constraint | $\sum u_i \le T_{\max}$ |
| Average host solve latency | **30.93 ns** |
| Latency budget | < 1,000 ns |
| Box-bound violations | **0** |
| Converged to optimal | 1,000 / 1,000 |

The multivariable solver therefore stays more than **32× under** the 1 µs host-side budget, leaving headroom for PX4 mixer integration and RF-contested operations.

### Nominal vs. Degraded Operation

In the nominal path, the 4-D solver enforces both per-channel bounds and the coupled linear inequality (e.g., total-thrust ceiling). If numerical degeneracy or an infeasible initial point is encountered, the kernel falls back to an independent per-channel clamp that preserves per-channel bounds and commands a safe hold. The coupled constraint is then reasserted on the next valid cycle. This degraded-mode behavior is explicitly bounded and documented in the software safety analysis, which will be delivered as part of the Phase II DO-178C Level A / DO-333 evidence package.

### Zero-Heap Discipline

The kernel enforces allocation-free execution at three levels:

1. **Crate-level `#![no_std]` / `#![no_main]`:** The production embedded build disables the Rust standard library and OS runtime. Entry points are `#[no_mangle]` C-ABI functions invoked from PX4 or bare-metal startup code.
2. **Static stack-frame bounds:** All working memory is declared as fixed-size arrays on the stack (`u_{\text{safe}}[4]`, working-set arrays of length `W_{\max} = 8`, normal-equation matrices $8 \times 8$). No `Vec`, `Box`, `Rc`, `Arc`, or allocator API appears in the hot path or solver modules.
3. **Compiled-object verification:** The release embedded profile sets `panic = "abort"`, `lto = true`, and `opt-level = 3`. A post-link disassembly inspection of the `.text` section confirms only Thumb-2 instructions; `.data` and `.bss` contain zero dynamic allocations attributable to the solver. Panic paths abort via an infinite loop rather than invoking an unwinder or allocator.
4. **Machine-code verification procedure:** Build with `cargo build --target thumbv7em-none-eabihf --release`, inspect `target/thumbv7em-none-eabihf/release/librelulayer_core.a` with `arm-none-eabi-objdump -h`, and confirm `.bss` and `.data` section sizes are 0 bytes for the solver object. The release linker map shows no `__rust_alloc`, `__rdl_alloc`, or `__rust_panic_handler` symbols reachable from `relulayer_solve_active_set`. These artifacts are included in the Phase II certification package.

---

## Section 5: Bare-Metal Silicon Footprint (STM32H7 / Pixhawk 6X)

ReluLayer is architected for the flight computers already deployed on Group 1–3 sUAS and many attritable swarm airframes. The kernel compiles to bare-metal Thumb-2 for the STM32H7 series used on the Pixhawk 6X.

| Attribute | Value |
|---|---|
| Scalar governor entry-point flash footprint (Thumb-2) | **54 B** |
| Worst-case execution cycles for scalar entry point | **128 cycles** |
| Worst-case execution time for scalar entry point at 480 MHz | **≈ 267 ns** |
| Dynamic heap allocation | **0 bytes** |
| Stack-only operation | Yes |
| Target flight computer | Pixhawk 6X / STM32H743 |

A 54-byte instruction footprint for the scalar per-channel entry point and a 128-cycle WCET for that entry point mean the governor's hot path runs inside the PX4 `actuator_outputs` pipeline without an additional MCU, co-processor, FPGA, or memory. The 4-D coupled QP solver validated in Sprint 4 is a separate module and is exercised in the Python/C host environment; its flight-computer WCET will be measured and bounded in Phase II.

### Kinetic, SWaP-C, and Swarm-Scale Bound Compliance

The bare-metal implementation is sized for the **Oct 4 DSIP Q&A** air-drop envelope. Each governed airframe is budgeted under the **< 50 lb (< 22.7 kg)** gross-weight limit, with the Pixhawk 6X + battery + latching hardware fully accounted. Deployment scenarios are bounded within **3,000–10,000 ft MSL** and **130–200 KIAS**, with the swarm transitioning from post-release freefall to autonomous perimeter operations without co-flight with or RF from the C-130J host. ReluLayer is designed for **≥ 10 simultaneous heterogeneous agents** in the baseline live-fly demonstration and has been exercised at **50+ agents** in distributed SITL.

---

## Section 6: Formal Proof Matrix

The kernel is accompanied by an AWS Kani bounded model checking harness. Kani symbolically exercises the active-set solver over the full input domain and verifies that no panic, division by zero, or unconstrained state is reachable.

| Proof ID | Property | Status | Standard |
|---|---|---|---|
| K-01 | No panics on any finite input | Verified | DO-333 FM.1 |
| K-02 | Output bounded inside actuator limits | Verified | DO-178C §6.4 |
| K-03 | No division by zero or unconstrained state | Verified | DO-333 FM.2 |
| K-04 | Deterministic iteration bound (≤ 20 iterations for 4-D coupled QP; scalar entry point terminates in 1 iteration) | Verified | DO-178C §6.4 |
| K-05 | Inductive active-set streaming equivalence & bounded step invariants without heap allocation (Audit Decision 5) | Verified | DO-333 FM.3 |

All five proofs pass with Kani's default bounded unwinding. **Audit Decision 5** specifically adds inductive AWS Kani bounded model checking harnesses that prove active-set streaming equivalence and bounded inductive step invariants without heap allocation, strengthening the DO-178C Level A / DO-333 software verification evidence package.

---

## Phase II Readiness & Conclusion

ReluLayer has already satisfied the technical risk-reduction objectives normally associated with Phase I:

- A formally verified, zero-heap active-set kernel in `#![no_std]` Rust.
- Sub-microsecond Python bridge latency validated over 100,000 simulation steps.
- PX4 mixer integration validated at 400 Hz with zero bound breaches under saturation.
- A 54-byte bare-metal footprint for the scalar governor entry point and a 128-cycle WCET for that entry point, compatible with fielded Pixhawk 6X hardware.
- A 4-D coupled active-set QP solver validated at 30.93 ns average latency over 1,000 Monte Carlo test vectors.

These results map directly to the DAF26BX06-DV026 evaluator concerns of swarm safety, autonomy at the edge, RF resilience, and transition speed.

---

## References

1. U.S. Air Force / AFWERX SBIR Topic DAF26BX06-DV026,
*Ground and Air Launched Drone Swarms Create a Self-Protecting Perimeter
Using Autonomous AI*, DoD SBIR Direct-to-Phase II solicitation.

2. RTCA DO-178C, *Software Considerations in Airborne Systems and Equipment
Certification*, 2011; and RTCA DO-333, *Formal Methods Supplement to DO-178C
and DO-278A*, 2011.

3. U.S. Department of Defense, MIL-STD-882E, *Standard Practice for System
Safety*, 2012.

4. NIST Special Publication 800-171 Rev 2, *Protecting Controlled Unclassified
Information in Nonfederal Systems and Organizations*, 2020.

5. Defense Federal Acquisition Regulation Supplement (DFARS) 252.227-7013
(*Rights in Technical Data—Noncommercial Items*) and 252.227-7992 (*Rights in
Computer Software and Computer Software Documentation*).

6. Defense Federal Acquisition Regulation Supplement (DFARS) 252.227-7018,
*Rights in Noncommercial Technical Data and Computer Software—Small Business
Innovation Research (SBIR) Program*.

7. Defense Federal Acquisition Regulation Supplement (DFARS) 252.204-7019 and
252.204-7020, CMMC / SPRS requirements.

8. Atelier Logic Group LLC dba ReluLayer™, ACCSE™ / ReluLayer™ technical
baseline, HIL telemetry, and patent-pending background IP estate (PPA I Ser.
No. 64/021,087; PPA II Ser. No. 64/058,892; PPA III Ser. No. 64/063,132;
PPA IV Ser. No. 64/067,735; PPA V Ser. No. 64/095,530; PPA VI Ser. No.
64/124,094; PPA VII Ser. No. 64/127,611).

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
