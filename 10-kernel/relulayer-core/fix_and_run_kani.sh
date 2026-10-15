#!/usr/bin/env bash

# ==============================================================================

# SCRIPT: fix_and_run_kani.sh

# Removes all markdown escape artifacts and compiles clean #!\[no_std\] Rust

# ==============================================================================

set -euo pipefail

# Ensure we are in 10-kernel/relulayer-core

if \[ -d "10-kernel/relulayer-core" \]; then
cd 10-kernel/relulayer-core
fi

echo "\[1/4\] Writing clean src/lib.rs..."
cat << 'EOF' > src/lib.rs
#!\[no_std\]
#!\[deny(unsafe_code)\]

pub mod core_math;
pub mod pendulum_sim;
pub mod benchmark_harness;

#\[cfg(kani)\]
pub mod kani_proofs;
EOF

echo "\[2/4\] Writing clean src/benchmark_harness.rs..."
cat << 'EOF' > src/benchmark_harness.rs
pub struct BenchmarkReport {
pub start_cycles: u32,
pub end_cycles: u32,
pub elapsed_cycles: u32,
pub elapsed_nanoseconds: u32,
}

pub struct HardwareCycleCounter;

impl HardwareCycleCounter {
#\[allow(unsafe_code)\]
pub fn init() {
#\[cfg(any(target_arch = "arm", target_arch = "aarch64"))\]
unsafe {
const DEMCR: \*mut u32 = 0xE000_EDFC as \*mut u32;
core::ptr::write_volatile(DEMCR, core::ptr::read_volatile(DEMCR) | (1 << 24));
const DWT_CYCCNT: \*mut u32 = 0xE000_1004 as \*mut u32;
core::ptr::write_volatile(DWT_CYCCNT, 0);
}
}

```
#[inline(always)]
#[allow(unsafe_code)]
pub fn read_cycles() -> u32 {
    #[cfg(any(target_arch = "arm", target_arch = "aarch64"))]
    unsafe {
        let dwt_cyccnt = 0xE000_1004 as *const u32;
        core::ptr::read_volatile(dwt_cyccnt)
    }
    #[cfg(not(any(target_arch = "arm", target_arch = "aarch64")))]
    {
        0
    }
}

pub fn measure<F, R>(f: F) -> (R, BenchmarkReport)
where
    F: FnOnce() -> R,
{
    Self::init();
    let start = Self::read_cycles();
    let result = f();
    let end = Self::read_cycles();
    let elapsed = end.wrapping_sub(start);
    let elapsed_ns = (elapsed as u64 * 125u64 / 21u64) as u32;
    let report = BenchmarkReport {
        start_cycles: start,
        end_cycles: end,
        elapsed_cycles: elapsed,
        elapsed_nanoseconds: elapsed_ns,
    };
    (result, report)
}

```

}

#\[cfg(test)\]
mod tests {
use super::\*;

```
#[test]
fn test_cycle_measurement() {
    let (_res, report) = HardwareCycleCounter::measure(|| {
        let mut sum = 0u32;
        for i in 0..100 {
            sum = sum.wrapping_add(i);
        }
        sum
    });
    let _ = report.elapsed_cycles;
}

```

}
EOF

echo "\[3/4\] Writing clean src/pendulum_sim.rs..."
cat << 'EOF' > src/pendulum_sim.rs
use crate::core_math::LinearConstraints;

pub const A_SYS: \[\[f32; 4\]; 4\] = \[
\[1.0000, 0.0100, 0.0000, 0.0000\],
\[0.0000, 1.0000, 0.0392, 0.0002\],
\[0.0000, 0.0000, 1.0354, 0.0102\],
\[0.0000, 0.0000, 7.1120, 1.0354\],
\];

pub const B_SYS: \[f32; 4\] = \[
0.0001,
0.0196,
\-0.0031,
\-0.6258,
\];

pub fn compute_step_constraints(
x: &\[f32; 4\],
p_limit: f32,
theta_limit: f32,
) -> LinearConstraints {
let p_free = A_SYS\[0\]\[0\] \* x\[0\] + A_SYS\[0\]\[1\] \* x\[1\] + A_SYS\[0\]\[2\] \* x\[2\] + A_SYS\[0\]\[3\] \* x\[3\];
let theta_free = A_SYS\[2\]\[0\] \* x\[0\] + A_SYS\[2\]\[1\] \* x\[1\] + A_SYS\[2\]\[2\] \* x\[2\] + A_SYS\[2\]\[3\] \* x\[3\];

```
LinearConstraints {
    a: [
        B_SYS[0],
        -B_SYS[0],
        B_SYS[2],
        -B_SYS[2],
    ],
    b: [
        p_limit - p_free,
        p_limit + p_free,
        theta_limit - theta_free,
        theta_limit + theta_free,
    ],
}

```

}

