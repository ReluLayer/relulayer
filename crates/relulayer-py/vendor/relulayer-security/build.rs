//! Compile-time guards for SHA-256 hardware acceleration features.
#![allow(unexpected_cfgs)]
//!
//! The `sha256-hw` feature requests architecture-specific SHA instructions.
//! To prevent silent fallback to software on a build that claims to be
//! hardware-accelerated, compilation halts when the required target feature is
//! missing.

fn main() {
    // Register the custom cfg flag used by Kani harnesses.
    println!("cargo::rustc-check-cfg=cfg(kani)");

    #[cfg(all(
        feature = "sha256-hw",
        target_arch = "x86_64",
        not(target_feature = "sha")
    ))]
    compile_error!(
        "Feature `sha256-hw` on x86_64 requires `target-feature=+sha` (SHA-NI). \
         Use `sha256-runtime-detect` for builds that must run on mixed target hardware."
    );

    #[cfg(all(
        feature = "sha256-hw",
        target_arch = "aarch64",
        not(target_feature = "crypto")
    ))]
    compile_error!(
        "Feature `sha256-hw` on aarch64 requires `target-feature=+crypto` (ARMv8 Crypto). \
         Use `sha256-runtime-detect` for builds that must run on mixed target hardware."
    );
}
