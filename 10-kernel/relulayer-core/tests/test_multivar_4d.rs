//! Host-side integration tests and 1,000-state Monte Carlo stress harness for the
//! 4-D multivariable active-set QP kernel.

use relulayer_core::multivar_4d::{
    relulayer_solve_multivar_4d, ActuatorLimits4D, LinearConstraints4D, SolverResult4D,
};
use relulayer_core::SolverStatus;

const N: usize = 4;
const P_MAX: usize = 4;

fn solve(
    u_raw: [f32; N],
    limits: &ActuatorLimits4D,
    constraints: &LinearConstraints4D,
) -> SolverResult4D {
    let mut result = SolverResult4D {
        u_safe: [0.0f32; N],
        iterations: 0,
        status: SolverStatus::InvalidInput,
    };
    let rc = relulayer_solve_multivar_4d(&u_raw, limits, constraints, &mut result);
    assert_eq!(rc, 0, "C-ABI call failed");
    result
}

#[test]
fn test_unconstrained_interior_pass_through() {
    let u_raw = [1.0f32, -2.0, 3.0, -4.0];
    let limits = ActuatorLimits4D {
        u_min: [-10.0f32; N],
        u_max: [10.0f32; N],
    };
    let constraints = LinearConstraints4D {
        p: 0,
        a: [[0.0f32; N]; P_MAX],
        b: [0.0f32; P_MAX],
    };
    let res = solve(u_raw, &limits, &constraints);
    assert_eq!(res.status, SolverStatus::Optimal);
    for i in 0..N {
        assert!((res.u_safe[i] - u_raw[i]).abs() < 1e-4);
    }
}

#[test]
fn test_independent_box_clipping() {
    let u_raw = [12.0f32, -15.0, 5.0, -1.0];
    let limits = ActuatorLimits4D {
        u_min: [-10.0f32, -8.0, 0.0, -2.0],
        u_max: [10.0f32, 8.0, 4.0, 2.0],
    };
    let constraints = LinearConstraints4D {
        p: 0,
        a: [[0.0f32; N]; P_MAX],
        b: [0.0f32; P_MAX],
    };
    let res = solve(u_raw, &limits, &constraints);
    assert_eq!(res.status, SolverStatus::Optimal);
    assert!((res.u_safe[0] - 10.0).abs() < 1e-4);
    assert!((res.u_safe[1] - (-8.0)).abs() < 1e-4);
    assert!((res.u_safe[2] - 4.0).abs() < 1e-4);
    assert!((res.u_safe[3] - (-1.0)).abs() < 1e-4);
}

#[test]
fn test_sum_thrust_coupled_constraint() {
    // Saturated individual demands of 0.9 must be scaled back so that the sum is <= 3.0.
    let u_raw = [0.9f32; N];
    let limits = ActuatorLimits4D {
        u_min: [0.0f32; N],
        u_max: [1.0f32; N],
    };
    let constraints = LinearConstraints4D {
        p: 1,
        a: [[1.0f32, 1.0, 1.0, 1.0], [0.0f32; N], [0.0f32; N], [0.0f32; N]],
        b: [3.0f32, 0.0, 0.0, 0.0],
    };
    let res = solve(u_raw, &limits, &constraints);
    assert_eq!(res.status, SolverStatus::Optimal);

    let sum: f32 = res.u_safe.iter().sum();
    assert!(
        (sum - 3.0).abs() < 1e-3,
        "expected total thrust 3.0, got {}",
        sum
    );

    for i in 0..N {
        assert!(res.u_safe[i] >= limits.u_min[i] - 1e-4);
        assert!(res.u_safe[i] <= limits.u_max[i] + 1e-4);
    }
}

