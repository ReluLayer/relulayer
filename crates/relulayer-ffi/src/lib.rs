//! C-ABI opaque-handle wrapper for the ReluLayer boundary interceptor.
//!
//! This crate exposes a stateful, replay-resistant authorization boundary to C,
//! Python (via PyO3), and other foreign runtimes. The persistent
//! `ReluInterceptor` handle encapsulates the boundary key and replay window;
//! it must be created with `relulayer_interceptor_create` and destroyed with
//! `relulayer_interceptor_destroy`.
//!
//! # Lifecycle
//!
//! ```c
//! ReluInterceptor *handle = NULL;
//! int32_t rc = relulayer_interceptor_create(key, 32, &handle);
//! if (rc != 0) { ... }
//! rc = relulayer_intercept_and_authorize(handle, action, action_len,
//!                                         payload, payload_len,
//!                                         expected_receipt, out_receipt);
//! relulayer_interceptor_destroy(handle);
//! ```
//!
//! # Safety
//!
//! - All pointer arguments must be valid for their respective lengths unless
//!   explicitly noted as optional.
//! - A `ReluInterceptor` handle is not thread-safe; concurrent use from multiple
//!   threads is undefined behavior.
//! - `relulayer_interceptor_destroy` must be called exactly once per handle.

use core::slice;
use relulayer_security::boundary::BoundaryInterceptor;
use relulayer_security::crypto::{authorize, AuthorizationReceipt, BoundaryKey};
use relulayer_security::limits::{
    MAX_ACTION_ID_SIZE, MAX_TOTAL_PAYLOAD_SIZE, NONCE_SIZE, RECEIPT_SERIALIZED_SIZE,
};
use relulayer_security::ReluError;

/// Opaque handle type. The layout is intentionally hidden from C callers.
#[repr(C)]
pub struct ReluInterceptor {
    interceptor: BoundaryInterceptor,
}

/// Create a new `ReluInterceptor` from a 32-byte boundary key.
///
/// On success, writes a non-NULL handle to `*out_handle` and returns `0`.
/// On failure, `*out_handle` is unchanged and a negative FFI error code is
/// returned. The caller must eventually destroy the handle with
/// `relulayer_interceptor_destroy`.
#[no_mangle]
pub unsafe extern "C" fn relulayer_interceptor_create(
    key_ptr: *const u8,
    key_len: usize,
    out_handle: *mut *mut ReluInterceptor,
) -> i32 {
    if out_handle.is_null() {
        return ReluError::InvalidPointer.ffi_code();
    }
    if key_ptr.is_null() {
        return ReluError::InvalidPointer.ffi_code();
    }
    if key_len != 32 {
        return ReluError::InvalidKeyLength.ffi_code();
    }

    let key_slice = slice::from_raw_parts(key_ptr, key_len);
    let key = match BoundaryKey::from_bytes(key_slice) {
        Ok(k) => k,
        Err(e) => return e.ffi_code(),
    };

    let handle = Box::into_raw(Box::new(ReluInterceptor {
        interceptor: BoundaryInterceptor::new(&key),
    }));
    core::ptr::write(out_handle, handle);
    0
}

/// Destroy a `ReluInterceptor` handle.
///
/// No-op if `handle` is NULL. After this call the pointer must not be used
/// again.
#[no_mangle]
pub unsafe extern "C" fn relulayer_interceptor_destroy(handle: *mut ReluInterceptor) {
    if !handle.is_null() {
        drop(Box::from_raw(handle));
    }
}

/// Verify an action/payload against an expected replay-resistant receipt using
/// a persistent interceptor handle.
///
/// # Parameters
/// - `handle`: interceptor created by `relulayer_interceptor_create`.
/// - `action_ptr`, `action_len`: action identifier.
/// - `payload_ptr`, `payload_len`: payload to authorize.
/// - `expected_receipt_ptr`: 60-byte replay-resistant receipt to verify.
/// - `out_receipt_ptr`: optional 60-byte output buffer. On success, a copy of
///   the verified receipt is written here; on failure the buffer is untouched.
///   May be NULL if the caller does not need a guaranteed-immutable copy.
///
/// # Returns
/// - `0` on success.
/// - Negative FFI error code on failure (see `ReluError::ffi_code`).
#[no_mangle]
pub unsafe extern "C" fn relulayer_intercept_and_authorize(
    handle: *mut ReluInterceptor,
    action_ptr: *const u8,
    action_len: usize,
    payload_ptr: *const u8,
    payload_len: usize,
    expected_receipt_ptr: *const u8,
    out_receipt_ptr: *mut u8,
) -> i32 {
    if handle.is_null()
        || action_ptr.is_null()
        || payload_ptr.is_null()
        || expected_receipt_ptr.is_null()
    {
        return ReluError::InvalidPointer.ffi_code();
    }
    if action_len > MAX_ACTION_ID_SIZE {
        return ReluError::ActionIdOverflow.ffi_code();
    }
    if payload_len > MAX_TOTAL_PAYLOAD_SIZE {
        return ReluError::PayloadOverflow.ffi_code();
    }

    let action_id = slice::from_raw_parts(action_ptr, action_len);
    let payload = slice::from_raw_parts(payload_ptr, payload_len);
    let receipt_bytes = slice::from_raw_parts(expected_receipt_ptr, RECEIPT_SERIALIZED_SIZE);

    let receipt = match AuthorizationReceipt::from_bytes(receipt_bytes) {
        Ok(r) => r,
        Err(e) => return e.ffi_code(),
    };

    let interceptor = &mut (*handle).interceptor;
    match interceptor.intercept_and_authorize(action_id, payload, &receipt) {
        Ok(()) => {
            if !out_receipt_ptr.is_null() {
                core::ptr::copy_nonoverlapping(
                    receipt_bytes.as_ptr(),
                    out_receipt_ptr,
                    RECEIPT_SERIALIZED_SIZE,
                );
            }
            0
        }
        Err(e) => e.ffi_code(),
    }
}

