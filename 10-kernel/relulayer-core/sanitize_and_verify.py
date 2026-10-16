#!/usr/bin/env python3
import os
import subprocess
import sys

# Ensure execution inside 10-kernel/relulayer-core

if os.path.exists("10-kernel/relulayer-core"):
os.chdir("10-kernel/relulayer-core")

os.makedirs("src", exist_ok=True)

# 1. src/lib.rs

lib_rs = """#!\[no_std\]
#!\[deny(unsafe_code)\]

pub mod core_math;
pub mod pendulum_sim;
pub mod benchmark_harness;

#\[cfg(kani)\]
pub mod kani_proofs;
"""

# 2. src/core_math.rs

core_math_rs = """#\[derive(Clone, Copy, Debug, PartialEq)\]
pub struct ActuatorLimits {
pub u_min: f32,
pub u_max: f32,
}

#\[derive(Clone, Copy, Debug, PartialEq)\]
pub struct LinearConstraints {
pub a: \[f32; 4\],
pub b: \[f32; 4\],
}

#\[derive(Clone, Copy, Debug, PartialEq, Eq)\]
pub enum SolverStatus {
Optimal,
MaxIterationsReached,
InfeasibleRelaxedApplied,
InvalidInput,
}

#\[derive(Clone, Copy, Debug, PartialEq)\]
pub struct SolverResult {
pub u_safe: f32,
pub iterations: usize,
pub status: SolverStatus,
}

pub fn solve_active_set_scalar(
u_raw: f32,
limits: ActuatorLimits,
constraints: &LinearConstraints,
) -> SolverResult {
// Step 1: Strict input validation and sanitization
if !u_raw.is_finite()
|| !limits.u_min.is_finite()
|| !limits.u_max.is_finite()
|| limits.u_min >= limits.u_max
{
return SolverResult {
u_safe: 0.0,
iterations: 0,
status: SolverStatus::InvalidInput,
};
}

```
for i in 0..4 {
    if !constraints.a[i].is_finite() || !constraints.b[i].is_finite() {
        return SolverResult {
            u_safe: 0.0,
            iterations: 0,
            status: SolverStatus::InvalidInput,
        };
    }
}

// Step 2: Contract feasible polytope into a 1D scalar interval [lower_bound, upper_bound]
let mut lower_bound = limits.u_min;
let mut upper_bound = limits.u_max;

for i in 0..4 {
    let ai = constraints.a[i];
    let bi = constraints.b[i];

    if ai > 1e-7 {
        let bound = bi / ai;
        if bound.is_finite() {
            if bound < upper_bound {
                upper_bound = bound;
            }
        } else if bi < 0.0 {
            upper_bound = limits.u_min - 1.0;
        }
    } else if ai < -1e-7 {
        let bound = bi / ai;
        if bound.is_finite() {
            if bound > lower_bound {
                lower_bound = bound;
            }
        } else if bi < 0.0 {
            lower_bound = limits.u_max + 1.0;
        }
    } else if bi < 0.0 {
        lower_bound = limits.u_max;
        upper_bound = limits.u_min;
        break;
    }
}

// Step 3: Handle empty feasible polytope (infeasible fallback state)
if lower_bound > upper_bound {
    let clamped_lb = if lower_bound < limits.u_min {
        limits.u_min
    } else if lower_bound > limits.u_max {
        limits.u_max
    } else {
        lower_bound
    };

    let clamped_ub = if upper_bound < limits.u_min {
        limits.u_min
    } else if upper_bound > limits.u_max {
        limits.u_max
    } else {
        upper_bound
    };

    // Half-sum computation avoiding float addition overflow
    let midpoint = 0.5 * clamped_lb + 0.5 * clamped_ub;
    let u_fallback = if midpoint < limits.u_min {
        limits.u_min
    } else if midpoint > limits.u_max {
        limits.u_max
    } else {
        midpoint
    };

    return SolverResult {
        u_safe: u_fallback,
        iterations: 1,
        status: SolverStatus::InfeasibleRelaxedApplied,
    };
}

// Step 4: Active-Set iterative projection with deterministic WCET bound
let mut current_u = u_raw;
let mut iterations = 0;

while iterations < 10 {
    iterations += 1;

    if current_u < lower_bound {
        current_u = lower_bound;
    } else if current_u > upper_bound {
        current_u = upper_bound;
    } else {
        return SolverResult {
            u_safe: current_u,
            iterations,
            status: SolverStatus::Optimal,
        };
    }

    if current_u >= lower_bound && current_u <= upper_bound {
        return SolverResult {
            u_safe: current_u,
            iterations,
            status: SolverStatus::Optimal,
        };
    }
}

SolverResult {
    u_safe: current_u,
    iterations,
    status: SolverStatus::MaxIterationsReached,
}

```

}
"""

