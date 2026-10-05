"""
Path P — optional local TTS for executive briefing rehearsal.

Set ``RELULAYER_PIPER_BIN`` (default ``piper``) and ``RELULAYER_PIPER_MODEL`` to a Piper
``.onnx`` model path. Piper must be on PATH or use an absolute binary path.

Browser ``speechSynthesis`` in the UI works without this.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def piper_synthesize_wav(
    text: str,
    *,
    project_root: Path,
    max_chars: int = 8000,
) -> str | None:
    """
    Write a WAV under ``assets/outputs/tts/`` via Piper stdin.

    Returns static href e.g. ``/static/outputs/tts/brief_....wav``, or None if disabled/failed.
    """
    model = os.environ.get("RELULAYER_PIPER_MODEL", "").strip()
    if not model:
        return None
    piper_bin = os.environ.get("RELULAYER_PIPER_BIN", "piper").strip() or "piper"
    clean = (text or "").strip()
    if not clean:
        return None
    clean = clean[:max_chars]

    out_dir = project_root / "assets" / "outputs" / "tts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_wav = out_dir / f"brief_{time.time_ns()}.wav"
    assets_root = (project_root / "assets").resolve()

    try:
        proc = subprocess.run(
            [piper_bin, "--model", model, "--output_file", str(out_wav)],
            input=clean.encode("utf-8"),
            capture_output=True,
            timeout=180,
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", errors="replace")[:500]
            logger.warning("narrative_tts.piper_failed rc=%s err=%s", proc.returncode, err)
            return None
        if not out_wav.is_file():
            return None
        rel = out_wav.resolve().relative_to(assets_root)
        return f"/static/{rel.as_posix()}"
    except FileNotFoundError:
        logger.warning("narrative_tts.piper_binary_missing bin=%r", piper_bin)
        return None
    except subprocess.TimeoutExpired:
        logger.warning("narrative_tts.piper_timeout")
        return None
    except Exception:
        logger.exception("narrative_tts.piper_unexpected")
        return None
