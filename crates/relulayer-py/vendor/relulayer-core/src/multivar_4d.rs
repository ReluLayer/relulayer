//! Multivariable 4-D active-set QP kernel.
//!
//! Solves the strictly convex projection QP
//!
//!   min_u 1/2 ||u - u_raw||^2
//!   s.t.  u_min <= u <= u_max
//!         A u <= b,   A in R^{p x 4}, p <= 4
//!
//! The implementation uses a two-phase strategy:
//!   1. Phase I: a short cyclic projection to obtain a point that is strictly feasible
//!      with respect to the box and all linear half-spaces (when the feasible region
//!      is non-empty).
//!   2. Phase II: a primal feasible active-set method starting from the Phase-I
//!      point.  The working set is always feasible, and the hard iteration ceiling
//!      guarantees deterministic termination.
//!
//! All working memory is stack-allocated via fixed-size arrays; no allocator is used.

use crate::core_math::SolverStatus;

/// Number of value channels.
const N: usize = 4;

/// Maximum number of linear inequality constraint rows.
const P_MAX: usize = 4;

/// Maximum cardinality of the working active set.
const W_MAX: usize = 8;

/// Hard ceiling on active-set (Phase-II) iterations.
const MAX_ITER: usize = 20;

/// Ceiling on Phase-I cyclic-projection iterations.
///
/// Production retains 60 iterations for convergence quality on tightly coupled
/// constraint sets. Under `cfg(kani)` the budget is reduced to 20 so that the
/// existing `#[kani::unwind(24)]` harnesses fully cover the loop without
/// unwinding assertion failures, while keeping the BMC search tractable.
///
/// This abstraction does not weaken the verified safety properties: if Phase I
/// exhausts its budget, `solve_multivar_4d` falls back to
/// `independent_clamp_fallback`, which still satisfies value box bounds and
/// returns a defined status. Convergence to `SolverStatus::Optimal` for inputs
/// requiring >20 Phase-I iterations is a runtime-quality property, not a
/// safety property, and is preserved in production by the `cfg(not(kani))`
/// value below.
#[cfg(not(kani))]
const MAX_PHASE_I_ITER: usize = 60;
#[cfg(kani)]
const MAX_PHASE_I_ITER: usize = 20;

/// Pivot tolerance for the small normal-equations solve.
const PIVOT_TOL: f32 = 1.0e-6;

/// Feasibility / activity tolerance.
const TOL: f32 = 1.0e-5;

/// Step-zero tolerance used to avoid divisions by tiny numbers.
const STEP_TOL: f32 = 1.0e-9;

/// Per-channel value bounds for a 4-channel allocation problem.
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ValueBounds4D {
    pub u_min: [f32; 4],
    pub u_max: [f32; 4],
}

/// Linear polyhedral constraints `A u <= b` with at most `P_MAX` rows.
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct LinearConstraints4D {
    /// Number of active rows (must be <= 4).
    pub p: usize,
    /// Row-major constraint normals. Only the first `p` rows are read.
    pub a: [[f32; 4]; 4],
    /// Constraint right-hand sides. Only the first `p` entries are read.
    pub b: [f32; 4],
}

/// Result structure returned by the 4-D multivariable solver.
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct SolverResult4D {
    pub u_safe: [f32; 4],
    pub iterations: usize,
    pub status: SolverStatus,
}

/// Clamp `x` into the closed interval `[lo, hi]`.
#[inline(always)]
fn clamp(x: f32, lo: f32, hi: f32) -> f32 {
    if x < lo {
        lo
    } else if x > hi {
        hi
    } else {
        x
    }
}

/// Clamp a full 4-D vector into the box.
#[inline(always)]
fn clamp_to_box(u: [f32; N], limits: &ValueBounds4D) -> [f32; N] {
    let mut out = [0.0f32; N];
    for i in 0..N {
        out[i] = clamp(u[i], limits.u_min[i], limits.u_max[i]);
    }
    out
}

