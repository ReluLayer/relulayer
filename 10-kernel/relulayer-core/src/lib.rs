#![no_std]
#![deny(unsafe_code)]

pub mod core_math;
pub mod pendulum_sim;
pub mod benchmark_harness;

#[cfg(kani)]
pub mod kani_proofs;
