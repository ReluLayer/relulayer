#!/usr/bin/env bash

# ==============================================================================

# SCRIPT: audit_repo_topology.sh (Comprehensive Read-Only Inspection)

# PURPOSE: Deep audit of Git boundaries, .gitignore rules, Cursor governance

# (.cursorrules, .cursor/rules/), PRDs, and architecture specifications

# across \~/Organizations and \~/Organizations/ReluLayer.

# ==============================================================================

set -euo pipefail

CYAN='\\033\[0;36m'
GREEN='\\033\[0;32m'
YELLOW='\\033\[1;33m'
BLUE='\\033\[0;34m'
MAGENTA='\\033\[0;35m'
RED='\\033\[0;31m'
BOLD='\\033\[1m'
NC='\\033\[0m'

ORGANIZATIONS_DIR="/home/iamin/Organizations"
RELULAYER_DIR="\${ORGANIZATIONS_DIR}/ReluLayer"

echo -e "${CYAN}==============================================================================${NC}"
echo -e "${CYAN}       COMPREHENSIVE REPOSITORY, GOVERNANCE & TOPOLOGY AUDIT${NC}"
echo -e "${CYAN}==============================================================================${NC}"
echo -e "Audit initiated: \$(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo -e "Inspection Scope: ${ORGANIZATIONS_DIR} and${RELULAYER_DIR}\\n"

# ------------------------------------------------------------------------------

# 1. GIT REPOSITORY BOUNDARIES & REMOTES

# ------------------------------------------------------------------------------

echo -e "${BLUE}[1/6] Mapping Git Repository Boundaries & Active Remotes...${NC}"

if \[ -d "${ORGANIZATIONS_DIR}/.git" ]; then
echo -e "  ${GREEN}[+] Git Root at Organizations:${NC}${ORGANIZATIONS_DIR}"
echo -e "      Active Branch: $(git -C "${ORGANIZATIONS_DIR}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'none')"
echo -e "      Remote Origin: $(git -C "${ORGANIZATIONS_DIR}" remote get-url origin 2>/dev/null || echo 'None configured')"
echo -e "      Commit SHA:    $(git -C "${ORGANIZATIONS_DIR}" rev-parse --short HEAD 2>/dev/null || echo 'none')"
else
echo -e "  ${YELLOW}[-] No .git repository directly at Organizations root.${NC}"
fi

if \[ -d "${RELULAYER_DIR}/.git" ]; then
echo -e "  ${GREEN}[+] Git Root inside ReluLayer:${NC}${RELULAYER_DIR}"
echo -e "      Active Branch: $(git -C "${RELULAYER_DIR}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'none')"
echo -e "      Remote Origin: $(git -C "${RELULAYER_DIR}" remote get-url origin 2>/dev/null || echo 'None configured')"
echo -e "      Commit SHA:    $(git -C "${RELULAYER_DIR}" rev-parse --short HEAD 2>/dev/null || echo 'none')"
else
echo -e "  ${YELLOW}[-] No independent .git directory found inside ReluLayer.${NC}"
fi

echo -e "\\n  All discoverable .git directories up to 4 levels deep:"
find "${ORGANIZATIONS_DIR}" -maxdepth 4 -name ".git" -type d 2>/dev/null | sort | while IFS= read -r git_dir; do
repo_path="$(dirname "$git_dir")"
branch="$(git -C "$repo_path" rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')"
remote="$(git -C "$repo_path" remote get-url origin 2>/dev/null || echo 'No remote')"
echo -e "    -> ${GREEN}Repo:${NC}${repo_path} \[Branch: ${CYAN}${branch}${NC}] [Remote:${MAGENTA}${remote}${NC}\]"
done

# ------------------------------------------------------------------------------

# 2. GIT IGNORE TRACE & ROOT CAUSE ANALYSIS

# ------------------------------------------------------------------------------

echo -e "\\n\${BLUE}\[2/6\] Tracing Git Ignore Rules Affecting ReluLayer...${NC}"

if \[ -f "${ORGANIZATIONS_DIR}/.gitignore" ]; then
echo -e "  ${GREEN}[+] Found:${NC}${ORGANIZATIONS_DIR}/.gitignore"
echo "  --- Lines referencing 'relu' (case-insensitive) ---"
grep -n -i "relu" "\${ORGANIZATIONS_DIR}/.gitignore" || echo "  (No line explicitly matched 'relu')"
echo "  --------------------------------------------------"
else
echo -e "  \${YELLOW}\[-\] No .gitignore located at ${ORGANIZATIONS_DIR}/.gitignore${NC}"
fi

echo -e "\\n  Evaluating 'git check-ignore -v' from Organizations root:"
(cd "\${ORGANIZATIONS_DIR}" && git check-ignore -v ReluLayer 2>/dev/null && echo "  -> ReluLayer is actively ignored by the rule above!" || echo "  -> ReluLayer is not ignored by standard gitignore rules.")

echo -e "\\n  Evaluating 'git check-ignore -v' on kernel files:"
(cd "\${ORGANIZATIONS_DIR}" && git check-ignore -v ReluLayer/10-kernel/relulayer-core/Cargo.toml 2>/dev/null || echo "  -> Kernel files not explicitly matched by check-ignore.")

# ------------------------------------------------------------------------------

# 3. CURSOR RULES & AGENT GOVERNANCE (.cursorrules, .cursor/rules/)

# ------------------------------------------------------------------------------

echo -e "\\n\${BLUE}\[3/6\] Discovering Cursor Rules & AI Agent Directives...${NC}"