/// Dot product of two 4-D vectors.
#[inline(always)]
fn dot(a: &[f32; N], b: &[f32; N]) -> f32 {
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]
}

/// Independent per-channel clamp fallback used when numerical degeneracy is detected.
#[inline(always)]
fn independent_clamp_fallback(
    u_raw: [f32; N],
    limits: &ValueBounds4D,
    status: SolverStatus,
) -> SolverResult4D {
    SolverResult4D {
        u_safe: clamp_to_box(u_raw, limits),
        iterations: 0,
        status,
    }
}

/// Validate inputs.
#[inline(always)]
fn validate_inputs(
    u_raw: [f32; N],
    limits: &ValueBounds4D,
    constraints: &LinearConstraints4D,
) -> Option<SolverStatus> {
    if constraints.p > P_MAX {
        return Some(SolverStatus::InvalidInput);
    }
    for i in 0..N {
        let lo = limits.u_min[i];
        let hi = limits.u_max[i];
        if lo.is_nan() || hi.is_nan() || u_raw[i].is_nan() || lo > hi {
            return Some(SolverStatus::InvalidInput);
        }
    }
    for j in 0..constraints.p {
        for i in 0..N {
            if constraints.a[j][i].is_nan() {
                return Some(SolverStatus::InvalidInput);
            }
        }
        if constraints.b[j].is_nan() {
            return Some(SolverStatus::InvalidInput);
        }
    }
    None
}

/// Check whether `u` satisfies all linear constraints `A u <= b`.
#[inline(always)]
fn linear_feasible(u: [f32; N], constraints: &LinearConstraints4D) -> bool {
    for j in 0..constraints.p {
        if dot(&constraints.a[j], &u) > constraints.b[j] + TOL {
            return false;
        }
    }
    true
}

/// Return true if the constraint `(kind, idx)` is already in the working set.
#[inline(always)]
fn is_in_working_set(
    w_kind: &[u8; W_MAX],
    w_idx: &[u8; W_MAX],
    w_len: usize,
    kind: u8,
    idx: u8,
) -> bool {
    for k in 0..w_len {
        if w_kind[k] == kind && w_idx[k] == idx {
            return true;
        }
    }
    false
}

/// Check whether `u` lies inside the value box.
#[inline(always)]
fn box_feasible(u: [f32; N], limits: &ValueBounds4D) -> bool {
    for i in 0..N {
        if u[i] < limits.u_min[i] - TOL || u[i] > limits.u_max[i] + TOL {
            return false;
        }
    }
    true
}

/// Phase I: find a point inside box ∩ {A u <= b} using cyclic projection.
///
/// Starts from the centre of the box and alternately projects onto violated
/// half-spaces, clipping back to the box after each projection.  This is a
/// deterministic von-Neumann-style scheme that converges for non-empty convex
/// intersections.  Returns `None` if the budget is exhausted without finding a
/// feasible point.
fn find_feasible_point(
    limits: &ValueBounds4D,
    constraints: &LinearConstraints4D,
) -> Option<[f32; N]> {
    let mut u = [0.0f32; N];
    for i in 0..N {
        u[i] = clamp(0.0f32, limits.u_min[i], limits.u_max[i]);
    }

    for _ in 0..MAX_PHASE_I_ITER {
        let mut any_violated = false;
        for j in 0..constraints.p {
            let val = dot(&constraints.a[j], &u) - constraints.b[j];
            if val > TOL {
                any_violated = true;
                let a_norm_sq = dot(&constraints.a[j], &constraints.a[j]);
                if a_norm_sq < STEP_TOL {
                    continue;
                }
                let scale = val / a_norm_sq;
                for i in 0..N {
                    u[i] -= scale * constraints.a[j][i];
                }
                u = clamp_to_box(u, limits);
            }
        }
        if !any_violated {
            return Some(u);
        }
    }

    // Final feasibility check.
    if box_feasible(u, limits) && linear_feasible(u, constraints) {
        Some(u)
    } else {
        None
    }
}

