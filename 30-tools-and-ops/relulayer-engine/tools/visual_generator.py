from __future__ import annotations

import base64
import gc
import hashlib
import io
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import xml.sax.saxutils as xml_esc
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from infrastructure.vram_manager import VRAMManager
from models.config import (
    image_synth_backend,
    image_synth_diffusion_model_id,
    image_synth_http_url,
)

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent

_ICON_SIZE = 512
_ICON_CORNER_RADIUS_RATIO = 96 / 512

# Hero synthesis (16:9 slide); multiples of 8 for most UNet checkpoints
DEFAULT_SYNTH_WIDTH = 1280
DEFAULT_SYNTH_HEIGHT = 720


def outputs_video_dir(project_root: Path | None = None) -> Path:
    """``assets/outputs/video/`` for Path HH video briefs."""
    root = project_root or _REPO_ROOT
    out = root / "assets" / "outputs" / "video"
    out.mkdir(parents=True, exist_ok=True)
    return out


def video_brief_asset_path(project_root: Path | None = None) -> Path:
    name = f"video_brief_{time.time_ns()}.mp4"
    return outputs_video_dir(project_root) / name


def outputs_synth_dir(project_root: Path | None = None) -> Path:
    """``assets/outputs/synth/`` for AI hero frames."""
    root = project_root or _REPO_ROOT
    out = root / "assets" / "outputs" / "synth"
    out.mkdir(parents=True, exist_ok=True)
    return out


def synth_hero_asset_path(slide_index: int, project_root: Path | None = None) -> Path:
    name = f"hero_slide_{slide_index}_{time.time_ns()}.png"
    return outputs_synth_dir(project_root) / name


def _photographic_negative_default() -> str:
    return (
        "text, watermark, logo, blurry, low quality, deformed, extra limbs, "
        "chart, diagram, screenshot, UI, typography"
    )


def _http_txt2img_automatic1111(
    *,
    base_url: str,
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    steps: int,
) -> bytes:
    url = f"{base_url.rstrip('/')}/sdapi/v1/txt2img"
    payload: dict[str, Any] = {
        "prompt": f"{prompt}, photorealistic, 8k uhd, professional photography, sharp focus",
        "negative_prompt": negative_prompt or _photographic_negative_default(),
        "steps": max(1, min(steps, 80)),
        "width": width,
        "height": height,
        "cfg_scale": float(os.environ.get("RELULAYER_IMAGE_CFG_SCALE", "7")),
        "restore_faces": False,
    }
    sampler = os.environ.get("RELULAYER_IMAGE_SAMPLER", "DPM++ 2M Karras")
    payload["sampler_name"] = sampler
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(
            f"Image API HTTP {e.code}: {err_body}",
        ) from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Could not reach image backend at {url!r}: {e}",
        ) from e

    images = body.get("images")
    if not images or not isinstance(images[0], str):
        raise RuntimeError("Image API returned no base64 images in 'images'.")
    return base64.b64decode(images[0])


def _diffusers_txt2img(
    *,
    model_id: str,
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    steps: int,
) -> bytes:
    import torch
    from diffusers import DiffusionPipeline

    VRAMManager.clear()
    pipe: Any = None
    try:
        torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        load_kw: dict[str, Any] = {"torch_dtype": torch_dtype}
        if torch_dtype == torch.float16:
            load_kw["variant"] = "fp16"
        pipe = DiffusionPipeline.from_pretrained(model_id, **load_kw)
        if torch.cuda.is_available():
            if os.environ.get("RELULAYER_DIFFUSERS_CPU_OFFLOAD", "").lower() in (
                "1",
                "true",
                "yes",
            ):
                pipe.enable_model_cpu_offload()
            else:
                pipe.to("cuda")
        else:
            pipe.to("cpu")

        full_prompt = (
            f"{prompt}, photorealistic, 8k uhd, professional photography, sharp focus"
        )
        neg = negative_prompt or _photographic_negative_default()
        gen_kw: dict[str, Any] = {
            "prompt": full_prompt,
            "width": width,
            "height": height,
            "guidance_scale": float(os.environ.get("RELULAYER_IMAGE_CFG_SCALE", "7")),
            "num_inference_steps": max(1, min(steps, 50)),
        }
        if "flux" not in model_id.lower():
            gen_kw["negative_prompt"] = neg
        out = pipe(**gen_kw)
        image = out.images[0]
        buf = io.BytesIO()
        image.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    finally:
        if pipe is not None:
            del pipe
        gc.collect()
        VRAMManager.clear()


