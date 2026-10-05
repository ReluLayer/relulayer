from __future__ import annotations

import copy
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE, PP_PLACEHOLDER_TYPE
from pptx.util import Emu, Inches, Pt

from infrastructure.vram_manager import VRAMManager

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent

_TITLE_TYPES: Iterable[PP_PLACEHOLDER_TYPE] = (
    PP_PLACEHOLDER_TYPE.TITLE,
    PP_PLACEHOLDER_TYPE.CENTER_TITLE,
    PP_PLACEHOLDER_TYPE.VERTICAL_TITLE,
)

_BODY_TYPES: Iterable[PP_PLACEHOLDER_TYPE] = (
    PP_PLACEHOLDER_TYPE.BODY,
    PP_PLACEHOLDER_TYPE.OBJECT,
    PP_PLACEHOLDER_TYPE.VERTICAL_BODY,
    PP_PLACEHOLDER_TYPE.VERTICAL_OBJECT,
)

_SUBTITLE_TYPES: Iterable[PP_PLACEHOLDER_TYPE] = (PP_PLACEHOLDER_TYPE.SUBTITLE,)

_META_PLACEHOLDER_TYPES: frozenset[PP_PLACEHOLDER_TYPE] = frozenset(
    (
        PP_PLACEHOLDER_TYPE.HEADER,
        PP_PLACEHOLDER_TYPE.FOOTER,
        PP_PLACEHOLDER_TYPE.SLIDE_NUMBER,
        PP_PLACEHOLDER_TYPE.DATE,
    )
)

_PICTURE_TYPES: Iterable[PP_PLACEHOLDER_TYPE] = (
    PP_PLACEHOLDER_TYPE.PICTURE,
    PP_PLACEHOLDER_TYPE.BITMAP,
    PP_PLACEHOLDER_TYPE.SLIDE_IMAGE,
)

_BODY_TYPES_FROZEN: frozenset[PP_PLACEHOLDER_TYPE] = frozenset(_BODY_TYPES)
_TITLE_TYPES_FROZEN: frozenset[PP_PLACEHOLDER_TYPE] = frozenset(_TITLE_TYPES)
_SUBTITLE_TYPES_FROZEN: frozenset[PP_PLACEHOLDER_TYPE] = frozenset(_SUBTITLE_TYPES)

_DEFAULT_FONT_PT: dict[str, float] = {
    "title": 44.0,
    "subtitle": 28.0,
    "body": 18.0,
    "notes": 12.0,
}

_CSS_CUSTOM_PROP_RE = re.compile(r"--([a-zA-Z0-9_-]+)\s*:\s*([^;}]+)")


# --- Path T: brand CSS / JSON → deck styling (Layer 5) ------------------------


@dataclass(frozen=True)
class BrandProfile:
    """Normalized enterprise brand tokens for typography, palette, and accents."""

    primary: RGBColor | None = None
    secondary: RGBColor | None = None
    accent: RGBColor | None = None
    text: RGBColor | None = None
    muted: RGBColor | None = None
    typography: dict[str, dict[str, Any]] = field(default_factory=dict)
    accent_bar_enabled: bool = False
    accent_bar_height_pt: float = 4.0
    accent_bar_position: str = "bottom"
    image_outline_pt: float = 2.0
    frame_chart_png: bool = True
    frame_hero_png: bool = True
    layout_boost_keywords: tuple[str, ...] = ()

    def accent_line_rgb(self) -> RGBColor | None:
        return self.accent or self.secondary or self.primary


def _rgb_to_hex(rgb: RGBColor) -> str:
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def _parse_css_custom_properties(css: str) -> dict[str, str]:
    """Extract ``--name: #hex`` (and similar) custom properties from a CSS snippet."""
    out: dict[str, str] = {}
    for m in _CSS_CUSTOM_PROP_RE.finditer(css or ""):
        key = m.group(1).strip()
        val = m.group(2).strip()
        hx = re.search(r"#([0-9a-fA-F]{3,8})\b", val)
        if hx:
            out[key] = "#" + hx.group(1)
    return out


def _first_hex_from_css_vars(css_vars: dict[str, str], *needles: str) -> str | None:
    needles_l = [n.lower() for n in needles if n]
    for k, v in css_vars.items():
        kl = k.lower()
        if any(n in kl for n in needles_l):
            return v
    return None


def _first_rgb(*candidates: str | None) -> RGBColor | None:
    for c in candidates:
        if c and isinstance(c, str):
            rgb = _parse_color(c.strip())
            if rgb is not None:
                return rgb
    return None


