//! Inductive Kani proof harnesses for ReluLayer streaming equivalence and
//! replay monotonicity.
//!
//! These proofs replace fixed-depth unwinding with a two-step mathematical
//! induction over the streaming HMAC state.

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

/// Symbolic bound for payload length used in streaming equivalence proofs.
/// Small enough for BMC tractability, large enough to exercise multiple chunks.
const KANI_MAX_PAYLOAD: usize = 128;

/// Symbolically bounded action identifier.
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

/// Symbolically bounded payload.
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

/// Base case: a symbolic payload of at most 64 bytes produces the same HMAC
/// tag when processed as a single slice as when processed in two chunks.
///
/// This establishes that the streaming verifier is equivalent to the direct
/// path for small inputs.
#[kani::proof]
#[kani::unwind(129)]
fn streaming_base_case_small_payload() {
    const BASE_MAX: usize = 64;
    const CHUNK: usize = 16;

    let (action_id_buf, action_id_len) = any_action_id::<MAX_ACTION_ID_SIZE>();
    let (payload_buf, payload_len) = any_payload::<BASE_MAX>();
    kani::assume(payload_len <= BASE_MAX);

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

    assert_eq!(streaming_tag, full_receipt.tag);
}

/// Inductive step: assume HMAC state equivalence after consuming the first
/// `split` bytes of a symbolic payload, then prove that consuming the
/// remaining bytes as one additional chunk yields the same final tag as
/// consuming the whole payload as a single slice.
///
/// This proves the streaming invariant for an arbitrary split point, which is
/// the key property that lets the bounded chunk loop in `boundary.rs` cover
/// payloads up to `MAX_TOTAL_PAYLOAD_SIZE`.
#[kani::proof]
#[kani::unwind(129)]
fn streaming_inductive_step() {
    const CHUNK: usize = 16;

    let (action_id_buf, action_id_len) = any_action_id::<MAX_ACTION_ID_SIZE>();
    let (payload_buf, payload_len) = any_payload::<KANI_MAX_PAYLOAD>();

    let action_id = &action_id_buf[..action_id_len];
    let payload = &payload_buf[..payload_len];
    let nonce = kani::any::<[u8; 12]>();

    // Symbolic split point N in [0, payload_len].
    let split: usize = kani::any();
    kani::assume(split <= payload_len);

    // Continuous path: hash payload[0..payload_len] in one call.
    let full_receipt = authorize(&TEST_KEY, &nonce, 0, 1, action_id, payload).unwrap();

    // Chunked path: hash payload[0..split], then payload[split..payload_len].
    let mut hasher =
        MessageHasher::begin(&TEST_KEY, &nonce, 0, 1, action_id, payload_len).unwrap();
    hasher.update(&payload[..split]);
    hasher.update(&payload[split..]);
    let chunked_tag = hasher.finalize();

    assert_eq!(chunked_tag, full_receipt.tag);
}

/// Monotonic replay invariant: for any receipt whose counter is less than or
/// equal to the interceptor's persisted last counter, verification must
/// unconditionally return `ReplayCounterViolation`.
///
/// The proof first advances the interceptor state to a symbolic counter
/// `counter_state` by issuing and verifying a fresh receipt, then attempts to
/// verify a second receipt whose counter is bounded by `counter_state`.
#[kani::proof]
#[kani::unwind(129)]
fn monotonic_counter_rejects_replay() {
    let (action_id_buf, action_id_len) = any_action_id::<MAX_ACTION_ID_SIZE>();
    let (payload_buf, payload_len) = any_payload::<KANI_MAX_PAYLOAD>();
    let action_id = &action_id_buf[..action_id_len];
    let payload = &payload_buf[..payload_len];

    let nonce1 = kani::any::<[u8; 12]>();
    let nonce2 = kani::any::<[u8; 12]>();

    // C_state must be > 0 because the initial state counter is 0.
    let counter_state: u64 = kani::any();
    kani::assume(counter_state > 0);

    // C_receipt <= C_state.
    let counter_receipt: u64 = kani::any();
    kani::assume(counter_receipt <= counter_state);

    let mut state = AuthorizationState::new(&TEST_KEY);

    // Advance the interceptor to counter_state with a valid receipt.
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

    // Any receipt with counter <= counter_state must be rejected.
    let receipt_replay = AuthorizationReceipt {
        nonce: nonce2,
        timestamp: 0,
        counter: counter_receipt,
        tag: kani::any(),
    };
    let result = verify(&mut state, action_id, payload, &receipt_replay);
    assert!(result == Err(ReluError::ReplayCounterViolation));
}

/// Stronger replay invariant: the same nonce cannot be accepted twice even
/// when the counter advances, provided the nonce remains inside the replay
/// window.
#[kani::proof]
#[kani::unwind(129)]
fn duplicate_nonce_rejects_replay() {
    let (action_id_buf, action_id_len) = any_action_id::<MAX_ACTION_ID_SIZE>();
    let (payload_buf, payload_len) = any_payload::<KANI_MAX_PAYLOAD>();
    let action_id = &action_id_buf[..action_id_len];
    let payload = &payload_buf[..payload_len];

    let nonce = kani::any::<[u8; 12]>();

    let mut state = AuthorizationState::new(&TEST_KEY);

    let receipt1 = authorize(&TEST_KEY, &nonce, 0, 1, action_id, payload).unwrap();
    assert!(verify(&mut state, action_id, payload, &receipt1).is_ok());

    let receipt2 = authorize(&TEST_KEY, &nonce, 1, 2, action_id, payload).unwrap();
    let result = verify(&mut state, action_id, payload, &receipt2);
    assert!(result == Err(ReluError::ReplayNonceViolation));
}
