#!/usr/bin/env python3
"""
ReluLayer Engine — architectural audit (9-Layer integrity, DSPy, VRAM, deterministic boundary, RateLimiter).
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Severity(Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class Finding:
    severity: Severity
    category: str
    message: str
    path: Path | None = None
    line: int | None = None

    def line_suffix(self) -> str:
        return f":{self.line}" if self.line is not None else ""


@dataclass
class AuditState:
    findings: list[Finding] = field(default_factory=list)

    def add(
        self,
        severity: Severity,
        category: str,
        message: str,
        path: Path | None = None,
        line: int | None = None,
    ) -> None:
        self.findings.append(
            Finding(severity, category, message, path=path, line=line)
        )

    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.CRITICAL)


# --- Layer / PRD expectations -------------------------------------------------

# 1. THE 9 LAYERS (Must be Directories)
MANDATORY_LAYERS = {
    "infrastructure", "security", "data", "knowledge",
    "models", "orchestration", "tools", "evaluation", "frontend"
}

# 2. THE COMPLIANCE GATE (Must be Files)
MANDATORY_FILES = {
    "LICENSE", "README.md", "PRD.md", ".cursorrules", "ARCHITECTURE.md"
}

# 3. THE ALLOWLIST (Permitted but not strictly required by the engine)
ALLOWLIST = {
    "docs", "assets", "tests", "smoke_test.py", "audit.py", "manage.sh",
    "CHANGELOG.md", "SECURITY.md", ".git", ".github", ".cursor",
    ".vscode", ".gitignore", "__pycache__", ".pytest_cache"
}

# Explicit junk / scratch names at repo root (case-insensitive match).
JUNK_ROOT_NAMES = frozenset(
    {"tmp", "temp", "junk", "trash", "scratch", "old", "backup", "untitled", "misc"}
)

# Heuristics: raw prompt material in orchestration (Layer 6).
PROMPT_PHRASES_RE = re.compile(
    r"(you\s+are\s+an?|you're\s+an?|act\s+as\s+(a|an)?|system\s*:|###\s*instruction|"
    r"^\s*instructions\s*:)",
    re.IGNORECASE | re.MULTILINE,
)

_TRIPLE_QUOTED_RE = re.compile(r'^[rRfFbBuU]*("""|\'\'\')')

MULTILINE_INSTRUCTION_BLOCK = re.compile(
    r"\binstructions?\b\s*:|\byou\s+are\s+an?\b",
    re.IGNORECASE,
)

# LLM / orchestration imports forbidden in tools/ (deterministic execution plane).
FORBIDDEN_TOOLS_IMPORTS = frozenset(
    {"dspy", "dspy_ai", "ollama", "openai", "anthropic", "litellm", "langchain", "instructor"}
)


def _repo_root() -> Path:
    # audit.py lives in evaluation/; the project root is one level up.
    return Path(__file__).resolve().parent.parent


def _iter_py_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.py") if p.is_file())