def brand_profile_from_deck_json(deck_json: dict[str, Any]) -> BrandProfile | None:
    """
    Build a ``BrandProfile`` from ``deck_json['brand']`` or ``design_specs['brand']``.
    Supports a ``colors`` map, ``typography`` per role, optional ``css`` / ``css_variables``
    string (--var: #hex), ``accent_bar``, and ``layout_boost`` keyword hints for layout pick.
    """
    raw: Any = deck_json.get("brand")
    if raw is None:
        ds = deck_json.get("design_specs")
        if isinstance(ds, dict):
            raw = ds.get("brand")
    if not isinstance(raw, dict):
        return None

    colors = raw.get("colors")
    colors = colors if isinstance(colors, dict) else {}
    css_blob = raw.get("css") or raw.get("css_variables") or raw.get("css_text") or ""
    css_vars = _parse_css_custom_properties(str(css_blob))

    primary = _first_rgb(
        colors.get("primary"),
        colors.get("brand_primary"),
        _first_hex_from_css_vars(css_vars, "primary", "brand"),
    )
    secondary = _first_rgb(
        colors.get("secondary"),
        colors.get("brand_secondary"),
        _first_hex_from_css_vars(css_vars, "secondary"),
    )
    accent = _first_rgb(
        colors.get("accent"),
        colors.get("highlight"),
        _first_hex_from_css_vars(css_vars, "accent", "highlight"),
    )
    text = _first_rgb(
        colors.get("text"),
        colors.get("foreground"),
        colors.get("on_surface"),
        _first_hex_from_css_vars(css_vars, "text", "foreground", "body"),
    )
    muted = _first_rgb(
        colors.get("muted"),
        colors.get("subtle"),
        _first_hex_from_css_vars(css_vars, "muted", "subtle", "secondary-text"),
    )

    typo_src = raw.get("typography") or raw.get("fonts") or {}
    typography: dict[str, dict[str, Any]] = {}
    if isinstance(typo_src, dict):
        for role in ("title", "body", "subtitle", "notes"):
            block = typo_src.get(role)
            if isinstance(block, dict):
                typography[role] = copy.deepcopy(block)

    accent_bar_enabled = False
    accent_bar_height_pt = 4.0
    accent_bar_position = "bottom"
    ab = raw.get("accent_bar")
    if isinstance(ab, dict):
        accent_bar_enabled = bool(ab.get("enabled", False))
        try:
            accent_bar_height_pt = float(ab.get("height_pt", accent_bar_height_pt))
        except (TypeError, ValueError):
            pass
        accent_bar_position = str(ab.get("position", accent_bar_position)).lower()

    try:
        image_outline_pt = float(raw.get("image_outline_pt", 2.0))
    except (TypeError, ValueError):
        image_outline_pt = 2.0
    frame_chart_png = bool(raw.get("frame_chart_png", True))
    frame_hero_png = bool(raw.get("frame_hero_png", True))

    lb = raw.get("layout_boost") or raw.get("layout_keywords")
    layout_boost_keywords: tuple[str, ...] = ()
    if isinstance(lb, list):
        layout_boost_keywords = tuple(
            _normalize(str(x)) for x in lb if isinstance(x, str) and str(x).strip()
        )

    has_signal = (
        any(x is not None for x in (primary, secondary, accent, text, muted))
        or bool(typography)
        or bool(css_vars)
        or accent_bar_enabled
        or bool(layout_boost_keywords)
    )
    if not has_signal:
        return None

    return BrandProfile(
        primary=primary,
        secondary=secondary,
        accent=accent,
        text=text,
        muted=muted,
        typography=typography,
        accent_bar_enabled=accent_bar_enabled,
        accent_bar_height_pt=accent_bar_height_pt,
        accent_bar_position=accent_bar_position,
        image_outline_pt=image_outline_pt,
        frame_chart_png=frame_chart_png,
        frame_hero_png=frame_hero_png,
        layout_boost_keywords=layout_boost_keywords,
    )


def _brand_as_design_specs(brand: BrandProfile | None) -> dict[str, Any]:
    """Lowest-priority design_specs layer: brand typography + default role colors."""
    if not brand:
        return {}
    specs: dict[str, Any] = {}
    for role in ("title", "body", "subtitle", "notes"):
        specs[role] = copy.deepcopy(brand.typography.get(role) or {})

    def _default_color(role: str, rgb: RGBColor | None) -> None:
        if rgb is None:
            return
        block = specs[role]
        if block.get("color") or block.get("color_hex"):
            return
        block["color_hex"] = _rgb_to_hex(rgb)

    _default_color("title", brand.primary)
    _default_color("subtitle", brand.secondary or brand.primary)
    _default_color("body", brand.text)
    _default_color("notes", brand.muted or brand.text)
    return specs


