//! Cryptographic authorization primitives.
//!
//! Provides replay-resistant HMAC-SHA256 receipts. Each receipt binds:
//!
//!   nonce (12 bytes) || timestamp (8 bytes, LE) || counter (8 bytes, LE) || tag (32 bytes)
//!
//! The HMAC input covers the metadata first, then the action identifier and
//! payload lengths, then the payload itself:
//!
//!   nonce || timestamp || counter || action_id_len || action_id || payload_len || payload
//!
//! This construction prevents length-extension ambiguity and binds both the
//! action identity and the exact payload bytes.

use crate::limits::{
    HMAC_SIZE, MAX_ACTION_ID_SIZE, MAX_TOTAL_PAYLOAD_SIZE, NONCE_SIZE, REPLAY_WINDOW_SIZE,
};
use crate::ReluError;
use core::convert::TryInto;
use hmac::{Hmac, Mac};
use sha2::Sha256;
use subtle::ConstantTimeEq;

type HmacSha256 = Hmac<Sha256>;

/// Opaque 32-byte boundary authorization key.
#[derive(Clone, Copy)]
#[repr(C)]
pub struct BoundaryKey {
    pub(crate) bytes: [u8; 32],
}

impl BoundaryKey {
    /// Create a key from a fixed 32-byte array.
    #[must_use]
    pub const fn from_array(bytes: [u8; 32]) -> Self {
        Self { bytes }
    }

    /// Create a key from a 32-byte slice.
    ///
    /// Returns `ReluError::InvalidKeyLength` for any other length.
    pub fn from_bytes(key: &[u8]) -> Result<Self, ReluError> {
        if key.len() != 32 {
            return Err(ReluError::InvalidKeyLength);
        }
        let mut bytes = [0u8; 32];
        bytes.copy_from_slice(key);
        Ok(Self { bytes })
    }

    /// Expose the raw key bytes for hashing.
    #[inline]
    pub const fn as_bytes(&self) -> &[u8; 32] {
        &self.bytes
    }
}

/// A replay-resistant authorization receipt.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(C)]
pub struct AuthorizationReceipt {
    pub nonce: [u8; NONCE_SIZE],
    pub timestamp: u64,
    pub counter: u64,
    pub tag: [u8; HMAC_SIZE],
}

impl AuthorizationReceipt {
    /// Serialize to a 60-byte buffer.
    pub fn to_bytes(&self) -> [u8; 12 + 8 + 8 + 32] {
        let mut out = [0u8; 12 + 8 + 8 + 32];
        out[0..12].copy_from_slice(&self.nonce);
        out[12..20].copy_from_slice(&self.timestamp.to_le_bytes());
        out[20..28].copy_from_slice(&self.counter.to_le_bytes());
        out[28..60].copy_from_slice(&self.tag);
        out
    }

    /// Deserialize from a slice.
    ///
    /// Returns `ReluError::InvalidReceipt` if the slice is not exactly 60 bytes.
    pub fn from_bytes(bytes: &[u8]) -> Result<Self, ReluError> {
        if bytes.len() != 12 + 8 + 8 + 32 {
            return Err(ReluError::InvalidReceipt);
        }
        let mut nonce = [0u8; NONCE_SIZE];
        nonce.copy_from_slice(&bytes[0..12]);
        let timestamp = u64::from_le_bytes(bytes[12..20].try_into().unwrap());
        let counter = u64::from_le_bytes(bytes[20..28].try_into().unwrap());
        let mut tag = [0u8; HMAC_SIZE];
        tag.copy_from_slice(&bytes[28..60]);
        Ok(Self {
            nonce,
            timestamp,
            counter,
            tag,
        })
    }
}

/// Sliding window used to reject duplicate nonces.
///
/// The window stores up to `REPLAY_WINDOW_SIZE` recently accepted nonces.
/// Because `#![no_std]` avoids heap allocation, the window is a fixed-size
/// ring buffer. A nonce is considered "fresh" if it is not present in the
/// window. Collisions are impossible in practice because nonces are 96-bit
/// random values.
pub struct ReplayWindow {
    nonces: [[u8; NONCE_SIZE]; REPLAY_WINDOW_SIZE],
    head: usize,
    len: usize,
}

impl ReplayWindow {
    /// Create an empty replay window.
    pub const fn new() -> Self {
        Self {
            nonces: [[0u8; NONCE_SIZE]; REPLAY_WINDOW_SIZE],
            head: 0,
            len: 0,
        }
    }