def _collect_import_modules(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod_name = getattr(node, 'module', None) or (node.names[0].name if hasattr(node, 'names') else "")
            base = mod_name.split(".", 1)[0]
            if base:
                names.add(base)
    return names


def _file_imports_torch(source: str) -> bool:
    return bool(re.search(r"^\s*(import|from)\s+torch\b", source, re.MULTILINE))


def _file_calls_vram_clear(source: str) -> bool:
    return "VRAMManager.clear(" in source


def _file_uses_dspy_construct(source: str) -> bool:
    return bool(re.search(r"\bdspy\.(Signature|Module)\b|class\s+\w+\s*\(\s*dspy\.(Signature|Module)\s*\)", source))


def audit_directory_integrity(root: Path, state: AuditState) -> None:
    # 1. Check Mandatory Layers (Directories)
    for name in MANDATORY_LAYERS:
        p = root / name
        if not p.is_dir():
            state.add(Severity.CRITICAL, "directory_integrity", f"Missing mandatory layer directory `{name}/`.", path=p)

    # 2. Check Mandatory Governance (Files)
    for name in MANDATORY_FILES:
        if name == "PRD.md":
            candidates = (root / "PRD.md", root / "docs" / "PRD.md")
            if not any(p.is_file() for p in candidates):
                state.add(
                    Severity.CRITICAL,
                    "directory_integrity",
                    "Missing mandatory PRD at `PRD.md` or `docs/PRD.md`.",
                    path=root / "docs" / "PRD.md",
                )
            continue
        p = root / name
        if not p.is_file():
            state.add(Severity.CRITICAL, "directory_integrity", f"Missing mandatory governance file `{name}`.", path=p)

    # 3. Drift Check (Unified Allowlist)
    sanctioned = {*MANDATORY_LAYERS, *MANDATORY_FILES, *ALLOWLIST}
    
    try:
        for entry in root.iterdir():
            if entry.name in sanctioned:
                continue
                
            lower_name = entry.name.lower()
            if lower_name in JUNK_ROOT_NAMES:
                state.add(Severity.WARNING, "directory_integrity", f"Junk item `{entry.name}` found in root.", path=entry)
            else:
                state.add(Severity.WARNING, "directory_integrity", f"Unsanctioned root item `{entry.name}`. Potential architectural drift.", path=entry)
    except OSError as e:
        state.add(Severity.CRITICAL, "directory_integrity", f"Cannot read root: {e}", path=root)


def _build_parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    """Map each child AST node to its parent."""
    parent_map: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_map[child] = parent
    return parent_map


def _inherits_from_dspy_signature(node: ast.ClassDef) -> bool:
    """Return True if the class inherits from dspy.Signature."""
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id == "Signature":
            return True
        if isinstance(base, ast.Attribute) and base.attr == "Signature":
            return True
    return False


def _is_dspy_signature_docstring(
    node: ast.Constant, parent_map: dict[ast.AST, ast.AST]
) -> bool:
    """Return True if the string constant is the docstring of a dspy.Signature class."""
    expr = parent_map.get(node)
    if not isinstance(expr, ast.Expr):
        return False
    class_node = parent_map.get(expr)
    if not isinstance(class_node, ast.ClassDef):
        return False
    if not class_node.body or class_node.body[0] is not expr:
        return False
    return _inherits_from_dspy_signature(class_node)


def _is_triple_quoted(segment: str) -> bool:
    """Return True if the source segment is a triple-quoted string literal."""
    return bool(_TRIPLE_QUOTED_RE.match(segment.strip()))


def audit_dspy_compliance(orchestration: Path, state: AuditState) -> None:
    if not orchestration.is_dir():
        return
    for path in _iter_py_files(orchestration):
        source = path.read_text(encoding="utf-8", errors="replace")

        try:
            tree = ast.parse(source)
        except SyntaxError:
            state.add(Severity.CRITICAL, "parse", "SyntaxError", path=path)
            continue

        parent_map = _build_parent_map(tree)

        # AST check for f-string prompts
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                text = "".join(
                    v.value
                    if isinstance(v, ast.Constant) and isinstance(v.value, str)
                    else ""
                    for v in node.values
                )
                if PROMPT_PHRASES_RE.search(text):
                    state.add(
                        Severity.CRITICAL,
                        "dspy_compliance",
                        "F-string resembles raw prompt; use DSPy Signatures.",
                        path=path,
                        line=node.lineno,
                    )

        # AST check for multi-line string blocks that look like raw prompts.
        # Docstrings of classes inheriting from dspy.Signature are allowed,
        # because DSPy Signatures legitimately use their docstring as a typed prompt.
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if _is_dspy_signature_docstring(node, parent_map):
                continue
            segment = ast.get_source_segment(source, node)
            if not segment or not _is_triple_quoted(segment):
                continue
            if MULTILINE_INSTRUCTION_BLOCK.search(node.value):
                state.add(
                    Severity.CRITICAL,
                    "dspy_compliance",
                    "Multi-line string block resembles raw prompt outside a DSPy Signature docstring.",
                    path=path,
                    line=node.lineno,
                )


def audit_vram(root: Path, state: AuditState) -> None:
    for layer in ("orchestration", "tools"):
        base = root / layer
        for path in _iter_py_files(base):
            source = path.read_text(encoding="utf-8", errors="replace")
            if _file_imports_torch(source) and not _file_calls_vram_clear(source):
                state.add(Severity.CRITICAL, "vram_safety", "Imports `torch` but missing `VRAMManager.clear()`.", path=path.relative_to(root))


def audit_deterministic_tools(root: Path, state: AuditState) -> None:
    tools = root / "tools"
    for path in _iter_py_files(tools):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            bad = sorted(_collect_import_modules(tree) & FORBIDDEN_TOOLS_IMPORTS)
            if bad:
                state.add(Severity.CRITICAL, "deterministic_boundary", f"Tools must not import LLM stacks: {', '.join(bad)}.", path=path.relative_to(root))
        except SyntaxError:
            continue


def print_report(state: AuditState, root: Path) -> None:
    width = 72
    print("=" * width)
    print(" ReluLayer Audit Report ".center(width, "="))
    print(f"Root: {root}\n")

    if not state.findings:
        print("Status: PASS — No findings.")
    else:
        for sev in Severity:
            items = [f for f in state.findings if f.severity == sev]
            if items:
                print(f"--- {sev.value} ({len(items)}) ---")
                for item in items:
                    print(f"  [{item.category}] {item.message}\n    → {item.path or 'Root'}{item.line_suffix()}")

    print("=" * width)
    sys.exit(1 if state.critical_count() else 0)


def main():
    root = _repo_root().resolve()
    state = AuditState()
    audit_directory_integrity(root, state)
    audit_dspy_compliance(root / "orchestration", state)
    audit_vram(root, state)
    audit_deterministic_tools(root, state)
    print_report(state, root)


if __name__ == "__main__":
    main()