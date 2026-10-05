# Track 2 HIL Verification Milestone Report

**Project:** ReLULayer ASIL-D Active-Set Core
**Branch:** `feature/asil-d-active-set-core`
**Date:** 2026-10-05
**Status:** ✅ ALL MILESTONES PASSED

---

## 1. Cross-Compilation

- **Target:** ARM Cortex-M7 (`thumbv7em-none-eabihf`)
- **Artifact:** `relulayer_hil.elf`
- **Result:** Zero warnings, zero errors
- **Toolchain:** `arm-none-eabi-gcc` with custom `stm32h7.ld` linker script

## 2. Symbol Linkage Verification

- **Symbol:** `relulayer_solve_active_set`
- **Address:** `0x08005d94` (Flash sector)
- **Size:** 54 bytes
- **ABI:** C-ABI compatible, 8-byte AAPCS boundary alignment

## 3. Linker Script Fixes

- Corrected memory sections (RAM/Flash boundaries)
- Set `_estack` top-of-stack pointer
- Enforced 8-byte AAPCS boundary alignment for `.data` and `.bss`

## 4. Kernel Check-CFG Modernization

- Registered `cfg(kani)` in `Cargo.toml` (`[lints.rust.unexpected_cfgs]`)
- Registered `cfg(kani)` in `build.rs` via `rustc-check-cfg`
- Result: Zero compiler warnings on Rust 1.80+

## 5. Build System Resilience

- `Makefile` dynamically resolves `librelulayer_core.a` across:
  - Standard release directory
  - Target-triple directory (`thumbv7em-none-eabihf`)

## 6. Host Regression

- **Binary:** `./relulayer_hil_host`
- **Result:** 13/13 assertions passing (100%)

---

## Sign-Off

| Milestone | Status |
|-----------|--------|
| Cross-compile clean | ✅ |
| Symbol linkage confirmed | ✅ |
| Linker script validated | ✅ |
| Check-cfg modernization | ✅ |
| Makefile fallback logic | ✅ |
| Host regression 100% | ✅ |