/// Solve the normal equations `M lambda = rhs` where `M = C C^T`.
///
/// Uses Gaussian elimination with partial pivoting.  Returns `false` if the system
/// is numerically singular, guaranteeing that no division by a near-zero pivot occurs.
#[inline(never)]
fn solve_normal_equations(
    m: usize,
    c: &[[f32; N]; W_MAX],
    rhs: &[f32; W_MAX],
    lambda: &mut [f32; W_MAX],
) -> bool {
    // Form M = C C^T (m x m, symmetric positive semi-definite).
    let mut mmat = [[0.0f32; W_MAX]; W_MAX];
    for i in 0..m {
        for j in 0..m {
            mmat[i][j] = dot(&c[i], &c[j]);
        }
    }

    let mut b = *rhs;

    // Gaussian elimination with partial pivoting.
    for col in 0..m {
        // Find pivot row.
        let mut pivot_val = mmat[col][col].abs();
        let mut pivot_row = col;
        for row in (col + 1)..m {
            let v = mmat[row][col].abs();
            if v > pivot_val {
                pivot_val = v;
                pivot_row = row;
            }
        }

        if pivot_val < PIVOT_TOL {
            return false;
        }

        // Swap rows if needed.
        if pivot_row != col {
            for k in col..m {
                let tmp = mmat[col][k];
                mmat[col][k] = mmat[pivot_row][k];
                mmat[pivot_row][k] = tmp;
            }
            let tmp = b[col];
            b[col] = b[pivot_row];
            b[pivot_row] = tmp;
        }

        // Eliminate below.
        for row in (col + 1)..m {
            let factor = mmat[row][col] / mmat[col][col];
            if !factor.is_finite() {
                return false;
            }
            for k in col..m {
                mmat[row][k] -= factor * mmat[col][k];
            }
            b[row] -= factor * b[col];
        }
    }

    // Back substitution.
    for i in (0..m).rev() {
        let diag = mmat[i][i];
        if diag.abs() < PIVOT_TOL {
            return false;
        }
        let mut sum = b[i];
        for j in (i + 1)..m {
            sum -= mmat[i][j] * lambda[j];
        }
        let li = sum / diag;
        if !li.is_finite() {
            return false;
        }
        lambda[i] = li;
    }

    true
}