    /// Check whether `nonce` has already been accepted.
    pub fn contains(&self, nonce: &[u8; NONCE_SIZE]) -> bool {
        let count = self.len.min(REPLAY_WINDOW_SIZE);
        for i in 0..count {
            let idx = (self.head + REPLAY_WINDOW_SIZE - i - 1) % REPLAY_WINDOW_SIZE;
            if self.nonces[idx].ct_eq(nonce).into() {
                return true;
            }
        }
        false
    }

    /// Record a newly accepted nonce, evicting the oldest entry if necessary.
    pub fn record(&mut self, nonce: &[u8; NONCE_SIZE]) {
        self.nonces[self.head] = *nonce;
        self.head = (self.head + 1) % REPLAY_WINDOW_SIZE;
        if self.len < REPLAY_WINDOW_SIZE {
            self.len += 1;
        }
    }

    /// Clear the window. Useful on key rotation or session reset.
    pub fn clear(&mut self) {
        self.head = 0;
        self.len = 0;
        self.nonces = [[0u8; NONCE_SIZE]; REPLAY_WINDOW_SIZE];
    }
}

impl Default for ReplayWindow {
    fn default() -> Self {
        Self::new()
    }
}

/// State required to enforce replay resistance.
pub struct AuthorizationState {
    key: BoundaryKey,
    pub(crate) last_counter: u64,
    pub(crate) replay_window: ReplayWindow,
}

impl AuthorizationState {
    /// Initialize authorization state with a 32-byte key.
    pub fn new(key: &BoundaryKey) -> Self {
        Self {
            key: *key,
            last_counter: 0,
            replay_window: ReplayWindow::new(),
        }
    }

    /// Returns the last accepted monotonic counter.
    pub const fn last_counter(&self) -> u64 {
        self.last_counter
    }

    /// Returns a reference to the boundary key.
    pub const fn key(&self) -> &BoundaryKey {
        &self.key
    }
}

/// Streaming HMAC builder for the canonical message format.
///
/// Used internally by both `authorize` (full-buffer) and the streaming
/// verification path in `boundary.rs`.
pub struct MessageHasher {
    mac: HmacSha256,
}

impl MessageHasher {
    /// Begin hashing a message. `payload_len` is the expected total payload
    /// size; the caller must feed exactly this many bytes before finalization.
    pub fn begin(
        key: &BoundaryKey,
        nonce: &[u8; NONCE_SIZE],
        timestamp: u64,
        counter: u64,
        action_id: &[u8],
        payload_len: usize,
    ) -> Result<Self, ReluError> {
        if action_id.len() > MAX_ACTION_ID_SIZE {
            return Err(ReluError::ActionIdOverflow);
        }
        if payload_len > MAX_TOTAL_PAYLOAD_SIZE {
            return Err(ReluError::PayloadOverflow);
        }

        let mut mac = HmacSha256::new_from_slice(key.as_bytes())
            .map_err(|_| ReluError::AuthenticationFailure)?;

        mac.update(nonce);
        mac.update(&timestamp.to_le_bytes());
        mac.update(&counter.to_le_bytes());
        mac.update(&(action_id.len() as u64).to_le_bytes());
        mac.update(action_id);
        mac.update(&(payload_len as u64).to_le_bytes());

        Ok(Self { mac })
    }

    /// Feed a payload chunk.
    pub fn update(&mut self, chunk: &[u8]) {
        self.mac.update(chunk);
    }

    /// Finalize and return the HMAC tag.
    pub fn finalize(self) -> [u8; HMAC_SIZE] {
        self.mac.finalize().into_bytes().into()
    }
}

/// Compute a replay-resistant authorization receipt over a full payload.
///
/// `nonce` must be generated by a cryptographically secure random source in the
/// host runtime. `counter` must be strictly monotonic for each authorization
/// scope. `timestamp` is advisory and helps detect clock-skew attacks by the
/// host.
pub fn authorize(
    key: &BoundaryKey,
    nonce: &[u8; NONCE_SIZE],
    timestamp: u64,
    counter: u64,
    action_id: &[u8],
    payload: &[u8],
) -> Result<AuthorizationReceipt, ReluError> {
    let mut hasher = MessageHasher::begin(key, nonce, timestamp, counter, action_id, payload.len())?;
    hasher.update(payload);
    let tag = hasher.finalize();

    Ok(AuthorizationReceipt {
        nonce: *nonce,
        timestamp,
        counter,
        tag,
    })
}

