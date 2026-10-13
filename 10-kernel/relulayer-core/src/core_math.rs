#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SolverStatus {
    InvalidInput = 0,
    Optimal = 1,
    MaxIterationsReached = 2,
    InfeasibleRelaxedApplied = 3,
    NumericalDegeneracy = 4,
}

#[repr(C)]
pub struct ActuatorLimits {
    pub u_min: f32,
    pub u_max: f32,
}

#[repr(C)]
pub struct LinearConstraints {
    pub a: [f32; 4],
    pub b: [f32; 4],
}

#[repr(C)]
pub struct SolverResult {
    pub u_safe: f32,
    pub iterations: usize,
    pub status: SolverStatus,
}

#[inline(always)]
fn clamp_scalar(x: f32, lo: f32, hi: f32) -> f32 {
    if x < lo {
        lo
    } else if x > hi {
        hi
    } else {
        x
    }
}

/// Scalar active-set projection solver.
///
/// Solves `min (u - u_raw)^2` subject to `u_min <= u <= u_max` and the first
/// polyhedral half-space constraint `a[0] * u <= b[0]`.  If the box and the
/// half-space do not intersect, the solver returns the best box-feasible point
/// with status `InfeasibleRelaxedApplied`.  For coupled multi-channel allocation
/// see `solve_multivar_4d` in `multivar_4d.rs`.
pub fn solve_active_set_scalar(
    u_raw: f32,
    limits: ActuatorLimits,
    constraints: &LinearConstraints,
) -> SolverResult {
    let a = constraints.a[0];
    let b = constraints.b[0];

    // Degenerate / unbounded half-space.
    if a == 0.0 {
        if b < 0.0 {
            // Half-space is empty; fall back to box projection.
            return SolverResult {
                u_safe: clamp_scalar(u_raw, limits.u_min, limits.u_max),
                iterations: 1,
                status: SolverStatus::InfeasibleRelaxedApplied,
            };
        }
        // Half-space is always satisfied; just apply box limits.
        return SolverResult {
            u_safe: clamp_scalar(u_raw, limits.u_min, limits.u_max),
            iterations: 1,
            status: SolverStatus::Optimal,
        };
    }

    let boundary = b / a;

    if a > 0.0 {
        // Feasible region: u <= boundary, intersected with box.
        if limits.u_min > boundary {
            // Infeasible: box lies entirely above the half-space.
            return SolverResult {
                u_safe: clamp_scalar(boundary, limits.u_min, limits.u_max),
                iterations: 1,
                status: SolverStatus::InfeasibleRelaxedApplied,
            };
        }
        let u = clamp_scalar(u_raw, limits.u_min, boundary.min(limits.u_max));
        return SolverResult {
            u_safe: u,
            iterations: 1,
            status: SolverStatus::Optimal,
        };
    }

    // a < 0.0: Feasible region: u >= boundary, intersected with box.
    if limits.u_max < boundary {
        // Infeasible: box lies entirely below the half-space.
        return SolverResult {
            u_safe: clamp_scalar(boundary, limits.u_min, limits.u_max),
            iterations: 1,
            status: SolverStatus::InfeasibleRelaxedApplied,
        };
    }
    let u = clamp_scalar(u_raw, boundary.max(limits.u_min), limits.u_max);
    SolverResult {
        u_safe: u,
        iterations: 1,
        status: SolverStatus::Optimal,
    }
}

/// Standard C-ABI entry point for external flight controllers (PX4, ArduPilot, bare-metal C).
#[allow(unsafe_code)]
#[no_mangle]
pub extern "C" fn relulayer_solve_active_set(
    u_raw: f32,
    limits: ActuatorLimits,
    constraints: *const LinearConstraints,
    out_result: *mut SolverResult,
) -> i32 {
    if constraints.is_null() || out_result.is_null() {
        return -1;
    }
    let constraints_ref = unsafe { &*constraints };
    let res = solve_active_set_scalar(u_raw, limits, constraints_ref);
    unsafe {
        *out_result = res;
    }
    0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_c_ffi_entrypoint() {
        let limits = ActuatorLimits {
            u_min: -20.0,
            u_max: 20.0,
        };
        let constraints = LinearConstraints {
            a: [1.0, -1.0, 0.0, 0.0],
            b: [10.0, 10.0, 100.0, 100.0],
        };
        let mut result = SolverResult {
            u_safe: 0.0,
            iterations: 0,
            status: SolverStatus::InvalidInput,
        };
        let rc = relulayer_solve_active_set(15.0, limits, &constraints, &mut result);
        assert_eq!(rc, 0);
        match result.status {
            SolverStatus::Optimal => {}
            _ => panic!("Unexpected solver status"),
        }
        assert!((result.u_safe - 10.0).abs() < 1e-6);
    }
}
