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
pub enum SolverStatus {
    InvalidInput = 0,
    Optimal = 1,
    // Add additional statuses as needed
}

#[repr(C)]
pub struct SolverResult {
    pub u_safe: f32,
    pub iterations: usize,
    pub status: SolverStatus,
}

// Example implementation of the core scalar active-set solver
// Adjust this function as per the actual algorithm
pub fn solve_active_set_scalar(u_raw: f32, _limits: ActuatorLimits, constraints: &LinearConstraints) -> SolverResult {
    // For demonstration, we'll clip u_raw to the first constraint's b value if it exceeds it
    let u_safe = if u_raw > constraints.b[0] { constraints.b[0] } else { u_raw };
    let iterations = 5; // dummy iteration count
    let status = SolverStatus::Optimal;
    SolverResult { u_safe, iterations, status }
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
        let limits = ActuatorLimits { u_min: -20.0, u_max: 20.0 };
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
        // Verify that the status is Optimal
        match result.status {
            SolverStatus::Optimal => {},
            _ => panic!("Unexpected solver status"),
        }
        // Check u_safe is correctly projected (15.0 clipped to 10.0)
        assert!((result.u_safe - 10.0).abs() < 1e-6);
    }
}