# 3. src/benchmark_harness.rs

benchmark_harness_rs = """pub struct BenchmarkReport {
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
"""

# 4. src/pendulum_sim.rs

pendulum_sim_rs = """use crate::core_math::LinearConstraints;

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
"""

# 5. src/kani_proofs.rs

kani_proofs_rs = """use crate::core_math::\*;

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

let constraints = LinearConstraints {
    a: [kani::any(), kani::any(), kani::any(), kani::any()],
    b: [kani::any(), kani::any(), kani::any(), kani::any()],
};

for i in 0..4 {
    kani::assume(!constraints.a[i].is_nan() && !constraints.a[i].is_infinite());
    kani::assume(!constraints.b[i].is_nan() && !constraints.b[i].is_infinite());
    kani::assume(constraints.a[i] >= -50.0 && constraints.a[i] <= 50.0);
    kani::assume(constraints.b[i] >= -500.0 && constraints.b[i] <= 500.0);
}

let limits = ActuatorLimits { u_min, u_max };
let result = solve_active_set_scalar(u_raw, limits, &constraints);

// Unconditional Safety Invariant: u_safe strictly within actuator limits
assert!(result.u_safe >= u_min && result.u_safe <= u_max);

// Status invariant: solver always reports an intentional enum variant
assert!(
    result.status == SolverStatus::Optimal
        || result.status == SolverStatus::InfeasibleRelaxedApplied
        || result.status == SolverStatus::MaxIterationsReached
        || result.status == SolverStatus::InvalidInput
);

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

assert!(res.status == SolverStatus::Optimal);
assert!(res.u_safe >= u_min && res.u_safe <= u_max);

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

assert!(res.status == SolverStatus::InfeasibleRelaxedApplied);
assert!(res.u_safe >= u_min && res.u_safe <= u_max);

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

let constraints = LinearConstraints {
    a: [kani::any(), kani::any(), kani::any(), kani::any()],
    b: [kani::any(), kani::any(), kani::any(), kani::any()],
};

for i in 0..4 {
    kani::assume(!constraints.a[i].is_nan() && !constraints.a[i].is_infinite());
    kani::assume(!constraints.b[i].is_nan() && !constraints.b[i].is_infinite());
    kani::assume(constraints.a[i] >= -50.0 && constraints.a[i] <= 50.0);
    kani::assume(constraints.b[i] >= -500.0 && constraints.b[i] <= 500.0);
}

let limits = ActuatorLimits { u_min, u_max };
let res = solve_active_set_scalar(u_raw, limits, &constraints);

assert!(res.iterations <= 10);

```

}
"""

files = {
"src/lib.rs": lib_rs,
"src/core_math.rs": core_math_rs,
"src/benchmark_harness.rs": benchmark_harness_rs,
"src/pendulum_sim.rs": pendulum_sim_rs,
"src/kani_proofs.rs": kani_proofs_rs,
}

for path, content in files.items():
print(f"Writing clean {path}...")
with open(path, "w", encoding="utf-8") as f:
f.write(content)

print("\\nFiles updated. Running AWS Kani Model Checker...\\n")
sys.stdout.flush()
res = subprocess.run(\["cargo", "kani", "--default-unwind", "12"\])
sys.exit(res.returncode)