def _merge_brand_design_layer(
    brand: BrandProfile | None,
    deck_specs: dict[str, Any],
    slide_specs: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge order: brand defaults → deck ``design_specs`` → per-slide ``design_specs``."""
    layer = _brand_as_design_specs(brand)
    merged = _merge_design_specs(layer, deck_specs)
    slide_clean: dict[str, Any] | None = None
    if isinstance(slide_specs, dict):
        slide_clean = {k: v for k, v in slide_specs.items() if k != "brand"}
    return _merge_design_specs(merged, slide_clean)


def _add_brand_accent_bar(slide: Any, prs: Presentation, brand: BrandProfile | None) -> None:
    if not brand or not brand.accent_bar_enabled:
        return
    rgb = brand.accent_line_rgb()
    if rgb is None and brand.primary is not None:
        rgb = brand.primary
    if rgb is None:
        return
    pos = (brand.accent_bar_position or "bottom").lower()
    try:
        h_emu = int(Emu(Pt(float(brand.accent_bar_height_pt))))
    except (TypeError, ValueError):
        h_emu = int(Emu(Pt(4.0)))
    sw, sh = int(prs.slide_width), int(prs.slide_height)
    if pos == "top":
        left, top, width, height = 0, 0, sw, h_emu
    elif pos == "left":
        left, top, width, height = 0, 0, h_emu, sh
    else:
        left, top, width, height = 0, sh - h_emu, sw, h_emu
    try:
        bar = slide.shapes.add_shape(
            MSO_AUTO_SHAPE_TYPE.RECTANGLE, left, top, width, height
        )
        bar.fill.solid()
        bar.fill.fore_color.rgb = rgb
        bar.line.fill.background()
    except Exception:
        logger.warning("pptx_builder.accent_bar_failed", exc_info=True)


def _apply_brand_picture_outline(
    shape: Any,
    brand: BrandProfile | None,
    *,
    enabled: bool,
) -> None:
    if not brand or not enabled:
        return
    rgb = brand.accent_line_rgb()
    if rgb is None:
        return
    try:
        shape.line.color.rgb = rgb
        shape.line.width = Pt(float(brand.image_outline_pt))
    except Exception:
        logger.debug("pptx_builder.brand_outline_skipped", exc_info=True)


# --- Path M: structural overflow auditor (Layer 5/6) ------------------------


def _structural_audit_enabled() -> bool:
    return os.environ.get("RELULAYER_STRUCTURAL_AUDIT", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _structural_min_font_pt() -> float:
    try:
        return max(6.0, float(os.environ.get("RELULAYER_STRUCTURAL_MIN_PT", "8")))
    except ValueError:
        return 8.0


def _structural_min_font_scale() -> float:
    try:
        return min(1.0, max(0.35, float(os.environ.get("RELULAYER_STRUCTURAL_MIN_FONT_SCALE", "0.62"))))
    except ValueError:
        return 0.62


@dataclass
class StructuralAdjustment:
    """One fix applied to keep placeholder text within estimated bounds."""

    slide_index: int
    role: str
    action: str
    message: str


@dataclass
class StructuralAuditReport:
    """Returned from ``assemble_deck`` for materialization telemetry (Path M)."""

    audit_enabled: bool
    adjustments: list[StructuralAdjustment] = field(default_factory=list)
    checks_performed: int = 0

    def to_json_records(self) -> list[dict[str, Any]]:
        return [
            {
                "slide_index": a.slide_index,
                "role": a.role,
                "action": a.action,
                "message": a.message,
            }
            for a in self.adjustments
        ]


def _emu_to_pt(length: Any) -> float:
    try:
        if length is None:
            return 0.0
        return float(Emu(length).pt)
    except Exception:
        return 0.0


def _usable_text_area_pt(shape: Any) -> tuple[float, float]:
    """Inner width/height (pt) after text-frame insets."""
    w = _emu_to_pt(getattr(shape, "width", 0))
    h = _emu_to_pt(getattr(shape, "height", 0))
    tf = shape.text_frame
    ml = _emu_to_pt(getattr(tf, "margin_left", 0))
    mr = _emu_to_pt(getattr(tf, "margin_right", 0))
    mt = _emu_to_pt(getattr(tf, "margin_top", 0))
    mb = _emu_to_pt(getattr(tf, "margin_bottom", 0))
    inner_w = max(16.0, w - ml - mr)
    inner_h = max(16.0, h - mt - mb)
    return inner_w, inner_h


def _classify_placeholder_role(shape: Any) -> str:
    try:
        t = shape.placeholder_format.type
    except (AttributeError, ValueError):
        return "body"
    if t in _TITLE_TYPES:
        return "title"
    if t in _SUBTITLE_TYPES:
        return "subtitle"
    if t in _BODY_TYPES:
        return "body"
    return "body"


def _read_effective_font_pt(shape: Any, role: str, merged_specs: dict[str, Any]) -> float:
    spec = merged_specs.get(role)
    if isinstance(spec, dict) and spec.get("size_pt") is not None:
        try:
            return float(spec["size_pt"])
        except (TypeError, ValueError):
            pass
    try:
        for para in shape.text_frame.paragraphs:
            for run in para.runs:
                if run.font.size is not None:
                    return float(run.font.size.pt)
    except Exception:
        pass
    return _DEFAULT_FONT_PT.get(role, 18.0)


def _apply_uniform_font_pt(shape: Any, pt: float) -> None:
    try:
        for para in shape.text_frame.paragraphs:
            for run in para.runs:
                run.font.size = Pt(pt)
    except Exception:
        logger.warning("pptx_builder.structural.uniform_font_failed", exc_info=True)


def _estimate_wrapped_lines(text: str, width_pt: float, font_pt: float) -> int:
    """Heuristic line count (wrapping + explicit newlines)."""
    if not (text or "").strip():
        return 0
    font_pt = max(4.0, font_pt)
    width_pt = max(8.0, width_pt)
    chars_per_line = max(5, int(width_pt / (font_pt * 0.52)))
    total = 0
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            total += 1
            continue
        total += max(1, (len(line) + chars_per_line - 1) // chars_per_line)
    return max(1, total)


def _max_lines_fit(height_pt: float, font_pt: float) -> int:
    font_pt = max(4.0, font_pt)
    height_pt = max(8.0, height_pt)
    line_height = font_pt * 1.22
    return max(1, int(height_pt / line_height))


def _smart_truncate_for_lines(
    text: str,
    max_lines: int,
    width_pt: float,
    font_pt: float,
) -> str:
    t = (text or "").strip()
    if not t:
        return t
    font_pt = max(4.0, font_pt)
    width_pt = max(8.0, width_pt)
    if _estimate_wrapped_lines(t, width_pt, font_pt) <= max_lines:
        return t
    for cut in range(len(t) - 1, 7, -1):
        stem = t[:cut].rstrip().rstrip(".,; ")
        if not stem:
            continue
        cand = stem + "…"
        if _estimate_wrapped_lines(cand, width_pt, font_pt) <= max_lines:
            return cand
    return (t[:8].rstrip() + "…") if len(t) > 8 else t + "…"


def _structural_fix_placeholder_shape(
    slide_index: int,
    shape: Any,
    role: str,
    merged_specs: dict[str, Any],
    report: StructuralAuditReport,
) -> None:
    if not shape.has_text_frame:
        return
    text = (shape.text_frame.text or "").strip()
    if not text:
        return
    report.checks_performed += 1
    inner_w, inner_h = _usable_text_area_pt(shape)
    font_pt = _read_effective_font_pt(shape, role, merged_specs)
    est_lines = _estimate_wrapped_lines(text, inner_w, font_pt)
    max_lines = _max_lines_fit(inner_h, font_pt)
    if est_lines <= max_lines:
        return

    orig_pt = font_pt
    min_pt_floor = _structural_min_font_pt()
    min_pt_scale = max(min_pt_floor, orig_pt * _structural_min_font_scale())
    target_pt = orig_pt

    while target_pt >= min_pt_scale - 1e-6:
        est2 = _estimate_wrapped_lines(text, inner_w, target_pt)
        max2 = _max_lines_fit(inner_h, target_pt)
        if est2 <= max2:
            if target_pt + 0.02 < orig_pt:
                _apply_uniform_font_pt(shape, target_pt)
                report.adjustments.append(
                    StructuralAdjustment(
                        slide_index=slide_index,
                        role=role,
                        action="font_scale_down",
                        message=(
                            f"Reduced {role} font from ~{orig_pt:.1f}pt to ~{target_pt:.1f}pt "
                            f"(estimated {est_lines} lines down to fit ~{max2} lines in placeholder)."
                        ),
                    ),
                )
            return
        target_pt -= max(0.45, target_pt * 0.045)

    final_pt = max(min_pt_scale, min_pt_floor)
    _apply_uniform_font_pt(shape, final_pt)
    max_final = _max_lines_fit(inner_h, final_pt)
    new_text = _smart_truncate_for_lines(text, max_final, inner_w, final_pt)
    shape.text_frame.text = new_text
    _apply_font_spec(shape, role, merged_specs)
    _apply_uniform_font_pt(shape, final_pt)
    report.adjustments.append(
        StructuralAdjustment(
            slide_index=slide_index,
            role=role,
            action="smart_truncate",
            message=(
                f"{role}: text still exceeded placeholder after min font (~{final_pt:.1f}pt); "
                f"truncated to ~{len(new_text)} chars with ellipsis for visual integrity."
            ),
        ),
    )


def _structural_audit_slide_placeholders(
    slide: Any,
    slide_index: int,
    merged_specs: dict[str, Any],
    report: StructuralAuditReport,
) -> None:
    for shape in slide.placeholders:
        if not shape.has_text_frame:
            continue
        if not (shape.text_frame.text or "").strip():
            continue
        role = _classify_placeholder_role(shape)
        _structural_fix_placeholder_shape(slide_index, shape, role, merged_specs, report)


def _structural_audit_notes(
    slide: Any,
    slide_index: int,
    merged_specs: dict[str, Any],
    report: StructuralAuditReport,
) -> None:
    try:
        ns = slide.notes_slide
    except Exception:
        return
    body_shape = None
    for sh in ns.shapes:
        if not sh.has_text_frame:
            continue
        try:
            if sh.placeholder_format.type == PP_PLACEHOLDER_TYPE.BODY:
                body_shape = sh
                break
        except (AttributeError, ValueError):
            continue
    if body_shape is None:
        for sh in ns.shapes:
            if sh.has_text_frame:
                body_shape = sh
                break
    if body_shape is None:
        return
    if not (body_shape.text_frame.text or "").strip():
        return
    _structural_fix_placeholder_shape(
        slide_index,
        body_shape,
        "notes",
        merged_specs,
        report,
    )


@dataclass(frozen=True)
class LayoutProfile:
    """Inspected placeholder footprint of a master slide layout (python-pptx)."""

    index: int
    name: str
    name_norm: str
    body_slots: int
    title_slots: int
    subtitle_slots: int
    meta_placeholder_slots: int
    has_picture: bool
    layout: Any  # SlideLayout


def outputs_assets_dir(project_root: Path | None = None) -> Path:
    root = project_root or _REPO_ROOT
    out = root / "assets" / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _resolve_output_path(output_path: str, project_root: Path) -> Path:
    p = Path(output_path)
    out_root = outputs_assets_dir(project_root).resolve()
    if p.is_absolute():
        resolved = p.resolve()
    else:
        resolved = (out_root / p).resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    try:
        resolved.relative_to(out_root)
    except ValueError:
        if p.is_absolute():
            logger.warning(
                "pptx_builder.output_outside_outputs_dir path=%r (saving as requested)",
                str(resolved),
            )
    return resolved


def _slides_from_deck(deck_json: dict[str, Any]) -> list[dict[str, Any]]:
    slides = deck_json.get("slides")
    if slides is None:
        logger.warning("pptx_builder.missing_slides_key using empty list")
        return []
    if not isinstance(slides, list):
        raise TypeError("deck_json['slides'] must be a list of slide dicts.")
    return [s for s in slides if isinstance(s, dict)]


def _merge_design_specs(
    deck_specs: dict[str, Any],
    slide_specs: dict[str, Any] | None,
) -> dict[str, Any]:
    base = copy.deepcopy(deck_specs) if deck_specs else {}
    if not slide_specs:
        return base
    for key, val in slide_specs.items():
        if (
            key in base
            and isinstance(base[key], dict)
            and isinstance(val, dict)
        ):
            merged = {**base[key], **val}
            base[key] = merged
        else:
            base[key] = copy.deepcopy(val) if isinstance(val, dict) else val
    return base


def _normalize(s: str) -> str:
    return " ".join(s.strip().lower().split())


def _profile_slide_layout(layout: Any, index: int) -> LayoutProfile:
    body_slots = 0
    title_slots = 0
    subtitle_slots = 0
    meta_placeholder_slots = 0
    has_picture = False
    for shape in layout.placeholders:
        try:
            ph = shape.placeholder_format
        except (AttributeError, ValueError):
            continue
        t = ph.type
        if t in _PICTURE_TYPES:
            has_picture = True
        elif t in _TITLE_TYPES:
            title_slots += 1
        elif t in _SUBTITLE_TYPES:
            subtitle_slots += 1
        elif t in _BODY_TYPES:
            body_slots += 1
        elif t in _META_PLACEHOLDER_TYPES:
            meta_placeholder_slots += 1
    return LayoutProfile(
        index=index,
        name=layout.name,
        name_norm=_normalize(layout.name),
        body_slots=body_slots,
        title_slots=title_slots,
        subtitle_slots=subtitle_slots,
        meta_placeholder_slots=meta_placeholder_slots,
        has_picture=has_picture,
        layout=layout,
    )


def build_layout_catalog(prs: Presentation) -> list[LayoutProfile]:
    """Inspect all ``SlideLayout`` objects on the template (placeholders + names)."""
    layouts = prs.slide_layouts
    if not layouts:
        raise ValueError("Template has no slide layouts.")
    return [_profile_slide_layout(layout, i) for i, layout in enumerate(layouts)]


def inspect_template_layouts(template_path: str) -> list[dict[str, Any]]:
    """
    Public mapping tool: describe each layout's name and placeholder counts
    (for debugging or UI when authoring ``slide.type`` strings).
    """
    tpl = Path(template_path)
    if not tpl.is_file():
        raise FileNotFoundError(f"Template not found: {tpl}")
    prs = Presentation(str(tpl))
    try:
        catalog = build_layout_catalog(prs)
    finally:
        del prs
        VRAMManager.clear()
    return [
        {
            "index": p.index,
            "name": p.name,
            "name_normalized": p.name_norm,
            "body_placeholder_count": p.body_slots,
            "title_placeholder_count": p.title_slots,
            "subtitle_placeholder_count": p.subtitle_slots,
            "meta_placeholder_count": p.meta_placeholder_slots,
            "has_picture_placeholder": p.has_picture,
        }
        for p in catalog
    ]


def _score_layout_match(
    profile: LayoutProfile,
    slide_type_norm: str,
    *,
    has_image: bool,
    brand_keywords: tuple[str, ...] = (),
) -> float:
    """Higher is better. Combines name match with structural fit to JSON ``type``."""
    score = 0.0
    req = slide_type_norm.strip()
    nn = profile.name_norm

    if req:
        if nn == req:
            score += 1000.0
        elif req in nn:
            score += 520.0
        elif nn in req:
            score += 480.0
        req_tokens = {t for t in re.split(r"[\s\-]+", req) if len(t) > 1}
        name_tokens = {t for t in re.split(r"[\s\-]+", nn) if len(t) > 1}
        score += 90.0 * len(req_tokens & name_tokens)

    two_col_hint = any(
        k in req
        for k in (
            "comparison",
            "two content",
            "two-content",
            "2 content",
            "double",
            "dual",
            "side by side",
        )
    )
    if two_col_hint:
        if profile.body_slots >= 2:
            score += 260.0
        if any(x in nn for x in ("comparison", "two", "double", "2")):
            score += 220.0

    pic_hint = any(
        k in req
        for k in (
            "picture",
            "caption",
            "photo",
            "image",
        )
    )
    if pic_hint:
        if profile.has_picture:
            score += 240.0
        if any(x in nn for x in ("picture", "caption", "photo", "image")):
            score += 200.0

    if "title only" in req or req in ("title", "title slide"):
        if profile.body_slots <= 1 and profile.title_slots >= 1:
            score += 180.0
    if "blank" in req:
        if profile.body_slots == 0 and profile.title_slots == 0:
            score += 200.0
        elif profile.body_slots == 0:
            score += 100.0

    if has_image and profile.has_picture:
        score += 130.0

    if not req or "content" in req or "title and" in req or "section" in req:
        if profile.body_slots >= 1:
            score += 95.0
        if "section" in req and "section" in nn:
            score += 200.0

    for kw in brand_keywords:
        if kw and (kw in nn or kw in req):
            score += 75.0

    return score


def pick_best_layout(
    catalog: list[LayoutProfile],
    requested_type: str | None,
    *,
    has_image: bool,
    brand: BrandProfile | None = None,
) -> LayoutProfile:
    """
    Choose the template layout that best matches ``slide_data['type']`` and optional hero image.
    Optional ``brand`` boosts layouts whose names match ``brand.layout_boost_keywords``.
    Falls back to legacy index-1 / index-0 behavior on ties or empty request.
    """
    if not catalog:
        raise ValueError("Empty layout catalog.")

    req = _normalize(requested_type or "")
    brand_kw = brand.layout_boost_keywords if brand else ()
    scored = [
        (
            _score_layout_match(
                p, req, has_image=has_image, brand_keywords=brand_kw
            ),
            p,
        )
        for p in catalog
    ]
    scored.sort(
        key=lambda x: (x[0], x[1].body_slots, -x[1].index),
        reverse=True,
    )
    best_score, best = scored[0]

    if best_score <= 0.0 and req:
        for p in catalog:
            if req in p.name_norm or p.name_norm in req:
                best = p
                logger.info(
                    "pptx_builder.layout_name_fallback name=%r for type=%r",
                    p.name,
                    requested_type,
                )
                break
        else:
            logger.warning(
                "pptx_builder.layout_no_score_match type=%r using_structural_fallback",
                requested_type,
            )
            best = max(
                catalog,
                key=lambda p: (p.body_slots, p.has_picture, len(p.name_norm)),
            )

    if best_score <= 0.0 and not req:
        if len(catalog) > 1:
            best = catalog[1]
            logger.warning(
                "pptx_builder.layout_fallback index=1 name=%r",
                best.name,
            )
        else:
            best = catalog[0]
            logger.warning(
                "pptx_builder.layout_fallback index=0 name=%r",
                best.name,
            )

    logger.info(
        "pptx_builder.layout_picked name=%r score=%.1f body_slots=%s picture=%s type=%r",
        best.name,
        best_score,
        best.body_slots,
        best.has_picture,
        requested_type,
    )
    return best


def _pick_slide_layout(prs: Presentation, requested: str | None) -> Any:
    """Backward-compatible: build catalog and pick best layout (image-agnostic)."""
    catalog = build_layout_catalog(prs)
    return pick_best_layout(catalog, requested, has_image=False).layout


def _ordered_text_shapes(slide: Any, types: frozenset[PP_PLACEHOLDER_TYPE]) -> list[Any]:
    rows: list[tuple[int, Any]] = []
    for shape in slide.placeholders:
        try:
            ph = shape.placeholder_format
        except (AttributeError, ValueError):
            continue
        if ph.type not in types or not shape.has_text_frame:
            continue
        rows.append((ph.idx, shape))
    rows.sort(key=lambda x: x[0])
    return [s for _, s in rows]


def _split_body_for_placeholders(
    body: str,
    n_slots: int,
    slide_type_norm: str,
) -> list[str]:
    if n_slots <= 0:
        return []
    text = (body or "").strip()
    if n_slots == 1:
        return [text]

    explicit = re.split(r"\n-{3,}\n", text, maxsplit=1)
    if len(explicit) == 2 and explicit[0].strip() and explicit[1].strip():
        parts = [explicit[0].strip(), explicit[1].strip()]
        while len(parts) < n_slots:
            parts.append("")
        return parts[:n_slots]

    if "\n\n" in text:
        a, b = text.split("\n\n", 1)
        if a.strip() and b.strip():
            parts = [a.strip(), b.strip()]
            while len(parts) < n_slots:
                parts.append("")
            return parts[:n_slots]

    mid = max(1, len(text) // 2)
    if two_col_hint := any(
        k in slide_type_norm
        for k in ("comparison", "two content", "double", "dual", "side by side")
    ):
        split_at = text.rfind(". ", 0, mid)
        if split_at == -1:
            split_at = text.find(" ", mid)
        if split_at > 0:
            left = text[: split_at + 1].strip()
            right = text[split_at + 1 :].strip()
            parts = [left, right]
            while len(parts) < n_slots:
                parts.append("")
            return parts[:n_slots]

    chunk = max(1, (len(text) + n_slots - 1) // n_slots)
    parts = []
    i = 0
    for _ in range(n_slots - 1):
        parts.append(text[i : i + chunk].strip())
        i += chunk
    parts.append(text[i:].strip())
    return parts


def _fill_body_placeholders_distributed(
    slide: Any,
    slide_data: dict[str, Any],
    slide_type_norm: str,
) -> None:
    """Fill one or more BODY/OBJECT placeholders; split ``body`` when layout is multi-column."""
    shapes = _ordered_text_shapes(slide, _BODY_TYPES_FROZEN)
    if not shapes:
        return

    bl = slide_data.get("body_left")
    br = slide_data.get("body_right")
    bc = slide_data.get("body_columns")
    body = slide_data.get("body")

    if (
        isinstance(bc, list)
        and len(bc) >= 2
        and all(isinstance(x, str) for x in bc[: len(shapes)])
    ):
        for i, sh in enumerate(shapes):
            sh.text_frame.text = str(bc[i]) if i < len(bc) else ""
        return

    if bl is not None and br is not None and len(shapes) >= 2:
        shapes[0].text_frame.text = str(bl).strip()
        shapes[1].text_frame.text = str(br).strip()
        for sh in shapes[2:]:
            sh.text_frame.text = ""
        return

    if body is None and bl is None and br is None:
        return

    parts = _split_body_for_placeholders(
        str(body or ""),
        len(shapes),
        slide_type_norm,
    )
    for i, sh in enumerate(shapes):
        sh.text_frame.text = parts[i] if i < len(parts) else ""


def _parse_color(value: str | None) -> RGBColor | None:
    if not value or not isinstance(value, str):
        return None
    s = value.strip().lstrip("#")
    if len(s) == 6:
        return RGBColor(int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    if len(s) == 3:
        return RGBColor(
            int(s[0] + s[0], 16),
            int(s[1] + s[1], 16),
            int(s[2] + s[2], 16),
        )
    logger.warning("pptx_builder.bad_color %r", value)
    return None


def _apply_run_style_from_spec(run: Any, spec: dict[str, Any]) -> None:
    if "size_pt" in spec:
        run.font.size = Pt(float(spec["size_pt"]))
    col = spec.get("color") or spec.get("color_hex")
    rgb = _parse_color(col) if col else None
    if rgb is not None:
        run.font.color.rgb = rgb
    fn = spec.get("font") or spec.get("font_name") or spec.get("family")
    if fn:
        run.font.name = str(fn)
    if spec.get("bold") is True:
        run.font.bold = True
    elif spec.get("bold") is False:
        run.font.bold = False
    if spec.get("italic") is True:
        run.font.italic = True
    elif spec.get("italic") is False:
        run.font.italic = False
    w = spec.get("font_weight")
    if isinstance(w, (int, float)) and float(w) >= 600:
        run.font.bold = True
    elif isinstance(w, str) and w.strip().lower() in (
        "bold",
        "semibold",
        "semi-bold",
        "600",
        "700",
        "800",
        "900",
    ):
        run.font.bold = True


def _apply_font_spec(shape: Any, role: str, specs: dict[str, Any]) -> None:
    spec = specs.get(role)
    if not spec or not shape.has_text_frame:
        return
    try:
        for para in shape.text_frame.paragraphs:
            for run in para.runs:
                _apply_run_style_from_spec(run, spec)
    except Exception:
        logger.warning("pptx_builder.style_failed role=%r shape=%r", role, shape, exc_info=True)


def _set_placeholder_text(
    slide: Any,
    types: Iterable[PP_PLACEHOLDER_TYPE],
    text: str | None,
    role: str,
) -> bool:
    if text is None or text == "":
        return False
    for shape in slide.placeholders:
        try:
            ph = shape.placeholder_format
        except (AttributeError, ValueError):
            continue
        if ph.type in types and shape.has_text_frame:
            shape.text_frame.text = str(text)
            logger.debug("pptx_builder.text_set role=%r placeholder=%s", role, ph.type)
            return True
    logger.warning("pptx_builder.missing_placeholder role=%r slide_types=%s", role, types)
    return False


def _set_notes(slide: Any, text: str | None, merged_specs: dict[str, Any]) -> None:
    if text is None or text == "":
        return
    try:
        ns = slide.notes_slide
        tf = ns.notes_text_frame
        tf.text = str(text)
        spec = merged_specs.get("notes")
        if spec and isinstance(spec, dict):
            for para in tf.paragraphs:
                for run in para.runs:
                    _apply_run_style_from_spec(run, spec)
    except Exception:
        logger.warning("pptx_builder.notes_failed", exc_info=True)


def _picture_to_background(
    slide: Any, prs: Presentation, image_path: Path
) -> Any | None:
    width = prs.slide_width
    height = prs.slide_height
    pic = slide.shapes.add_picture(str(image_path), 0, 0, width=width, height=height)
    el = pic._element
    parent = el.getparent()
    if parent is None:
        logger.warning("pptx_builder.background_reorder_skipped")
        return pic
    try:
        parent.remove(el)
        parent.insert(2, el)
        logger.debug("pptx_builder.background_image_ordered path=%r", str(image_path))
    except Exception:
        logger.warning(
            "pptx_builder.background_reorder_failed path=%r",
            str(image_path),
            exc_info=True,
        )
    return pic


def _inject_icon_corner(slide: Any, prs: Presentation, icon_path: str | None) -> None:
    """
    Place a small square icon at the top-right (theme mark); does not replace hero image.
    """
    if not icon_path:
        return
    path = Path(icon_path)
    if not path.is_file():
        logger.warning("pptx_builder.icon_missing path=%r", str(path))
        return
    margin = Inches(0.35)
    side = Inches(1.2)
    left = int(prs.slide_width - side - margin)
    top = int(margin)
    try:
        slide.shapes.add_picture(str(path), left, top, width=side, height=side)
        logger.info("pptx_builder.icon_corner path=%r", str(path))
    except Exception:
        logger.warning(
            "pptx_builder.icon_corner_failed path=%r",
            str(path),
            exc_info=True,
        )


def _largest_body_placeholder_shape(slide: Any) -> Any | None:
    """Body / OBJECT text placeholder with the greatest area (main content well)."""
    shapes = _ordered_text_shapes(slide, _BODY_TYPES_FROZEN)
    if not shapes:
        return None
    return max(shapes, key=lambda s: int(s.width) * int(s.height))


def _inject_chart_into_content_area(
    slide: Any,
    prs: Presentation,
    chart_path: str | None,
    brand: BrandProfile | None = None,
) -> None:
    """
    Path N: place a data chart PNG in the largest body/content placeholder.
    Clears that placeholder's text so the chart is not obscured by body copy.
    """
    if not chart_path:
        return
    path = Path(chart_path)
    if not path.is_file():
        logger.warning("pptx_builder.chart_missing path=%r", str(path))
        return
    target = _largest_body_placeholder_shape(slide)
    if target is None:
        logger.warning(
            "pptx_builder.chart_no_body_placeholder falling_back_to_hero_behavior path=%r",
            str(path),
        )
        _inject_image(slide, prs, str(chart_path), brand=brand)
        return
    try:
        target.text_frame.clear()
    except Exception:
        logger.warning("pptx_builder.chart_clear_body_failed", exc_info=True)
    margin = int(Inches(0.07))
    left = int(target.left) + margin
    top = int(target.top) + margin
    w = max(int(Inches(0.6)), int(target.width) - 2 * margin)
    h = max(int(Inches(0.6)), int(target.height) - 2 * margin)
    try:
        pic = slide.shapes.add_picture(str(path), left, top, width=w, height=h)
        _apply_brand_picture_outline(
            pic,
            brand,
            enabled=bool(brand and brand.frame_chart_png),
        )
        logger.info("pptx_builder.chart_content_area path=%r", str(path))
    except Exception:
        logger.warning(
            "pptx_builder.chart_add_picture_failed path=%r",
            str(path),
            exc_info=True,
        )


def _inject_image(
    slide: Any,
    prs: Presentation,
    image_path: str | None,
    brand: BrandProfile | None = None,
) -> None:
    if not image_path:
        return
    path = Path(image_path)
    if not path.is_file():
        logger.warning("pptx_builder.image_missing path=%r", str(path))
        return

    for shape in slide.placeholders:
        try:
            ph = shape.placeholder_format
        except (AttributeError, ValueError):
            continue
        if ph.type in _PICTURE_TYPES:
            try:
                shape.insert_picture(str(path))
                _apply_brand_picture_outline(
                    shape,
                    brand,
                    enabled=bool(brand and brand.frame_hero_png),
                )
                logger.info("pptx_builder.image_placeholder path=%r", str(path))
                return
            except Exception:
                logger.warning(
                    "pptx_builder.image_placeholder_failed path=%r",
                    str(path),
                    exc_info=True,
                )

    logger.warning(
        "pptx_builder.no_picture_placeholder using_background path=%r",
        str(path),
    )
    pic = _picture_to_background(slide, prs, path)
    if pic is not None:
        _apply_brand_picture_outline(
            pic,
            brand,
            enabled=bool(brand and brand.frame_hero_png),
        )


def assemble_deck(
    deck_json: dict[str, Any],
    template_path: str,
    output_path: str,
    project_root: Path | None = None,
) -> tuple[str, StructuralAuditReport]:
    """
    Merge structured slide data into a user template and save under ``assets/outputs/``
    (or the given absolute path).

    Expected ``deck_json`` shape::

        {
          "slides": [
            {
              "type": "Title and Content",
              "title": "...",
              "body": "...",
              "subtitle": "...",
              "speaker_notes": "...",
              "image_path": "/abs/or/rel/path.png",
              "chart_path": "/abs/chart.png (optional; from chart_request at materialize, Path N)",
              "icon_path": "/abs/path/to/icon.png (optional; from icon_request at materialize)",
              "design_specs": { ... optional per-slide ... },
              "body_left": "optional column A for Two Content / Comparison",
              "body_right": "optional column B",
              "body_columns": ["col1", "col2", "..."]
            }
          ],
          "design_specs": {
            "title": {"size_pt": 44, "color": "#FFFFFF"},
            "body": {"size_pt": 18, "color": "#333333"},
            "subtitle": {"size_pt": 24},
            "notes": {"size_pt": 12},
          },
          "brand": {
            "colors": {"primary": "#003366", "accent": "#FF8C00", "text": "#222222"},
            "typography": {
              "title": {"font": "Source Sans Pro", "size_pt": 40, "bold": true},
              "body": {"font": "Source Sans Pro", "size_pt": 16}
            },
            "css": ":root { --brand-primary: #112233; }",
            "accent_bar": {"enabled": true, "height_pt": 5, "position": "bottom"},
            "image_outline_pt": 2,
            "frame_chart_png": true,
            "frame_hero_png": true,
            "layout_boost": ["executive", "strategy"]
          }
        }

    Brand may also live under ``design_specs.brand``. Merge order for text styles is
    brand defaults → deck ``design_specs`` → per-slide ``design_specs``.

    ``speaker_notes`` may be omitted in favor of ``notes``.

    Returns:
        ``(absolute_path_str, StructuralAuditReport)`` — Path M runs a placeholder overflow
        heuristic after each slide (before save) when ``RELULAYER_STRUCTURAL_AUDIT`` is on.
    """
    root = project_root or _REPO_ROOT
    tpl = Path(template_path)
    if not tpl.is_file():
        raise FileNotFoundError(f"Template not found: {tpl}")

    final_path = _resolve_output_path(output_path, root)
    deck_specs_raw = deck_json.get("design_specs") or {}
    if deck_specs_raw and not isinstance(deck_specs_raw, dict):
        logger.warning("pptx_builder.design_specs_invalid ignoring")
        deck_specs_raw = {}
    deck_specs = {
        k: v for k, v in deck_specs_raw.items() if k != "brand"
    }

    brand = brand_profile_from_deck_json(deck_json)

    report = StructuralAuditReport(audit_enabled=_structural_audit_enabled())
    prs: Presentation | None = None
    try:
        prs = Presentation(str(tpl))
        slides_data = _slides_from_deck(deck_json)
        layout_catalog = build_layout_catalog(prs)

        for idx, slide_data in enumerate(slides_data):
            image_path = slide_data.get("image_path")
            chart_path = slide_data.get("chart_path")
            icon_path = slide_data.get("icon_path")
            layout_prof = pick_best_layout(
                layout_catalog,
                slide_data.get("type"),
                has_image=bool(image_path or chart_path),
                brand=brand,
            )
            slide = prs.slides.add_slide(layout_prof.layout)
            merged_specs = _merge_brand_design_layer(
                brand,
                deck_specs,
                slide_data.get("design_specs"),
            )

            title = slide_data.get("title")
            subtitle = slide_data.get("subtitle")
            notes = slide_data.get("speaker_notes")
            if notes is None:
                notes = slide_data.get("notes")

            if image_path:
                _inject_image(slide, prs, str(image_path), brand=brand)

            _set_placeholder_text(slide, _TITLE_TYPES, title, "title")
            _set_placeholder_text(slide, _SUBTITLE_TYPES, subtitle, "subtitle")
            slide_type_norm = _normalize(str(slide_data.get("type") or ""))
            _fill_body_placeholders_distributed(
                slide,
                slide_data,
                slide_type_norm,
            )

            for shape in slide.placeholders:
                if not shape.has_text_frame:
                    continue
                try:
                    ph = shape.placeholder_format.type
                except (AttributeError, ValueError):
                    continue
                if ph in _TITLE_TYPES:
                    _apply_font_spec(shape, "title", merged_specs)
                elif ph in _SUBTITLE_TYPES:
                    _apply_font_spec(shape, "subtitle", merged_specs)
                elif ph in _BODY_TYPES:
                    _apply_font_spec(shape, "body", merged_specs)

            if chart_path:
                _inject_chart_into_content_area(
                    slide, prs, str(chart_path), brand=brand
                )

            _set_notes(slide, str(notes) if notes is not None else None, merged_specs)

            if report.audit_enabled:
                _structural_audit_slide_placeholders(slide, idx, merged_specs, report)
                _structural_audit_notes(slide, idx, merged_specs, report)

            if icon_path:
                _inject_icon_corner(slide, prs, str(icon_path))

            _add_brand_accent_bar(slide, prs, brand)

            logger.info(
                "pptx_builder.slide_built index=%s layout=%r body_slots=%s meta_ph=%s",
                idx,
                layout_prof.name,
                layout_prof.body_slots,
                layout_prof.meta_placeholder_slots,
            )

        prs.save(str(final_path))
        logger.info(
            "pptx_builder.saved path=%r slides=%s structural_adjustments=%s",
            str(final_path),
            len(slides_data),
            len(report.adjustments),
        )
        return str(final_path.resolve()), report
    finally:
        del prs
        VRAMManager.clear()
