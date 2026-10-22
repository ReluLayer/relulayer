//! Legacy scalar active-set governor retained for backward compatibility.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use relulayer_core::{solve_active_set_scalar, LinearConstraints, ValueBounds};

/// Python wrapper around the ReluLayer scalar active-set projection kernel.
#[pyclass]
pub struct Governor {
    min_bound: f32,
    max_bound: f32,
    constraints: LinearConstraints,
}

#[pymethods]
impl Governor {
    /// Construct a new governor with the given value bounds.
    #[new]
    fn new(min_bound: f32, max_bound: f32) -> PyResult<Self> {
        if !(min_bound < max_bound) {
            return Err(PyValueError::new_err(
                "min_bound must be strictly less than max_bound",
            ));
        }

        let constraints = LinearConstraints {
            a: [1.0, -1.0, 0.0, 0.0],
            b: [max_bound, -min_bound, 0.0, 0.0],
        };

        Ok(Self {
            min_bound,
            max_bound,
            constraints,
        })
    }

    /// Project a single scalar value into the safe envelope.
    fn project(&self, u_desired: f32) -> f32 {
        let limits = ValueBounds {
            u_min: self.min_bound,
            u_max: self.max_bound,
        };
        let result = solve_active_set_scalar(u_desired, limits, &self.constraints);
        result.u_safe.clamp(self.min_bound, self.max_bound)
    }

    /// Project a vector of scalar values in a single call.
    fn project_batch(&self, u_vec: Vec<f32>) -> Vec<f32> {
        u_vec.into_iter().map(|u| self.project(u)).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn governor_clamps_scalar() {
        let gov = Governor::new(-12.0, 12.0).unwrap();
        assert!((gov.project(-25.0) - (-12.0)).abs() < f32::EPSILON);
        assert!((gov.project(25.0) - 12.0).abs() < f32::EPSILON);
        assert!((gov.project(5.0) - 5.0).abs() < f32::EPSILON);
    }

    #[test]
    fn governor_rejects_inverted_bounds() {
        assert!(Governor::new(12.0, -12.0).is_err());
        assert!(Governor::new(12.0, 12.0).is_err());
    }

    #[test]
    fn governor_batch_no_violations() {
        let gov = Governor::new(-12.0, 12.0).unwrap();
        let out = gov.project_batch(vec![-100.0, -5.0, 0.0, 7.0, 100.0]);
        assert!(out.iter().all(|&v| v >= -12.0 && v <= 12.0));
    }
}
