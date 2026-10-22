//! ReluLayer Security Micro-Kernel
//!
//! A zero-heap, `#![no_std]` boundary interceptor that authorizes AI agent action
//! requests using replay-resistant HMAC-SHA256 over a snapshot-and-seal view of the
//! caller payload.
//!
//! # Hardening principles
//!
//! 1. **Zero heap**: every allocation is on the caller's stack; chunks are fixed size.
//! 2. **Streaming**: payloads larger than the stack chunk are processed in 4 KiB windows.
//! 3. **Replay resistance**: each receipt binds a monotonic counter, a timestamp, and a nonce.
//! 4. **TOCTOU mitigation**: the kernel copies (snapshots) the caller buffer before HMAC begins.
//! 5. **Hardware crypto**: auto-selected Intel SHA-NI / ARMv8 Crypto with a software fallback.

// `#![no_std]` is active when the `std` feature is disabled (production
// builds). When the `std` feature is enabled (default for host tests and
// tooling), the crate links to the standard library. The library code itself
// uses only `core` APIs and remains `#![no_std]`-capable.
#![cfg_attr(not(feature = "std"), no_std)]
#![warn(clippy::pedantic)]

#[cfg(not(feature = "std"))]
use core::panic::PanicInfo;

#[cfg(not(feature = "std"))]
#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    loop {}
}

pub mod boundary;
pub mod crypto;
pub mod limits;
pub mod sha;

#[cfg(kani)]
pub mod kani_proofs;

/// Errors returned by the boundary interceptor.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(C)]
pub enum ReluError {
    /// Input pointer was null or misaligned.
    InvalidPointer = 1,
    /// Action ID exceeds `MAX_ACTION_ID_SIZE`.
    ActionIdOverflow = 2,
    /// Payload exceeds `MAX_TOTAL_PAYLOAD_SIZE`.
    PayloadOverflow = 3,
    /// Authorization receipt is malformed or has incorrect length.
    InvalidReceipt = 4,
    /// Key length is not 32 bytes.
    InvalidKeyLength = 5,
    /// HMAC verification failed (receipt does not match message).
    AuthenticationFailure = 6,
    /// Receipt counter is not strictly greater than the last accepted counter.
    ReplayCounterViolation = 7,
    /// Receipt nonce was seen inside the replay window.
    ReplayNonceViolation = 8,
    /// Hardware SHA-256 is unavailable but was explicitly required.
    HardwareShaUnavailable = 9,
}

impl ReluError {
    /// C-compatible sentinel: zero means success for FFI return codes.
    pub const fn ffi_code(self) -> i32 {
        -(self as i32)
    }
}

/// Opaque result type used by the C ABI.
pub type ReluResult<T> = Result<T, ReluError>;
