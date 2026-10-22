//! Formal verification harnesses for Kani bounded model checking.
//!
//! These proofs are intentionally *bounded* and *stubbed* so that every harness
//! terminates quickly (target: < 60 s, low memory).  The cryptographic hash
//! engine is replaced on a per-harness basis by the lightweight
//! `crate::crypto::mock_hash` stubs so the solver only reasons about the HMAC
//! protocol framing (length fields, key sizing, padding order, streaming
//! equivalence) rather than bitwise SHA-256 compression rounds.

use crate::crypto::{
    authorize, verify, AuthorizationReceipt, AuthorizationState, BoundaryKey, MessageHasher,
};
use crate::limits::{HMAC_SIZE, MAX_ACTION_ID_SIZE, NONCE_SIZE};
use crate::ReluError;

// ---------------------------------------------------------------------------
// Symbolic input bounds
// ---------------------------------------------------------------------------

/// Maximum symbolic action-id length used in any harness.
///
/// Keeping this <= 4 means every variable-length loop has at most 4 iterations,
/// so `#[kani::unwind(5)]` is sufficient for all harnesses.
const KANI_MAX_ACTION_ID: usize = 4;

/// Maximum symbolic payload length used in any harness.
const KANI_MAX_PAYLOAD: usize = 4;

const TEST_KEY: BoundaryKey = BoundaryKey::from_array([
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E,
    0x0F, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D,
    0x1E, 0x1F,
]);

// ---------------------------------------------------------------------------
// Bounded symbolic helpers (no variable-length loops)
// ---------------------------------------------------------------------------

/// Symbolically bounded action identifier.
fn any_action_id() -> ([u8; KANI_MAX_ACTION_ID], usize) {
    let len: usize = kani::any();
    kani::assume(len <= KANI_MAX_ACTION_ID);
    kani::assume(len <= MAX_ACTION_ID_SIZE);

    let v: u32 = kani::any();
    let mut buf = [0u8; KANI_MAX_ACTION_ID];
    buf.copy_from_slice(&v.to_le_bytes());
    (buf, len)
}

/// Symbolically bounded payload.
fn any_payload() -> ([u8; KANI_MAX_PAYLOAD], usize) {
    let len: usize = kani::any();
    kani::assume(len <= KANI_MAX_PAYLOAD);

    let v: u32 = kani::any();
    let mut buf = [0u8; KANI_MAX_PAYLOAD];
    buf.copy_from_slice(&v.to_le_bytes());
    (buf, len)
}

/// Symbolically bounded 12-byte nonce.
fn any_nonce() -> [u8; NONCE_SIZE] {
    let v: u128 = kani::any();
    let mut nonce = [0u8; NONCE_SIZE];
    nonce.copy_from_slice(&v.to_le_bytes()[..NONCE_SIZE]);
    nonce
}

/// Symbolically bounded 32-byte HMAC tag.
fn any_tag() -> [u8; HMAC_SIZE] {
    let low: u128 = kani::any();
    let high: u128 = kani::any();
    let mut tag = [0u8; HMAC_SIZE];
    tag[0..16].copy_from_slice(&low.to_le_bytes());
    tag[16..32].copy_from_slice(&high.to_le_bytes());
    tag
}

// ---------------------------------------------------------------------------
// Harnesses
// ---------------------------------------------------------------------------

/// Proof: `authorize` never panics for bounded symbolic inputs.
#[kani::proof]
#[kani::unwind(5)]
#[kani::stub(
    crate::crypto::MessageHasher::begin,
    crate::crypto::mock_hash::mock_message_hasher_begin
)]
#[kani::stub(
    crate::crypto::MessageHasher::update,
    crate::crypto::mock_hash::mock_message_hasher_update
)]
#[kani::stub(
    crate::crypto::MessageHasher::finalize,
    crate::crypto::mock_hash::mock_message_hasher_finalize
)]
fn authorize_no_panic_bounded() {
    let (action_id_buf, action_id_len) = any_action_id();
    let (payload_buf, payload_len) = any_payload();
    let nonce = any_nonce();
    let timestamp: u64 = kani::any();
    let counter: u64 = kani::any();

    let _ = authorize(
        &TEST_KEY,
        &nonce,
        timestamp,
        counter,
        &action_id_buf[..action_id_len],
        &payload_buf[..payload_len],
    );
}

