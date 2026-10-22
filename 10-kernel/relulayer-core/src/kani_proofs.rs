use crate::core_math::*;

#[kani::proof]
#[kani::unwind(12)]
pub fn verify_active_set_no_panics() {
    let u_raw: f32 = kani::any();
    let u_min: f32 = kani::any();
    let u_max: f32 = kani::any();

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
}

#[kani::proof]
#[kani::unwind(12)]
pub fn verify_feasible_bounds() {
    let u_raw: f32 = kani::any();
    let u_min: f32 = -20.0;
    let u_max: f32 = 20.0;

    kani::assume(!u_raw.is_nan() && !u_raw.is_infinite());

    let constraints = LinearConstraints {
        a: [1.0, -1.0, 1.0, -1.0],
        b: [u_max, -u_min, u_max, -u_min],
    };

    let limits = ActuatorLimits { u_min, u_max };
    let res = solve_active_set_scalar(u_raw, limits, &constraints);

    assert!(res.status == SolverStatus::Optimal);
    assert!(res.u_safe >= u_min && res.u_safe <= u_max);
}

#[kani::proof]
#[kani::unwind(12)]
pub fn verify_infeasible_fallback_boundedness() {
    let u_raw: f32 = kani::any();
    let u_min: f32 = -20.0;
    let u_max: f32 = 20.0;

    kani::assume(!u_raw.is_nan() && !u_raw.is_infinite());

    // First half-space is u <= -30; box [-20, 20] lies entirely above it,
    // so the solver must detect infeasibility and return a bounded relaxed point.
    let constraints = LinearConstraints {
        a: [1.0, -1.0, 1.0, -1.0],
        b: [-30.0, -15.0, 100.0, 100.0],
    };

    let limits = ActuatorLimits { u_min, u_max };
    let res = solve_active_set_scalar(u_raw, limits, &constraints);

    assert!(res.status == SolverStatus::InfeasibleRelaxedApplied);
    assert!(res.u_safe >= u_min && res.u_safe <= u_max);
}

#[kani::proof]
#[kani::unwind(12)]
pub fn verify_deterministic_wcet() {
    let u_raw: f32 = kani::any();
    let u_min: f32 = -20.0;
    let u_max: f32 = 20.0;

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
}