/// Stateless legacy verification helper.
///
/// **This function intentionally lacks replay resistance.** It creates a fresh
/// interceptor for every call, so monotonic counters and nonce windows are not
/// persisted. It is provided for backward compatibility with callers that
/// manage replay protection themselves and for direct HMAC verification of a
/// single receipt.
///
/// # Parameters
/// - `key_ptr`, `key_len`: 32-byte boundary key.
/// - `action_ptr`, `action_len`: action identifier.
/// - `payload_ptr`, `payload_len`: payload to authorize.
/// - `expected_receipt_ptr`: 60-byte replay-resistant receipt to verify.
///
/// # Returns
/// - `0` on success.
/// - Negative FFI error code on failure.
#[no_mangle]
pub unsafe extern "C" fn relulayer_verify_stateless(
    key_ptr: *const u8,
    key_len: usize,
    action_ptr: *const u8,
    action_len: usize,
    payload_ptr: *const u8,
    payload_len: usize,
    expected_receipt_ptr: *const u8,
) -> i32 {
    if key_ptr.is_null()
        || action_ptr.is_null()
        || payload_ptr.is_null()
        || expected_receipt_ptr.is_null()
    {
        return ReluError::InvalidPointer.ffi_code();
    }
    if action_len > MAX_ACTION_ID_SIZE {
        return ReluError::ActionIdOverflow.ffi_code();
    }
    if payload_len > MAX_TOTAL_PAYLOAD_SIZE {
        return ReluError::PayloadOverflow.ffi_code();
    }
    if key_len != 32 {
        return ReluError::InvalidKeyLength.ffi_code();
    }

    let key_slice = slice::from_raw_parts(key_ptr, key_len);
    let key = match BoundaryKey::from_bytes(key_slice) {
        Ok(k) => k,
        Err(e) => return e.ffi_code(),
    };

    let action_id = slice::from_raw_parts(action_ptr, action_len);
    let payload = slice::from_raw_parts(payload_ptr, payload_len);
    let receipt_bytes = slice::from_raw_parts(expected_receipt_ptr, RECEIPT_SERIALIZED_SIZE);
    let receipt = match AuthorizationReceipt::from_bytes(receipt_bytes) {
        Ok(r) => r,
        Err(e) => return e.ffi_code(),
    };

    // Stateless path: create a one-shot interceptor. Replay checks are still
    // performed relative to the fresh state (counter > 0, nonce not in empty
    // window), but no state persists across calls.
    let mut interceptor = BoundaryInterceptor::new(&key);
    match interceptor.intercept_and_authorize(action_id, payload, &receipt) {
        Ok(()) => 0,
        Err(e) => e.ffi_code(),
    }
}

