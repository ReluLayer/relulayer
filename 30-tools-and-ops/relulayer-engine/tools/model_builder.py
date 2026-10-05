"""
Path CC — Financial appendix workbook synthesis from GTM draft JSON.

Extracts numerical signals (ROI, NPV, headcount, chart series, etc.) and writes a
multi-sheet ``.xlsx`` via openpyxl with assumption tables and formula-based projections.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent

# (regex, canonical label, unit hint)
_FIN_LABEL_PATTERNS: tuple[tuple[str, str, str], ...] = (
    (
        r"(?i)(?:return on investment|\broi\b)[^\d%]{0,60}?(\d+(?:\.\d+)?)\s*%",
        "ROI",
        "%",
    ),
    (
        r"(?i)\birr\b[^\d%]{0,60}?(\d+(?:\.\d+)?)\s*%",
        "IRR",
        "%",
    ),
    (
        r"(?i)\bcagr\b[^\d%]{0,60}?(\d+(?:\.\d+)?)\s*%",
        "CAGR",
        "%",
    ),
    (
        r"(?i)\bmargin\b[^\d%]{0,40}?(\d+(?:\.\d+)?)\s*%",
        "Margin",
        "%",
    ),
    (
        r"(?i)\bnpv\b[^\d$€£]{0,40}?[$€£]?\s*([\d,]+(?:\.\d+)?)\s*([mbk])?\b",
        "NPV",
        "currency",
    ),
    (
        r"(?i)(?:arr|annual recurring revenue)[^\d$€£]{0,30}?[$€£]?\s*([\d,]+(?:\.\d+)?)\s*([mbk])?\b",
        "ARR",
        "currency",
    ),
    (
        r"(?i)(?:revenue|top[- ]?line|sales)[^\d$€£]{0,25}?[$€£]?\s*([\d,]+(?:\.\d+)?)\s*([mbk])?\b",
        "Revenue (mentioned)",
        "currency",
    ),
    (
        r"(?i)(?:capex|capital expenditure)[^\d$€£]{0,30}?[$€£]?\s*([\d,]+(?:\.\d+)?)\s*([mbk])?\b",
        "CAPEX",
        "currency",
    ),
    (
        r"(?i)(?:opex|operating expense)[^\d$€£]{0,30}?[$€£]?\s*([\d,]+(?:\.\d+)?)\s*([mbk])?\b",
        "OPEX",
        "currency",
    ),
    (
        r"(?i)(?:headcount|fte|full[- ]time equivalents?)\D{0,45}?(\d+(?:,\d{3})+|\d{2,})\b",
        "Headcount / FTE",
        "count",
    ),
    (
        r"(?i)(?:payback|breakeven)[^\d]{0,40}?(\d+(?:\.\d+)?)\s*(?:year|yr|months?|mo\b)",
        "Payback period",
        "duration",
    ),
)

_CURRENCY_INLINE = re.compile(
    r"[$€£]\s*([\d,]+(?:\.\d+)?)\s*([mbk]illion|[mbk])\b|[$€£]\s*([\d,]+(?:\.\d+)?)\b",
    re.IGNORECASE,
)


def _parse_number(raw: str, suffix: str | None = None) -> float | None:
    s = (raw or "").replace(",", "").strip()
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    suf = (suffix or "").strip().lower()
    if suf in ("m", "million", "mil"):
        v *= 1_000_000
    elif suf in ("b", "billion", "bn"):
        v *= 1_000_000_000
    elif suf in ("k", "thousand"):
        v *= 1_000
    return v


def _slide_text_blob(slide: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "title",
        "subtitle",
        "body",
        "body_left",
        "body_right",
        "speaker_notes",
    ):
        val = slide.get(key)
        if val is None:
            continue
        if isinstance(val, str) and val.strip():
            parts.append(val.strip())
        elif isinstance(val, list):
            parts.append(
                " ".join(str(x) for x in val if x is not None),
            )
    bc = slide.get("body_columns")
    if isinstance(bc, list):
        for col in bc:
            if isinstance(col, dict):
                parts.append(str(col.get("heading") or ""))
                parts.append(str(col.get("body") or ""))
    return "\n".join(parts)


def _coerce_number_list(val: Any) -> list[float]:
    out: list[float] = []
    if not isinstance(val, list):
        return out
    for x in val:
        if isinstance(x, (int, float)):
            out.append(float(x))
        elif isinstance(x, str):
            n = _parse_number(x, None)
            if n is not None:
                out.append(n)
    return out


def _coerce_axis_list(val: Any) -> list[str]:
    if not isinstance(val, list):
        return []
    return [str(x) if x is not None else "" for x in val]


def _extract_from_chart_spec(
    spec: dict[str, Any],
    slide_index: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(spec, dict) or not spec:
        return rows
    title = str(spec.get("title") or f"Slide {slide_index + 1} chart").strip()
    ct = str(spec.get("chart_type") or "bar").lower()
    if ct == "pie":
        labels = _coerce_axis_list(spec.get("labels"))
        values = _coerce_number_list(spec.get("values"))
        n = min(len(labels), len(values))
        for i in range(n):
            rows.append(
                {
                    "label": f"{title} — {labels[i]}",
                    "value": values[i],
                    "unit": "chart",
                    "source": f"slide {slide_index + 1} (pie)",
                },
            )
        return rows
    if isinstance(spec.get("series"), list) and spec["series"]:
        for s in spec["series"]:
            if not isinstance(s, dict):
                continue
            name = str(s.get("name") or "Series")
            xs = _coerce_axis_list(s.get("x"))
            ys = _coerce_number_list(s.get("y"))
            if not ys:
                continue
            if not xs:
                xs = [str(i) for i in range(len(ys))]
            n = min(len(xs), len(ys))
            for i in range(n):
                rows.append(
                    {
                        "label": f"{title} — {name} @ {xs[i]}",
                        "value": ys[i],
                        "unit": "chart",
                        "source": f"slide {slide_index + 1}",
                    },
                )
        return rows
    xs = _coerce_axis_list(spec.get("x"))
    ys = _coerce_number_list(
        spec.get("y") if spec.get("y") is not None else spec.get("values"),
    )
    if len(ys) >= 1:
        if not xs:
            xs = [str(i) for i in range(len(ys))]
        n = min(len(xs), len(ys))
        for i in range(n):
            rows.append(
                {
                    "label": f"{title} — {xs[i]}",
                    "value": ys[i],
                    "unit": "chart",
                    "source": f"slide {slide_index + 1}",
                },
            )
    return rows


def _extract_labeled_currency(text: str, slide_idx: int) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for m in _CURRENCY_INLINE.finditer(text):
        g1, g2, g3 = m.group(1), m.group(2), m.group(3)
        raw = g1 or g3 or ""
        suf = g2 if g2 and g2.lower() not in ("illion",) else None
        if g2 and g2.lower() in ("m", "b", "k"):
            suf = g2.lower()
        val = _parse_number(raw, suf)
        if val is None or val == 0:
            continue
        start = max(0, m.start() - 30)
        ctx = text[start : m.start()].strip()
        label = (ctx.split()[-3:] if ctx else [])
        label_s = " ".join(label)[:48] or "Currency (inline)"
        found.append(
            {
                "label": label_s,
                "value": val,
                "unit": "USD (parsed)",
                "source": f"slide {slide_idx + 1}",
            },
        )
    return found


class FinancialModelBuilder:
    """
    Parse GTM slide dicts for quantitative hints and emit a workbook with
    Assumptions, chart-derived series, parameters, and projection formulas.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self._root = project_root or _REPO_ROOT

    def extract_assumptions(self, slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        def add_row(label: str, value: float, unit: str, source: str) -> None:
            key = (label.strip().lower(), f"{value:.6g}")
            if key in seen:
                return
            seen.add(key)
            rows.append(
                {
                    "label": label.strip()[:120],
                    "value": value,
                    "unit": unit,
                    "source": source,
                },
            )

        for idx, slide in enumerate(slides):
            if not isinstance(slide, dict):
                continue
            blob = _slide_text_blob(slide)
            for rx, label, unit in _FIN_LABEL_PATTERNS:
                for m in re.finditer(rx, blob):
                    groups = m.groups()
                    val = None
                    u = unit
                    if unit == "currency" and groups:
                        val = _parse_number(groups[0], groups[1] if len(groups) > 1 else None)
                    elif unit == "%" and groups:
                        val = _parse_number(groups[0], None)
                    elif unit == "count" and groups:
                        val = _parse_number(groups[0].replace(",", ""), None)
                    elif unit == "duration" and groups:
                        val = _parse_number(groups[0], None)
                    if val is not None:
                        add_row(label, val, u, f"slide {idx + 1}")

            for cr_row in _extract_labeled_currency(blob, idx):
                add_row(
                    cr_row["label"],
                    float(cr_row["value"]),
                    cr_row["unit"],
                    cr_row["source"],
                )

            cr = slide.get("chart_request")
            if isinstance(cr, dict) and cr:
                for r in _extract_from_chart_spec(cr, idx):
                    add_row(r["label"], float(r["value"]), r["unit"], r["source"])

        # Drop noisy inline $ parses that duplicate a structured row on the same slide.
        structured_vals: dict[str, set[float]] = {}
        for r in rows:
            if r["unit"] == "USD (parsed)":
                continue
            if "currency" in r["unit"] or r["unit"] in ("%", "count", "chart", "duration"):
                structured_vals.setdefault(r["source"], set()).add(float(r["value"]))

        def _matches_structured(source: str, value: float) -> bool:
            for v in structured_vals.get(source, ()):
                if abs(value - v) <= max(1.0, abs(v) * 1e-9):
                    return True
            return False

        rows = [
            r
            for r in rows
            if not (
                r["unit"] == "USD (parsed)"
                and _matches_structured(r["source"], float(r["value"]))
            )
        ]

        rows.sort(key=lambda r: (r["source"], r["label"]))
        return rows

    def _pick_parameters(self, assumptions: list[dict[str, Any]]) -> dict[str, float]:
        """Choose defaults for Parameters sheet from extracted rows."""
        base_rev = 1_000_000.0
        growth = 0.08
        headcount = 50.0
        opex_fte = 150_000.0

        rev_keys = ("arr", "revenue", "chart")
        for r in assumptions:
            lab = r["label"].lower()
            if any(k in lab for k in rev_keys) and r["unit"] in ("currency", "USD (parsed)", "chart"):
                v = float(r["value"])
                if v > base_rev or "arr" in lab or "revenue" in lab:
                    base_rev = max(base_rev, v)

        for r in assumptions:
            if "cagr" in r["label"].lower() and r["unit"] == "%":
                growth = min(0.5, max(0.0, float(r["value"]) / 100.0))
                break

        for r in assumptions:
            if "headcount" in r["label"].lower() or "fte" in r["label"].lower():
                headcount = max(1.0, float(r["value"]))
                break

        for r in assumptions:
            if "opex" in r["label"].lower() and r["unit"] == "currency":
                opex_fte = max(10_000.0, float(r["value"]) / max(1.0, headcount))
                break

        return {
            "base_revenue": base_rev,
            "annual_growth": growth,
            "headcount": headcount,
            "opex_per_fte": opex_fte,
        }

    def build_and_save(
        self,
        slides: list[dict[str, Any]],
        output_xlsx: str | Path,
    ) -> str:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        out = Path(output_xlsx)
        out.parent.mkdir(parents=True, exist_ok=True)

        assumptions = self.extract_assumptions(slides)
        params = self._pick_parameters(assumptions)

        wb = Workbook()
        header_font = Font(bold=True, color="FFe2e8f0")
        header_fill = PatternFill("solid", fgColor="FF1e293b")

        # --- Cover ---
        ws0 = wb.active
        ws0.title = "Cover"
        ws0["A1"] = "ReluLayer — Financial Appendix"
        ws0["A1"].font = Font(bold=True, size=14)
        ws0["A3"] = "Generated (UTC):"
        ws0["B3"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
        ws0["A4"] = "Source:"
        ws0["B4"] = "GTM draft slides (Path CC — model builder)"
        ws0["A5"] = "Slides in deck:"
        ws0["B5"] = len([s for s in slides if isinstance(s, dict)])
        ws0["A6"] = "Extracted assumption rows:"
        ws0["B6"] = len(assumptions)
        ws0["A8"] = (
            "Figures are heuristically extracted from slide text and chart_request JSON. "
            "Validate all inputs before external distribution."
        )
        ws0["A8"].alignment = Alignment(wrap_text=True)
        ws0.column_dimensions["A"].width = 28
        ws0.column_dimensions["B"].width = 72

        # --- Assumptions ---
        ws_a = wb.create_sheet("Assumptions", 1)
        headers = ("Label", "Value", "Unit", "Source")
        for col, h in enumerate(headers, start=1):
            c = ws_a.cell(row=1, column=col, value=h)
            c.font = header_font
            c.fill = header_fill
        for i, r in enumerate(assumptions, start=2):
            ws_a.cell(row=i, column=1, value=r["label"])
            ws_a.cell(row=i, column=2, value=r["value"])
            ws_a.cell(row=i, column=3, value=r["unit"])
            ws_a.cell(row=i, column=4, value=r["source"])
        for col in range(1, 5):
            ws_a.column_dimensions[get_column_letter(col)].width = 18 if col != 1 else 40

        # --- Chart series (flat log) ---
        ws_c = wb.create_sheet("Chart_Series", 2)
        chart_rows = [r for r in assumptions if r["unit"] == "chart"]
        for col, h in enumerate(("Label", "Value", "Source"), start=1):
            c = ws_c.cell(row=1, column=col, value=h)
            c.font = header_font
            c.fill = header_fill
        if chart_rows:
            for i, r in enumerate(chart_rows, start=2):
                ws_c.cell(row=i, column=1, value=r["label"])
                ws_c.cell(row=i, column=2, value=r["value"])
                ws_c.cell(row=i, column=3, value=r["source"])
        else:
            ws_c.cell(row=2, column=1, value="(no chart_request series captured)")
        ws_c.column_dimensions["A"].width = 48
        ws_c.column_dimensions["B"].width = 14

        # --- Parameters (named drivers for formulas) ---
        ws_p = wb.create_sheet("Parameters", 3)
        ws_p["A1"] = "Parameter"
        ws_p["B1"] = "Value"
        ws_p["A1"].font = header_font
        ws_p["B1"].font = header_font
        ws_p["A1"].fill = header_fill
        ws_p["B1"].fill = header_fill
        param_rows = [
            ("Base revenue (Year 0)", params["base_revenue"], "$"),
            ("Annual revenue growth", params["annual_growth"], "decimal"),
            ("Headcount (Year 0)", params["headcount"], "FTE"),
            ("OPEX per FTE (annual)", params["opex_per_fte"], "$"),
        ]
        for i, (name, val, note) in enumerate(param_rows, start=2):
            ws_p.cell(row=i, column=1, value=name)
            ws_p.cell(row=i, column=2, value=val)
            ws_p.cell(row=i, column=3, value=note)
        ws_p.column_dimensions["A"].width = 28
        ws_p.column_dimensions["B"].width = 18

        # --- Projections (5 years, formulas) ---
        ws_pr = wb.create_sheet("Projections", 4)
        ws_pr["A1"] = "Metric"
        ws_pr["A1"].font = header_font
        ws_pr["A1"].fill = header_fill
        for y in range(6):
            col = 2 + y
            ws_pr.cell(row=1, column=col, value=f"Year {y}")
            c = ws_pr.cell(row=1, column=col)
            c.font = header_font
            c.fill = header_fill

        # Revenue row 2
        ws_pr["A2"] = "Revenue"
        ws_pr["B2"] = "=Parameters!$B$2"
        for y in range(1, 6):
            col_letter = get_column_letter(2 + y)
            prev = get_column_letter(1 + y)
            ws_pr[f"{col_letter}2"] = f"={prev}2*(1+Parameters!$B$3)"

        # OPEX row 3 = headcount * opex_per_fte * (1 + 0.03*year) simple ramp
        ws_pr["A3"] = "OPEX (illustrative)"
        ws_pr["B3"] = "=Parameters!$B$4*Parameters!$B$5"
        for y in range(1, 6):
            col_letter = get_column_letter(2 + y)
            prev = get_column_letter(1 + y)
            ws_pr[f"{col_letter}3"] = f"={prev}3*1.03"

        # Headcount row 4
        ws_pr["A4"] = "Headcount"
        ws_pr["B4"] = "=Parameters!$B$4"
        for y in range(1, 6):
            col_letter = get_column_letter(2 + y)
            prev = get_column_letter(1 + y)
            ws_pr[f"{col_letter}4"] = f"=ROUND({prev}4*1.05,0)"

        # Simple EBITDA proxy row 5
        ws_pr["A5"] = "EBITDA (proxy: Rev - OPEX)"
        for y in range(6):
            col_letter = get_column_letter(2 + y)
            rev = f"{col_letter}2"
            opex = f"{col_letter}3"
            ws_pr[f"{col_letter}5"] = f"={rev}-{opex}"

        ws_pr.column_dimensions["A"].width = 28
        for c in range(2, 8):
            ws_pr.column_dimensions[get_column_letter(c)].width = 14

        wb.save(str(out.resolve()))
        logger.info(
            "event=model_builder.saved path=%s assumptions=%s",
            out,
            len(assumptions),
        )
        return str(out.resolve())


def write_financial_appendix_workbook(
    slides: list[dict[str, Any]],
    output_xlsx: str | Path,
    *,
    project_root: Path | None = None,
) -> str:
    """Convenience: build workbook and return absolute path."""
    b = FinancialModelBuilder(project_root=project_root)
    return b.build_and_save(slides, output_xlsx)
