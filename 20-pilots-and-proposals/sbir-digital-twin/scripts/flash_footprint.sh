#!/usr/bin/env bash
# ReluLayer ARM Staticlib Flash Footprint Analysis
# US Army SBIR ARM26TX04-NV001 — Embedded Flight Controller Safety Kernel
#
# This script extracts the ARM staticlib archive produced by
# `cargo build --target thumbv7em-none-eabihf -p relulayer-ffi --release`
# and reports the size of the relulayer-specific objects. The archive also
# contains compiler_builtins/runtime objects that the linker pulls only as needed.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARM_LIB="${ROOT}/target/thumbv7em-none-eabihf/release/librelulayer_ffi.a"
WORK_DIR="$(mktemp -d)"
REPORT="${ROOT}/results/flash_footprint_arm.txt"

mkdir -p "$(dirname "$REPORT")"

if [[ ! -f "$ARM_LIB" ]]; then
    echo "ERROR: ARM staticlib not found at $ARM_LIB" >&2
    echo "Build it first with:" >&2
    echo "  export CARGO_TARGET_DIR=\$PWD/target" >&2
    echo "  cargo build --target thumbv7em-none-eabihf -p relulayer-ffi --release" >&2
    exit 1
fi

echo "=== ReluLayer ARM Staticlib Flash Footprint ===" > "$REPORT"
echo "Archive: $ARM_LIB" >> "$REPORT"
ls -lh "$ARM_LIB" >> "$REPORT"
echo "" >> "$REPORT"

cd "$WORK_DIR"
ar x "$ARM_LIB"

echo "--- ReluLayer-specific object sizes ---" >> "$REPORT"
size relulayer_core*.o relulayer_ffi*.o >> "$REPORT"

echo "" >> "$REPORT"
echo "--- Top contributors to archive size (all objects) ---" >> "$REPORT"
find . -maxdepth 1 -type f -name '*.o' -printf '%s %f\n' | sort -rn | head -20 | \
    awk '{printf "%8.2f KB  %s\n", $1/1024, $2}' >> "$REPORT"

echo "" >> "$REPORT"
echo "--- Notes ---" >> "$REPORT"
echo "* The relulayer_core/relulayer_ffi objects are the kernel code that will be" >> "$REPORT"
echo "  pulled into the final firmware image. The large archive size is dominated" >> "$REPORT"
echo "  by compiler_builtins and ARM EABI runtime objects that are only linked when" >> "$REPORT"
echo "  actually referenced by the application (e.g., soft-float helpers)." >> "$REPORT"
echo "* For a true flash footprint, link this archive into your firmware with a" >> "$REPORT"
echo "  target linker script and run arm-none-eabi-size on the resulting .elf." >> "$REPORT"

cat "$REPORT"
echo ""
echo "Report written to: $REPORT"

rm -rf "$WORK_DIR"
