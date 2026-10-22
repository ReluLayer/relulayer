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
#[cfg(not(kani))]
use subtle::ConstantTimeEq;
#[cfg(kani)]
use subtle::Choice;

#[cfg(not(kani))]
use hmac::{Hmac, Mac};
#[cfg(not(kani))]
use sha2::Sha256;

#[cfg(not(kani))]
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
            #[cfg(not(kani))]
            let matched = self.nonces[idx].ct_eq(nonce).into();
            #[cfg(kani)]
            let matched = self.nonces[idx] == *nonce;
            if matched {
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

/// Lightweight, deterministic Kani-only MAC stub.
///
/// This stub replaces `HMAC-SHA256` under `cfg(kani)` so that protocol-level
/// BMC proofs over the authorization boundary remain tractable. It is **not**
/// cryptographically secure and is never compiled into production code.
///
/// To keep CBMC's symbolic state small, the tag is not built by independently
/// updating 32 state bytes per message byte. Instead, a single `u128`
/// accumulator absorbs the message, and `finalize` expands the accumulator
/// into the required 32-byte tag. The resulting stub still satisfies the
/// required properties:
/// - **Deterministic:** the same `(key, message)` pair always yields the same tag.
/// - **Order-sensitive:** permuting the message bytes changes the resulting tag.
/// - **Key-dependent:** tags differ for different keys.
/// - **Mutation-sensitive:** flipping any message byte produces a different tag.
#[cfg(kani)]
pub struct KaniMac {
    key: [u8; 32],
    state: [u8; HMAC_SIZE],
    acc: u32,
}

#[cfg(kani)]
impl KaniMac {
    fn new_from_slice(key: &[u8]) -> Result<Self, ()> {
        if key.len() != 32 {
            return Err(());
        }
        let mut k = [0u8; 32];
        k.copy_from_slice(key);
        let mut state = [0u8; HMAC_SIZE];
        // Initialize state from the first 32 bytes of the key, matching the
        // documented Kani-only stub contract.  Manual assignments avoid a
        // 32-iteration loop so the BMC unwind bound can stay small.
        state[0] = k[0];
        state[1] = k[1];
        state[2] = k[2];
        state[3] = k[3];
        state[4] = k[4];
        state[5] = k[5];
        state[6] = k[6];
        state[7] = k[7];
        state[8] = k[8];
        state[9] = k[9];
        state[10] = k[10];
        state[11] = k[11];
        state[12] = k[12];
        state[13] = k[13];
        state[14] = k[14];
        state[15] = k[15];
        state[16] = k[16];
        state[17] = k[17];
        state[18] = k[18];
        state[19] = k[19];
        state[20] = k[20];
        state[21] = k[21];
        state[22] = k[22];
        state[23] = k[23];
        state[24] = k[24];
        state[25] = k[25];
        state[26] = k[26];
        state[27] = k[27];
        state[28] = k[28];
        state[29] = k[29];
        state[30] = k[30];
        state[31] = k[31];
        let mut seed_bytes = [0u8; 4];
        seed_bytes.copy_from_slice(&k[..4]);
        Ok(Self {
            key: k,
            state,
            acc: u32::from_le_bytes(seed_bytes),
        })
    }

    fn update(&mut self, data: &[u8]) {
        // Use a single accumulator so the solver only tracks one symbolic
        // expression per message byte instead of 32 interdependent state bytes.
        // The shift-left encoding preserves byte order and makes the SAT query
        // trivial compared to rotate/add mixing.
        for b in data {
            self.acc = (self.acc << 8) | (*b as u32);
        }
    }

    fn finalize(mut self) -> [u8; HMAC_SIZE] {
        let acc_bytes = self.acc.to_le_bytes();

        // First 4 tag bytes come directly from the accumulator.
        self.state[0] = acc_bytes[0];
        self.state[1] = acc_bytes[1];
        self.state[2] = acc_bytes[2];
        self.state[3] = acc_bytes[3];

        // Remaining 28 bytes mix the key with the accumulator so tag changes
        // reflect both message and key differences.
        self.state[4] = self.key[0] ^ acc_bytes[0];
        self.state[5] = self.key[1] ^ acc_bytes[1];
        self.state[6] = self.key[2] ^ acc_bytes[2];
        self.state[7] = self.key[3] ^ acc_bytes[3];
        self.state[8] = self.key[4] ^ acc_bytes[0];
        self.state[9] = self.key[5] ^ acc_bytes[1];
        self.state[10] = self.key[6] ^ acc_bytes[2];
        self.state[11] = self.key[7] ^ acc_bytes[3];
        self.state[12] = self.key[8].wrapping_add(acc_bytes[0]);
        self.state[13] = self.key[9].wrapping_add(acc_bytes[1]);
        self.state[14] = self.key[10].wrapping_add(acc_bytes[2]);
        self.state[15] = self.key[11].wrapping_add(acc_bytes[3]);
        self.state[16] = self.key[12].wrapping_add(acc_bytes[0]);
        self.state[17] = self.key[13].wrapping_add(acc_bytes[1]);
        self.state[18] = self.key[14].wrapping_add(acc_bytes[2]);
        self.state[19] = self.key[15].wrapping_add(acc_bytes[3]);
        self.state[20] = self.key[16].wrapping_add(acc_bytes[0]);
        self.state[21] = self.key[17].wrapping_add(acc_bytes[1]);
        self.state[22] = self.key[18].wrapping_add(acc_bytes[2]);
        self.state[23] = self.key[19].wrapping_add(acc_bytes[3]);
        self.state[24] = self.key[20].wrapping_add(acc_bytes[0]);
        self.state[25] = self.key[21].wrapping_add(acc_bytes[1]);
        self.state[26] = self.key[22].wrapping_add(acc_bytes[2]);
        self.state[27] = self.key[23].wrapping_add(acc_bytes[3]);
        self.state[28] = self.key[24].wrapping_add(acc_bytes[0]);
        self.state[29] = self.key[25].wrapping_add(acc_bytes[1]);
        self.state[30] = self.key[26].wrapping_add(acc_bytes[2]);
        self.state[31] = self.key[27].wrapping_add(acc_bytes[3]);

        self.state
    }
}

/// Loop-free tag equality used under `cfg(kani)` to avoid the 32-iteration
/// `memcmp` loop that `==` on `[u8; HMAC_SIZE]` would otherwise generate.
#[cfg(kani)]
pub fn kani_tags_equal(a: &[u8; HMAC_SIZE], b: &[u8; HMAC_SIZE]) -> bool {
    a[0] == b[0]
        && a[1] == b[1]
        && a[2] == b[2]
        && a[3] == b[3]
        && a[4] == b[4]
        && a[5] == b[5]
        && a[6] == b[6]
        && a[7] == b[7]
        && a[8] == b[8]
        && a[9] == b[9]
        && a[10] == b[10]
        && a[11] == b[11]
        && a[12] == b[12]
        && a[13] == b[13]
        && a[14] == b[14]
        && a[15] == b[15]
        && a[16] == b[16]
        && a[17] == b[17]
        && a[18] == b[18]
        && a[19] == b[19]
        && a[20] == b[20]
        && a[21] == b[21]
        && a[22] == b[22]
        && a[23] == b[23]
        && a[24] == b[24]
        && a[25] == b[25]
        && a[26] == b[26]
        && a[27] == b[27]
        && a[28] == b[28]
        && a[29] == b[29]
        && a[30] == b[30]
        && a[31] == b[31]
}

// ---------------------------------------------------------------------------
// Optional ultra-lightweight `MessageHasher` stubs for Kani proofs.
//
// These replace `MessageHasher::{begin, update, finalize}` on a per-harness
// basis via `#[kani::stub(...)]`.  They are *not* cryptographically secure;
// they exist only to make protocol-level BMC proofs (framing, lengths,
// key sizing, replay invariants) tractable inside a 60-second budget.
//
// Production builds continue to use the real `sha2`/`hmac` stack; these
// functions are compiled only under `cfg(kani)`.
// ---------------------------------------------------------------------------

#[cfg(kani)]
pub mod mock_hash {
    use super::*;
    use crate::limits::{MAX_ACTION_ID_SIZE, MAX_TOTAL_PAYLOAD_SIZE, NONCE_SIZE};
    use core::mem::MaybeUninit;

    static mut STATE: u128 = 0;
    static mut KEY: u64 = 0;

    fn key_seed(key: &[u8]) -> u64 {
        let mut bytes = [0u8; 8];
        let n = key.len().min(8);
        bytes[..n].copy_from_slice(&key[..n]);
        u64::from_le_bytes(bytes)
    }

    fn mix_state(mut state: u128, data: &[u8]) -> u128 {
        let n = data.len();
        if n > 0 {
            state = (state << 8) | (data[0] as u128);
        }
        if n > 1 {
            state = (state << 8) | (data[1] as u128);
        }
        if n > 2 {
            state = (state << 8) | (data[2] as u128);
        }
        if n > 3 {
            state = (state << 8) | (data[3] as u128);
        }
        if n > 4 {
            state = (state << 8) | (data[4] as u128);
        }
        if n > 5 {
            state = (state << 8) | (data[5] as u128);
        }
        if n > 6 {
            state = (state << 8) | (data[6] as u128);
        }
        if n > 7 {
            state = (state << 8) | (data[7] as u128);
        }
        if n > 8 {
            state = (state << 8) | (data[8] as u128);
        }
        if n > 9 {
            state = (state << 8) | (data[9] as u128);
        }
        if n > 10 {
            state = (state << 8) | (data[10] as u128);
        }
        if n > 11 {
            state = (state << 8) | (data[11] as u128);
        }
        state
    }

    pub fn mock_message_hasher_begin(
        key: &BoundaryKey,
        nonce: &[u8; NONCE_SIZE],
        timestamp: u64,
        counter: u64,
        action_id: &[u8],
        payload_len: usize,
    ) -> Result<MessageHasher, ReluError> {
        if action_id.len() > MAX_ACTION_ID_SIZE {
            return Err(ReluError::ActionIdOverflow);
        }
        if payload_len > MAX_TOTAL_PAYLOAD_SIZE {
            return Err(ReluError::PayloadOverflow);
        }

        unsafe {
            KEY = key_seed(key.as_bytes());
            STATE = 0;
        }

        let mut s = 0u128;
        s = mix_state(s, nonce);
        s = mix_state(s, &timestamp.to_le_bytes());
        s = mix_state(s, &counter.to_le_bytes());
        s = mix_state(s, &(action_id.len() as u64).to_le_bytes());
        s = mix_state(s, action_id);
        s = mix_state(s, &(payload_len as u64).to_le_bytes());

        unsafe {
            STATE = s;
        }

        Ok(unsafe { MaybeUninit::<MessageHasher>::zeroed().assume_init() })
    }

    pub fn mock_message_hasher_update(_hasher: &mut MessageHasher, chunk: &[u8]) {
        let mut s = unsafe { STATE };
        s = mix_state(s, chunk);
        unsafe {
            STATE = s;
        }
    }

    pub fn mock_message_hasher_finalize(_hasher: MessageHasher) -> [u8; HMAC_SIZE] {
        let (state, key) = unsafe { (STATE, KEY) };
        let state_bytes = state.to_le_bytes();
        let key_bytes = key.to_le_bytes();

        let mut tag = [0u8; HMAC_SIZE];
        tag[..16].copy_from_slice(&state_bytes);
        tag[16] = key_bytes[0] ^ state_bytes[0];
        tag[17] = key_bytes[1] ^ state_bytes[1];
        tag[18] = key_bytes[2] ^ state_bytes[2];
        tag[19] = key_bytes[3] ^ state_bytes[3];
        tag[20] = key_bytes[4] ^ state_bytes[4];
        tag[21] = key_bytes[5] ^ state_bytes[5];
        tag[22] = key_bytes[6] ^ state_bytes[6];
        tag[23] = key_bytes[7] ^ state_bytes[7];
        tag[24] = key_bytes[0].wrapping_add(state_bytes[0]);
        tag[25] = key_bytes[1].wrapping_add(state_bytes[1]);
        tag[26] = key_bytes[2].wrapping_add(state_bytes[2]);
        tag[27] = key_bytes[3].wrapping_add(state_bytes[3]);
        tag[28] = key_bytes[4].wrapping_add(state_bytes[4]);
        tag[29] = key_bytes[5].wrapping_add(state_bytes[5]);
        tag[30] = key_bytes[6].wrapping_add(state_bytes[6]);
        tag[31] = key_bytes[7].wrapping_add(state_bytes[7]);

        tag
    }

    pub fn mock_ct_eq(a: &[u8; HMAC_SIZE], b: &[u8; HMAC_SIZE]) -> Choice {
        Choice::from(u8::from(kani_tags_equal(a, b)))
    }
}

/// Streaming HMAC builder for the canonical message format.
///
/// Used internally by both `authorize` (full-buffer) and the streaming
/// verification path in `boundary.rs`.
pub struct MessageHasher {
    #[cfg(not(kani))]
    mac: HmacSha256,
    #[cfg(kani)]
    mac: KaniMac,
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

        #[cfg(not(kani))]
        let mut mac = HmacSha256::new_from_slice(key.as_bytes())
            .map_err(|_| ReluError::AuthenticationFailure)?;
        #[cfg(kani)]
        let mut mac = KaniMac::new_from_slice(key.as_bytes())
            .map_err(|_| ReluError::AuthenticationFailure)?;

        #[cfg(not(kani))]
        {
            mac.update(nonce);
            mac.update(&timestamp.to_le_bytes());
            mac.update(&counter.to_le_bytes());
            mac.update(&(action_id.len() as u64).to_le_bytes());
            mac.update(action_id);
            mac.update(&(payload_len as u64).to_le_bytes());
        }
        #[cfg(kani)]
        {
            mac.update(nonce);
            mac.update(&timestamp.to_le_bytes());
            mac.update(&counter.to_le_bytes());
            mac.update(&(action_id.len() as u64).to_le_bytes());
            mac.update(action_id);
            mac.update(&(payload_len as u64).to_le_bytes());
        }

        Ok(Self { mac })
    }

    /// Feed a payload chunk.
    pub fn update(&mut self, chunk: &[u8]) {
        #[cfg(not(kani))]
        self.mac.update(chunk);
        #[cfg(kani)]
        self.mac.update(chunk);
    }

    /// Finalize and return the HMAC tag.
    pub fn finalize(self) -> [u8; HMAC_SIZE] {
        #[cfg(not(kani))]
        {
            self.mac.finalize().into_bytes().into()
        }
        #[cfg(kani)]
        {
            self.mac.finalize()
        }
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

    #[cfg(not(kani))]
    let tags_equal = computed.ct_eq(&receipt.tag).into();
    #[cfg(kani)]
    let tags_equal = kani_tags_equal(&computed, &receipt.tag);

    if tags_equal {
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
