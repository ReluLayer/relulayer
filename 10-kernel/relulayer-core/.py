#!/usr/bin/env python3
import os
import subprocess
from pathlib import Path

ORGANIZATIONS = Path("/home/iamin/Organizations")
ALG = ORGANIZATIONS / "AtelierLogicGroup"
RELULAYER = ORGANIZATIONS / "ReluLayer"

print("=" * 80)
print("     ENTERPRISE REPOSITORY & TOPOLOGY AUDIT: ALG & RELULAYER")
print("=" * 80)
print(f"Root: {ORGANIZATIONS}\n")

# 1. Inspect Entity Identity & Governance
print("--- [1/4] Canonical Entity Identity & Root Governance ---")
gov_file = ALG / "00-governance" / "entity-identity.md"
if gov_file.exists():
    print(f"  [+] Found: {gov_file}")
    try:
        with open(gov_file, encoding="utf-8", errors="replace") as f:
            for line in [next(f) for _ in range(20)]:
                print(f"      | {line.rstrip()}")
    except Exception as e:
        print(f"      [!] Error reading: {e}")
else:
    print(f"  [-] {gov_file} not found directly; searching for governance files...")
    for p in ALG.glob("**/entity-identity.md"):
        print(f"      Found candidate: {p}")

# 2. Map all Git Repositories in AtelierLogicGroup
print("\n--- [2/4] Git Repositories in AtelierLogicGroup ---")
if ALG.exists():
    git_dirs = sorted(ALG.glob("**/.git"))
    git_dirs = [g for g in git_dirs if "target" not in g.parts and "node_modules" not in g.parts and ".venv" not in g.parts]
    if git_dirs:
        for g in git_dirs:
            repo_root = g.parent
            branch = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
                                    capture_output=True, text=True).stdout.strip() or "detached"
            remote = subprocess.run(["git", "-C", str(repo_root), "remote", "get-url", "origin"],
                                    capture_output=True, text=True).stdout.strip() or "No origin"
            rel_path = repo_root.relative_to(ORGANIZATIONS)
            print(f"  * Repo: {rel_path}")
            print(f"    Branch: {branch} | Remote: {remote}")
    else:
        print("  [-] No independent .git repos found inside AtelierLogicGroup.")
else:
    print(f"  [!] {ALG} does not exist.")

# 3. Two-Level Directory Layout of AtelierLogicGroup
print("\n--- [3/4] AtelierLogicGroup Subdirectory Layout ---")
if ALG.exists():
    for item in sorted(ALG.glob("*")):
        if item.name.startswith(".") or item.name in ["target", "node_modules", ".venv"]:
            continue
        print(f"  Folder: {item.name}/")
        if item.is_dir():
            for sub in sorted(item.glob("*")):
                if sub.name.startswith(".") or sub.name in ["target", "node_modules", ".venv"]:
                    continue
                # Mark if sub has .git
                has_git = " [GIT REPO]" if (sub / ".git").exists() else ""
                print(f"    ├── {sub.name}{has_git}")

# 4. Compare ReluLayer vs AtelierLogicGroup Structure
print("\n--- [4/4] Cross-Entity Alignment ---")
print(f"  AtelierLogicGroup top-level directories: {[d.name for d in sorted(ALG.glob('*')) if d.is_dir() and not d.name.startswith('.')]}")
print(f"  ReluLayer top-level directories:         {[d.name for d in sorted(RELULAYER.glob('*')) if d.is_dir() and not d.name.startswith('.')]}")

print("\n" + "=" * 80)
print("                     AUDIT READY")
print("=" * 80)