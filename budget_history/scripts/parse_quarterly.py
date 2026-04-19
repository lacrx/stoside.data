"""Parse Quarterly Financial Status Reports for top-line metrics.

Extracts: adopted GF rev/exp, all-funds rev/exp, YTD actual rev/exp, and
reported surplus/(deficit) from the narrative header. These are the
executive-summary figures staff highlighted for Council.

Output goes into data_model.json under 'quarterly'.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
TEXT_DIR = ROOT / "text"
INV = ROOT / "inventory.json"
MODEL = ROOT / "data_model.json"


def mm(s: str) -> float | None:
    """Parse a '$X.XX million' style number. Returns USD (not millions)."""
    try:
        return float(s.replace(",", "")) * 1_000_000
    except ValueError:
        return None


# Regexes targeting the narrative language used in most reports.
PATTERNS = {
    "adopted_gf_revenue": [
        # Must mention "General Fund" explicitly — otherwise we pick up all-funds totals.
        r"General\s+Fund\s+revenues\s+of\s*\$?\s*([\d,]+(?:\.\d+)?)\s*million",
        r"General\s+Fund[^$]*\$?\s*([\d,]+(?:\.\d+)?)\s*million\s+in\s+revenues",
    ],
    "adopted_gf_expenditure": [
        # Require "expenditures" close to "General Fund"
        r"General\s+Fund[^.]*expenditures?\s+(?:totaling|of)\s*\$?\s*([\d,]+(?:\.\d+)?)\s*million",
        r"expenditures\s+of\s*\$?\s*([\d,]+(?:\.\d+)?)\s*million\.\s*The\s+City",
    ],
    "adopted_all_funds_revenue": [
        r"all\s+funds\s+is\s*\$?\s*([\d,]+(?:\.\d+)?)\s*million\s+in\s+revenues",
        r"all\s+funds.*?budget\s+of\s*\$?\s*([\d,]+(?:\.\d+)?)\s*million\s+in\s+revenues",
    ],
    "adopted_all_funds_expenditure": [
        r"all\s+funds.*?\$?\s*([\d,]+(?:\.\d+)?)\s*million\s+in\s+expenditures",
    ],
    "actual_gf_revenue": [
        r"Preliminary\s+total\s+revenues\s+are\s+at\s*\$?\s*([\d,]+\.?\d*)\s*million",
        r"total\s+General\s+Fund\s+revenues?\s+(?:came|came\s+in)?\s*at\s*\$?\s*([\d,]+\.?\d*)\s*million",
        r"(?:Actual|Total)\s+revenues\s+(?:for\s+the\s+year\s+)?totaled\s*\$?\s*([\d,]+\.?\d*)\s*million",
    ],
    "actual_gf_expenditure": [
        r"Total\s+General\s+Fund\s+expenditures\s+for\s+the\s+fourth\s+quarter\s+amount\s+to\s*\$?\s*([\d,]+\.?\d*)\s*million",
        r"General\s+Fund\s+expenditures\s+(?:for\s+the\s+year\s+)?(?:totaled|amount\s+to)\s*\$?\s*([\d,]+\.?\d*)\s*million",
    ],
    "gf_surplus": [
        r"General\s+Fund\s+will\s+have\s+a\s*\$?\s*([\d,]+\.?\d*)\s*million\s+surplus",
        r"General\s+Fund\s+surplus\s+of\s*\$?\s*([\d,]+\.?\d*)\s*million",
    ],
}


def extract_first(text: str, pats: list[str]) -> float | None:
    for pat in pats:
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            v = mm(m.group(1))
            if v is not None:
                return v
    return None


def main():
    inv = json.loads(INV.read_text())
    qrs = sorted(
        [r for r in inv if r["doc_type"].startswith("quarterly_")],
        key=lambda r: (r["fiscal_year"] or "", r["doc_type"]),
    )
    rows = []
    for r in qrs:
        doc_id = r["doc_id"]
        fy = r["fiscal_year"]
        quarter = r["doc_type"].replace("quarterly_q", "Q")
        text_path = TEXT_DIR / f"{doc_id}.txt"
        if not text_path.exists():
            continue
        text = text_path.read_text(encoding="utf-8", errors="replace")
        # Look at the first ~6000 chars (synopsis + background)
        narrative = text[:6000]
        row = {
            "fiscal_year": fy,
            "quarter": quarter,
            "source_doc_id": doc_id,
        }
        for metric, pats in PATTERNS.items():
            v = extract_first(narrative, pats)
            if v is not None:
                row[metric] = v
        # Only emit if we got at least one metric beyond identifiers
        data_fields = [k for k in row if k not in ("fiscal_year", "quarter", "source_doc_id")]
        if data_fields:
            rows.append(row)
        print(
            f"[{fy} {quarter}] adopted_rev=${row.get('adopted_gf_revenue', 0)/1e6:.1f}M "
            f"actual_rev=${row.get('actual_gf_revenue', 0)/1e6:.1f}M "
            f"surplus=${row.get('gf_surplus', 0)/1e6:.1f}M "
            f"fields={len(data_fields)}",
            file=sys.stderr,
        )
    model = json.loads(MODEL.read_text())
    model["quarterly"] = rows
    MODEL.write_text(json.dumps(model, indent=2))
    print(f"wrote {len(rows)} quarterly rows", file=sys.stderr)


if __name__ == "__main__":
    main()
