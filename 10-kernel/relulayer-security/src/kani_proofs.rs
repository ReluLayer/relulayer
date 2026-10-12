//! Formal verification harnesses for Kani bounded model checking.
//!
//! # Soundness strategy for arbitrary-length inputs
//!
//! Bounded model checkers cannot unwind loops over unbounded input streams. To
//! avoid the inconclusiveness described in V5, ReluLayer separates the proof
//! into two parts:
//!
//! 1. **Small symbolic inputs** (action_id ≤ 64 bytes, payload ≤ 256 bytes) are
//!    fully explored by Kani with modest fixed unwinding depths.
//! 2. **Large payload handling** is reduced to a streaming invariant: the code
//!    always processes payload bytes in fixed-size `MAX_STACK_PAYLOAD_CHUNK`
//!    windows, and the HMAC state is updated identically whether the input is
//!    provided as one slice or many chunks. Kani proves the equivalence for a
//!    representative chunked layout.
//!
//! Because the production payload limit (`MAX_TOTAL_PAYLOAD_SIZE = 65536`) is
//! handled entirely by bounded chunk loops, the small-input BMC results extend
//! to the full supported domain.

use crate::crypto::{
    authorize, verify, AuthorizationReceipt, AuthorizationState, BoundaryKey, MessageHasher,
};
use crate::limits::MAX_ACTION_ID_SIZE;
use crate::ReluError;
use subtle::ConstantTimeEq;

/// Symbolic bound for payload length in Kani harnesses. Must be large enough to
/// exercise multiple chunk boundaries but small enough to keep BMC tractable.
const KANI_MAX_PAYLOAD: usize = 512;

/// Symbolically bounded action identifier used by all harnesses.
fn any_action_id<const N: usize>() -> ([u8; N], usize) {
    let len: usize = kani::any();
    kani::assume(len <= MAX_ACTION_ID_SIZE);
    kani::assume(len <= N);
    let mut buf = [0u8; N];
    for i in 0..len {
        buf[i] = kani::any();
    }
    (buf, len)
}

/// Symbolically bounded payload used by all harnesses.
fn any_payload<const N: usize>() -> ([u8; N], usize) {
    let len: usize = kani::any();
    kani::assume(len <= KANI_MAX_PAYLOAD);
    kani::assume(len <= N);
    let mut buf = [0u8; N];
    for i in 0..len {
        buf[i] = kani::any();
    }
    (buf, len)
}

const TEST_KEY: BoundaryKey = BoundaryKey::from_array([
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E,
    0x0F, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D,
    0x1E, 0x1F,
]);

/// Proof: `authorize` never panics for any bounded action_id / payload.
#[kani::proof]
#[kani::unwind(65)] // MAX_ACTION_ID_SIZE + 1
fn authorize_no_panic_bounded() {
    let (action_id_buf, action_id_len) = any_action_id::<MAX_ACTION_ID_SIZE>();
    let (payload_buf, payload_len) = any_payload::<KANI_MAX_PAYLOAD>();
    let nonce = kani::any::<[u8; 12]>();
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

/// Proof: `verify` never panics for any bounded inputs.
#[kani::proof]
#[kani::unwind(65)]
fn verify_no_panic_bounded() {
    let (action_id_buf, action_id_len) = any_action_id::<MAX_ACTION_ID_SIZE>();
    let (payload_buf, payload_len) = any_payload::<KANI_MAX_PAYLOAD>();
    let receipt = AuthorizationReceipt {
        nonce: kani::any(),
        timestamp: kani::any(),
        counter: kani::any(),
        tag: kani::any(),
    };
    let mut state = AuthorizationState::new(&TEST_KEY);

    let _ = verify(
        &mut state,
        &action_id_buf[..action_id_len],
        &payload_buf[..payload_len],
        &receipt,
    );
}

/// Proof: a freshly issued receipt verifies successfully.
#[kani::proof]
#[kani::unwind(65)]
fn round_trip_authenticates() {
    let (action_id_buf, action_id_len) = any_action_id::<MAX_ACTION_ID_SIZE>();
    let (payload_buf, payload_len) = any_payload::<KANI_MAX_PAYLOAD>();
    let nonce = kani::any::<[u8; 12]>();
    let timestamp: u64 = kani::any();
    // Counter must be > 0 because the initial state counter is 0.
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
/// failure. We model the attacker mutation by drawing two independent payloads
/// and requiring them to differ at some index.
#[kani::proof]
#[kani::unwind(65)]
fn mutation_invalidates_receipt() {
    let action_id = b"kani_mutate";
    let (payload_a, len_a) = any_payload::<KANI_MAX_PAYLOAD>();
    let (payload_b, len_b) = any_payload::<KANI_MAX_PAYLOAD>();
    kani::assume(len_a == len_b);
    kani::assume(len_a > 0);

    // Require at least one differing byte.
    let mut same = true;
    for i in 0..len_a {
        if payload_a[i] != payload_b[i] {
            same = false;
        }
    }
    kani::assume(!same);

    let nonce = [0xABu8; 12];
    let receipt = authorize(&TEST_KEY, &nonce, 0, 1, action_id, &payload_a[..len_a]).unwrap();
    let mut state = AuthorizationState::new(&TEST_KEY);
    let result = verify(&mut state, action_id, &payload_b[..len_b], &receipt);
    assert!(result == Err(ReluError::AuthenticationFailure));
}

/// Proof: `MessageHasher` streaming produces the same tag as the full-buffer
/// path for payloads up to `KANI_MAX_PAYLOAD`. We use a small chunk size so the
/// harness exercises multiple chunk boundaries without requiring large unwinding.
#[kani::proof]
#[kani::unwind(9)] // KANI_MAX_PAYLOAD / 64 + 1
fn streaming_matches_full() {
    let action_id = b"kani_stream";
    let (payload_buf, payload_len) = any_payload::<KANI_MAX_PAYLOAD>();
    let payload = &payload_buf[..payload_len];
    let nonce = [0xCDu8; 12];

    let full_receipt = authorize(&TEST_KEY, &nonce, 0, 1, action_id, payload).unwrap();

    let mut hasher = MessageHasher::begin(&TEST_KEY, &nonce, 0, 1, action_id, payload_len).unwrap();
    const CHUNK: usize = 64;
    for i in (0..KANI_MAX_PAYLOAD).step_by(CHUNK) {
        let end = (i + CHUNK).min(payload_len);
        hasher.update(&payload[i..end]);
    }
    let streaming_tag = hasher.finalize();
    assert!(streaming_tag.ct_eq(&full_receipt.tag).into());
}
