#![no_std]
#![deny(unsafe_op_in_unsafe_fn)]

//! # ReluLayer C FFI Bridge
//! Exposes the bare-metal `relulayer-core` safety kernel through a C-compatible ABI.
//! Designed for integration with embedded flight software on ARM Cortex-M4/M7 targets
//! (Pixhawk 6X / STM32H7 / TMS570 class hardware).

pub use relulayer_core::{
    audit_phase_space_invariant, process_command_vector, InterceptionResult, Vector3DQ16, Q16,
    Q16_ONE, Q16_TOLERANCE,
};

use core::panic::PanicInfo;

/// Minimal panic handler for bare-metal staticlib builds.
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    loop {}
}

/// Convert a single-precision float to Q16.16 fixed-point.
#[inline(always)]
pub fn float_to_q16(val: f32) -> Q16 {
    (val * 65536.0) as i32
}

/// Convert a Q16.16 fixed-point value to single-precision float.
#[inline(always)]
pub fn q16_to_float(val: Q16) -> f32 {
    (val as f32) / 65536.0
}

/// C ABI wrapper: convert a single-precision float to Q16.16 fixed-point.
#[unsafe(no_mangle)]
pub extern "C" fn relulayer_float_to_q16(val: f32) -> Q16 {
    float_to_q16(val)
}

/// C ABI wrapper: convert a Q16.16 fixed-point value to single-precision float.
#[unsafe(no_mangle)]
pub extern "C" fn relulayer_q16_to_float(val: Q16) -> f32 {
    q16_to_float(val)
}

/// Out-of-band symplectic phase-space auditor.
/// Returns non-zero (true) if `|det_j - 1.0| <= ~0.001` in Q16.16.
#[unsafe(no_mangle)]
pub extern "C" fn relulayer_audit_phase_space_invariant(det_j: Q16) -> u8 {
    if audit_phase_space_invariant(det_j) {
        1
    } else {
        0
    }
}

/// Core O(1) convex quadratic velocity projection kernel.
/// Returns a safe command vector and auditor status for the given proposed velocity,
/// current position, Jacobian determinant, velocity ceiling, and geofence half-width.
#[unsafe(no_mangle)]
pub extern "C" fn relulayer_process_command_vector(
    v_prop: Vector3DQ16,
    pos: Vector3DQ16,
    det_j: Q16,
    v_max: Q16,
    geofence_half_width: Q16,
) -> InterceptionResult {
    process_command_vector(v_prop, pos, det_j, v_max, geofence_half_width)
}