/// Issue a replay-resistant authorization receipt for the given action/payload.
///
/// This is a convenience C ABI for the policy engine that creates tickets. The
/// nonce, timestamp, and counter must be supplied by the caller; the counter
/// must be strictly monotonic within the authorization scope.
///
/// # Parameters
/// - `key_ptr`, `key_len`: 32-byte boundary key.
/// - `nonce_ptr`: 12-byte nonce.
/// - `timestamp`: advisory timestamp.
/// - `counter`: strictly monotonic counter.
/// - `action_ptr`, `action_len`: action identifier.
/// - `payload_ptr`, `payload_len`: payload.
/// - `out_receipt_ptr`: output buffer of at least 60 bytes.
///
/// # Returns
/// - `0` on success.
/// - Negative FFI error code on failure.
#[no_mangle]
pub unsafe extern "C" fn relulayer_issue_receipt(
    key_ptr: *const u8,
    key_len: usize,
    nonce_ptr: *const u8,
    timestamp: u64,
    counter: u64,
    action_ptr: *const u8,
    action_len: usize,
    payload_ptr: *const u8,
    payload_len: usize,
    out_receipt_ptr: *mut u8,
) -> i32 {
    if key_ptr.is_null()
        || nonce_ptr.is_null()
        || action_ptr.is_null()
        || payload_ptr.is_null()
        || out_receipt_ptr.is_null()
    {
        return ReluError::InvalidPointer.ffi_code();
    }
    if key_len != 32 {
        return ReluError::InvalidKeyLength.ffi_code();
    }
    if action_len > MAX_ACTION_ID_SIZE {
        return ReluError::ActionIdOverflow.ffi_code();
    }
    if payload_len > MAX_TOTAL_PAYLOAD_SIZE {
        return ReluError::PayloadOverflow.ffi_code();
    }

    let key_slice = slice::from_raw_parts(key_ptr, key_len);
    let key = match BoundaryKey::from_bytes(key_slice) {
        Ok(k) => k,
        Err(e) => return e.ffi_code(),
    };

    let nonce = slice::from_raw_parts(nonce_ptr, NONCE_SIZE);
    let mut nonce_arr = [0u8; NONCE_SIZE];
    nonce_arr.copy_from_slice(nonce);

    let action_id = slice::from_raw_parts(action_ptr, action_len);
    let payload = slice::from_raw_parts(payload_ptr, payload_len);

    match authorize(&key, &nonce_arr, timestamp, counter, action_id, payload) {
        Ok(receipt) => {
            let bytes = receipt.to_bytes();
            core::ptr::copy_nonoverlapping(bytes.as_ptr(), out_receipt_ptr, bytes.len());
            0
        }
        Err(e) => e.ffi_code(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use relulayer_security::crypto::BoundaryKey;

    const TEST_KEY: BoundaryKey = BoundaryKey::from_array([
        0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D,
        0x0E, 0x0F, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B,
        0x1C, 0x1D, 0x1E, 0x1F,
    ]);

    #[test]
    fn handle_create_and_destroy() {
        unsafe {
            let mut handle: *mut ReluInterceptor = core::ptr::null_mut();
            let rc = relulayer_interceptor_create(TEST_KEY.as_bytes().as_ptr(), 32, &mut handle);
            assert_eq!(rc, 0);
            assert!(!handle.is_null());
            relulayer_interceptor_destroy(handle);
        }
    }

    #[test]
    fn stateful_intercept_rejects_replay() {
        unsafe {
            let mut handle: *mut ReluInterceptor = core::ptr::null_mut();
            let rc = relulayer_interceptor_create(TEST_KEY.as_bytes().as_ptr(), 32, &mut handle);
            assert_eq!(rc, 0);

            let nonce = [7u8; 12];
            let mut receipt = [0u8; RECEIPT_SERIALIZED_SIZE];
            let rc = relulayer_issue_receipt(
                TEST_KEY.as_bytes().as_ptr(),
                32,
                nonce.as_ptr(),
                0,
                1,
                b"read".as_ptr(),
                4,
                b"hello".as_ptr(),
                5,
                receipt.as_mut_ptr(),
            );
            assert_eq!(rc, 0);

            let rc = relulayer_intercept_and_authorize(
                handle,
                b"read".as_ptr(),
                4,
                b"hello".as_ptr(),
                5,
                receipt.as_ptr(),
                core::ptr::null_mut(),
            );
            assert_eq!(rc, 0);

            // Replay of the same receipt must be rejected.
            let rc = relulayer_intercept_and_authorize(
                handle,
                b"read".as_ptr(),
                4,
                b"hello".as_ptr(),
                5,
                receipt.as_ptr(),
                core::ptr::null_mut(),
            );
            assert_eq!(rc, ReluError::ReplayCounterViolation.ffi_code());

            relulayer_interceptor_destroy(handle);
        }
    }

    #[test]
    fn stateless_verify_lacks_replay_persistence() {
        unsafe {
            let nonce = [8u8; 12];
            let mut receipt = [0u8; RECEIPT_SERIALIZED_SIZE];
            let rc = relulayer_issue_receipt(
                TEST_KEY.as_bytes().as_ptr(),
                32,
                nonce.as_ptr(),
                0,
                1,
                b"read".as_ptr(),
                4,
                b"hello".as_ptr(),
                5,
                receipt.as_mut_ptr(),
            );
            assert_eq!(rc, 0);

            let rc = relulayer_verify_stateless(
                TEST_KEY.as_bytes().as_ptr(),
                32,
                b"read".as_ptr(),
                4,
                b"hello".as_ptr(),
                5,
                receipt.as_ptr(),
            );
            assert_eq!(rc, 0);

            // Stateless verification accepts the same receipt again because no
            // state persists between calls.
            let rc = relulayer_verify_stateless(
                TEST_KEY.as_bytes().as_ptr(),
                32,
                b"read".as_ptr(),
                4,
                b"hello".as_ptr(),
                5,
                receipt.as_ptr(),
            );
            assert_eq!(rc, 0);
        }
    }
}