def generate_flux_image(
    image_prompt: str,
    output_path: str | Path,
    *,
    width: int = DEFAULT_SYNTH_WIDTH,
    height: int = DEFAULT_SYNTH_HEIGHT,
    negative_prompt: str = "",
    steps: int | None = None,
) -> str:
    """
    Synthesize a hero frame (default 1280×720) via local HTTP (A1111) or in-process diffusers.

    Clears GPU cache before and after diffusers to reduce VRAM overlap with Ollama.
    For HTTP backends, VRAM is owned by the remote process; we still clear in case
    this worker held CUDA tensors from earlier steps.

    Env:
      - ``RELULAYER_IMAGE_BACKEND``: ``disabled`` | ``http`` | ``diffusers``
      - ``RELULAYER_IMAGE_HTTP_URL``: A1111 base (default ``http://127.0.0.1:7860``)
      - ``RELULAYER_DIFFUSION_MODEL_ID``: HF repo for diffusers (SDXL / Flux Schnell, etc.)
      - ``RELULAYER_IMAGE_STEPS``: inference steps (default 28 http / 25 diffusers)
    """
    backend = image_synth_backend()
    if backend in ("", "none", "disabled", "off"):
        raise RuntimeError(
            "Image synthesis is disabled. Set RELULAYER_IMAGE_BACKEND=http "
            "(Automatic1111 at RELULAYER_IMAGE_HTTP_URL) or diffusers "
            "(install torch+diffusers; set RELULAYER_DIFFUSION_MODEL_ID).",
        )

    w = max(512, min(width, 2048))
    h = max(512, min(height, 2048))
    w = (w // 8) * 8
    h = (h // 8) * 8

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    VRAMManager.clear()
    raw: bytes
    try:
        if backend == "http":
            st = steps if steps is not None else int(os.environ.get("RELULAYER_IMAGE_STEPS", "28"))
            raw = _http_txt2img_automatic1111(
                base_url=image_synth_http_url(),
                prompt=image_prompt.strip(),
                negative_prompt=negative_prompt,
                width=w,
                height=h,
                steps=st,
            )
        elif backend == "diffusers":
            st = steps if steps is not None else int(os.environ.get("RELULAYER_IMAGE_STEPS", "25"))
            raw = _diffusers_txt2img(
                model_id=image_synth_diffusion_model_id(),
                prompt=image_prompt.strip(),
                negative_prompt=negative_prompt,
                width=w,
                height=h,
                steps=st,
            )
        else:
            raise RuntimeError(
                f"Unknown RELULAYER_IMAGE_BACKEND={backend!r}; use http, diffusers, or disabled.",
            )
    finally:
        VRAMManager.clear()

    process_raster_image(raw, "png", str(out.resolve()))
    logger.info(
        "visual_generator.flux_saved path=%r backend=%s size=%sx%s",
        str(out),
        backend,
        w,
        h,
    )
    return str(out.resolve())


def outputs_icons_dir(project_root: Path | None = None) -> Path:
    """``assets/outputs/icons/`` for materialized slide icons (SVG + PNG)."""
    root = project_root or _REPO_ROOT
    out = root / "assets" / "outputs" / "icons"
    out.mkdir(parents=True, exist_ok=True)
    return out


def icon_asset_basenames(slide_index: int) -> tuple[str, str]:
    """Return (svg_name, png_name) with a unique timestamp suffix."""
    ts = time.time_ns()
    base = f"slide_{slide_index}_{ts}"
    return f"{base}.svg", f"{base}.png"


def _theme_digest(theme: str) -> bytes:
    t = (theme or "").strip().encode("utf-8", errors="replace")
    return hashlib.sha256(t).digest()


def _hex_rgb(b0: int, b1: int, b2: int) -> str:
    return f"#{b0:02x}{b1:02x}{b2:02x}"


def _palette_from_digest(d: bytes) -> tuple[str, str, str]:
    """Three hex colors: gradient A/B and accent (for strokes)."""
    a = _hex_rgb(d[0], d[1], d[2])
    b = _hex_rgb(255 - d[3] % 200, 255 - d[4] % 180, 255 - d[5] % 160)
    # Keep accent light for contrast on saturated fills
    acc = _hex_rgb(
        min(255, 220 + d[6] % 35),
        min(255, 220 + d[7] % 35),
        min(255, 240),
    )
    return a, b, acc


def _pattern_variant(d: bytes) -> int:
    return int.from_bytes(d[8:12], "big") % 4


def build_theme_icon_svg(theme: str) -> str:
    """
    Deterministic structured SVG icon from a short theme string (no external models).
    Suitable for slides, favicon-style marks, and audit-friendly reproducibility.
    """
    d = _theme_digest(theme)
    c0, c1, accent = _palette_from_digest(d)
    vid = _pattern_variant(d)
    esc_theme = xml_esc.escape((theme or "").strip()[:120] or "theme")

    # Simple geometric motifs by variant
    if vid == 0:
        shapes = (
            f'<circle cx="256" cy="256" r="140" fill="none" stroke="{accent}" '
            f'stroke-width="20" opacity="0.95"/>'
            f'<circle cx="256" cy="256" r="90" fill="none" stroke="{accent}" '
            f'stroke-width="16" opacity="0.85"/>'
            f'<circle cx="256" cy="256" r="40" fill="{accent}" opacity="0.35"/>'
        )
    elif vid == 1:
        shapes = (
            f'<path d="M256 120 L420 400 L92 400 Z" fill="none" stroke="{accent}" '
            f'stroke-width="22" stroke-linejoin="round" opacity="0.92"/>'
            f'<circle cx="256" cy="290" r="36" fill="{accent}" opacity="0.4"/>'
        )
    elif vid == 2:
        shapes = (
            f'<rect x="140" y="140" width="100" height="100" rx="16" fill="none" '
            f'stroke="{accent}" stroke-width="18"/>'
            f'<rect x="272" y="140" width="100" height="100" rx="16" fill="none" '
            f'stroke="{accent}" stroke-width="18"/>'
            f'<rect x="140" y="272" width="100" height="100" rx="16" fill="none" '
            f'stroke="{accent}" stroke-width="18"/>'
            f'<rect x="272" y="272" width="100" height="100" rx="16" fill="none" '
            f'stroke="{accent}" stroke-width="18"/>'
        )
    else:
        shapes = (
            f'<path d="M120 320 L220 160 L320 280 L420 200" fill="none" '
            f'stroke="{accent}" stroke-width="22" stroke-linecap="round" '
            f'stroke-linejoin="round" opacity="0.9"/>'
            f'<circle cx="220" cy="160" r="14" fill="{accent}"/>'
        )

    grad_id = f"g{d[0]:02x}{d[1]:02x}{d[2]:02x}"
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" role="img" aria-label="{esc_theme}">
  <defs>
    <linearGradient id="{grad_id}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{c0}"/>
      <stop offset="100%" stop-color="{c1}"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="96" fill="url(#{grad_id})"/>
  {shapes}
</svg>
'''


def _lerp_byte(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def render_theme_icon_png_bytes(theme: str, size: int = _ICON_SIZE) -> bytes:
    """Raster companion to :func:`build_theme_icon_svg` (Pillow only)."""
    d = _theme_digest(theme)
    c0, c1, accent = _palette_from_digest(d)
    vid = _pattern_variant(d)

    def parse_hex(h: str) -> tuple[int, int, int]:
        s = h.lstrip("#")
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)

    r0, g0, b0 = parse_hex(c0)
    r1, g1, b1 = parse_hex(c1)
    ar, ag, ab = parse_hex(accent)

    im = Image.new("RGB", (size, size), (r0, g0, b0))
    px = im.load()
    for y in range(size):
        t = y / max(size - 1, 1)
        rr = _lerp_byte(r0, r1, t)
        gg = _lerp_byte(g0, g1, t)
        bb = _lerp_byte(b0, b1, t)
        for x in range(size):
            tx = x / max(size - 1, 1)
            u = (tx + t) / 2
            px[x, y] = (
                _lerp_byte(r0, r1, u),
                _lerp_byte(g0, g1, u),
                _lerp_byte(b0, b1, u),
            )

    draw = ImageDraw.Draw(im)
    rad = int(size * _ICON_CORNER_RADIUS_RATIO)
    # Clip to rounded rect via alpha mask
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle((0, 0, size, size), radius=rad, fill=255)
    im_rgba = im.convert("RGBA")
    im_rgba.putalpha(mask)
    im = Image.new("RGB", (size, size), (r0, g0, b0))
    im.paste(im_rgba, (0, 0), im_rgba)

    draw = ImageDraw.Draw(im)
    s = size / 512.0
    ac = (ar, ag, ab)
    lw = max(2, int(20 * s))

    if vid == 0:
        r_big = int(140 * s)
        draw.ellipse(
            (
                size // 2 - r_big,
                size // 2 - r_big,
                size // 2 + r_big,
                size // 2 + r_big,
            ),
            outline=ac,
            width=max(2, int(20 * s)),
        )
        r_mid = int(90 * s)
        draw.ellipse(
            (
                size // 2 - r_mid,
                size // 2 - r_mid,
                size // 2 + r_mid,
                size // 2 + r_mid,
            ),
            outline=ac,
            width=max(2, int(16 * s)),
        )
        r_sm = int(40 * s)
        draw.ellipse(
            (
                size // 2 - r_sm,
                size // 2 - r_sm,
                size // 2 + r_sm,
                size // 2 + r_sm,
            ),
            fill=ac,
        )
    elif vid == 1:
        tri = [
            (int(256 * s), int(120 * s)),
            (int(420 * s), int(400 * s)),
            (int(92 * s), int(400 * s)),
        ]
        draw.polygon(tri, outline=ac, width=max(2, int(22 * s)))
        r = int(36 * s)
        draw.ellipse(
            (size // 2 - r, int(290 * s) - r, size // 2 + r, int(290 * s) + r),
            fill=ac,
        )
    elif vid == 2:
        step = int(132 * s)
        base_x, base_y = int(140 * s), int(140 * s)
        for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
            x0 = base_x + dx * step
            y0 = base_y + dy * step
            wh = int(100 * s)
            draw.rounded_rectangle(
                (x0, y0, x0 + wh, y0 + wh),
                radius=int(16 * s),
                outline=ac,
                width=max(2, int(18 * s)),
            )
    else:
        pts = [
            (int(120 * s), int(320 * s)),
            (int(220 * s), int(160 * s)),
            (int(320 * s), int(280 * s)),
            (int(420 * s), int(200 * s)),
        ]
        draw.line(pts, fill=ac, width=max(2, int(22 * s)))
        r = int(14 * s)
        draw.ellipse(
            (int(220 * s) - r, int(160 * s) - r, int(220 * s) + r, int(160 * s) + r),
            fill=ac,
        )

    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def generate_slide_theme_icon_assets(
    *,
    icon_request: str | dict[str, Any],
    slide_index: int,
    slide_title: str | None = None,
    project_root: Path | None = None,
) -> dict[str, str]:
    """
    Build SVG + PNG under ``assets/outputs/icons/`` from ``icon_request``.

    ``icon_request`` may be a theme string or ``{"theme": "..."}``.
    Returns paths: ``{"svg": "...", "png": "..."}`` (absolute, resolved).
    """
    if isinstance(icon_request, dict):
        theme = str(
            icon_request.get("theme")
            or icon_request.get("label")
            or icon_request.get("concept")
            or "",
        ).strip()
    else:
        theme = str(icon_request).strip()
    if slide_title and len(theme) < 2:
        theme = f"{slide_title} — {theme}".strip(" —")
    if not theme:
        theme = f"slide_{slide_index}"

    root = project_root or _REPO_ROOT
    out_dir = outputs_icons_dir(root)
    svg_name, png_name = icon_asset_basenames(slide_index)
    svg_path = out_dir / svg_name
    png_path = out_dir / png_name

    svg_body = build_theme_icon_svg(theme)
    save_svg_asset(svg_body, str(svg_path))
    process_raster_image(render_theme_icon_png_bytes(theme), "png", str(png_path))

    logger.info(
        "visual_generator.theme_icon_done slide=%s theme_chars=%s svg=%r png=%r",
        slide_index,
        len(theme),
        str(svg_path),
        str(png_path),
    )
    return {"svg": str(svg_path.resolve()), "png": str(png_path.resolve())}


def generated_assets_dir(project_root: Path | None = None) -> Path:
    """Ensure `assets/generated/` exists and return it."""
    root = project_root or _REPO_ROOT
    out = root / "assets" / "generated"
    out.mkdir(parents=True, exist_ok=True)
    return out


def slide_asset_path(
    slide_number: int,
    extension: str,
    project_root: Path | None = None,
) -> str:
    """
    Unique path under `assets/generated/`, e.g. `slide_{n}_{timestamp}.png`.
    Use this when building `output_path` for the raster/ICO helpers.
    """
    ext = extension.lstrip(".").lower()
    name = f"slide_{slide_number}_{time.time_ns()}.{ext}"
    path = generated_assets_dir(project_root) / name
    return str(path.resolve())


def process_raster_image(image_bytes: bytes, format: str, output_path: str) -> None:
    """
    Decode raster bytes with Pillow and write PNG or JPEG with appropriate compression.
    Calls `VRAMManager.clear()` after processing (VRAM hygiene for mixed GPU pipelines).
    """
    fmt = format.lower().lstrip(".")
    if fmt == "jpeg":
        fmt = "jpg"

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    im: Image.Image | None = None
    try:
        im = Image.open(io.BytesIO(image_bytes))
        im.load()

        if fmt in ("jpg", "jpeg"):
            rgb = im.convert("RGB")
            rgb.save(
                path,
                format="JPEG",
                quality=92,
                optimize=True,
                progressive=True,
            )
        elif fmt == "png":
            im.save(path, format="PNG", optimize=True)
        else:
            raise ValueError(
                f"Unsupported raster format {format!r}; expected png, jpg, or jpeg.",
            )
        logger.info(
            "visual_generator.raster_saved path=%r format=%r bytes_in=%s",
            str(path),
            fmt,
            len(image_bytes),
        )
    finally:
        if im is not None:
            im.close()
        VRAMManager.clear()


def save_svg_asset(svg_code: str, output_path: str) -> None:
    """Write raw SVG/XML text to disk (deterministic; no GPU post-processing)."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg_code, encoding="utf-8")
    logger.info(
        "visual_generator.svg_saved path=%r chars=%s",
        str(path),
        len(svg_code),
    )


# --- Path N: Plotly / Matplotlib data charts for PPTX content placeholders ----------


def outputs_charts_dir(project_root: Path | None = None) -> Path:
    root = project_root or _REPO_ROOT
    out = root / "assets" / "outputs" / "charts"
    out.mkdir(parents=True, exist_ok=True)
    return out


def chart_asset_path(slide_index: int, project_root: Path | None = None) -> str:
    name = f"chart_slide_{slide_index}_{time.time_ns()}.png"
    path = outputs_charts_dir(project_root) / name
    return str(path.resolve())


def _chart_dims() -> tuple[int, int, int]:
    try:
        w = max(480, int(os.environ.get("RELULAYER_CHART_WIDTH", "1200")))
        h = max(270, int(os.environ.get("RELULAYER_CHART_HEIGHT", "675")))
        sc = max(1, min(4, int(os.environ.get("RELULAYER_CHART_SCALE", "2"))))
    except ValueError:
        w, h, sc = 1200, 675, 2
    return w, h, sc


def _coerce_number_list(vals: Any) -> list[float]:
    out: list[float] = []
    if not isinstance(vals, list):
        return out
    for v in vals:
        try:
            if v is None:
                continue
            out.append(float(v))
        except (TypeError, ValueError):
            continue
    return out


def _coerce_label_list(vals: Any) -> list[str]:
    if not isinstance(vals, list):
        return []
    return [str(x) for x in vals if x is not None and str(x).strip() != ""]


def _coerce_axis_list(vals: Any) -> list[Any]:
    """X-axis values: numbers preferred, else strings (categories)."""
    if not isinstance(vals, list):
        return []
    out: list[Any] = []
    for v in vals:
        if v is None:
            continue
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            out.append(str(v))
    return out


def _validate_chart_spec(spec: dict[str, Any]) -> dict[str, Any]:
    if not spec:
        raise ValueError("empty chart spec")
    ct = str(spec.get("chart_type") or "bar").strip().lower()
    if ct not in ("bar", "line", "scatter", "pie"):
        ct = "bar"
    out: dict[str, Any] = {"chart_type": ct, "title": str(spec.get("title") or "").strip()}
    if ct == "pie":
        labels = _coerce_label_list(spec.get("labels"))
        values = _coerce_number_list(spec.get("values"))
        if len(labels) < 2 or len(values) < 2:
            raise ValueError("pie chart needs labels and values (>=2 each)")
        n = min(len(labels), len(values))
        out["labels"] = labels[:n]
        out["values"] = values[:n]
        return out
    series_raw = spec.get("series")
    if isinstance(series_raw, list) and series_raw:
        series: list[dict[str, Any]] = []
        for s in series_raw:
            if not isinstance(s, dict):
                continue
            xv = s.get("x")
            xs = _coerce_axis_list(xv) if isinstance(xv, list) else []
            ys = _coerce_number_list(s.get("y"))
            if not xs and ys:
                xs = [float(i) for i in range(len(ys))]
            if len(xs) >= 2 and len(ys) >= 2:
                n = min(len(xs), len(ys))
                series.append(
                    {
                        "name": str(s.get("name") or "Series"),
                        "x": xs[:n],
                        "y": ys[:n],
                    },
                )
        if not series:
            raise ValueError("series[] entries invalid")
        out["series"] = series
        return out
    x = spec.get("x")
    if not isinstance(x, list) or len(x) < 2:
        raise ValueError("chart needs x and y (or series[])")
    xs = _coerce_axis_list(x)
    ys = _coerce_number_list(spec.get("y") if spec.get("y") is not None else spec.get("values"))
    if len(xs) < 2 or len(ys) < 2:
        raise ValueError("chart needs at least two x/y points")
    n = min(len(xs), len(ys))
    out["x"] = xs[:n]
    out["y"] = ys[:n]
    return out


def _build_plotly_figure(spec: dict[str, Any]) -> Any:
    import plotly.graph_objects as go

    ct = spec["chart_type"]
    title = spec.get("title") or ""
    if ct == "pie":
        return go.Figure(
            data=[
                go.Pie(
                    labels=spec["labels"],
                    values=spec["values"],
                    hole=0.08,
                ),
            ],
            layout={"title": title},
        )
    if "series" in spec:
        fig = go.Figure()
        mode = "lines+markers" if ct == "line" else "markers" if ct == "scatter" else "lines+markers"
        for s in spec["series"]:
            if ct == "bar":
                fig.add_trace(
                    go.Bar(name=s["name"], x=s["x"], y=s["y"]),
                )
            else:
                fig.add_trace(
                    go.Scatter(
                        name=s["name"],
                        x=s["x"],
                        y=s["y"],
                        mode=mode,
                    ),
                )
        fig.update_layout(title=title)
        if ct == "bar":
            fig.update_layout(barmode="group")
        return fig
    if ct == "bar":
        return go.Figure(
            data=[go.Bar(x=spec["x"], y=spec["y"])],
            layout={"title": title},
        )
    mode = "markers" if ct == "scatter" else "lines+markers"
    return go.Figure(
        data=[
            go.Scatter(x=spec["x"], y=spec["y"], mode=mode),
        ],
        layout={"title": title},
    )


def _render_plotly_png(spec: dict[str, Any], out_path: Path) -> None:
    fig = _build_plotly_figure(spec)
    w, h, scale = _chart_dims()
    fig.update_layout(
        template="plotly_white",
        width=w,
        height=h,
        margin=dict(l=64, r=48, t=72 if spec.get("title") else 48, b=56),
        paper_bgcolor="white",
        plot_bgcolor="#fafafa",
    )
    fig.write_image(str(out_path), width=w, height=h, scale=scale)


def _render_matplotlib_png(spec: dict[str, Any], out_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    spec_l = dict(spec)
    if "series" in spec_l:
        ser = spec_l["series"]
        if len(ser) > 1:
            logger.warning(
                "visual_generator.matplotlib_first_series_only n=%s (use plotly+kaleido for multi-series)",
                len(ser),
            )
        s0 = ser[0]
        spec_l = {k: v for k, v in spec_l.items() if k != "series"}
        spec_l["x"] = s0["x"]
        spec_l["y"] = s0["y"]

    w_in, h_in = 12, 6.75
    fig, ax = plt.subplots(figsize=(w_in, h_in), dpi=200, facecolor="white")
    ct = spec_l["chart_type"]
    title = spec_l.get("title") or ""
    if title:
        ax.set_title(title)
    if ct == "pie":
        ax.pie(spec_l["values"], labels=spec_l["labels"], autopct="%1.0f%%")
        ax.axis("equal")
    elif ct == "bar":
        ax.bar(spec_l["x"], spec_l["y"])
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=25, ha="right")
    else:
        ax.plot(spec_l["x"], spec_l["y"], marker="o", linestyle="-")
    ax.set_facecolor("#fafafa")
    fig.tight_layout()
    fig.savefig(str(out_path), bbox_inches="tight", facecolor="white")
    plt.close(fig)


def render_slide_chart_from_spec(
    chart_spec: dict[str, Any],
    slide_index: int,
    project_root: Path | None = None,
) -> str:
    """
    Build a high-resolution PNG chart from ``chart_request`` / ``chart_data`` JSON.
    Tries Plotly+Kaleido first, then Matplotlib (Agg).
    """
    spec = _validate_chart_spec(chart_spec)
    out = Path(chart_asset_path(slide_index, project_root=project_root))
    plotly_ok = os.environ.get("RELULAYER_CHART_ENGINE", "auto").strip().lower() in (
        "auto",
        "plotly",
    )
    if plotly_ok:
        try:
            _render_plotly_png(spec, out)
            logger.info(
                "visual_generator.chart_plotly slide=%s path=%r type=%s",
                slide_index,
                str(out),
                spec["chart_type"],
            )
            VRAMManager.clear()
            return str(out.resolve())
        except Exception as e:
            logger.warning(
                "visual_generator.chart_plotly_failed slide=%s err=%s (try matplotlib)",
                slide_index,
                e,
            )
    try:
        _render_matplotlib_png(spec, out)
        logger.info(
            "visual_generator.chart_matplotlib slide=%s path=%r type=%s",
            slide_index,
            str(out),
            spec["chart_type"],
        )
    except Exception:
        logger.exception("visual_generator.chart_matplotlib_failed slide=%s", slide_index)
        raise
    finally:
        VRAMManager.clear()
    return str(out.resolve())


def plotly_web_bundle_from_chart_spec(chart_spec: dict[str, Any]) -> dict[str, Any] | None:
    """
    Path Z: serialize ``chart_request`` / ``chart_data`` to Plotly.js ``data`` + ``layout`` for HTML embeds.
    Returns None if the spec is invalid or Plotly is unavailable.
    """
    try:
        spec = _validate_chart_spec(dict(chart_spec))
        fig = _build_plotly_figure(spec)
    except (ValueError, TypeError, KeyError):
        return None
    except Exception as e:
        logger.warning("visual_generator.plotly_web_bundle_invalid err=%s", e)
        return None
    try:
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(15,23,42,0.75)",
            plot_bgcolor="rgba(30,41,59,0.9)",
            font=dict(color="#e2e8f0", size=13),
            title=dict(font=dict(size=15)),
            autosize=True,
            margin=dict(
                l=56,
                r=40,
                t=72 if spec.get("title") else 56,
                b=48,
            ),
        )
        blob = json.loads(fig.to_json())
        return {
            "data": blob.get("data") or [],
            "layout": blob.get("layout") or {},
        }
    except Exception as e:
        logger.warning("visual_generator.plotly_web_bundle_failed err=%s", e)
        return None


def write_executive_microsite_html(
    deck: dict[str, Any],
    *,
    page_title: str = "Executive briefing",
    subtitle: str = "",
    project_root: Path | None = None,
) -> tuple[str, str]:
    """
    Path Z: delegate to :func:`tools.site_builder.build_executive_microsite` for a single-file HTML export.
    """
    from tools.site_builder import build_executive_microsite

    raw_slides = deck.get("slides") if isinstance(deck, dict) else None
    slides_list = raw_slides if isinstance(raw_slides, list) else []
    return build_executive_microsite(
        slides=[s for s in slides_list if isinstance(s, dict)],
        page_title=page_title,
        subtitle=subtitle,
        project_root=project_root,
    )


def build_financial_appendix_for_materialize(
    slides: list[dict[str, Any]],
    output_xlsx: str | Path,
    *,
    project_root: Path | None = None,
) -> str:
    """
    Path CC: write a multi-sheet financial appendix ``.xlsx`` from GTM slide JSON.

    Delegates to :mod:`tools.model_builder` (openpyxl). Returns absolute path.
    """
    from tools.model_builder import write_financial_appendix_workbook

    return write_financial_appendix_workbook(
        slides,
        output_xlsx,
        project_root=project_root,
    )


def create_icon_from_image(source_bytes: bytes, output_path: str) -> None:
    """
    Build a multi-resolution `.ico` from a high-res raster using Pillow.
    Clears VRAM after the heavy resize/encode pass.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    im: Image.Image | None = None
    try:
        im = Image.open(io.BytesIO(source_bytes))
        im.load()
        im.save(path, format="ICO", sizes=sizes)
        logger.info(
            "visual_generator.ico_saved path=%r bytes_in=%s sizes=%s",
            str(path),
            len(source_bytes),
            sizes,
        )
    finally:
        if im is not None:
            im.close()
        VRAMManager.clear()


def _require_ffmpeg() -> str:
    exe = os.environ.get("RELULAYER_FFMPEG", "").strip() or "ffmpeg"
    if shutil.which(exe) is None:
        raise RuntimeError(
            "ffmpeg not found. Install ffmpeg or set RELULAYER_FFMPEG to the executable path.",
        )
    return exe


def _sadtalker_configured() -> bool:
    return bool(os.environ.get("RELULAYER_SADTALKER_DIR", "").strip())


def _run_sadtalker(
    *,
    avatar_image_path: str,
    audio_wav_path: str,
    output_mp4_path: str,
) -> str:
    """
    Best-effort local SadTalker integration.

    Requires env:
    - RELULAYER_SADTALKER_DIR: path to SadTalker repo
    - RELULAYER_SADTALKER_PY (optional): python executable (default: python)
    - RELULAYER_SADTALKER_ARGS (optional): extra args string
    """
    repo = Path(os.environ.get("RELULAYER_SADTALKER_DIR", "").strip())
    if not repo.is_dir():
        raise RuntimeError("SadTalker not configured: RELULAYER_SADTALKER_DIR missing/invalid.")
    py = os.environ.get("RELULAYER_SADTALKER_PY", "").strip() or "python"
    extra = os.environ.get("RELULAYER_SADTALKER_ARGS", "").strip().split()
    out_dir = Path(output_mp4_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    # NOTE: SadTalker output conventions vary by fork; we invoke and then best-effort locate mp4.
    cmd = [
        py,
        str(repo / "inference.py"),
        "--driven_audio",
        str(Path(audio_wav_path).resolve()),
        "--source_image",
        str(Path(avatar_image_path).resolve()),
        "--result_dir",
        str(out_dir.resolve()),
        *extra,
    ]
    logger.info("visual_generator.sadtalker.start cmd=%r", cmd[:8])
    try:
        subprocess.run(
            cmd,
            cwd=str(repo.resolve()),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        out = (e.stdout or "")[-2000:]
        raise RuntimeError(f"SadTalker failed: {out}") from e

    # Heuristic: pick newest mp4 in result_dir.
    mp4s = sorted(out_dir.glob("**/*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not mp4s:
        raise RuntimeError("SadTalker completed but produced no .mp4 under result_dir.")
    src = mp4s[0]
    dst = Path(output_mp4_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return str(dst.resolve())


def build_video_brief(
    *,
    slide_image_paths: list[str],
    talk_track_wav_path: str,
    output_mp4_path: str | None = None,
    avatar_image_path: str | None = None,
    project_root: Path | None = None,
    seconds_per_slide: float = 4.0,
) -> str:
    """
    Path HH: generate a short video brief.

    Priority:
    1) If SadTalker is configured and avatar_image_path is provided, generate a talking-head mp4.
    2) Fallback: slideshow mp4 from slide hero images + talk track audio (ffmpeg).

    Returns absolute mp4 path.
    """
    root = project_root or _REPO_ROOT
    out_path = Path(output_mp4_path) if output_mp4_path else video_brief_asset_path(root)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    audio = Path(talk_track_wav_path).resolve()
    if not audio.is_file():
        raise RuntimeError(f"Talk track WAV not found: {audio}")

    imgs = [str(Path(p).resolve()) for p in (slide_image_paths or []) if p and Path(p).is_file()]
    if _sadtalker_configured() and avatar_image_path and Path(avatar_image_path).is_file():
        try:
            return _run_sadtalker(
                avatar_image_path=str(Path(avatar_image_path).resolve()),
                audio_wav_path=str(audio),
                output_mp4_path=str(out_path),
            )
        finally:
            VRAMManager.clear()

    if not imgs:
        raise RuntimeError("No slide hero images available to build a slideshow video.")

    ffmpeg = _require_ffmpeg()
    dur = max(1.0, float(seconds_per_slide))

    # ffmpeg concat demuxer requires a file list.
    with tempfile.TemporaryDirectory(prefix="relulayer_video_") as td:
        tmp = Path(td)
        list_path = tmp / "slides.txt"
        # Use the concat demuxer with per-file duration.
        lines: list[str] = []
        for p in imgs:
            lines.append(f"file '{p}'")
            lines.append(f"duration {dur:.3f}")
        # Repeat last file without duration to avoid it being dropped.
        lines.append(f"file '{imgs[-1]}'")
        list_path.write_text("\n".join(lines), encoding="utf-8")

        # Build 1280x720 h264 mp4, merge audio.
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-i",
            str(audio),
            "-shortest",
            "-vf",
            "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            str(out_path),
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        except subprocess.CalledProcessError as e:
            out = (e.stdout or "")[-2000:]
            raise RuntimeError(f"ffmpeg slideshow failed: {out}") from e
        finally:
            VRAMManager.clear()

    return str(out_path.resolve())
