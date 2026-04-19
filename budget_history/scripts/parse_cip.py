"""Parse the FY 2025-26 Capital Improvement Program doc to extract the
program-level 5-year capital plan summary.

The CIP categorizes projects by funding program (TransNet, SB1-RMRA, Water,
Sewer, Muni Buildings, etc.) and presents a 5-year plan. We pull the
program-level proposed amounts as a time series.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
TEXT_DIR = ROOT / "text"
INV = ROOT / "inventory.json"
MODEL = ROOT / "data_model.json"

# Programs we care about. The text uses (FUND_ID) after name; we normalize.
PROGRAMS = [
    ("TRANSNET PROGRAM", "TransNet", "212"),
    ("THOROUGHFARE PROGRAM", "Thoroughfare", "561"),
    ("T'HFARE/SIGNALS PROGRAM", "Thoroughfare/Signals", "562"),
    ("CITYWIDE DRAINAGE PROGRAM", "Citywide Drainage", "516"),
    ("SB1-RMRA PROGRAM", "SB1-RMRA Gas Tax", "265"),
    ("PARKS PROGRAM", "Parks", "598"),
    ("MUNI BLDGS PROGRAM", "Muni Buildings", "503+581"),
    ("WATER PROGRAM", "Water", "712+715"),
    ("SEWER PROGRAM", "Sewer", "722+726"),
    ("MISC CITY PROJECTS", "Misc City Projects", "501"),
    ("HARBOR PROGRAM", "Harbor", "740"),
    ("MEASURE X", "Measure X", "mx"),
    ("GAS TAX", "Gas Tax", "211"),
    ("PUBLIC FACILITY FEES", "Public Facility Fees", "503"),
    ("COMMUNITY DEVELOPMENT", "Community Development", "cdbg"),
]

MONEY_RE = re.compile(r"\$?\s*([\d,]+)\s*(?:\s|$)")


def parse_money(s: str) -> float | None:
    s = s.replace("$", "").replace(",", "").strip()
    if not s or s == "-":
        return 0.0
    try:
        return float(s)
    except ValueError:
        return None


def find_program_summary_page(pages):
    for i, p in enumerate(pages):
        if "TRANSNET PROGRAM" in p and "SEWER PROGRAM" in p and "PROPOSED FY 25-26" in p:
            return i
    # Looser fallback
    for i, p in enumerate(pages):
        if "TRANSNET" in p.upper() and "SEWER" in p.upper() and re.search(r"PROPOSED", p):
            return i
    return None


def parse_program_summary(page: str) -> list[dict]:
    """Parse the 5-year program table. Column order: FY25-26, 26-27, 27-28, 28-29, 29-30."""
    years = ["FY2025-2026", "FY2026-2027", "FY2027-2028", "FY2028-2029", "FY2029-2030"]
    rows = []
    lines = [ln.rstrip() for ln in page.splitlines()]
    for marker, canonical, fund_id in PROGRAMS:
        # Find line starting with marker
        found_idx = None
        for i, ln in enumerate(lines):
            if ln.strip().startswith(marker):
                found_idx = i
                break
        if found_idx is None:
            continue
        # Collect next 5 monetary values from subsequent lines
        vals = []
        j = found_idx + 1
        while j < len(lines) and len(vals) < 5:
            # Stop if we hit another program marker
            if any(lines[j].strip().startswith(p[0]) for p in PROGRAMS):
                break
            # Extract $X,XXX,XXX style numbers
            for m in re.findall(r"\$?\s*\(?-?[\d,]+(?:\.\d+)?\)?", lines[j]):
                v = parse_money(m.strip("()"))
                if v is not None and (abs(v) > 100 or v == 0):
                    vals.append(v)
                    if len(vals) >= 5:
                        break
            j += 1
        if len(vals) >= 5:
            for yr, amt in zip(years, vals[:5]):
                rows.append({
                    "fiscal_year": yr,
                    "program": canonical,
                    "fund_id": fund_id,
                    "amount_usd": amt,
                })
        elif 0 < len(vals) < 5:
            # Only partial data — emit what we have
            for yr, amt in zip(years[: len(vals)], vals):
                rows.append({
                    "fiscal_year": yr,
                    "program": canonical,
                    "fund_id": fund_id,
                    "amount_usd": amt,
                    "partial": True,
                })
    return rows


def main():
    inv = json.loads(INV.read_text())
    cip_docs = [r for r in inv if r["doc_type"] == "cip"]
    if not cip_docs:
        print("no CIP docs in inventory", file=sys.stderr)
        return

    all_rows = []
    for r in cip_docs:
        doc_id = r["doc_id"]
        fy = r["fiscal_year"]
        text_path = TEXT_DIR / f"{doc_id}.txt"
        if not text_path.exists():
            continue
        pages = text_path.read_text(encoding="utf-8", errors="replace").split("\x0c")
        pg = find_program_summary_page(pages)
        if pg is None:
            print(f"[{fy}] NO summary page", file=sys.stderr)
            continue
        rows = parse_program_summary(pages[pg])
        for row in rows:
            row["source_doc_id"] = doc_id
            row["source_doc_fy"] = fy
            row["source_page_idx"] = pg
        all_rows.extend(rows)
        print(f"[{fy}] page {pg} rows={len(rows)}", file=sys.stderr)

    model = json.loads(MODEL.read_text())
    model["cip_program"] = all_rows
    MODEL.write_text(json.dumps(model, indent=2))
    print(f"wrote {len(all_rows)} CIP program rows", file=sys.stderr)


if __name__ == "__main__":
    main()
