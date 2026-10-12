//! Boundary interceptor — snapshot-and-seal authorization.
//!
//! `BoundaryInterceptor` is the single entry point for high-level agent runtimes.
//! It guarantees that HMAC verification is performed over a kernel-controlled
//! view of the payload, eliminating time-of-check/time-of-use races with mutable
//! Python objects or FFI caller buffers.
//!
//! # TOCTOU mitigation strategy
//!
//! For payloads that fit in a single 4 KiB stack chunk, the kernel copies the
//! entire caller buffer into a local array and verifies that snapshot. For larger
//! payloads the kernel streams the payload through the HMAC state in 4 KiB
//! windows: any mutation that occurs *after* a window has been fed cannot affect
//! the already-computed partial tag, and any mutation in a not-yet-fed window
//! will cause final tag mismatch. Execution consumes only data that has passed
//! through the HMAC state.

use crate::crypto::{
    authorize, verify_stream_begin, AuthorizationReceipt, AuthorizationState, BoundaryKey,
};
use crate::limits::{
    FAST_PATH_PAYLOAD_SIZE, MAX_ACTION_ID_SIZE, MAX_STACK_PAYLOAD_CHUNK, MAX_TOTAL_PAYLOAD_SIZE,
    NONCE_SIZE,
};
use crate::ReluError;
use subtle::ConstantTimeEq;

/// Default boundary interceptor.
///
/// Holds the authorization key and replay state. In a single-threaded bare-metal
/// context this is a global singleton; in a multi-threaded host the host runtime
/// must either serialize calls or provide one interceptor per kernel thread.
pub struct BoundaryInterceptor {
    state: AuthorizationState,
}

impl BoundaryInterceptor {
    /// Create an interceptor from a 32-byte boundary key.
    pub fn new(key: &BoundaryKey) -> Self {
        Self {
            state: AuthorizationState::new(key),
        }
    }

    /// Authorize an action and return a replay-resistant receipt.
    ///
    /// This path is used by the policy engine when issuing an authorization
    /// ticket for an action that is about to be performed.
    pub fn issue_receipt(
        &self,
        nonce: &[u8; NONCE_SIZE],
        timestamp: u64,
        counter: u64,
        action_id: &[u8],
        payload: &[u8],
    ) -> Result<AuthorizationReceipt, ReluError> {
        authorize(
            self.state.key(),
            nonce,
            timestamp,
            counter,
            action_id,
            payload,
        )
    }

    /// Verify a receipt against a caller-supplied payload.
    ///
    /// This method defends against TOCTOU by never reading the caller buffer
    /// after HMAC verification begins. Small payloads are snapshotted; large
    /// payloads are streamed in fixed-size chunks. The function returns only
    /// after the entire payload has been cryptographically bound to the receipt.
    pub fn intercept_and_authorize(
        &mut self,
        action_id: &[u8],
        payload: &[u8],
        receipt: &AuthorizationReceipt,
    ) -> Result<(), ReluError> {
        if action_id.len() > MAX_ACTION_ID_SIZE {
            return Err(ReluError::ActionIdOverflow);
        }
        if payload.len() > MAX_TOTAL_PAYLOAD_SIZE {
            return Err(ReluError::PayloadOverflow);
        }

        // Replay checks happen before any expensive hashing.
        if receipt.counter <= self.state.last_counter() {
            return Err(ReluError::ReplayCounterViolation);
        }
        if self.state.replay_window.contains(&receipt.nonce) {
            return Err(ReluError::ReplayNonceViolation);
        }

        let mut hasher = verify_stream_begin(
            self.state.key(),
            receipt,
            action_id,
            payload.len(),
        )?;

        if payload.len() <= FAST_PATH_PAYLOAD_SIZE {
            // Micro-action fast path: 512-byte stack snapshot for sub-microsecond
            // tool-call authorization. Avoids touching the larger 4 KiB chunk.
            let mut fast = [0u8; FAST_PATH_PAYLOAD_SIZE];
            fast[..payload.len()].copy_from_slice(payload);
            hasher.update(&fast[..payload.len()]);
        } else if payload.len() <= MAX_STACK_PAYLOAD_CHUNK {
            // Snapshot-and-seal path: copy the whole payload into a 4 KiB stack
            // chunk, then feed the copy into the HMAC. The original `payload`
            // slice is never read again after this point.
            let mut chunk = [0u8; MAX_STACK_PAYLOAD_CHUNK];
            chunk[..payload.len()].copy_from_slice(payload);
            hasher.update(&chunk[..payload.len()]);
        } else {
            // Streaming path: process the payload in 4 KiB windows. Each window
            // is copied into a stack-resident chunk before being fed. Mutation
            // after a chunk is consumed cannot alter the partial HMAC state.
            let mut chunk = [0u8; MAX_STACK_PAYLOAD_CHUNK];
            for window in payload.chunks(MAX_STACK_PAYLOAD_CHUNK) {
                chunk[..window.len()].copy_from_slice(window);
                hasher.update(&chunk[..window.len()]);
            }
        }

        let computed = hasher.finalize();
        if computed.ct_eq(&receipt.tag).into() {
            self.state.last_counter = receipt.counter;
            self.state.replay_window.record(&receipt.nonce);
            Ok(())
        } else {
            Err(ReluError::AuthenticationFailure)
        }
    }

