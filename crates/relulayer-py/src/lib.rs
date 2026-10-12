//! PyO3 bindings for the ReluLayer boundary interceptor.
//!
//! Exposes a Python class `ReluBoundary` that wraps a persistent
//! `BoundaryInterceptor`. The Rust side receives Python `bytes` objects as
//! immutable `&[u8]` slices and copies them into local stack frames before
//! HMAC evaluation, guaranteeing that concurrent Python threads cannot mutate
//! the buffer mid-execution.
//!
//! # Example
//!
//! ```python
//! from relulayer_py import ReluBoundary
//! boundary = ReluBoundary(b"\x07" * 32)
//! receipt = boundary.issue_receipt(nonce, timestamp, counter, action, payload)
//! boundary.intercept_and_authorize(action, payload, receipt)
//! ```

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use relulayer_security::boundary::BoundaryInterceptor;
use relulayer_security::crypto::{authorize, AuthorizationReceipt, BoundaryKey};
use relulayer_security::limits::{
    MAX_ACTION_ID_SIZE, MAX_TOTAL_PAYLOAD_SIZE, NONCE_SIZE, RECEIPT_SERIALIZED_SIZE,
};
use relulayer_security::ReluError;

/// Convert a `ReluError` into a Python `ValueError` with a descriptive message.
fn relu_err_to_py(err: ReluError) -> PyErr {
    let msg = match err {
        ReluError::InvalidPointer => "invalid pointer",
        ReluError::ActionIdOverflow => "action id exceeds maximum length",
        ReluError::PayloadOverflow => "payload exceeds maximum length",
        ReluError::InvalidReceipt => "invalid receipt",
        ReluError::InvalidKeyLength => "key must be 32 bytes",
        ReluError::AuthenticationFailure => "authentication failure",
        ReluError::ReplayCounterViolation => "replay counter violation",
        ReluError::ReplayNonceViolation => "replay nonce violation",
        ReluError::HardwareShaUnavailable => "hardware SHA-256 unavailable",
    };
    PyValueError::new_err(msg)
}

/// Python wrapper around a stateful ReluLayer boundary interceptor.
///
/// Instances are not thread-safe. Each Python thread should use its own
/// `ReluBoundary` instance, or the caller must serialize access.
#[pyclass]
pub struct ReluBoundary {
    key: BoundaryKey,
    interceptor: BoundaryInterceptor,
}

#[pymethods]
impl ReluBoundary {
    /// Create a boundary interceptor from a 32-byte key.
    #[new]
    fn new(key: &Bound<'_, PyBytes>) -> PyResult<Self> {
        let key_slice = key.as_bytes();
        if key_slice.len() != 32 {
            return Err(PyValueError::new_err("key must be 32 bytes"));
        }
        let key = BoundaryKey::from_bytes(key_slice).map_err(relu_err_to_py)?;
        Ok(Self {
            key,
            interceptor: BoundaryInterceptor::new(&key),
        })
    }

    /// Issue a replay-resistant authorization receipt.
    ///
    /// `nonce` must be exactly 12 bytes. `counter` must be strictly monotonic
    /// for the authorization scope.
    fn issue_receipt<'py>(
        &self,
        py: Python<'py>,
        nonce: &Bound<'_, PyBytes>,
        timestamp: u64,
        counter: u64,
        action_id: &Bound<'_, PyBytes>,
        payload: &Bound<'_, PyBytes>,
    ) -> PyResult<Bound<'py, PyBytes>> {
        let nonce = nonce.as_bytes();
        if nonce.len() != NONCE_SIZE {
            return Err(PyValueError::new_err("nonce must be 12 bytes"));
        }
        let mut nonce_arr = [0u8; NONCE_SIZE];
        nonce_arr.copy_from_slice(nonce);

        let action_id = action_id.as_bytes();
        let payload = payload.as_bytes();

        let receipt = authorize(
            &self.key,
            &nonce_arr,
            timestamp,
            counter,
            action_id,
            payload,
        )
        .map_err(relu_err_to_py)?;

        Ok(PyBytes::new(py, &receipt.to_bytes()))
    }

    /// Verify a receipt against a Python payload snapshot.
    ///
    /// The Rust kernel copies `action_id` and `payload` into local stack
    /// frames before HMAC evaluation, preventing a concurrent Python thread
    /// from mutating the bytes object mid-execution.
    fn intercept_and_authorize(
        &mut self,
        action_id: &Bound<'_, PyBytes>,
        payload: &Bound<'_, PyBytes>,
        receipt: &Bound<'_, PyBytes>,
    ) -> PyResult<()> {
        let action_id = action_id.as_bytes();
        let payload = payload.as_bytes();
        let receipt_bytes = receipt.as_bytes();

        if action_id.len() > MAX_ACTION_ID_SIZE {
            return Err(relu_err_to_py(ReluError::ActionIdOverflow));
        }
        if payload.len() > MAX_TOTAL_PAYLOAD_SIZE {
            return Err(relu_err_to_py(ReluError::PayloadOverflow));
        }
        if receipt_bytes.len() != RECEIPT_SERIALIZED_SIZE {
            return Err(relu_err_to_py(ReluError::InvalidReceipt));
        }

        let receipt = AuthorizationReceipt::from_bytes(receipt_bytes).map_err(relu_err_to_py)?;
        self.interceptor
            .intercept_and_authorize(action_id, payload, &receipt)
            .map_err(relu_err_to_py)
    }
}

/// Python module registration.
#[pymodule]
fn relulayer_py(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<ReluBoundary>()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use pyo3::types::PyBytes;

    #[test]
    fn py_boundary_round_trip() {
        pyo3::prepare_freethreaded_python();
        Python::with_gil(|py| {
            let key = PyBytes::new(py, &[0x07u8; 32]);
            let mut boundary = ReluBoundary::new(&key).unwrap();

            let nonce = PyBytes::new(py, &[1u8; 12]);
            let action = PyBytes::new(py, b"read");
            let payload = PyBytes::new(py, b"hello");

            let receipt = boundary
                .issue_receipt(py, &nonce, 0, 1, &action, &payload)
                .unwrap();
            assert_eq!(receipt.len().unwrap(), RECEIPT_SERIALIZED_SIZE);

            boundary
                .intercept_and_authorize(&action, &payload, &receipt)
                .unwrap();
        });
    }
}
