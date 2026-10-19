#!/usr/bin/env bash
# ReluLayer DP2 Proposal Package Verification Script
# Topic: DAF26BX06-DV026
# Usage: ./verify_proposal_package.sh

set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${SCRIPT_DIR}"
BUILD_DIR="${ROOT}/build"
FEAS_DIR="${ROOT}/feasibility"
TECH_DIR="${ROOT}/technical_volume"
QA_DIR="${ROOT}/qa_responses"

ERRORS=0
WARNINGS=0

log_ok() { printf '  [PASS] %s\n' "$1"; }
log_err() { printf '  [FAIL] %s\n' "$1"; ((ERRORS++)); }
log_warn() { printf '  [WARN] %s\n' "$1"; ((WARNINGS++)); }
log_info() { printf '  [INFO] %s\n' "$1"; }

# Ensure build directory exists.
mkdir -p "${BUILD_DIR}"

echo "=================================================================="
echo "ReluLayer DP2 Proposal Package Verification"
echo "Topic: DAF26BX06-DV026"
echo "=================================================================="

# ------------------------------------------------------------------
# 1. Required directory structure
# ------------------------------------------------------------------
echo ""
echo "[1/7] Directory structure"
for d in "${FEAS_DIR}" "${TECH_DIR}" "${QA_DIR}" "${BUILD_DIR}"; do
    if [[ -d "$d" ]]; then
        log_ok "Directory exists: $d"
    else
        log_err "Missing directory: $d"
    fi
done

# ------------------------------------------------------------------
# 2. Required files present
# ------------------------------------------------------------------
echo ""
echo "[2/7] Required files"
REQUIRED_FILES=(
    "${FEAS_DIR}/feasibility_report.md"
    "${FEAS_DIR}/feasibility_report.tex"
    "${QA_DIR}/dsip_qa_compliance.md"
    "${TECH_DIR}/sow_milestones.md"
)
for f in "${REQUIRED_FILES[@]}"; do
    if [[ -f "$f" ]]; then
        log_ok "File exists: $(basename "$f")"
    else
        log_err "Missing file: $f"
    fi
done

# Check for compiled PDF.
if [[ -f "${FEAS_DIR}/feasibility_report.pdf" ]]; then
    log_ok "Compiled PDF exists: feasibility_report.pdf"
else
    log_warn "Compiled PDF missing: feasibility_report.pdf (run pdflatex/latexmk)"
fi

# ------------------------------------------------------------------
# 3. Word counts
# ------------------------------------------------------------------
echo ""
echo "[3/7] Word counts"
word_count() {
    local file="$1"
    if [[ -f "$file" ]]; then
        # Strip markdown/latex markup for approximate count.
        sed -E 's/\\[a-zA-Z]+(\[[^]]*\])?(\{[^}]*\})?//g; s/\[([^]]+)\]\([^)]+\)/\1/g; s/[#*|_`$]//g' "$file" | wc -w
    else
        echo 0
    fi
}

FEAS_WORDS=$(word_count "${FEAS_DIR}/feasibility_report.md")
QA_WORDS=$(word_count "${QA_DIR}/dsip_qa_compliance.md")
SOW_WORDS=$(word_count "${TECH_DIR}/sow_milestones.md")

log_info "Feasibility Volume (md): ~${FEAS_WORDS} words"
log_info "Q&A Response Matrix:     ~${QA_WORDS} words"
log_info "SOW & Milestones:        ~${SOW_WORDS} words"

if [[ "$FEAS_WORDS" -lt 800 ]]; then
    log_warn "Feasibility Volume is short (< 800 words)."
else
    log_ok "Feasibility Volume meets minimum length."
fi

if [[ "$QA_WORDS" -lt 300 ]]; then
    log_warn "Q&A Response Matrix is short (< 300 words)."
else
    log_ok "Q&A Response Matrix meets minimum length."
fi

