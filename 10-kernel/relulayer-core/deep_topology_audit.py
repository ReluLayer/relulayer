#!/usr/bin/env python3
import os
import subprocess
import glob
from pathlib import Path

ORGANIZATIONS = Path("/home/iamin/Organizations")
HOME = Path("/home/iamin")

print("=" * 80)
print("      DEEP REPOSITORY, TOPOLOGY & GOVERNANCE AUDIT")
print("=" * 80)
print(f"Organizations Root: {ORGANIZATIONS}")
print(f"Working Directory:  {Path.cwd()}\n")

# 1. Inspect all .git directories in ~/Organizations
print("--- [1/5] Discovering Git Repositories and Remotes ---")
git_dirs = sorted(ORGANIZATIONS.glob("**/.git"))
# Filter out target/ dirs
git_dirs = [g for g in git_dirs if "target" not in g.parts]

for g in git_dirs:
    repo_root = g.parent
    branch_proc = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
                                 capture_output=True, text=True)
    branch = branch_proc.stdout.strip() or "detached"
    
    remote_proc = subprocess.run(["git", "-C", str(repo_root), "remote", "get-url", "origin"],
                                 capture_output=True, text=True)
    remote = remote_proc.stdout.strip() or "No origin remote"
    
    print(f"  * Repo: {repo_root}")
    print(f"    Branch: {branch} | Remote: {remote}")

# 2. Check Git status of /home/iamin/Organizations and /home/iamin
print("\n--- [2/5] Git Context Analysis ---")
for check_path in [ORGANIZATIONS, ORGANIZATIONS / "ReluLayer"]:
    if (check_path / ".git").exists():
        print(f"  [+] DIRECT .git found at: {check_path}")
    else:
        print(f"  [-] No .git at: {check_path}")

org_top = subprocess.run(["git", "-C", str(ORGANIZATIONS), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True).stdout.strip()
print(f"  Current Git toplevel according to Git: {org_top}")

if (ORGANIZATIONS / ".gitignore").exists():
    print(f"\n  Inspecting {ORGANIZATIONS / '.gitignore'}:")
    with open(ORGANIZATIONS / ".gitignore") as f:
        for idx, line in enumerate(f, 1):
            if any(term in line.lower() for term in ["relu", "target", "kernel", "org"]):
                print(f"    Line {idx}: {line.strip()}")

# 3. Discover Cursor rules (.cursorrules, .cursor/rules/)
print("\n--- [3/5] Cursor Rules & Governance Directives ---")
cursor_candidates = []
cursor_candidates.extend(HOME.glob(".cursorrules"))
cursor_candidates.extend(HOME.glob(".cursor/rules/*"))
cursor_candidates.extend(ORGANIZATIONS.glob("**/.cursorrules"))
cursor_candidates.extend(ORGANIZATIONS.glob("**/.cursor/rules/*"))

cursor_files = [f for f in sorted(set(cursor_candidates)) if f.is_file() and "target" not in f.parts]

if cursor_files:
    print(f"  Found {len(cursor_files)} Cursor rule configuration file(s):")
    for cf in cursor_files:
        print(f"\n  === Asset: {cf} ({cf.stat().st_size} bytes) ===")
        try:
            with open(cf, encoding="utf-8", errors="replace") as f:
                lines = [next(f) for _ in range(15)]
                for line in lines:
                    print(f"    | {line.rstrip()}")
        except StopIteration:
            pass
        except Exception as e:
            print(f"    [!] Error reading: {e}")
else:
    print("  [-] No .cursorrules or .cursor/rules/ files discovered.")

# 4. Search for PRDs, System Specifications, and Roadmaps
print("\n--- [4/5] PRDs, System Specs, and Roadmaps ---")
doc_files = []
patterns = ["*prd*.md", "*spec*.md", "*roadmap*.md", "*architecture*.md", "*requirements*.md"]
for pat in patterns:
    for p in ORGANIZATIONS.glob(f"**/{pat}"):
        if "target" not in p.parts and ".git" not in p.parts:
            doc_files.append(p)

doc_files = sorted(set(doc_files))
if doc_files:
    print(f"  Found {len(doc_files)} specification document(s):")
    for df in doc_files:
        print(f"\n  === Document: {df} ===")
        try:
            with open(df, encoding="utf-8", errors="replace") as f:
                lines = [next(f) for _ in range(15)]
                for line in lines:
                    print(f"    | {line.rstrip()}")
        except StopIteration:
            pass
        except Exception as e:
            print(f"    [!] Error reading: {e}")
else:
    print("  [-] No explicit PRD or spec markdown files found in Organizations.")

# 5. Directory layout inside ReluLayer
print("\n--- [5/5] ReluLayer Subdirectory Layout ---")
relulayer_root = ORGANIZATIONS / "ReluLayer"
if relulayer_root.exists():
    for item in sorted(relulayer_root.glob("*")):
        if item.name.startswith(".") or item.name == "target":
            continue
        print(f"  Folder: {item.name}/")
        if item.is_dir():
            for sub in sorted(item.glob("*")):
                if sub.name.startswith(".") or sub.name == "target":
                    continue
                print(f"    ├── {sub.name}")
else:
    print(f"  [!] {relulayer_root} does not exist.")

print("\n" + "=" * 80)
print("                       AUDIT COMPLETED")
print("=" * 80)