pub fn step_dynamics(x: &\[f32; 4\], u: f32) -> \[f32; 4\] {
let mut x_next = \[0.0f32; 4\];
for i in 0..4 {
let mut sum = 0.0f32;
for j in 0..4 {
sum += A_SYS\[i\]\[j\] \* x\[j\];
}
x_next\[i\] = sum + B_SYS\[i\] \* u;
}
x_next
}

#\[cfg(test)\]
mod tests {
use super::\*;

```
#[test]
fn test_zero_state_zero_control() {
    let x0 = [0.0f32; 4];
    let x1 = step_dynamics(&x0, 0.0);
    for val in x1.iter() {
        assert!(val.abs() < 1e-6);
    }
}

#[test]
fn test_constraint_generation_symmetry() {
    let x0 = [0.0f32; 4];
    let constraints = compute_step_constraints(&x0, 0.5, 0.2618);
    assert!((constraints.b[0] - constraints.b[1]).abs() < 1e-6);
    assert!((constraints.b[2] - constraints.b[3]).abs() < 1e-6);
}

```

}
EOF

echo "\[4/4\] Writing clean src/kani_proofs.rs..."
cat << 'EOF' > src/kani_proofs.rs
use crate::core_math::\*;

#\[kani::proof\]
#\[kani::unwind(12)\]
pub fn verify_active_set_no_panics() {
let u_raw: f32 = kani::any();
let u_min: f32 = kani::any();
let u_max: f32 = kani::any();

```
kani::assume(!u_raw.is_nan() && !u_raw.is_infinite());
kani::assume(!u_min.is_nan() && !u_min.is_infinite());
kani::assume(!u_max.is_nan() && !u_max.is_infinite());
kani::assume(u_min >= -100.0 && u_min < u_max);
kani::assume(u_max <= 100.0);

let constraints: LinearConstraints = kani::any();
for i in 0..4 {
    kani::assume(!constraints.a[i].is_nan() && !constraints.a[i].is_infinite());
    kani::assume(!constraints.b[i].is_nan() && !constraints.b[i].is_infinite());
}

let limits = ActuatorLimits { u_min, u_max };
let result = solve_active_set_scalar(u_raw, limits, &constraints);

kani::assert(result.u_safe >= u_min && result.u_safe <= u_max);

if result.status == SolverStatus::Optimal {
    for i in 0..4 {
        kani::assert(constraints.a[i] * result.u_safe <= constraints.b[i] + 1e-4);
    }
}

```

}

#\[kani::proof\]
#\[kani::unwind(12)\]
pub fn verify_feasible_bounds() {
let u_raw: f32 = kani::any();
let u_min: f32 = -20.0;
let u_max: f32 = 20.0;

```
kani::assume(!u_raw.is_nan() && !u_raw.is_infinite());

let constraints = LinearConstraints {
    a: [1.0, -1.0, 1.0, -1.0],
    b: [u_max, -u_min, u_max, -u_min],
};

let limits = ActuatorLimits { u_min, u_max };
let res = solve_active_set_scalar(u_raw, limits, &constraints);

kani::assert(res.status == SolverStatus::Optimal);
kani::assert(res.u_safe >= u_min && res.u_safe <= u_max);

```

}

#\[kani::proof\]
#\[kani::unwind(12)\]
pub fn verify_infeasible_fallback_boundedness() {
let u_raw: f32 = kani::any();
let u_min: f32 = -20.0;
let u_max: f32 = 20.0;

```
kani::assume(!u_raw.is_nan() && !u_raw.is_infinite());

let constraints = LinearConstraints {
    a: [1.0, -1.0, 1.0, -1.0],
    b: [-10.0, -15.0, 100.0, 100.0],
};

let limits = ActuatorLimits { u_min, u_max };
let res = solve_active_set_scalar(u_raw, limits, &constraints);

kani::assert(res.status == SolverStatus::InfeasibleRelaxedApplied);
kani::assert(res.u_safe >= u_min && res.u_safe <= u_max);

```

}

#\[kani::proof\]
#\[kani::unwind(12)\]
pub fn verify_deterministic_wcet() {
let u_raw: f32 = kani::any();
let u_min: f32 = -20.0;
let u_max: f32 = 20.0;

```
kani::assume(!u_raw.is_nan() && !u_raw.is_infinite());

let constraints: LinearConstraints = kani::any();
for i in 0..4 {
    kani::assume(!constraints.a[i].is_nan() && !constraints.a[i].is_infinite());
    kani::assume(!constraints.b[i].is_nan() && !constraints.b[i].is_infinite());
}

let limits = ActuatorLimits { u_min, u_max };
let res = solve_active_set_scalar(u_raw, limits, &constraints);

kani::assert(res.iterations <= 10);

```

}
EOF

echo "All files sanitized. Running AWS Kani Formal Bounded Model Checking..."
cargo kani --default-unwind 12