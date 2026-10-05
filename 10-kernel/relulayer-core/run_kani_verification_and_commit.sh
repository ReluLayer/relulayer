#!/bin/bash
set -e

# Run AWS Kani formal verification suite for the relulayer-core crate

echo "Running Kani verification suite..."

# Set the cargo manifest directory to ensure correct resolution
export CARGO_MANIFEST_DIR="/home/iamin/Organizations/ReluLayer/10-kernel/relulayer-core"

cargo kani --manifest-path /home/iamin/Organizations/ReluLayer/10-kernel/relulayer-core/Cargo.toml

# Optionally: commit changes if verification passes (if in a git repo)
# git add .
# git commit -m "Run Kani formal verification and update proofs"
