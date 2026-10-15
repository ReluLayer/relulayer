"""Deterministic tabular extraction for Agentic ETL (Excel/CSV → LLM-safe text)."""

import io
from pathlib import Path

import pandas as pd


def _load_dataframe(file_bytes: bytes, filename: str) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    buf = io.BytesIO(file_bytes)

    if suffix == ".csv":
        return pd.read_csv(buf)
    if suffix in (".xlsx", ".xlsm"):
        return pd.read_excel(buf, engine="openpyxl")
    raise ValueError(
        f"Unsupported extension {suffix!r}; expected .csv or .xlsx / .xlsm."
    )


def _md_table_from_dataframe(
    table: pd.DataFrame, columns: list[str] | None = None
) -> str:
    """Pipe-delimited Markdown table without extra dependencies."""
    use = table.copy()
    if columns is not None:
        use.columns = columns

    def cell(v) -> str:
        if pd.isna(v):
            return ""
        s = str(v).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        return s.replace("|", "¦")

    cols = [str(c) for c in use.columns]
    out = [
        "| " + " | ".join(cell(c) for c in cols) + " |",
        "| " + " | ".join("---" for _ in cols) + " |",
    ]
    for _, row in use.iterrows():
        out.append("| " + " | ".join(cell(row[c]) for c in use.columns) + " |")
    return "\n".join(out)


def _schema_block(df: pd.DataFrame) -> str:
    lines = ["## Schema", ""]
    info = pd.DataFrame(
        {
            "column": df.columns.astype(str),
            "dtype": [str(df[c].dtype) for c in df.columns],
            "non_null": [int(df[c].notna().sum()) for c in df.columns],
            "null": [int(df[c].isna().sum()) for c in df.columns],
        }
    )
    lines.append(_md_table_from_dataframe(info))
    lines.append("")
    lines.append(f"**Rows (total):** {len(df)}")
    lines.append("")
    return "\n".join(lines)


def _md_cell(v) -> str:
    if pd.isna(v):
        return ""
    s = str(v).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    return s.replace("|", "¦")


def _markdown_table(df: pd.DataFrame, max_rows: int = 50) -> str:
    sample = df.head(max_rows).copy()
    cols = [str(c) for c in sample.columns]
    header = "| " + " | ".join(_md_cell(c) for c in cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    rows_out = []
    for _, row in sample.iterrows():
        cells = [_md_cell(row[c]) for c in sample.columns]
        rows_out.append("| " + " | ".join(cells) + " |")
    parts = [
        "## Sample data (first rows)",
        "",
        f"*Showing up to {max_rows} rows.*",
        "",
        header,
        sep,
    ]
    parts.extend(rows_out)
    parts.append("")
    return "\n".join(parts)


def _aggregates_block(df: pd.DataFrame) -> str:
    num = df.select_dtypes(include=["number"])
    if num.empty:
        return "## Numeric aggregates\n\n*No numeric columns detected.*\n"

    agg = num.agg(["sum", "mean"]).T.reset_index().rename(columns={"index": "column"})
    lines = ["## Numeric aggregates", ""]
    lines.append(
        "*Per-column `sum` and `mean` (pandas dtypes: integer, float, etc.).*"
    )
    lines.append("")
    lines.append(_md_table_from_dataframe(agg))
    lines.append("")
    return "\n".join(lines)


def extract_tabular_data(file_bytes: bytes, filename: str) -> str:
    """
    Ingest tabular bytes and return a single deterministic string: schema summary,
    first 50 rows as Markdown, and numeric sum/mean aggregates.

    No inference or LLM calls; suitable for orchestrator context injection.
    """
    df = _load_dataframe(file_bytes, filename)

    parts = [
        f"# Tabular extract: `{Path(filename).name}`",
        "",
        _schema_block(df),
        _markdown_table(df, max_rows=50),
        _aggregates_block(df),
    ]
    return "\n".join(parts).strip() + "\n"
