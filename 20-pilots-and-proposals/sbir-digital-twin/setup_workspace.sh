#!/usr/bin/env bash
set -e

echo "=== Creating ReluLayer Multi-Crate Workspace Structure ==="

# 1. Create workspace root Cargo.toml
cat << 'CARGO' > Cargo.toml
[workspace]
members = [
    "crates/relulayer-core",
    "crates/relulayer-ffi",
    "crates/relulayer-py",
]
resolver = "2"
CARGO

# 2. Create directory hierarchy
mkdir -p crates/relulayer-core/src
mkdir -p crates/relulayer-ffi/src
mkdir -p crates/relulayer-py/src

# 3. Create relulayer-core Manifest
cat << 'CARGO' > crates/relulayer-core/Cargo.toml
[package]
name = "relulayer-core"
version = "0.1.0"
edition = "2021"
authors = ["Atelier Logic Group LLC"]

[dependencies]
# Zero external dependencies for strict #![no_std] compliance
CARGO

# 4. Create relulayer-py Manifest (PyO3)
cat << 'CARGO' > crates/relulayer-py/Cargo.toml
[package]
name = "relulayer-py"
version = "0.1.0"
edition = "2021"

[lib]
name = "relulayer_py"
crate-type = ["cdylib"]

[dependencies]
relulayer-core = { path = "../relulayer-core" }
pyo3 = { version = "0.20", features = ["extension-module"] }
CARGO

echo "✅ Workspace directory structure created successfully!"
