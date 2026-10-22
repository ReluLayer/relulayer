#!/bin/bash
set -e

# Run AWS Kani formal verification suite for the relulayer-core crate

echo "Running Kani verification suite..."

# Set the cargo manifest directory to ensure correct resolution
export CARGO_MANIFEST_DIR="/home/iamin/Organizations/ReluLayer/10-kernel/relulayer-core"

# Run each relulayer-core harness individually with a timeout and explicit harness.
timeout 60s cargo kani --manifest-path /home/iamin/Organizations/ReluLayer/10-kernel/relulayer-core/Cargo.toml --harness verify_active_set_no_panics
timeout 60s cargo kani --manifest-path /home/iamin/Organizations/ReluLayer/10-kernel/relulayer-core/Cargo.toml --harness verify_feasible_bounds
timeout 60s cargo kani --manifest-path /home/iamin/Organizations/ReluLayer/10-kernel/relulayer-core/Cargo.toml --harness verify_infeasible_fallback_boundedness
timeout 60s cargo kani --manifest-path /home/iamin/Organizations/ReluLayer/10-kernel/relulayer-core/Cargo.toml --harness verify_deterministic_wcet
timeout 60s cargo kani --manifest-path /home/iamin/Organizations/ReluLayer/10-kernel/relulayer-core/Cargo.toml --harness verify_multivar_no_panics
timeout 60s cargo kani --manifest-path /home/iamin/Organizations/ReluLayer/10-kernel/relulayer-core/Cargo.toml --harness verify_multivar_actuator_bounds
timeout 60s cargo kani --manifest-path /home/iamin/Organizations/ReluLayer/10-kernel/relulayer-core/Cargo.toml --harness verify_multivar_iteration_bound

# Optionally: commit changes if verification passes (if in a git repo)
# git add .
# git commit -m "Run Kani formal verification and update proofs"