CURSOR_FILES=()
while IFS= read -r file; do
\[ -n "\$file" \] && CURSOR_FILES+=("$file")
done < <(find "${ORGANIZATIONS_DIR}" -maxdepth 5 $-name ".cursorrules" -o -path "*/.cursor/rules/*" -o -name ".cursor"$ 2>/dev/null | sort)

# Also check user home root for global cursor rules

if \[ -f "/home/iamin/.cursorrules" \]; then
CURSOR_FILES+=("/home/iamin/.cursorrules")
fi
if \[ -d "/home/iamin/.cursor/rules" \]; then
while IFS= read -r file; do
\[ -n "\$file" \] && CURSOR_FILES+=("$file")
done < <(find "/home/iamin/.cursor/rules" -type f 2>/dev/null | sort)
fi

if \[ ${#CURSOR_FILES[@]} -gt 0 ]; then
echo -e "  ${GREEN}[+] Located${#CURSOR_FILES[@]} Cursor configuration/rule asset(s):${NC}"
for cf in "${CURSOR_FILES[@]}"; do
echo -e "\n  ${BOLD}--- Asset:${CYAN}${cf}\${NC} ---"
if \[ -f "\$cf" \]; then
echo -e "  Size: \$(wc -c < "$cf") bytes | Lines: $(wc -l < "$cf")"
echo "  Preview (first 15 lines):"
head -n 15 "\$cf" | sed 's/^/    | /'
if \[ \$(wc -l < "$cf") -gt 15 \]; then
echo "    | ... \[truncated, total \$(wc -l < "$cf") lines\]"
fi
elif \[ -d "\$cf" \]; then
echo "  (Directory) Contents:"
ls -la "\$cf" | sed 's/^/    | /'
fi
done
else
echo -e "  ${YELLOW}[-] No .cursorrules or .cursor/rules/ files discovered in Organizations or home.${NC}"
fi

# ------------------------------------------------------------------------------

# 4. PRODUCT REQUIREMENT DOCS (PRD) & SPECIFICATION FILES

# ------------------------------------------------------------------------------

echo -e "\\n\${BLUE}\[4/6\] Searching for PRDs, System Specs, Roadmaps & Architecture Docs...${NC}"

DOC_MATCHES=()
while IFS= read -r doc; do
\[ -n "\$doc" \] && DOC_MATCHES+=("$doc")
done < <(find "${ORGANIZATIONS_DIR}" -maxdepth 5 $-iname "*prd*.md" -o -iname "*spec*.md" -o -iname "*roadmap*.md" -o -iname "*architecture*.md" -o -iname "*requirements*.md"$ -not -path "*/target/*" -not -path "*/.git/*" 2>/dev/null | sort)

if \[ ${#DOC_MATCHES[@]} -gt 0 ]; then
echo -e "  ${GREEN}[+] Located${#DOC_MATCHES[@]} PRD/Specification document(s):${NC}"
for doc in "${DOC_MATCHES[@]}"; do
echo -e "\n  ${BOLD}=== Document:${CYAN}${doc}\${NC} ==="
echo -e "  Modified: \$(stat -c %y "$doc" 2>/dev/null \\vert{}\\vert{} date -r "$doc")"
echo "  Preview (first 20 lines):"
head -n 20 "\$doc" | sed 's/^/    | /'
if \[ \$(wc -l < "$doc") -gt 20 ]; then
echo "    | ... [$(wc -l < "\$doc") total lines\]"
fi
done
else
echo -e "  ${YELLOW}[-] No explicit *prd*.md or *spec*.md documents found in the search path.${NC}"
fi

# ------------------------------------------------------------------------------

# 5. CARGO WORKSPACE & PROJECT STRUCTURE

# ------------------------------------------------------------------------------

echo -e "\\n\${BLUE}\[5/6\] Inspecting Cargo Manifests & Project Topologies...${NC}"

find "${ORGANIZATIONS_DIR}" -maxdepth 4 -name "Cargo.toml" -not -path "*/target/*" 2>/dev/null | sort | while IFS= read -r toml; do
echo -e "\n  ${BOLD}--- Manifest:${CYAN}${toml}\${NC} ---"
if grep -q "

$$
workspace
$$

" "\$toml"; then
echo -e "  ${MAGENTA}Type: Workspace Root${NC}"
grep -A 8 "members\\s\*=" "$toml" | sed 's/^/    /' || true
else
pkg_name="$(grep -m 1 '^name\\s\*=' "$toml" | cut -d '=' -f2 | tr -d ' "' || echo 'unknown')"
pkg_version="$(grep -m 1 '^version\\s\*=' "\$toml" | cut -d '=' -f2 | tr -d ' "' || echo 'unknown')"
echo -e "  ${GREEN}Package:${NC} ${pkg_name} (v${pkg_version})"
fi
done

# ------------------------------------------------------------------------------

# 6. DIRECTORY TREE (DEPTH 2) INSIDE RELULAYER

# ------------------------------------------------------------------------------

echo -e "\\n\${BLUE}\[6/6\] ReluLayer Internal Directory Layout...${NC}"
if [ -d "${RELULAYER_DIR}" \]; then
find "\${RELULAYER_DIR}" -maxdepth 3 -not -path '*/.*' -not -path '*/target*' 2>/dev/null | sort | sed 's/^/  /'
else
echo -e "  \${RED}\[!\] Directory ${RELULAYER_DIR} not found.${NC}"
fi

echo -e "\\n\${CYAN}${NC}"
echo -e "${GREEN}                  COMPREHENSIVE AUDIT SCRIPT COMPLETE\${NC}"
echo -e "\${CYAN}${NC}"