//! Zero-overhead PyO3 bindings for the ReluLayer active-set safety governor.
//!
//! Exposes a Python class `Governor` that clamps scalar and vector actuator
//! commands to strict symmetric or asymmetric bounds via the verified
//! `#![no_std]` ReluLayer core. The hot-path `.project()` method performs no
//! dynamic heap allocation and no panicking branches.
//!
//! # Example
//!
//! ```python
//! from relulayer import Governor
//! gov = Governor(min_bound=-12.0, max_bound=12.0)
//! safe_torque = gov.project(policy(obs))
//! ```

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use relulayer_core::{ActuatorLimits, LinearConstraints, solve_active_set_scalar};

/// Python wrapper around the ReluLayer scalar active-set projection kernel.
#[pyclass]
pub struct Governor {
    min_bound: f32,
    max_bound: f32,
    constraints: LinearConstraints,
}

#[pymethods]
impl Governor {
    /// Construct a new governor with the given actuator limits.
    ///
    /// # Errors
    ///
    /// Raises `ValueError` if `min_bound` is not strictly less than `max_bound`.
    #[new]
    fn new(min_bound: f32, max_bound: f32) -> PyResult<Self> {
        if !(min_bound < max_bound) {
            return Err(PyValueError::new_err(
                "min_bound must be strictly less than max_bound",
            ));
        }

        // Encode the box constraints as two half-space constraints so the core
        // active-set solver can participate. The lower-bound constraint is
        // expressed as `-u <= -min_bound`, i.e. `a = -1.0`, `b = -min_bound`.
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

    /// Project a single scalar actuator command into the safe envelope.
    ///
    /// This method is allocation-free and panic-free on the Rust side.
    fn project(&self, u_desired: f32) -> f32 {
        // Reconstruct limits from the cached scalar bounds so the hot path
        // never moves out of `&self`.
        let limits = ActuatorLimits {
            u_min: self.min_bound,
            u_max: self.max_bound,
        };
        let result = solve_active_set_scalar(u_desired, limits, &self.constraints);
        // Defensive final clamp guarantees the public safety contract even if
        // the core solver returns a numerical outlier.
        result.u_safe.clamp(self.min_bound, self.max_bound)
    }

    /// Project a vector of actuator commands in a single call.
    ///
    /// Allocates only the output `Vec<f32>`; the per-element projection
    /// remains allocation-free.
    fn project_batch(&self, u_vec: Vec<f32>) -> Vec<f32> {
        u_vec.into_iter().map(|u| self.project(u)).collect()
    }
}

/// Python module registration.
#[pymodule]
fn relulayer(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Governor>()?;
    m.add("__version__", "0.1.0")?;
    Ok(())
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
