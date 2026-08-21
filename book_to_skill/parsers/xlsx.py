from __future__ import annotations

import csv
import sys
from pathlib import Path

# 超大表格最多提取多少行，避免把几千行的纯数据灌进 skill
_MAX_ROWS = 2000


def extract_spreadsheet(input_path: str) -> str | None:
    """Extract text from a spreadsheet (.xlsx / .xls / .csv), preserving each
    sheet as a Markdown table so table structure survives into the skill."""
    ext = Path(input_path).suffix.lower()
    try:
        if ext == ".xlsx":
            return _extract_xlsx(input_path)
        elif ext == ".xls":
            return _extract_xls(input_path)
        elif ext == ".csv":
            return _extract_csv(input_path)
    except Exception as e:
        print(
            f"  [warn] extract_spreadsheet failed: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
    return None


def _extract_xlsx(path: str) -> str:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        parts = []
        for ws in wb.worksheets:
            rows = [list(r) for r in ws.iter_rows(values_only=True)]
            if rows:
                parts.append(f"## Sheet: {ws.title}\n\n{_rows_to_markdown(rows)}")
        return "\n\n".join(parts)
    finally:
        wb.close()


def _extract_xls(path: str) -> str:
    import xlrd

    book = xlrd.open_workbook(path)
    parts = []
    for sheet in book.sheets():
        rows = [sheet.row_values(i) for i in range(sheet.nrows)]
        if rows:
            parts.append(f"## Sheet: {sheet.name}\n\n{_rows_to_markdown(rows)}")
    return "\n\n".join(parts)


def _extract_csv(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return ""
    return f"## CSV: {Path(path).name}\n\n{_rows_to_markdown(rows)}"


def _rows_to_markdown(rows: list, max_rows: int = _MAX_ROWS) -> str:
    """Convert a list-of-rows into a Markdown table.

    First row is the header. Empty/None cells become empty strings; embedded
    pipes and newlines are neutralised so they don't break the table."""
    if not rows:
        return ""

    max_cols = max(len(r) for r in rows)
    truncated = len(rows) > max_rows + 1  # +1 keeps the header row out of the count
    rows = rows[: max_rows + 1] if truncated else rows

    def cell_str(v) -> str:
        if v is None:
            return ""
        s = str(v).replace("|", "\\|").replace("\n", " ").replace("\r", " ").strip()
        return s

    norm = []
    for r in rows:
        norm.append([r[i] if i < len(r) else "" for i in range(max_cols)])

    lines = []
    header = norm[0]
    lines.append("| " + " | ".join(cell_str(c) for c in header) + " |")
    lines.append("|" + "|".join(" --- " for _ in header) + "|")
    for row in norm[1:]:
        lines.append("| " + " | ".join(cell_str(c) for c in row) + " |")

    if truncated:
        lines.append(f"\n> …（表格超过 {max_rows} 行，已截断）")

    return "\n".join(lines)
