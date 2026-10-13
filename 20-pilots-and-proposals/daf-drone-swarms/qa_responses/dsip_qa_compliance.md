# DSIP Topic Q&A Response Matrix

**Topic:** `DAF26BX06-DV026` — Ground and Air Launched Drone Swarms Create a Self-Protecting Perimeter Using Autonomous AI  
**Company:** Atelier Logic Group LLC dba ReluLayer™  
**CAGE:** `20JX8` | **UEI:** `G9WFN3AL69J3`

---

## Q1: How does ReluLayer handle multi-agent swarm scalability without saturating RF comms?

**A:** ReluLayer executes fully decentralized at the edge of every drone. No inter-drone communication is required for boundary enforcement; each drone's autopilot independently enforces dynamic physical limits in **26.1 ns** per 4-channel frame. The safety invariant is therefore preserved even when RF links are jammed, multipath-degraded, or intentionally off.

Because the boundary is local, swarm cardinality scales with the number of available platforms rather than with radio bandwidth or central planner throughput. A 50-drone perimeter and a 500-drone perimeter use the same per-airframe compute budget: **< 0.001%** of a 400 Hz PX4 frame and **54 bytes** of Thumb-2 Flash per drone.

---

## Q2: What is the impact on flight controller SWaP-C (Size, Weight, Power, and Cost)?n

**A:** Zero hardware additions are required. ReluLayer runs on the existing Pixhawk 6X / STM32H7 / PX4 flight computer already carried by the airframe.

| SWaP-C Dimension | Impact |
|---|---|
| **Size** | 54 bytes of additional Flash; no new board, connector, or antenna. |
| **Weight** | 0 g — no payload change. |
| **Power** | Negligible: 128 cycles at 480 MHz ≈ 267 ns per solve, executed once per 2.5 ms frame. |
| **Cost** | $0 BOM impact; uses existing MCU. |

The per-frame latency of **26.11 ns** consumes less than **0.001%** of the 400 Hz flight-controller budget, leaving attitude/position controllers, EKF2, and telemetry untouched.

---

## Q3: How does the software integrate with existing DoD flight architectures?

**A:** Integration uses the standard C-ABI header `relulayer.h`. The interceptor drops directly between the PX4 control allocator and the ESC PWM / DShot / CAN drivers.

```text
PX4 Control Allocator
        │
        ▼
┌───────────────────────┐
│ ReluLayer Barrier     │  ← C-ABI call: relulayer_solve_active_set()
│ (C++17 interceptor)   │
└───────────────────────┘
        │
        ▼
   ESC / DShot / CAN
```

The same C-ABI is drop-in compatible with:

- PX4 / NuttX and ArduPilot flight stacks
- ROS 2 / Micro-XRCE-DDS middleware pipelines
- Bare-metal STM32H7 and other ARM Cortex-M flight computers
- CPython / PyO3 simulation and reinforcement-learning toolchains

No operating-system patches or custom drivers are required.

---

## Q4: What are the SBIR Data Rights and licensing boundaries?

**A:** ReluLayer follows a dual-tier intellectual-property model aligned with the SBIR transition pathway:

| Tier | Scope | License / Rights |
|---|---|---|
| **Open-source community bridges** | `relulayer-py` PyO3 bindings, example notebooks, benchmark harnesses | Apache-2.0 OR MIT — encourages academic and industry adoption |
| **Proprietary high-assurance flight core** | `relulayer-core` kernel, `bridges/px4-mixer` interceptor, DO-178C/DO-333 artifacts | DFARS SBIR Data Rights (FAR 52.227-20 / DFARS 252.227-7018); protected proprietary data for 20 years |

GovernmentPurpose Rights are available for Phase II deliverables, with negotiated licensing for production transition.

---

## Compliance Cross-Reference

| DSIP Evaluation Theme | Where Addressed |
|---|---|
| Technical feasibility and risk reduction | Feasibility Volume §2–§5 |
| Relevance to DAF26BX06-DV026 swarm defense | Feasibility Volume §1, §6 |
| Commercial / DoD transition path | Q4 and `technical_volume/sow_milestones.md` |
| Schedule and measurable deliverables | `technical_volume/sow_milestones.md` |
| Data rights and IP boundaries | Q4 and Feasibility Volume data-rights notice |
