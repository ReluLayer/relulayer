//! AWS Kani bounded-model-checking proofs for the 4-D multivariable QP kernel.

use crate::core_math::SolverStatus;
use crate::multivar_4d::{ActuatorLimits4D, LinearConstraints4D, solve_multivar_4d};

const N: usize = 4;
const P_MAX: usize = 4;

/// Reasonable finite bounds used to keep the BMC search space tractable.
const RAW_BOUND: f32 = 50.0;
const LIMIT_BOUND: f32 = 50.0;
const A_BOUND: f32 = 10.0;
const B_BOUND: f32 = 100.0;

#[kani::proof]
#[kani::unwind(24)]
pub fn verify_multivar_no_panics() {
    let mut u_raw = [0.0f32; N];
    for i in 0..N {
        u_raw[i] = kani::any::<f32>();
        kani::assume(!u_raw[i].is_nan() && !u_raw[i].is_infinite());
        kani::assume(u_raw[i] >= -RAW_BOUND && u_raw[i] <= RAW_BOUND);
    }

    let mut limits = ActuatorLimits4D {
        u_min: [0.0f32; N],
        u_max: [0.0f32; N],
    };
    for i in 0..N {
        limits.u_min[i] = kani::any::<f32>();
        limits.u_max[i] = kani::any::<f32>();
        kani::assume(!limits.u_min[i].is_nan() && !limits.u_min[i].is_infinite());
        kani::assume(!limits.u_max[i].is_nan() && !limits.u_max[i].is_infinite());
        kani::assume(limits.u_min[i] >= -LIMIT_BOUND);
        kani::assume(limits.u_max[i] <= LIMIT_BOUND);
        kani::assume(limits.u_min[i] <= limits.u_max[i]);
    }

    let p = kani::any::<usize>();
    kani::assume(p <= P_MAX);

    let mut constraints = LinearConstraints4D {
        p,
        a: [[0.0f32; N]; P_MAX],
        b: [0.0f32; P_MAX],
    };
    for j in 0..P_MAX {
        for i in 0..N {
            constraints.a[j][i] = kani::any::<f32>();
            kani::assume(!constraints.a[j][i].is_nan() && !constraints.a[j][i].is_infinite());
            kani::assume(constraints.a[j][i] >= -A_BOUND && constraints.a[j][i] <= A_BOUND);
        }
        constraints.b[j] = kani::any::<f32>();
        kani::assume(!constraints.b[j].is_nan() && !constraints.b[j].is_infinite());
        kani::assume(constraints.b[j] >= -B_BOUND && constraints.b[j] <= B_BOUND);
    }

    let result = solve_multivar_4d(u_raw, &limits, &constraints);

    // The result must always report a defined status variant.
    let _ = match result.status {
        SolverStatus::InvalidInput
        | SolverStatus::Optimal
        | SolverStatus::MaxIterationsReached
        | SolverStatus::InfeasibleRelaxedApplied
        | SolverStatus::NumericalDegeneracy => true,
    };

    // No panic => the proof succeeds if control reaches this point.
    assert!(true);
}

#[kani::proof]
#[kani::unwind(24)]
pub fn verify_multivar_actuator_bounds() {
    let mut u_raw = [0.0f32; N];
    for i in 0..N {
        u_raw[i] = kani::any::<f32>();
        kani::assume(!u_raw[i].is_nan() && !u_raw[i].is_infinite());
        kani::assume(u_raw[i] >= -RAW_BOUND && u_raw[i] <= RAW_BOUND);
    }

    let mut limits = ActuatorLimits4D {
        u_min: [0.0f32; N],
        u_max: [0.0f32; N],
    };
    for i in 0..N {
        limits.u_min[i] = kani::any::<f32>();
        limits.u_max[i] = kani::any::<f32>();
        kani::assume(!limits.u_min[i].is_nan() && !limits.u_min[i].is_infinite());
        kani::assume(!limits.u_max[i].is_nan() && !limits.u_max[i].is_infinite());
        kani::assume(limits.u_min[i] >= -LIMIT_BOUND);
        kani::assume(limits.u_max[i] <= LIMIT_BOUND);
        kani::assume(limits.u_min[i] <= limits.u_max[i]);
    }

    let p = kani::any::<usize>();
    kani::assume(p <= P_MAX);

    let mut constraints = LinearConstraints4D {
        p,
        a: [[0.0f32; N]; P_MAX],
        b: [0.0f32; P_MAX],
    };
    for j in 0..P_MAX {
        for i in 0..N {
            constraints.a[j][i] = kani::any::<f32>();
            kani::assume(!constraints.a[j][i].is_nan() && !constraints.a[j][i].is_infinite());
            kani::assume(constraints.a[j][i] >= -A_BOUND && constraints.a[j][i] <= A_BOUND);
        }
        constraints.b[j] = kani::any::<f32>();
        kani::assume(!constraints.b[j].is_nan() && !constraints.b[j].is_infinite());
        kani::assume(constraints.b[j] >= -B_BOUND && constraints.b[j] <= B_BOUND);
    }

    let result = solve_multivar_4d(u_raw, &limits, &constraints);

    for i in 0..N {
        assert!(result.u_safe[i] >= limits.u_min[i]);
        assert!(result.u_safe[i] <= limits.u_max[i]);
    }
}

#[kani::proof]
#[kani::unwind(24)]
pub fn verify_multivar_iteration_bound() {
    let mut u_raw = [0.0f32; N];
    for i in 0..N {
        u_raw[i] = kani::any::<f32>();
        kani::assume(!u_raw[i].is_nan() && !u_raw[i].is_infinite());
        kani::assume(u_raw[i] >= -RAW_BOUND && u_raw[i] <= RAW_BOUND);
    }

    let mut limits = ActuatorLimits4D {
        u_min: [0.0f32; N],
        u_max: [0.0f32; N],
    };
    for i in 0..N {
        limits.u_min[i] = kani::any::<f32>();
        limits.u_max[i] = kani::any::<f32>();
        kani::assume(!limits.u_min[i].is_nan() && !limits.u_min[i].is_infinite());
        kani::assume(!limits.u_max[i].is_nan() && !limits.u_max[i].is_infinite());
        kani::assume(limits.u_min[i] >= -LIMIT_BOUND);
        kani::assume(limits.u_max[i] <= LIMIT_BOUND);
        kani::assume(limits.u_min[i] <= limits.u_max[i]);
    }

    let p = kani::any::<usize>();
    kani::assume(p <= P_MAX);

    let mut constraints = LinearConstraints4D {
        p,
        a: [[0.0f32; N]; P_MAX],
        b: [0.0f32; P_MAX],
    };
    for j in 0..P_MAX {
        for i in 0..N {
            constraints.a[j][i] = kani::any::<f32>();
            kani::assume(!constraints.a[j][i].is_nan() && !constraints.a[j][i].is_infinite());
            kani::assume(constraints.a[j][i] >= -A_BOUND && constraints.a[j][i] <= A_BOUND);
        }
        constraints.b[j] = kani::any::<f32>();
        kani::assume(!constraints.b[j].is_nan() && !constraints.b[j].is_infinite());
        kani::assume(constraints.b[j] >= -B_BOUND && constraints.b[j] <= B_BOUND);
    }

    let result = solve_multivar_4d(u_raw, &limits, &constraints);

    // The implementation enforces a hard ceiling of 20 iterations.
    assert!(result.iterations <= 20);
}
