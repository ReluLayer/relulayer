#!/usr/bin/env bash
set -euo pipefail

MONOREPO_ROOT="/home/iamin/Organizations/ReluLayer"
OSS_MIRROR_DIR="/home/iamin/Dist/relulayer-oss"
GIT_AUTHOR_NAME="Ishmael Amin"
GIT_AUTHOR_EMAIL="ishmael.amin@outlook.com"

echo "=== ReluLayer™ OSS Synchronization Pipeline ==="

if [ ! -d "$MONOREPO_ROOT" ] || [ ! -d "$OSS_MIRROR_DIR" ]; then
    echo "[-] Error: Specified directories do not exist."
    exit 1
fi

cd "$MONOREPO_ROOT"

if [ -n "$(git status --porcelain)" ]; then
    echo "[-] Error: Monorepo working tree is dirty. Commit changes first."
    exit 1
fi

echo "[+] Syncing open-core tree to mirror..."
rsync -av --delete \
    --exclude='.git' \
    --exclude='target' \
    --exclude='crates/relulayer-safety' \
    --exclude='crates/relulayer-fleet' \
    --exclude='compliance' \
    --exclude='COMMERCIAL.md' \
    --exclude='sync-mirror.sh' \
    "$MONOREPO_ROOT/" "$OSS_MIRROR_DIR/"

# Strip proprietary workspace members from the public mirror's Cargo.toml
echo "[+] Sanitizing public mirror Cargo.toml..."
sed -i '/"crates\/relulayer-safety",/d' "$OSS_MIRROR_DIR/Cargo.toml"
sed -i '/"crates\/relulayer-fleet",/d' "$OSS_MIRROR_DIR/Cargo.toml"

cd "$OSS_MIRROR_DIR"
git config user.name "$GIT_AUTHOR_NAME"
git config user.email "$GIT_AUTHOR_EMAIL"

# Verify that the mirror workspace compiles standalone
echo "[+] Verifying public mirror workspace standalone compilation..."
cargo check --workspace

if [ -n "$(git status --porcelain)" ]; then
    git add -A
    git commit -m "relulayer-oss: sanitize workspace manifest for open-core release"
    echo "[+] Public mirror committed cleanly."
else
    echo "[+] Public mirror is already up to date."
fi

echo "=== Synchronization Complete ==="