/// Verify an authorization receipt and enforce replay resistance.
///
/// On success, updates `state.last_counter` and records the nonce in the replay
/// window. The comparison of the recomputed tag is constant-time.
pub fn verify(
    state: &mut AuthorizationState,
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

    // Counter must be strictly monotonic. This prevents infinite replay of old
    // receipts even if the nonce generation is compromised.
    if receipt.counter <= state.last_counter {
        return Err(ReluError::ReplayCounterViolation);
    }

    // Nonce must not have been observed in the recent window.
    if state.replay_window.contains(&receipt.nonce) {
        return Err(ReluError::ReplayNonceViolation);
    }

    let mut hasher = MessageHasher::begin(
        state.key(),
        &receipt.nonce,
        receipt.timestamp,
        receipt.counter,
        action_id,
        payload.len(),
    )?;
    hasher.update(payload);
    let computed = hasher.finalize();

    if computed.ct_eq(&receipt.tag).into() {
        state.last_counter = receipt.counter;
        state.replay_window.record(&receipt.nonce);
        Ok(())
    } else {
        Err(ReluError::AuthenticationFailure)
    }
}

/// Streaming verification entry point.
///
/// The caller feeds the payload in fixed-size chunks; the returned tag can be
/// compared against the receipt. Replay checks (counter/nonce) are the
/// responsibility of the caller and are enforced by `verify_stream`.
pub fn verify_stream_begin(
    key: &BoundaryKey,
    receipt: &AuthorizationReceipt,
    action_id: &[u8],
    payload_len: usize,
) -> Result<MessageHasher, ReluError> {
    MessageHasher::begin(
        key,
        &receipt.nonce,
        receipt.timestamp,
        receipt.counter,
        action_id,
        payload_len,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use hex_literal::hex;

    const TEST_KEY: BoundaryKey = BoundaryKey::from_array(hex!(
        "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
    ));

    #[test]
    fn receipt_round_trip() {
        let nonce = [1u8; NONCE_SIZE];
        let receipt = authorize(&TEST_KEY, &nonce, 0x1234_5678, 1, b"read", b"{}").unwrap();
        let bytes = receipt.to_bytes();
        let parsed = AuthorizationReceipt::from_bytes(&bytes).unwrap();
        assert_eq!(receipt, parsed);
    }

    #[test]
    fn verify_valid_receipt() {
        let nonce = [2u8; NONCE_SIZE];
        let receipt = authorize(&TEST_KEY, &nonce, 0, 1, b"transfer", b"{}").unwrap();
        let mut state = AuthorizationState::new(&TEST_KEY);
        assert!(verify(&mut state, b"transfer", b"{}", &receipt).is_ok());
        assert_eq!(state.last_counter(), 1);
    }

    #[test]
    fn reject_replayed_counter() {
        let nonce = [3u8; NONCE_SIZE];
        let receipt = authorize(&TEST_KEY, &nonce, 0, 7, b"exec", b"x").unwrap();
        let mut state = AuthorizationState::new(&TEST_KEY);
        assert!(verify(&mut state, b"exec", b"x", &receipt).is_ok());

        let replay = authorize(&TEST_KEY, &nonce, 1, 7, b"exec", b"x").unwrap();
        assert_eq!(
            verify(&mut state, b"exec", b"x", &replay),
            Err(ReluError::ReplayCounterViolation)
        );
    }

    #[test]
    fn reject_mutated_payload() {
        let nonce = [4u8; NONCE_SIZE];
        let receipt = authorize(&TEST_KEY, &nonce, 0, 1, b"read", b"public").unwrap();
        let mut state = AuthorizationState::new(&TEST_KEY);
        assert_eq!(
            verify(&mut state, b"read", b"secret", &receipt),
            Err(ReluError::AuthenticationFailure)
        );
    }

    #[test]
    fn streaming_verification_matches_full() {
        let nonce = [5u8; NONCE_SIZE];
        let payload = [0xCDu8; 10_000];
        let receipt = authorize(&TEST_KEY, &nonce, 0, 1, b"stream", &payload).unwrap();

        let mut hasher = verify_stream_begin(&TEST_KEY, &receipt, b"stream", payload.len()).unwrap();
        for chunk in payload.chunks(1234) {
            hasher.update(chunk);
        }
        let tag = hasher.finalize();
        assert_eq!(tag, receipt.tag);
    }
}