/// Proof: `verify` never panics for bounded symbolic inputs.
#[kani::proof]
#[kani::unwind(5)]
#[kani::stub(
    crate::crypto::MessageHasher::begin,
    crate::crypto::mock_hash::mock_message_hasher_begin
)]
#[kani::stub(
    crate::crypto::MessageHasher::update,
    crate::crypto::mock_hash::mock_message_hasher_update
)]
#[kani::stub(
    crate::crypto::MessageHasher::finalize,
    crate::crypto::mock_hash::mock_message_hasher_finalize
)]
fn verify_no_panic_bounded() {
    let (action_id_buf, action_id_len) = any_action_id();
    let (payload_buf, payload_len) = any_payload();
    let receipt = AuthorizationReceipt {
        nonce: any_nonce(),
        timestamp: kani::any(),
        counter: kani::any(),
        tag: any_tag(),
    };
    let mut state = AuthorizationState::new(&TEST_KEY);

    let _ = verify(
        &mut state,
        &action_id_buf[..action_id_len],
        &payload_buf[..payload_len],
        &receipt,
    );
}

/// Proof: a freshly issued receipt verifies successfully and updates the
/// monotonic counter.
#[kani::proof]
#[kani::unwind(5)]
#[kani::stub(
    crate::crypto::MessageHasher::begin,
    crate::crypto::mock_hash::mock_message_hasher_begin
)]
#[kani::stub(
    crate::crypto::MessageHasher::update,
    crate::crypto::mock_hash::mock_message_hasher_update
)]
#[kani::stub(
    crate::crypto::MessageHasher::finalize,
    crate::crypto::mock_hash::mock_message_hasher_finalize
)]
fn round_trip_authenticates() {
    let (action_id_buf, action_id_len) = any_action_id();
    let (payload_buf, payload_len) = any_payload();
    let nonce = any_nonce();
    let timestamp: u64 = kani::any();
    let counter: u64 = kani::any();
    kani::assume(counter > 0);

    let action_id = &action_id_buf[..action_id_len];
    let payload = &payload_buf[..payload_len];

    let receipt = authorize(&TEST_KEY, &nonce, timestamp, counter, action_id, payload).unwrap();
    let mut state = AuthorizationState::new(&TEST_KEY);
    let result = verify(&mut state, action_id, payload, &receipt);
    assert!(result.is_ok());
    assert!(state.last_counter() == counter);
}

/// Proof: mutating a single payload byte after authorization causes verification
/// failure.  A witness index guarantees the two payloads differ.
#[kani::proof]
#[kani::unwind(5)]
#[kani::stub(
    crate::crypto::MessageHasher::begin,
    crate::crypto::mock_hash::mock_message_hasher_begin
)]
#[kani::stub(
    crate::crypto::MessageHasher::update,
    crate::crypto::mock_hash::mock_message_hasher_update
)]
#[kani::stub(
    crate::crypto::MessageHasher::finalize,
    crate::crypto::mock_hash::mock_message_hasher_finalize
)]
fn mutation_invalidates_receipt() {
    let action_id = b"kani_mutate";
    let (payload_a, len) = any_payload();
    let (payload_b, _) = any_payload();
    kani::assume(len > 0);

    let diff_idx: usize = kani::any();
    kani::assume(diff_idx < len);
    kani::assume(payload_a[diff_idx] != payload_b[diff_idx]);

    let nonce = [0xABu8; NONCE_SIZE];
    let receipt = authorize(&TEST_KEY, &nonce, 0, 1, action_id, &payload_a[..len]).unwrap();
    let mut state = AuthorizationState::new(&TEST_KEY);
    let result = verify(&mut state, action_id, &payload_b[..len], &receipt);
    assert!(result == Err(ReluError::AuthenticationFailure));
}

/// Proof: streaming the payload in 2-byte chunks produces the same tag as the
/// full-buffer path.
#[kani::proof]
#[kani::unwind(5)]
#[kani::stub(
    crate::crypto::MessageHasher::begin,
    crate::crypto::mock_hash::mock_message_hasher_begin
)]
#[kani::stub(
    crate::crypto::MessageHasher::update,
    crate::crypto::mock_hash::mock_message_hasher_update
)]
#[kani::stub(
    crate::crypto::MessageHasher::finalize,
    crate::crypto::mock_hash::mock_message_hasher_finalize
)]
fn streaming_matches_full() {
    let action_id = b"kani_stream";
    let (payload_buf, payload_len) = any_payload();
    let payload = &payload_buf[..payload_len];
    let nonce = [0xCDu8; NONCE_SIZE];

    let full_receipt = authorize(&TEST_KEY, &nonce, 0, 1, action_id, payload).unwrap();

    let mut hasher = MessageHasher::begin(&TEST_KEY, &nonce, 0, 1, action_id, payload_len).unwrap();
    const CHUNK: usize = 2;
    for i in (0..KANI_MAX_PAYLOAD).step_by(CHUNK) {
        if i < payload_len {
            let end = (i + CHUNK).min(payload_len);
            hasher.update(&payload[i..end]);
        }
    }
    let streaming_tag = hasher.finalize();
    assert!(crate::crypto::kani_tags_equal(&streaming_tag, &full_receipt.tag));
}