if [[ "$SOW_WORDS" -lt 400 ]]; then
    log_warn "SOW & Milestones is short (< 400 words)."
else
    log_ok "SOW & Milestones meets minimum length."
fi

# ------------------------------------------------------------------
# 4. Mandatory benchmark / metric strings
# ------------------------------------------------------------------
echo ""
echo "[4/7] Mandatory benchmark strings"

MANDATORY_METRICS=(
    "42.1 ns"
    "100,000"
    "26.11 ns"
    "400 Hz"
    "27,666"
    "54 B"
    "128 cycles"
    "267 ns"
    "DO-178C Level A"
    "DO-333"
    "DAF26BX06-DV026"
)

# Aggregate all markdown source into one searchable corpus.
COMBINED_MD="${BUILD_DIR}/.combined_md_check.txt"
cat "${FEAS_DIR}/feasibility_report.md" "${QA_DIR}/dsip_qa_compliance.md" "${TECH_DIR}/sow_milestones.md" > "$COMBINED_MD"

for metric in "${MANDATORY_METRICS[@]}"; do
    if grep -Fq "$metric" "$COMBINED_MD"; then
        log_ok "Metric present: $metric"
    else
        log_err "Missing metric: $metric"
    fi
done

# ------------------------------------------------------------------
# 5. Non-dilutive data rights notices
# ------------------------------------------------------------------
echo ""
echo "[5/7] Non-dilutive data rights notices"

DATA_RIGHTS_STRINGS=(
    "SBIR Data Rights"
    "DFARS"
    "FAR 52.227-20"
    "DFARS 252.227-7018"
    "Apache-2.0"
    "MIT"
)

for s in "${DATA_RIGHTS_STRINGS[@]}"; do
    if grep -Fq "$s" "$COMBINED_MD"; then
        log_ok "Data-rights term present: $s"
    else
        log_err "Missing data-rights term: $s"
    fi
done

# ------------------------------------------------------------------
# 6. Table consistency checks
# ------------------------------------------------------------------
echo ""
echo "[6/7] Table consistency"

# Count markdown tables in each file.
FEAS_TABLES=$(grep -cE '^\|.*\|.*\|' "${FEAS_DIR}/feasibility_report.md" || true)
QA_TABLES=$(grep -cE '^\|.*\|.*\|' "${QA_DIR}/dsip_qa_compliance.md" || true)
SOW_TABLES=$(grep -cE '^\|.*\|.*\|' "${TECH_DIR}/sow_milestones.md" || true)

log_info "Markdown table lines: Feasibility=${FEAS_TABLES}, Q&A=${QA_TABLES}, SOW=${SOW_TABLES}"

if [[ "$FEAS_TABLES" -ge 6 ]]; then
    log_ok "Feasibility Volume contains expected tables"
else
    log_warn "Feasibility Volume has fewer table lines than expected"
fi

if [[ "$QA_TABLES" -ge 4 ]]; then
    log_ok "Q&A Response Matrix contains expected tables"
else
    log_warn "Q&A Response Matrix has fewer table lines than expected"
fi

if [[ "$SOW_TABLES" -ge 4 ]]; then
    log_ok "SOW contains expected tables"
else
    log_warn "SOW has fewer table lines than expected"
fi

# ------------------------------------------------------------------
# 7. DSIP compliance trap checks
# ------------------------------------------------------------------
echo ""
echo "[7/7] DSIP compliance trap checks"

DFARS_SOURCE_FILES=(
    "${FEAS_DIR}/feasibility_report.md"
    "${FEAS_DIR}/feasibility_report.tex"
    "${QA_DIR}/dsip_qa_compliance.md"
    "${TECH_DIR}/sow_milestones.md"
)

DFARS_REQUIRED_FIELDS=(
    "SBIR DATA RIGHTS"
    "Contractor Name: Atelier Logic Group LLC dba ReluLayer™"
    "CAGE: 20JX8"
    "UEI: G9WFN3AL69J3"
    "DFARS 252.227-7018"
    "Expiration of SBIR Data Rights Period: October 21, 2046"
)

