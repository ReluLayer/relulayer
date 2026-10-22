//! Inductive Kani proof harnesses for ReluLayer streaming equivalence and
//! replay monotonicity.
//!
//! These harnesses replace `MessageHasher` with the lightweight
//! `relulayer_security::crypto::mock_hash` stubs so the solver focuses on
//! protocol-level invariants rather than bitwise HMAC-SHA256 compression.

use relulayer_security::crypto::{
    authorize, verify, AuthorizationReceipt, AuthorizationState, BoundaryKey, MessageHasher,
};
use relulayer_security::limits::MAX_ACTION_ID_SIZE;
use relulayer_security::ReluError;

const TEST_KEY: BoundaryKey = BoundaryKey::from_array([
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E,
    0x0F, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D,
    0x1E, 0x1F,
]);

/// Symbolic bound for payload and action-id length.  Kept at 4 bytes so every
/// variable-length loop has at most 4 iterations.
const KANI_MAX_LEN: usize = 4;

/// Symbolically bounded action identifier.
fn any_action_id<const N: usize>() -> ([u8; N], usize) {
    let len: usize = kani::any();
    kani::assume(len <= MAX_ACTION_ID_SIZE);
    kani::assume(len <= N);
    kani::assume(len <= KANI_MAX_LEN);
    let mut buf = [0u8; N];
    for i in 0..len {
        buf[i] = kani::any();
    }
    (buf, len)
}

/// Symbolically bounded payload.
fn any_payload<const N: usize>() -> ([u8; N], usize) {
    let len: usize = kani::any();
    kani::assume(len <= N);
    kani::assume(len <= KANI_MAX_LEN);
    let mut buf = [0u8; N];
    for i in 0..len {
        buf[i] = kani::any();
    }
    (buf, len)
}

/// Base case: a symbolic payload of at most 4 bytes produces the same HMAC
/// tag when processed as a single slice as when processed in two 2-byte
/// chunks.
#[kani::proof]
#[kani::unwind(13)] // 12-byte nonce equality loop + 4-byte input loops
#[kani::stub(
    relulayer_security::crypto::MessageHasher::begin,
    relulayer_security::crypto::mock_hash::mock_message_hasher_begin
)]
#[kani::stub(
    relulayer_security::crypto::MessageHasher::update,
    relulayer_security::crypto::mock_hash::mock_message_hasher_update
)]
#[kani::stub(
    relulayer_security::crypto::MessageHasher::finalize,
    relulayer_security::crypto::mock_hash::mock_message_hasher_finalize
)]
fn streaming_base_case_small_payload() {
    const BASE_MAX: usize = 4;
    const CHUNK: usize = 2;

    let (action_id_buf, action_id_len) = any_action_id::<BASE_MAX>();
    let (payload_buf, payload_len) = any_payload::<BASE_MAX>();

    let action_id = &action_id_buf[..action_id_len];
    let payload = &payload_buf[..payload_len];
    let nonce = kani::any::<[u8; 12]>();

    let full_receipt = authorize(&TEST_KEY, &nonce, 0, 1, action_id, payload).unwrap();

    let mut hasher =
        MessageHasher::begin(&TEST_KEY, &nonce, 0, 1, action_id, payload_len).unwrap();
    for i in (0..BASE_MAX).step_by(CHUNK) {
        if i < payload_len {
            let end = (i + CHUNK).min(payload_len);
            hasher.update(&payload[i..end]);
        }
    }
    let streaming_tag = hasher.finalize();

    assert!(relulayer_security::crypto::kani_tags_equal(&streaming_tag, &full_receipt.tag));
}

/// Inductive step: for any split point, consuming the payload in two chunks
/// yields the same tag as consuming it in one chunk.
#[kani::proof]
#[kani::unwind(13)] // 12-byte nonce equality loop + 4-byte input loops
#[kani::stub(
    relulayer_security::crypto::MessageHasher::begin,
    relulayer_security::crypto::mock_hash::mock_message_hasher_begin
)]
#[kani::stub(
    relulayer_security::crypto::MessageHasher::update,
    relulayer_security::crypto::mock_hash::mock_message_hasher_update
)]
#[kani::stub(
    relulayer_security::crypto::MessageHasher::finalize,
    relulayer_security::crypto::mock_hash::mock_message_hasher_finalize
)]
fn streaming_inductive_step() {
    let (action_id_buf, action_id_len) = any_action_id::<KANI_MAX_LEN>();
    let (payload_buf, payload_len) = any_payload::<KANI_MAX_LEN>();

    let action_id = &action_id_buf[..action_id_len];
    let payload = &payload_buf[..payload_len];
    let nonce = kani::any::<[u8; 12]>();

    let split: usize = kani::any();
    kani::assume(split <= payload_len);

    let full_receipt = authorize(&TEST_KEY, &nonce, 0, 1, action_id, payload).unwrap();

    let mut hasher =
        MessageHasher::begin(&TEST_KEY, &nonce, 0, 1, action_id, payload_len).unwrap();
    hasher.update(&payload[..split]);
    hasher.update(&payload[split..]);
    let chunked_tag = hasher.finalize();

    assert!(relulayer_security::crypto::kani_tags_equal(&chunked_tag, &full_receipt.tag));
}

