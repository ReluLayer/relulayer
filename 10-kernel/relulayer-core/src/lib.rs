#![no_std]

use core::panic::PanicInfo;

#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    loop {}
}

pub mod core_math;
pub mod pendulum_sim;
pub mod benchmark_harness;

#[cfg(kani)]
pub mod kani_proofs;
