//! ReluLayer formal verification proofs.
//!
//! Kani bounded-model-checking harnesses live in `kani_boundary.rs` and are
//! compiled only when the `kani` cfg is active.

#[cfg(kani)]
pub mod kani_boundary;