/// Monotonic replay invariant: a receipt with a stale counter is rejected.
#[kani::proof]
#[kani::unwind(13)] // 12-byte nonce equality loop + 4-byte input loops
#[kani::stub(
    relulayer_security::crypto::MessageHasher::begin,
    relulayer_security::crypto::mock_hash::mock_message_hasher_begin
)]
#[kani::stub(
    relulayer_security::crypto::MessageHasher::update,
    relulayer_security::crypto::mock_hash::mock_message_hasher_update
)]
#[kani::stub(
    relulayer_security::crypto::MessageHasher::finalize,
    relulayer_security::crypto::mock_hash::mock_message_hasher_finalize
)]
fn monotonic_counter_rejects_replay() {
    // Replay monotonicity depends only on the counter relationship, so fix the
    // message content and nonces to keep the BMC search tractable.
    let action_id = b"mono";
    let payload = b"";

    let nonce1 = [0xA1u8; 12];
    let nonce2 = [0xB2u8; 12];

    // Use a u8 BMC variable for the counter and cast to u64 for the API.
    let counter_state_u8: u8 = kani::any();
    kani::assume(counter_state_u8 > 0);
    let counter_state = counter_state_u8 as u64;

    let counter_receipt_u8: u8 = kani::any();
    kani::assume(counter_receipt_u8 <= counter_state_u8);
    let counter_receipt = counter_receipt_u8 as u64;

    let mut state = AuthorizationState::new(&TEST_KEY);

    let receipt_state = authorize(
        &TEST_KEY,
        &nonce1,
        0,
        counter_state,
        action_id,
        payload,
    )
    .unwrap();
    let accept = verify(&mut state, action_id, payload, &receipt_state);
    assert!(accept.is_ok());
    assert!(state.last_counter() == counter_state);

    let receipt_replay = AuthorizationReceipt {
        nonce: nonce2,
        timestamp: 0,
        counter: counter_receipt,
        tag: kani::any(),
    };
    let result = verify(&mut state, action_id, payload, &receipt_replay);
    assert!(matches!(result, Err(ReluError::ReplayCounterViolation)));
}

/// Duplicate-nonce invariant: the same nonce cannot be accepted twice.
#[kani::proof]
#[kani::unwind(13)] // 12-byte nonce equality loop + 4-byte input loops
#[kani::stub(
    relulayer_security::crypto::MessageHasher::begin,
    relulayer_security::crypto::mock_hash::mock_message_hasher_begin
)]
#[kani::stub(
    relulayer_security::crypto::MessageHasher::update,
    relulayer_security::crypto::mock_hash::mock_message_hasher_update
)]
#[kani::stub(
    relulayer_security::crypto::MessageHasher::finalize,
    relulayer_security::crypto::mock_hash::mock_message_hasher_finalize
)]
fn duplicate_nonce_rejects_replay() {
    let (action_id_buf, action_id_len) = any_action_id::<KANI_MAX_LEN>();
    let (payload_buf, payload_len) = any_payload::<KANI_MAX_LEN>();
    let action_id = &action_id_buf[..action_id_len];
    let payload = &payload_buf[..payload_len];

    let nonce = kani::any::<[u8; 12]>();

    let mut state = AuthorizationState::new(&TEST_KEY);

    let receipt1 = authorize(&TEST_KEY, &nonce, 0, 1, action_id, payload).unwrap();
    assert!(verify(&mut state, action_id, payload, &receipt1).is_ok());

    let receipt2 = authorize(&TEST_KEY, &nonce, 1, 2, action_id, payload).unwrap();
    let result = verify(&mut state, action_id, payload, &receipt2);
    assert!(matches!(result, Err(ReluError::ReplayNonceViolation)));
}
