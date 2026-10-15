//! Zero-overhead PyO3 bindings for the ReluLayer™ deterministic edge governor.
//!
//! Exposes `ReluBoundary`, `ReluReceipt`, `ReluViolation`, and
//! `MonotonicCounter` under the public `relulayer` namespace. The hot-path
//! `authorize_action()` method performs all safety checks over stack-resident
//! fixed-size buffers and delegates HMAC computation to the verified
//! `#![no_std]` `relulayer-security` micro-kernel.

use pyo3::exceptions::{PyException, PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use relulayer_security::boundary::BoundaryInterceptor;
use relulayer_security::crypto::{authorize, AuthorizationReceipt, BoundaryKey};
use relulayer_security::limits::{MAX_ACTION_ID_SIZE, NONCE_SIZE, RECEIPT_SERIALIZED_SIZE};
use relulayer_security::ReluError;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};

// Re-export the legacy scalar active-set governor so existing examples and
// benchmarks keep working while the public namespace migrates to ReluBoundary.
mod governor;
pub use governor::Governor;

/// Current Python package version.
const PYTHON_VERSION: &str = "0.2.0";

/// Nanosecond timestamp since the Unix epoch.
fn now_nanos() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos() as u64
}

/// A monotonically increasing 64-bit counter.
#[pyclass]
pub struct MonotonicCounter {
    value: AtomicU64,
}

#[pymethods]
impl MonotonicCounter {
    #[new]
    #[pyo3(signature = (initial_value = 0))]
    fn new(initial_value: u64) -> Self {
        Self {
            value: AtomicU64::new(initial_value),
        }
    }

    /// Return the next strictly greater counter value.
    fn next_value(&self) -> u64 {
        self.value.fetch_add(1, Ordering::SeqCst) + 1
    }

    /// Return the current counter value without advancing it.
    fn current_value(&self) -> u64 {
        self.value.load(Ordering::SeqCst)
    }
}

/// Exception raised when an action request violates the ReluLayer boundary.
#[pyclass(extends = PyException)]
pub struct ReluViolation {
    #[pyo3(get)]
    axis: i32,
    #[pyo3(get)]
    violation_type: String,
    #[pyo3(get)]
    message: String,
}

#[pymethods]
impl ReluViolation {
    #[new]
    #[pyo3(signature = (axis = 0, violation_type = String::new(), message = String::new()))]
    fn new(axis: i32, violation_type: String, message: String) -> Self {
        Self {
            axis,
            violation_type,
            message,
        }
    }

    fn __str__(&self) -> String {
        format!(
            "ReluViolation(axis={}, violation_type={}): {}",
            self.axis, self.violation_type, self.message
        )
    }
}

/// Replay-resistant authorization receipt returned by `ReluBoundary`.
#[pyclass]
pub struct ReluReceipt {
    authorized: bool,
    sequence_id: u64,
    timestamp_nanos: u64,
    receipt_bytes: [u8; RECEIPT_SERIALIZED_SIZE],
    action_id: String,
    payload: [u8; 16],
}

#[pymethods]
impl ReluReceipt {
    #[getter]
    fn is_authorized(&self) -> bool {
        self.authorized
    }

    #[getter]
    fn sequence_id(&self) -> u64 {
        self.sequence_id
    }

    #[getter]
    fn timestamp_nanos(&self) -> u64 {
        self.timestamp_nanos
    }

    #[getter]
    fn receipt_hash<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new(py, &self.receipt_bytes)
    }

    /// Re-verify this receipt against a 32-byte boundary key.
    fn verify(&self, key: &[u8]) -> PyResult<bool> {
        if key.len() != 32 {
            return Ok(false);
        }
        let boundary_key = match BoundaryKey::from_bytes(key) {
            Ok(k) => k,
            Err(_) => return Ok(false),
        };
        let receipt = match AuthorizationReceipt::from_bytes(&self.receipt_bytes) {
            Ok(r) => r,
            Err(_) => return Ok(false),
        };
        match authorize(
            &boundary_key,
            &receipt.nonce,
            receipt.timestamp,
            receipt.counter,
            self.action_id.as_bytes(),
            &self.payload,
        ) {
            Ok(expected) => Ok(expected.tag == receipt.tag),
            Err(_) => Ok(false),
        }
    }
}

/// Mutable state owned by a `ReluBoundary` instance.
struct BoundaryState {
    interceptor: BoundaryInterceptor,
    window_start: u64,
    window_count: u64,
}

/// Deterministic edge governor that authorizes physical actions.
#[pyclass]
pub struct ReluBoundary {
    rate_limit: u64,
    max_velocity: f64,
    #[allow(dead_code)]
    monotonic_window_size: usize,
    counter: AtomicU64,
    state: Mutex<BoundaryState>,
}

