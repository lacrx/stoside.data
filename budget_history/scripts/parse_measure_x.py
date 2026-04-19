"""Parse Measure X Fund audit reports — extract Statement of Revenues,
Expenditures, and Changes in Fund Balance (the authoritative year-end figures).

Adds rows to data_model.json under 'measure_x' with one row per
(fiscal_year, line_item, fund_type, amount).

fund_type: Operating | Capital | Total
Note: The FY2019 report has a CMap-encoding problem that leaves the text
garbled; that year is skipped.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
TEXT_DIR = ROOT / "text"
INV = ROOT / "inventory.json"
MODEL = ROOT / "data_model.json"

# Line items of interest, in order of appearance in the statement
LINE_ITEMS = [
    ("Taxes", "revenue", "Taxes"),
    ("Total Revenues", "revenue", "Total Revenues"),
    ("General government", "expenditure", "General Government"),
    ("Public safety", "expenditure", "Public Safety"),
    ("Public works", "expenditure", "Public Works"),
    ("Community development", "expenditure", "Community Development"),
    ("Community services", "expenditure", "Community Services"),
    ("Capital outlay", "expenditure", "Capital Outlay"),
    ("Total Expenditures", "expenditure", "Total Expenditures"),
    ("Excess (Deficiency)", "net", "Excess of Revenues over Expenditures"),
    ("Transfers in (out)", "transfer", "Net Transfers"),
    ("Total Other Financing", "transfer", "Total Other Financing"),
    ("Net Change in Fund Balances", "net", "Net Change in Fund Balance"),
    ("Fund Balances - Beginning", "balance", "Fund Balance Beginning"),
    ("Fund Balances - Ending", "balance", "Fund Balance Ending"),
]

MONEY_RE = re.compile(
    r"\(?-?\$?\(?-?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?|-(?!\d)|\(?-?\$?\d+\.\d{1,2}\)?"
)


def parse_money(s: str) -> float | None:
    s = s.strip()
    if not s or s in {"-", "$-"}:
        return 0.0
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    s = s.replace("$", "").replace(",", "").strip()
    if not s or s == "-":
        return 0.0
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def find_statement_page(pages):
    """Find the page with 'Statement of Revenues, Expenditures, and Changes in Fund Balance'."""
    for i, p in enumerate(pages):
        up = p.upper()
        if "STATEMENT OF REVENUES" in up and ("FUND BALANCE" in up or "FUND BALANCES" in up):
            if "Taxes" in p and re.search(r"\d{1,3},\d{3}", p):
                return i
    return None


def parse_statement(page: str, fy: str, doc_id: str):
    """Parse a Measure X Statement of R/E/C page.

    Structure (since FY 2020):  Operating | Capital | Total, three columns of $ values.
    """
    rows = []
    # Normalize whitespace; keep line breaks as meaningful separators for column breaks
    lines = [ln.strip() for ln in page.splitlines()]
    # Drop empty lines but keep a marker
    lines = [ln for ln in lines if ln]

    # For each line item, find its line and collect the next 3 monetary values
    for marker, kind, canonical in LINE_ITEMS:
        marker_lower = marker.lower()
        found_idx = None
        for i, ln in enumerate(lines):
            if ln.lower().startswith(marker_lower):
                found_idx = i
                break
        if found_idx is None:
            continue

        # Collect values on the same line after marker + subsequent lines.
        after_marker = lines[found_idx][len(marker):]
        candidates = [after_marker] + lines[found_idx + 1:found_idx + 10]
        vals = []
        for txt in candidates:
            for m in MONEY_RE.findall(txt):
                v = parse_money(m)
                if v is not None:
                    vals.append(v)
                    if len(vals) >= 3:
                        break
            if len(vals) >= 3:
                break
        if len(vals) < 3:
            continue
        operating, capital, total = vals[:3]
        # Sanity: total should ≈ operating + capital (allow tiny rounding)
        if abs((operating + capital) - total) > max(1.0, 0.01 * abs(total)):
            # Some early reports only have a single column (combined)
            # Re-treat as a single "Total" value
            if abs(vals[0]) > 0:
                rows.append({
                    "fiscal_year": fy,
                    "line_item": canonical,
                    "kind": kind,
                    "fund_type": "Total",
                    "amount_usd": vals[0],
                    "source_doc_id": doc_id,
                })
            continue

        for ft, amt in (("Operating", operating), ("Capital", capital), ("Total", total)):
            rows.append({
                "fiscal_year": fy,
                "line_item": canonical,
                "kind": kind,
                "fund_type": ft,
                "amount_usd": amt,
                "source_doc_id": doc_id,
            })
    return rows


def main():
    inv = json.loads(INV.read_text())
    mx = sorted([r for r in inv if r["doc_type"] == "measure_x_report"],
                key=lambda r: r["fiscal_year"] or "")
    all_rows = []
    for r in mx:
        doc_id = r["doc_id"]
        fy = r["fiscal_year"]
        text_path = TEXT_DIR / f"{doc_id}.txt"
        if not text_path.exists():
            continue
        text = text_path.read_text(encoding="utf-8", errors="replace")
        pages = text.split("\x0c")
        idx = find_statement_page(pages)
        if idx is None:
            print(f"[{fy}] NO STATEMENT PAGE", file=sys.stderr)
            continue
        rows = parse_statement(pages[idx], fy, doc_id)
        all_rows.extend(rows)
        print(f"[{fy}] page {idx}  rows={len(rows)}", file=sys.stderr)

    model = json.loads(MODEL.read_text())
    model["measure_x"] = all_rows
    MODEL.write_text(json.dumps(model, indent=2))
    print(f"wrote {len(all_rows)} Measure X rows", file=sys.stderr)


if __name__ == "__main__":
    main()
