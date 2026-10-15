//! SHA-256 implementation selection and runtime feature detection.
//!
//! ReluLayer delegates all hashing to the audited `sha2` crate from RustCrypto.
//! The implementation path is selected at compile time:
//!
//! | Feature                   | x86_64 target-feature | aarch64 target-feature | Behavior                          |
//! |---------------------------|-----------------------|------------------------|-----------------------------------|
//! | `sha256-hw`               | `+sha`                | `+crypto`              | Hardware acceleration             |
//! | `sha256-software`         | (none)                | (none)                 | Portable bitwise impl             |
//! | `sha256-runtime-detect`   | (none)                | (none)                 | Runtime CPUID / ID_AA64ISAR0_EL1  |
//! | default                   | (none)                | (none)                 | Portable bitwise impl             |
//!
//! The `sha2/asm` feature enables assembly-optimized compression routines; on
//! supported CPUs these routines use Intel SHA-NI or ARMv8 Crypto instructions.
//! The `sha2/force-soft` feature disables all native code paths.
//!
//! # Runtime detection
//!
//! `#![no_std]` environments typically run on a fixed target, so compile-time
//! selection is preferred. For hosts that require runtime feature detection,
//! enable `sha256-runtime-detect`. The detection function reports whether the
//! current CPU exposes the required SHA extensions; callers may use this to
//! refuse hardware-only builds on unsupported silicon or to select a
//! target-specific assembly module.

/// True when the `sha256-hw` feature is enabled.
pub const HW_ENABLED: bool = cfg!(feature = "sha256-hw");

/// True when the build explicitly requested the software implementation.
pub const SW_FORCED: bool = cfg!(feature = "sha256-software");

/// True when runtime CPU feature detection is enabled.
pub const RUNTIME_DETECT_ENABLED: bool = cfg!(feature = "sha256-runtime-detect");

/// Compile-time assertion that exactly one of the explicit SHA paths is selected.
#[cfg(all(feature = "sha256-hw", feature = "sha256-software"))]
compile_error!("Features `sha256-hw` and `sha256-software` are mutually exclusive.");

/// Reports whether the current CPU supports hardware SHA-256 acceleration.
///
/// - When `sha256-hw` is enabled, returns `true` at compile time (the build
///   itself guarantees the target feature is present).
/// - When `sha256-runtime-detect` is enabled, probes CPUID / ID_AA64ISAR0_EL1.
/// - Otherwise returns `false` and the constant-time software implementation is
///   used.
#[cfg(feature = "sha256-hw")]
#[inline]
pub fn hardware_sha256_available() -> bool {
    true
}

#[cfg(all(feature = "sha256-runtime-detect", target_arch = "x86_64", not(kani)))]
#[inline]
pub fn hardware_sha256_available() -> bool {
    // CPUID leaf 7 sub-leaf 0, EBX bit 29 = SHA-NI.
    // Use a static so the detection is performed once per process.
    use core::sync::atomic::{AtomicBool, Ordering};
    static AVAILABLE: AtomicBool = AtomicBool::new(false);
    static INITIALIZED: AtomicBool = AtomicBool::new(false);
    if !INITIALIZED.swap(true, Ordering::Relaxed) {
        let have_sha = detect_x86_sha_ni();
        AVAILABLE.store(have_sha, Ordering::Relaxed);
    }
    AVAILABLE.load(Ordering::Relaxed)
}

#[cfg(all(feature = "sha256-runtime-detect", target_arch = "aarch64", not(kani)))]
#[inline]
pub fn hardware_sha256_available() -> bool {
    // ID_AA64ISAR0_EL1.SHA2 bits [15:12] must be >= 0b0010 for SHA-256.
    use core::sync::atomic::{AtomicBool, Ordering};
    static AVAILABLE: AtomicBool = AtomicBool::new(false);
    static INITIALIZED: AtomicBool = AtomicBool::new(false);
    if !INITIALIZED.swap(true, Ordering::Relaxed) {
        let have_sha = detect_aarch64_sha256();
        AVAILABLE.store(have_sha, Ordering::Relaxed);
    }
    AVAILABLE.load(Ordering::Relaxed)
}

#[cfg(any(
    kani,
    not(any(
        feature = "sha256-hw",
        all(feature = "sha256-runtime-detect", any(target_arch = "x86_64", target_arch = "aarch64")),
    )),
))]
#[inline]
pub fn hardware_sha256_available() -> bool {
    false
}

#[cfg(all(feature = "sha256-runtime-detect", target_arch = "x86_64", not(kani)))]
fn detect_x86_sha_ni() -> bool {
    // Safe inline assembly: CPUID is supported on all x86_64 hosts.
    let result = unsafe { core::arch::x86_64::__cpuid_count(7, 0) };
    (result.ebx & (1 << 29)) != 0
}

#[cfg(all(feature = "sha256-runtime-detect", target_arch = "aarch64", not(kani)))]
fn detect_aarch64_sha256() -> bool {
    // Reading ID_AA64ISAR0_EL1 is safe at EL0 on modern ARMv8 Linux; the
    // register is architecturally read-only and trapped by the kernel.
    let isar0: u64;
    unsafe {
        core::arch::asm!(
            "mrs {}, ID_AA64ISAR0_EL1",
            out(reg) isar0,
            options(nomem, nostack),
        );
    }
    // SHA2 field: bits [15:12]. 0b0010 means SHA-256 and SHA-1 supported.
    ((isar0 >> 12) & 0xF) >= 2
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detection_is_consistent() {
        // Detection must return the same boolean on repeated calls.
        let a = hardware_sha256_available();
        let b = hardware_sha256_available();
        assert_eq!(a, b);
    }
}
