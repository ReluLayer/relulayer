#!/usr/bin/env python3
"""
Lightweight sanity checks from the repository root (imports + architectural audit).
Does not require Ollama, GPU, or Docker to be running.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _root() -> Path:
    # smoke_test.py lives in evaluation/; the project root is one level up.
    return Path(__file__).resolve().parent.parent


def main() -> int:
    root = _root()
    audit = subprocess.run(
        [sys.executable, str(root / "audit.py")],
        cwd=root,
        check=False,
    )
    if audit.returncode != 0:
        return audit.returncode

    sys.path.insert(0, str(root))
    import models.config  # noqa: F401
    import knowledge.ingestion  # noqa: F401
    import orchestration.dspy_modules.modules  # noqa: F401
    import tools.visual_generator  # noqa: F401
    import tools.pptx_builder  # noqa: F401

    print("smoke_test: imports and audit OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
