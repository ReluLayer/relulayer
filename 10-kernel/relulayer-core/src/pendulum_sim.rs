use crate::core_math::LinearConstraints;

pub const A_SYS: [[f32; 4]; 4] = [
    [1.0000, 0.0100, 0.0000, 0.0000],
    [0.0000, 1.0000, 0.0392, 0.0002],
    [0.0000, 0.0000, 1.0354, 0.0102],
    [0.0000, 0.0000, 7.1120, 1.0354],
];

pub const B_SYS: [f32; 4] = [
    0.0001,
    0.0196,
    -0.0031,
    -0.6258,
];

pub fn compute_step_constraints(
    x: &[f32; 4],
    p_limit: f32,
    theta_limit: f32,
) -> LinearConstraints {
    let p_free = A_SYS[0][0] * x[0] + A_SYS[0][1] * x[1] + A_SYS[0][2] * x[2] + A_SYS[0][3] * x[3];
    let theta_free = A_SYS[2][0] * x[0] + A_SYS[2][1] * x[1] + A_SYS[2][2] * x[2] + A_SYS[2][3] * x[3];

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
}

pub fn step_dynamics(x: &[f32; 4], u: f32) -> [f32; 4] {
    let mut x_next = [0.0f32; 4];
    for i in 0..4 {
        let mut sum = 0.0f32;
        for j in 0..4 {
            sum += A_SYS[i][j] * x[j];
        }
        x_next[i] = sum + B_SYS[i] * u;
    }
    x_next
}

#[cfg(test)]
mod tests {
    use super::*;

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
}