#[test]
fn test_c_abi_null_pointer_rejection() {
    let limits = ActuatorLimits4D {
        u_min: [0.0f32; N],
        u_max: [1.0f32; N],
    };
    let constraints = LinearConstraints4D {
        p: 0,
        a: [[0.0f32; N]; P_MAX],
        b: [0.0f32; P_MAX],
    };
    let mut result = SolverResult4D {
        u_safe: [0.0f32; N],
        iterations: 0,
        status: SolverStatus::InvalidInput,
    };

    assert_eq!(
        relulayer_solve_multivar_4d(
            std::ptr::null(),
            &limits,
            &constraints,
            &mut result
        ),
        -1
    );
    assert_eq!(
        relulayer_solve_multivar_4d(
            &[1.0f32; N],
            std::ptr::null(),
            &constraints,
            &mut result
        ),
        -1
    );
    assert_eq!(
        relulayer_solve_multivar_4d(
            &[1.0f32; N],
            &limits,
            std::ptr::null(),
            &mut result
        ),
        -1
    );
    assert_eq!(
        relulayer_solve_multivar_4d(
            &[1.0f32; N],
            &limits,
            &constraints,
            std::ptr::null_mut()
        ),
        -1
    );
}

#[test]
fn test_monte_carlo_1000_states_latency_and_convergence() {
    use std::time::Instant;

    let mut rng = SimpleLcg::new(0xACE1_ACE1);
    const SAMPLES: usize = 1_000;

    let mut total_iters: usize = 0;
    let mut max_iters: usize = 0;
    let mut converged: usize = 0;
    let mut fallback: usize = 0;
    let mut violations: usize = 0;

    let limits = ActuatorLimits4D {
        u_min: [-1.0f32; N],
        u_max: [1.0f32; N],
    };

    // Sum-of-thrust ceiling set loose enough that the box is the dominant limiter,
    // but tight enough to exercise the active-set logic regularly.
    let constraints = LinearConstraints4D {
        p: 1,
        a: [[1.0f32, 1.0, 1.0, 1.0], [0.0f32; N], [0.0f32; N], [0.0f32; N]],
        b: [2.5f32, 0.0, 0.0, 0.0],
    };

    let start = Instant::now();
    for _ in 0..SAMPLES {
        let u_raw = [
            rng.next_f32_range(-3.0, 3.0),
            rng.next_f32_range(-3.0, 3.0),
            rng.next_f32_range(-3.0, 3.0),
            rng.next_f32_range(-3.0, 3.0),
        ];

        let res = solve(u_raw, &limits, &constraints);

        total_iters += res.iterations;
        if res.iterations > max_iters {
            max_iters = res.iterations;
        }
        if res.status == SolverStatus::Optimal {
            converged += 1;
        } else {
            fallback += 1;
        }

        // Box-bound invariant must always hold.
        for i in 0..N {
            if res.u_safe[i] < limits.u_min[i] - 1e-4 || res.u_safe[i] > limits.u_max[i] + 1e-4 {
                violations += 1;
            }
        }
    }
    let elapsed = start.elapsed();

    let avg_ns = elapsed.as_nanos() as f64 / SAMPLES as f64;

    println!("=== 4D Monte Carlo Stress Test ===");
    println!("samples:        {}", SAMPLES);
    println!("converged:      {}", converged);
    println!("fallback:       {}", fallback);
    println!("box violations: {}", violations);
    println!("total iters:    {}", total_iters);
    println!("max iters:      {}", max_iters);
    println!("avg iters:      {:.2}", total_iters as f64 / SAMPLES as f64);
    println!("elapsed:        {:?}", elapsed);
    println!("avg latency:    {:.2} ns", avg_ns);

    assert_eq!(violations, 0, "box bounds violated");
    assert_eq!(converged + fallback, SAMPLES);
    assert!(avg_ns < 1000.0, "average latency {} ns exceeds 1 us budget", avg_ns);
}

/// Tiny deterministic LCG for reproducible Monte Carlo without pulling in `rand`.
struct SimpleLcg {
    state: u64,
}

impl SimpleLcg {
    fn new(seed: u64) -> Self {
        Self { state: seed }
    }

    fn next_u64(&mut self) -> u64 {
        self.state = self
            .state
            .wrapping_mul(6_364_136_223_846_793_005)
            .wrapping_add(1_442_695_040_888_963_407);
        self.state
    }

    fn next_f32_range(&mut self, lo: f32, hi: f32) -> f32 {
        let bits = self.next_u64();
        let frac = (bits >> 32) as u32;
        let norm = frac as f32 / (u32::MAX as f32);
        lo + norm * (hi - lo)
    }
}