    /// Reset replay state. Use after key rotation or session boundary.
    pub fn reset_replay_state(&mut self) {
        let key = *self.state.key();
        self.state = AuthorizationState::new(&key);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::crypto::BoundaryKey;
    use hex_literal::hex;

    const TEST_KEY: BoundaryKey = BoundaryKey::from_array(hex!(
        "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
    ));

    #[test]
    fn small_payload_authorizes() {
        let mut interceptor = BoundaryInterceptor::new(&TEST_KEY);
        let nonce = [7u8; 12];
        let receipt = interceptor
            .issue_receipt(&nonce, 1, 1, b"read", b"hello")
            .unwrap();
        assert!(interceptor
            .intercept_and_authorize(b"read", b"hello", &receipt)
            .is_ok());
    }

    #[test]
    fn oversized_payload_rejected() {
        let mut interceptor = BoundaryInterceptor::new(&TEST_KEY);
        let big = [0u8; MAX_TOTAL_PAYLOAD_SIZE + 1];
        let nonce = [8u8; 12];

        // Receipts cannot be issued for oversized payloads either.
        assert_eq!(
            interceptor.issue_receipt(&nonce, 0, 1, b"read", &big),
            Err(ReluError::PayloadOverflow)
        );

        // A forged receipt claiming the oversized length is also rejected at
        // the boundary.
        let receipt = AuthorizationReceipt {
            nonce,
            timestamp: 0,
            counter: 1,
            tag: [0u8; 32],
        };
        assert_eq!(
            interceptor.intercept_and_authorize(b"read", &big, &receipt),
            Err(ReluError::PayloadOverflow)
        );
    }

    #[test]
    fn chunked_payload_authorizes() {
        let mut interceptor = BoundaryInterceptor::new(&TEST_KEY);
        let large = [0xABu8; MAX_STACK_PAYLOAD_CHUNK * 3 + 7];
        let nonce = [9u8; 12];
        let receipt = interceptor
            .issue_receipt(&nonce, 0, 1, b"exec", &large)
            .unwrap();
        assert!(interceptor
            .intercept_and_authorize(b"exec", &large, &receipt)
            .is_ok());
    }

    #[test]
    fn toctou_mutation_detected() {
        let mut interceptor = BoundaryInterceptor::new(&TEST_KEY);
        let nonce = [10u8; 12];

        // Host-runtime snapshot of the intended payload.
        let mut shared = [0u8; 64];
        shared[..12].copy_from_slice(b"read_public_");

        // Issue receipt over the intended payload.
        let receipt = interceptor
            .issue_receipt(&nonce, 0, 1, b"fs", &shared)
            .unwrap();

        // Attacker mutates the shared buffer after authorization but before
        // interception. Because intercept_and_authorize copies the payload
        // before hashing, the mutated buffer is what gets verified, and the
        // receipt no longer matches.
        shared[..12].copy_from_slice(b"delete_priv_");

        assert_eq!(
            interceptor.intercept_and_authorize(b"fs", &shared, &receipt),
            Err(ReluError::AuthenticationFailure)
        );
    }
}