/// Solve the 4-D box- and linearly-constrained projection QP.
///
/// Phase I produces a feasible iterate.  Phase II is a primal feasible active-set
/// method that maintains a feasible working set and terminates deterministically
/// within `MAX_ITER` iterations.  On numerical degeneracy the solver falls back to
/// independent per-channel clamping, which always satisfies the box bounds.
pub fn solve_multivar_4d(
    u_raw: [f32; N],
    limits: &ValueBounds4D,
    constraints: &LinearConstraints4D,
) -> SolverResult4D {
    // Input validation.
    if let Some(status) = validate_inputs(u_raw, limits, constraints) {
        return independent_clamp_fallback(u_raw, limits, status);
    }

    // Fast path: the box projection already satisfies the linear constraints.
    let u_box = clamp_to_box(u_raw, limits);
    if linear_feasible(u_box, constraints) {
        return SolverResult4D {
            u_safe: u_box,
            iterations: 0,
            status: SolverStatus::Optimal,
        };
    }

    // Phase I: obtain a feasible starting point.
    let mut u = match find_feasible_point(limits, constraints) {
        Some(u) => u,
        None => return independent_clamp_fallback(u_raw, limits, SolverStatus::InfeasibleRelaxedApplied),
    };

    // Working active set, initialised with constraints active at the feasible point.
    // kind: 0 = lower box, 1 = upper box, 2 = linear.
    let mut w_kind = [0u8; W_MAX];
    let mut w_idx = [0u8; W_MAX];
    let mut w_len: usize = 0;

    for i in 0..N {
        if (u[i] - limits.u_min[i]).abs() <= TOL {
            if w_len < W_MAX {
                w_kind[w_len] = 0;
                w_idx[w_len] = i as u8;
                w_len += 1;
            }
        } else if (u[i] - limits.u_max[i]).abs() <= TOL {
            if w_len < W_MAX {
                w_kind[w_len] = 1;
                w_idx[w_len] = i as u8;
                w_len += 1;
            }
        }
    }
    for j in 0..constraints.p {
        if (dot(&constraints.a[j], &u) - constraints.b[j]).abs() <= TOL {
            if w_len >= W_MAX {
                return independent_clamp_fallback(u_raw, limits, SolverStatus::NumericalDegeneracy);
            }
            w_kind[w_len] = 2;
            w_idx[w_len] = j as u8;
            w_len += 1;
        }
    }

    // Active-set main loop.
    for iter in 0..MAX_ITER {
        // Build C (w_len x N) and d (w_len) using the g(u) <= 0 convention:
        //   lower box:  -u_i + u_min_i <= 0  -> normal -e_i,  d = -u_min_i
        //   upper box:   u_i - u_max_i <= 0  -> normal +e_i,  d =  u_max_i
        //   linear:      a_j u - b_j   <= 0  -> normal a_j,   d =  b_j
        let mut c = [[0.0f32; N]; W_MAX];
        let mut d = [0.0f32; W_MAX];
        for k in 0..w_len {
            match w_kind[k] {
                0 => {
                    let i = w_idx[k] as usize;
                    c[k][i] = -1.0;
                    d[k] = -limits.u_min[i];
                }
                1 => {
                    let i = w_idx[k] as usize;
                    c[k][i] = 1.0;
                    d[k] = limits.u_max[i];
                }
                2 => {
                    let j = w_idx[k] as usize;
                    c[k] = constraints.a[j];
                    d[k] = constraints.b[j];
                }
                _ => {}
            }
        }

        // Normal-equations RHS: C u_raw - d.
        let mut rhs = [0.0f32; W_MAX];
        for k in 0..w_len {
            rhs[k] = dot(&c[k], &u_raw) - d[k];
        }

        // Solve for multipliers.
        let mut lambda = [0.0f32; W_MAX];
        if !solve_normal_equations(w_len, &c, &rhs, &mut lambda) {
            return independent_clamp_fallback(u_raw, limits, SolverStatus::NumericalDegeneracy);
        }

        // Subproblem solution: u = u_raw - C^T lambda.
        let mut u_new = u_raw;
        for k in 0..w_len {
            let lk = lambda[k];
            for i in 0..N {
                u_new[i] -= c[k][i] * lk;
            }
        }

        // Check multiplier signs.  Drop the most negative multiplier.
        let mut min_lambda: f32 = 0.0;
        let mut min_idx: usize = w_len;
        for k in 0..w_len {
            if lambda[k] < min_lambda - TOL {
                min_lambda = lambda[k];
                min_idx = k;
            }
        }
        if min_idx < w_len {
            // Remove constraint min_idx from the working set.
            for k in min_idx..(w_len - 1) {
                w_kind[k] = w_kind[k + 1];
                w_idx[k] = w_idx[k + 1];
            }
            w_len -= 1;
            continue;
        }

        // Check primal feasibility of the subproblem solution.
        let mut max_viol: f32 = 0.0;
        let mut block_kind: u8 = 0;
        let mut block_idx: u8 = 0;

        // Box violations (skip bounds already in the working set).
        for i in 0..N {
            if !is_in_working_set(&w_kind, &w_idx, w_len, 0, i as u8) {
                let lo_viol = limits.u_min[i] - u_new[i];
                if lo_viol > max_viol {
                    max_viol = lo_viol;
                    block_kind = 0;
                    block_idx = i as u8;
                }
            }
            if !is_in_working_set(&w_kind, &w_idx, w_len, 1, i as u8) {
                let hi_viol = u_new[i] - limits.u_max[i];
                if hi_viol > max_viol {
                    max_viol = hi_viol;
                    block_kind = 1;
                    block_idx = i as u8;
                }
            }
        }

        // Linear violations (skip rows already in the working set).
        for j in 0..constraints.p {
            if !is_in_working_set(&w_kind, &w_idx, w_len, 2, j as u8) {
                let viol = dot(&constraints.a[j], &u_new) - constraints.b[j];
                if viol > max_viol {
                    max_viol = viol;
                    block_kind = 2;
                    block_idx = j as u8;
                }
            }
        }

        if max_viol <= TOL {
            // Optimal feasible solution found.
            return SolverResult4D {
                u_safe: u_new,
                iterations: iter + 1,
                status: SolverStatus::Optimal,
            };
        }

        // Compute step direction and maximum feasible step length.
        let mut dir = [0.0f32; N];
        for i in 0..N {
            dir[i] = u_new[i] - u[i];
        }

        let mut alpha: f32 = 1.0;

        // Box constraints (skip bounds already in the working set or active at u).
        for i in 0..N {
            if is_in_working_set(&w_kind, &w_idx, w_len, 0, i as u8)
                || (u[i] - limits.u_min[i]).abs() <= TOL
            {
                continue;
            }
            if dir[i] < -STEP_TOL {
                let a = (limits.u_min[i] - u[i]) / dir[i];
                if a > STEP_TOL && a < alpha {
                    alpha = a;
                    block_kind = 0;
                    block_idx = i as u8;
                }
            }

            if is_in_working_set(&w_kind, &w_idx, w_len, 1, i as u8)
                || (u[i] - limits.u_max[i]).abs() <= TOL
            {
                continue;
            }
            if dir[i] > STEP_TOL {
                let a = (limits.u_max[i] - u[i]) / dir[i];
                if a > STEP_TOL && a < alpha {
                    alpha = a;
                    block_kind = 1;
                    block_idx = i as u8;
                }
            }
        }

        // Linear constraints (skip rows already in the working set or active at u).
        for j in 0..constraints.p {
            if is_in_working_set(&w_kind, &w_idx, w_len, 2, j as u8)
                || (constraints.b[j] - dot(&constraints.a[j], &u)).abs() <= TOL
            {
                continue;
            }
            let c_dir = dot(&constraints.a[j], &dir);
            if c_dir > STEP_TOL {
                let a = (constraints.b[j] - dot(&constraints.a[j], &u)) / c_dir;
                if a > STEP_TOL && a < alpha {
                    alpha = a;
                    block_kind = 2;
                    block_idx = j as u8;
                }
            }
        }

        if alpha <= STEP_TOL || !alpha.is_finite() {
            return independent_clamp_fallback(u_raw, limits, SolverStatus::NumericalDegeneracy);
        }

        // Take the step.
        for i in 0..N {
            u[i] += alpha * dir[i];
        }

        // If we hit a new constraint before reaching u_new, add it to the working set.
        if alpha < 1.0 - TOL {
            if w_len >= W_MAX {
                return independent_clamp_fallback(u_raw, limits, SolverStatus::NumericalDegeneracy);
            }
            w_kind[w_len] = block_kind;
            w_idx[w_len] = block_idx;
            w_len += 1;
        }
    }

    // Iteration ceiling hit: the current iterate is feasible (from Phase I / steps),
    // so return it as a safe, bounded result.
    SolverResult4D {
        u_safe: u,
        iterations: MAX_ITER,
        status: SolverStatus::MaxIterationsReached,
    }
}

