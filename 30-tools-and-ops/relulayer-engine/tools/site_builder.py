from __future__ import annotations

import base64
import html
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from tools.visual_generator import plotly_web_bundle_from_chart_spec

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent

PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.27.0.min.js"
TAILWIND_CDN = "https://cdn.tailwindcss.com"


def outputs_sites_dir(project_root: Path | None = None) -> Path:
    """``assets/outputs/sites/`` — served as ``/static/outputs/sites/``."""
    root = project_root or _REPO_ROOT
    out = root / "assets" / "outputs" / "sites"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _resolve_asset_path(path_str: str | None, project_root: Path) -> Path | None:
    if not path_str or not str(path_str).strip():
        return None
    p = Path(str(path_str).strip())
    if p.is_file():
        return p.resolve()
    cand = (project_root / p).resolve()
    if cand.is_file():
        return cand
    return None


def _file_to_data_uri(path: Path, *, max_bytes: int = 12_000_000) -> str | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if len(raw) > max_bytes:
        logger.warning("site_builder.embed_skip_too_large path=%r bytes=%s", str(path), len(raw))
        return None
    ext = path.suffix.lower()
    if ext in (".jpg", ".jpeg"):
        mime = "image/jpeg"
    elif ext == ".webp":
        mime = "image/webp"
    elif ext == ".svg":
        mime = "image/svg+xml"
    else:
        mime = "image/png"
    b64 = base64.standard_b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _format_body_to_html(text: str) -> str:
    t = (text or "").replace("\r\n", "\n")
    if not t.strip():
        return ""
    lines = t.split("\n")
    parts: list[str] = []
    in_ul = False
    for line in lines:
        s = line.strip()
        bullet = False
        item_text = ""
        for prefix in ("- ", "* ", "• "):
            if s.startswith(prefix):
                bullet = True
                item_text = s[len(prefix) :].strip()
                break
        if bullet:
            if not in_ul:
                parts.append(
                    '<ul class="list-disc pl-5 space-y-1 my-3 text-slate-300 text-sm leading-relaxed">',
                )
                in_ul = True
            parts.append(f"<li>{html.escape(item_text)}</li>")
        else:
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            if s:
                parts.append(
                    f'<p class="text-slate-300 text-sm leading-relaxed my-2 whitespace-pre-wrap">{html.escape(line)}</p>',
                )
            else:
                parts.append('<div class="h-2"></div>')
    if in_ul:
        parts.append("</ul>")
    return "\n".join(parts)


def _json_for_script(obj: Any) -> str:
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return s.replace("</script>", "<\\/script>")