# (a) Exact DFARS legend field checks.
all_dfars_ok=1
for target_file in "${DFARS_SOURCE_FILES[@]}"; do
    for field in "${DFARS_REQUIRED_FIELDS[@]}"; do
        if grep -Fq "$field" "$target_file"; then
            log_ok "'$(basename "$target_file")' contains DFARS field: '$field'"
        else
            log_err "'$(basename "$target_file")' missing DFARS field: '$field'"
            all_dfars_ok=0
        fi
    done
done

if [[ "$all_dfars_ok" -eq 1 ]]; then
    log_ok "All DFARS legend fields present in all source files."
fi

# (b) Expiration date consistency across files.
exp_dates=$(grep -hF "Expiration of SBIR Data Rights Period" "${DFARS_SOURCE_FILES[@]}" 2>/dev/null | sort -u | wc -l)
if [[ "$exp_dates" -eq 1 ]]; then
    log_ok "SBIR Data Rights expiration date is consistent across all source files."
else
    log_err "SBIR Data Rights expiration date is inconsistent across source files."
fi

# (c) Anti-ITAR / wrong-clause trap detection.
BANNED_STRINGS=(
    "ITAR"
    "DISTRIBUTION STATEMENT D"
    "252.227-7013"
    "252.227-7992"
    "Data Protection Period"
)

trap_found=0
for target_file in "${DFARS_SOURCE_FILES[@]}"; do
    for bad in "${BANNED_STRINGS[@]}"; do
        if grep -qwi "$bad" "$target_file"; then
            log_err "'$(basename "$target_file")' contains banned compliance string: '$bad'"
            trap_found=1
        fi
    done
done

if [[ "$trap_found" -eq 0 ]]; then
    log_ok "No ITAR, Distribution Statement D, non-SBIR DFARS clauses, or non-standard 'Data Protection Period' strings found."
fi

# (d) PDF freshness check.
PDF_SRC="${FEAS_DIR}/feasibility_report.tex"
PDF_OUT="${FEAS_DIR}/feasibility_report.pdf"
if [[ -f "$PDF_OUT" ]]; then
    if [[ "$PDF_OUT" -nt "$PDF_SRC" ]]; then
        log_ok "Compiled PDF is newer than its LaTeX source."
    else
        log_warn "Compiled PDF is older than its LaTeX source; rebuild with pdflatex."
    fi
else
    log_warn "Compiled PDF missing; rebuild with pdflatex."
fi

# (e) Page-count sanity check.
if command -v pdfinfo >/dev/null 2>&1 && [[ -f "$PDF_OUT" ]]; then
    pages=$(pdfinfo "$PDF_OUT" | awk '/Pages:/ {print $2}')
    if [[ "$pages" =~ ^[0-9]+$ ]]; then
        log_info "Compiled PDF page count: $pages"
        if [[ "$pages" -ge 5 && "$pages" -le 15 ]]; then
            log_ok "PDF page count ($pages) is within the expected 5–15 page range."
        else
            log_warn "PDF page count ($pages) is outside the expected 5–15 page range."
        fi
    else
        log_warn "Could not determine PDF page count."
    fi
else
    log_warn "pdfinfo not available; skipping PDF page-count check."
fi

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
echo ""
echo "=================================================================="
echo "Verification Summary"
echo "=================================================================="
printf "Errors:   %d\n" "$ERRORS"
printf "Warnings: %d\n" "$WARNINGS"

if [[ "$ERRORS" -eq 0 ]]; then
    echo ""
    echo "RESULT: ALL MANDATORY CHECKS PASSED"
    echo "The proposal package is ready for DSIP upload pending any open warnings."
    exit 0
else
    echo ""
    echo "RESULT: VERIFICATION FAILED"
    echo "Correct the errors above before uploading."
    exit 1
fi
