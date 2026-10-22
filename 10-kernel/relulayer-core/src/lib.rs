#![cfg_attr(not(feature = "std"), no_std)]

#[cfg(not(feature = "std"))]
use core::panic::PanicInfo;

#[cfg(not(feature = "std"))]
#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    loop {}
}

pub mod core_math;
pub use core_math::*;

pub mod multivar_4d;
pub use multivar_4d::*;

#[cfg(feature = "internal-extras")]
pub mod pendulum_sim;
#[cfg(feature = "internal-extras")]
pub mod benchmark_harness;

#[cfg(kani)]
pub mod kani_proofs;

#[cfg(kani)]
pub mod kani_multivar_proofs;