def build_executive_microsite(
    *,
    slides: list[dict[str, Any]],
    page_title: str = "Executive briefing",
    subtitle: str = "",
    project_root: Path | None = None,
) -> tuple[str, str]:
    """
    Path Z: write one self-contained HTML file with Tailwind (CDN) and Plotly (CDN).

    Returns ``(absolute_path, static_href)`` e.g. ``("/.../assets/outputs/sites/x.html", "/static/outputs/sites/x.html")``.
    """
    root = (project_root or _REPO_ROOT).resolve()
    slides_norm = [s for s in slides if isinstance(s, dict)]
    uid = uuid.uuid4().hex[:10]
    fname = f"microsite_{uid}.html"
    out_path = outputs_sites_dir(root) / fname

    nav_items: list[str] = []
    sections: list[str] = []
    init_scripts: list[str] = []

    for i, slide in enumerate(slides_norm):
        sid = f"slide-{i}"
        nav_items.append(
            f'<a href="#{sid}" class="inline-block lg:block max-w-[220px] py-1 px-2 rounded-md hover:bg-slate-800/80 text-slate-400 hover:text-cyan-300 truncate" title="{html.escape(str(slide.get("title") or f"Slide {i+1}"), quote=True)}">'
            f"{i + 1}. {html.escape(str(slide.get('title') or 'Slide')[:48])}"
            f"</a>",
        )

        title = html.escape(str(slide.get("title") or f"Slide {i + 1}"))
        stype = html.escape(str(slide.get("type") or "Content"))
        sub = slide.get("subtitle")
        sub_html = (
            f'<p class="text-cyan-500/90 text-xs font-mono uppercase tracking-widest mt-1">{html.escape(str(sub))}</p>'
            if sub
            else ""
        )

        hero_block = ""
        ip = slide.get("image_path")
        resolved = _resolve_asset_path(str(ip) if ip else None, root)
        if resolved:
            du = _file_to_data_uri(resolved)
            if du:
                hero_block = (
                    f'<figure class="mt-6 rounded-xl overflow-hidden border border-slate-700/80 bg-slate-900/50 shadow-lg shadow-cyan-950/20">'
                    f'<img src="{du}" alt="" class="w-full h-auto max-h-[min(70vh,520px)] object-cover object-center"/>'
                    f"</figure>"
                )

        chart_block = ""
        cr = slide.get("chart_request")
        if not isinstance(cr, dict) or not cr:
            cd = slide.get("chart_data")
            if isinstance(cd, dict) and cd:
                cr = cd
        bundle = plotly_web_bundle_from_chart_spec(cr) if isinstance(cr, dict) and cr else None
        plotly_div_id = f"plotly-{i}"
        if bundle and bundle.get("data"):
            data_j = _json_for_script(bundle["data"])
            layout_j = _json_for_script(bundle.get("layout") or {})
            init_scripts.append(
                f"(function(){{var d={data_j};var l={layout_j};"
                f"Plotly.newPlot('{plotly_div_id}',d,l,"
                f"{{responsive:true,displayModeBar:true,displaylogo:false}});}})();",
            )
            chart_block = (
                f'<div class="mt-6 rounded-xl border border-slate-700/60 bg-slate-950/40 p-4 backdrop-blur-sm">'
                f'<p class="text-[10px] uppercase tracking-widest text-slate-500 font-mono mb-3">Path N — interactive chart</p>'
                f'<div id="{plotly_div_id}" class="w-full min-h-[320px]"></div></div>'
            )
        else:
            cp = slide.get("chart_path")
            cr_path = _resolve_asset_path(str(cp) if cp else None, root)
            if cr_path:
                du_c = _file_to_data_uri(cr_path)
                if du_c:
                    chart_block = (
                        f'<div class="mt-6 rounded-xl border border-slate-700/60 bg-slate-950/40 p-4">'
                        f'<p class="text-[10px] uppercase tracking-widest text-slate-500 font-mono mb-2">Chart (static)</p>'
                        f'<img src="{du_c}" alt="Chart" class="w-full h-auto rounded-lg"/></div>'
                    )

        body_html = _format_body_to_html(str(slide.get("body") or ""))
        notes = slide.get("speaker_notes") or slide.get("notes")
        notes_html = ""
        if notes and str(notes).strip():
            notes_html = (
                f'<details class="mt-4 text-xs text-slate-500 border border-slate-800 rounded-lg p-3 bg-slate-950/30">'
                f"<summary class=\"cursor-pointer text-slate-400 font-sans\">Speaker notes</summary>"
                f'<div class="mt-2 whitespace-pre-wrap text-slate-400">{html.escape(str(notes))}</div></details>'
            )

        empty_body = '<p class="text-slate-500 text-sm">(no body)</p>'
        sections.append(
            f'<section id="{sid}" class="scroll-mt-24 border-b border-slate-800/80 pb-16 mb-16 last:border-0 last:pb-0 last:mb-0">'
            f'<header class="flex flex-wrap items-baseline justify-between gap-2">'
            f'<div><span class="text-[10px] font-mono text-slate-500">{stype}</span>'
            f'<h2 class="text-2xl md:text-3xl font-bold text-slate-100 font-sans tracking-tight">{title}</h2>{sub_html}</div>'
            f'<span class="text-xs font-mono text-slate-600">#{i + 1}</span></header>'
            f"{hero_block}{chart_block}"
            f'<article class="mt-6 prose prose-invert prose-sm max-w-none">{body_html or empty_body}</article>'
            f"{notes_html}</section>",
        )

    nav_html = "\n".join(nav_items) if nav_items else '<span class="text-slate-600 text-xs">No slides</span>'
    main_html = "\n".join(sections) if sections else '<p class="text-slate-500">No slides in deck.</p>'
    script_body = "\n".join(init_scripts)

    sub_hdr = (
        f'<p class="mt-2 text-slate-400 text-sm max-w-2xl">{html.escape(subtitle)}</p>'
        if subtitle.strip()
        else ""
    )

    doc = f"""<!DOCTYPE html>
<html lang="en" class="scroll-smooth">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{html.escape(page_title)}</title>
  <script src="{TAILWIND_CDN}"></script>
  <script>
    tailwind.config = {{
      theme: {{
        extend: {{
          fontFamily: {{
            sans: ["ui-sans-serif", "system-ui", "sans-serif"],
            mono: ["ui-monospace", "monospace"],
          }},
        }},
      }},
    }};
  </script>
  <script src="{PLOTLY_CDN}" defer></script>
  <style>
    body {{ background: linear-gradient(165deg, #020617 0%, #0f172a 45%, #020617 100%); }}
  </style>
</head>
<body class="min-h-screen text-slate-200 antialiased">
  <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 pb-24">
    <header class="mb-12 border-b border-slate-800/80 pb-8">
      <p class="text-[10px] uppercase tracking-[0.25em] text-cyan-500/80 font-mono mb-2">ReluLayer · Path Z</p>
      <h1 class="text-3xl sm:text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-cyan-300 to-emerald-400 font-sans">{html.escape(page_title)}</h1>
      {sub_hdr}
      <p class="mt-4 text-[11px] text-slate-600 font-mono">Single-file executive microsite · Tailwind CDN · Plotly.js charts</p>
    </header>
    <div class="lg:grid lg:grid-cols-[minmax(0,220px)_1fr] lg:gap-12 items-start">
      <nav class="mb-8 lg:mb-0 flex flex-wrap lg:flex-col gap-1 lg:sticky lg:top-8 lg:self-start rounded-xl border border-slate-800 bg-slate-950/50 p-3 text-xs font-sans backdrop-blur-sm max-h-none lg:max-h-[70vh] lg:overflow-y-auto" aria-label="Slide index">
        <p class="w-full text-[10px] uppercase tracking-widest text-slate-500 mb-1 px-2">Index</p>
        <div class="flex flex-wrap lg:flex-col gap-0.5 w-full">{nav_html}</div>
      </nav>
      <main class="min-w-0">{main_html}</main>
    </div>
    <footer class="mt-20 pt-8 border-t border-slate-800 text-center text-[11px] text-slate-600 font-mono">
      Generated by ReluLayer Web Materializer · local /static/outputs/sites/
    </footer>
  </div>
  <script>
    document.addEventListener("DOMContentLoaded", function() {{
      if (typeof Plotly === "undefined") return;
      {script_body}
    }});
  </script>
</body>
</html>
"""

    out_path.write_text(doc, encoding="utf-8")
    try:
        rel = out_path.resolve().relative_to((root / "assets").resolve())
        href = f"/static/{rel.as_posix()}"
    except ValueError:
        href = f"/static/outputs/sites/{fname}"

    logger.info("site_builder.microsite_written path=%r slides=%s", str(out_path), len(slides_norm))
    return str(out_path.resolve()), href
