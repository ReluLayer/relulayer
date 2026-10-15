//! Size limits for the boundary interceptor.
//!
//! The kernel never performs a dynamic allocation. All buffers are either
//! function-local fixed-size arrays or caller-provided slices. Large payloads are
//! handled by streaming HMAC over fixed-size stack chunks.

/// Maximum length of an action identifier in bytes.
pub const MAX_ACTION_ID_SIZE: usize = 64;

/// Size of a single stack-resident payload chunk used for streaming HMAC.
pub const MAX_STACK_PAYLOAD_CHUNK: usize = 4096;

/// Fast-path threshold: payloads at or below this size use a dedicated
/// sub-microsecond stack snapshot to preserve ~0.199 µs latency for short
/// tool calls.
pub const FAST_PATH_PAYLOAD_SIZE: usize = 512;

/// Maximum total payload size the kernel will accept.
///
/// This is a policy limit, not a stack allocation limit. Payloads up to this
/// size are processed in `MAX_STACK_PAYLOAD_CHUNK` windows.
pub const MAX_TOTAL_PAYLOAD_SIZE: usize = 65_536; // 64 KiB

/// Length of the HMAC-SHA256 tag in bytes.
pub const HMAC_SIZE: usize = 32;

/// Length of the anti-replay nonce in bytes.
pub const NONCE_SIZE: usize = 12;

/// Serialized receipt length: nonce(12) + timestamp(8) + counter(8) + tag(32).
pub const RECEIPT_SERIALIZED_SIZE: usize = NONCE_SIZE + 8 + 8 + HMAC_SIZE; // 60

/// Default replay-window size (number of recent nonces tracked).
pub const REPLAY_WINDOW_SIZE: usize = 1024;

/// Checks whether a payload length is acceptable.
#[inline]
pub const fn payload_size_ok(len: usize) -> bool {
    len <= MAX_TOTAL_PAYLOAD_SIZE
}

/// Checks whether an action-id length is acceptable.
#[inline]
pub const fn action_id_size_ok(len: usize) -> bool {
    len <= MAX_ACTION_ID_SIZE
}