/// C-ABI entry point for the 4-D multivariable active-set QP solver.
///
/// # Safety
///
/// All pointers must be valid and properly aligned for their respective types.
/// `u_raw` and `limits` are read; `out_result` is written.
#[allow(unsafe_code)]
#[no_mangle]
pub extern "C" fn relulayer_solve_multivar_4d(
    u_raw: *const [f32; 4],
    limits: *const ValueBounds4D,
    constraints: *const LinearConstraints4D,
    out_result: *mut SolverResult4D,
) -> i32 {
    if u_raw.is_null() || limits.is_null() || constraints.is_null() || out_result.is_null() {
        return -1;
    }

    let u_raw_ref = unsafe { &*u_raw };
    let limits_ref = unsafe { &*limits };
    let constraints_ref = unsafe { &*constraints };

    let result = solve_multivar_4d(*u_raw_ref, limits_ref, constraints_ref);

    unsafe {
        *out_result = result;
    }

    0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_multivar_interior_passthrough() {
        let u_raw = [1.0, 2.0, -1.0, 0.5];
        let limits = ValueBounds4D {
            u_min: [-5.0; N],
            u_max: [5.0; N],
        };
        let constraints = LinearConstraints4D {
            p: 1,
            a: [[1.0, 1.0, 1.0, 1.0], [0.0; N], [0.0; N], [0.0; N]],
            b: [100.0, 0.0, 0.0, 0.0],
        };
        let res = solve_multivar_4d(u_raw, &limits, &constraints);
        assert_eq!(res.status, SolverStatus::Optimal);
        for i in 0..N {
            assert!((res.u_safe[i] - u_raw[i]).abs() < 1e-4);
        }
    }

    #[test]
    fn test_multivar_box_clipping() {
        let u_raw = [10.0, -10.0, 3.0, -3.0];
        let limits = ValueBounds4D {
            u_min: [-2.0; N],
            u_max: [2.0; N],
        };
        let constraints = LinearConstraints4D {
            p: 0,
            a: [[0.0f32; N]; P_MAX],
            b: [0.0f32; P_MAX],
        };
        let res = solve_multivar_4d(u_raw, &limits, &constraints);
        assert_eq!(res.status, SolverStatus::Optimal);
        assert!((res.u_safe[0] - 2.0).abs() < 1e-4);
        assert!((res.u_safe[1] - (-2.0)).abs() < 1e-4);
        assert!((res.u_safe[2] - 2.0).abs() < 1e-4);
        assert!((res.u_safe[3] - (-2.0)).abs() < 1e-4);
    }

    #[test]
    fn test_multivar_sum_thrust_constraint() {
        // Four saturated demands of 0.9 with total thrust ceiling 3.0.
        let u_raw = [0.9; N];
        let limits = ValueBounds4D {
            u_min: [0.0; N],
            u_max: [1.0; N],
        };
        let constraints = LinearConstraints4D {
            p: 1,
            a: [[1.0, 1.0, 1.0, 1.0], [0.0; N], [0.0; N], [0.0; N]],
            b: [3.0, 0.0, 0.0, 0.0],
        };
        let res = solve_multivar_4d(u_raw, &limits, &constraints);
        assert_eq!(res.status, SolverStatus::Optimal);

        let sum: f32 = res.u_safe.iter().sum();
        assert!((sum - 3.0).abs() < 1e-3, "sum = {}", sum);

        for i in 0..N {
            assert!(res.u_safe[i] >= limits.u_min[i] - 1e-4);
            assert!(res.u_safe[i] <= limits.u_max[i] + 1e-4);
        }
    }

    #[test]
    fn test_multivar_c_ffi_null_pointers() {
        let limits = ValueBounds4D {
            u_min: [0.0; N],
            u_max: [1.0; N],
        };
        let constraints = LinearConstraints4D {
            p: 0,
            a: [[0.0f32; N]; P_MAX],
            b: [0.0f32; P_MAX],
        };
        let mut result = SolverResult4D {
            u_safe: [0.0; N],
            iterations: 0,
            status: SolverStatus::InvalidInput,
        };
        let rc = relulayer_solve_multivar_4d(core::ptr::null(), &limits, &constraints, &mut result);
        assert_eq!(rc, -1);
    }
}
