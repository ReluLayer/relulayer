#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ActuatorLimits {
    pub u_min: f32,
    pub u_max: f32,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct LinearConstraints {
    pub a: [f32; 4],
    pub b: [f32; 4],
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SolverStatus {
    Optimal,
    MaxIterationsReached,
    InfeasibleRelaxedApplied,
    InvalidInput,
}

#[derive(Clone, Copy, Debug, PartialEq)]
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

        let midpoint = 0.5 * (clamped_lb + clamped_ub);
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
}