#[pymethods]
impl ReluBoundary {
    #[new]
    #[pyo3(signature = (rate_limit = 1000, max_velocity_rad_s = 4.18, monotonic_window_size = 64, hmac_key = None))]
    fn new(
        rate_limit: u64,
        max_velocity_rad_s: f64,
        monotonic_window_size: usize,
        hmac_key: Option<&[u8]>,
    ) -> PyResult<Self> {
        let key = match hmac_key {
            Some(k) => BoundaryKey::from_bytes(k)
                .map_err(|_| PyValueError::new_err("hmac_key must be exactly 32 bytes"))?,
            None => BoundaryKey::from_bytes(&[0u8; 32]).expect("zero key is valid"),
        };

        Ok(Self {
            rate_limit,
            max_velocity: max_velocity_rad_s,
            monotonic_window_size,
            counter: AtomicU64::new(0),
            state: Mutex::new(BoundaryState {
                interceptor: BoundaryInterceptor::new(&key),
                window_start: now_nanos(),
                window_count: 0,
            }),
        })
    }

    /// Authorize a single actuator command and return a signed receipt.
    fn authorize_action(
        &self,
        target_axis: i32,
        requested_position: f64,
        commanded_velocity: f64,
    ) -> PyResult<ReluReceipt> {
        // Velocity safety envelope.
        if commanded_velocity.abs() > self.max_velocity {
            return Err(PyErr::new::<ReluViolation, _>((
                target_axis,
                "velocity_exceeded",
                format!(
                    "commanded_velocity {} rad/s exceeds max_velocity_rad_s {} rad/s",
                    commanded_velocity, self.max_velocity
                ),
            )));
        }

        let mut state = self
            .state
            .lock()
            .map_err(|_| PyRuntimeError::new_err("ReluBoundary state is poisoned"))?;

        let now = now_nanos();
        if now - state.window_start >= 1_000_000_000 {
            state.window_start = now;
            state.window_count = 1;
        } else {
            state.window_count += 1;
            if state.window_count > self.rate_limit {
                return Err(PyErr::new::<ReluViolation, _>((
                    target_axis,
                    "rate_limited",
                    "action rate limit exceeded",
                )));
            }
        }

        let sequence_id = self.counter.fetch_add(1, Ordering::SeqCst) + 1;

        let mut nonce = [0u8; NONCE_SIZE];
        getrandom::getrandom(&mut nonce)
            .map_err(|e| PyRuntimeError::new_err(format!("failed to generate nonce: {e}")))?;

        let action_id = format!("axis_{}", target_axis);
        if action_id.len() > MAX_ACTION_ID_SIZE {
            return Err(PyValueError::new_err("target_axis produces oversized action id").into());
        }

        let mut payload = [0u8; 16];
        payload[..8].copy_from_slice(&requested_position.to_le_bytes());
        payload[8..].copy_from_slice(&commanded_velocity.to_le_bytes());

        let receipt = state
            .interceptor
            .issue_receipt(&nonce, now, sequence_id, action_id.as_bytes(), &payload)
            .map_err(|e| relu_error_to_py_err(target_axis, e))?;

        // Persist replay state by validating the just-issued receipt.
        state
            .interceptor
            .intercept_and_authorize(action_id.as_bytes(), &payload, &receipt)
            .map_err(|e| relu_error_to_py_err(target_axis, e))?;

        Ok(ReluReceipt {
            authorized: true,
            sequence_id,
            timestamp_nanos: now,
            receipt_bytes: receipt.to_bytes(),
            action_id,
            payload,
        })
    }
}

fn relu_error_to_py_err(axis: i32, err: ReluError) -> PyErr {
    let (ty, msg): (&str, &str) = match err {
        ReluError::InvalidPointer => ("invalid_pointer", "null or misaligned pointer"),
        ReluError::ActionIdOverflow => ("action_id_overflow", "action id exceeds maximum size"),
        ReluError::PayloadOverflow => ("payload_overflow", "payload exceeds maximum size"),
        ReluError::InvalidReceipt => ("invalid_receipt", "receipt is malformed"),
        ReluError::InvalidKeyLength => ("invalid_key_length", "key must be 32 bytes"),
        ReluError::AuthenticationFailure => ("authentication_failure", "HMAC verification failed"),
        ReluError::ReplayCounterViolation => {
            ("replay_counter", "monotonic counter violation (replay)")
        }
        ReluError::ReplayNonceViolation => ("replay_nonce", "nonce reuse detected"),
        ReluError::HardwareShaUnavailable => {
            ("hardware_sha_unavailable", "hardware SHA unavailable")
        }
    };
    PyErr::new::<ReluViolation, _>((axis, ty, msg))
}

/// Python module registration.
#[pymodule]
fn _relulayer(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", PYTHON_VERSION)?;
    m.add_class::<ReluBoundary>()?;
    m.add_class::<ReluReceipt>()?;
    m.add_class::<ReluViolation>()?;
    m.add_class::<MonotonicCounter>()?;
    m.add_class::<Governor>()?;
    Ok(())
}
