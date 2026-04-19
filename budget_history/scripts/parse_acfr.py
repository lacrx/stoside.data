"""Parse ACFRs to extract General Fund balance detail and government-wide
Net Position.

Produces two lists in data_model.json:
  - acfr_gf_balance       : General Fund balance components per FY
  - acfr_net_position     : Government-wide Net Position per FY
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
TEXT_DIR = ROOT / "text"
INV = ROOT / "inventory.json"
MODEL = ROOT / "data_model.json"

MONEY_RE = re.compile(
    r"\(?-?\$?\(?-?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?|\(?-?\$?\d+\.\d{1,2}\)?"
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
    if not s:
        return 0.0
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def find_gf_balance_page(pages):
    """Balance Sheet - Governmental Funds, page 1 (General Fund is first column)."""
    for i, p in enumerate(pages):
        up = p.upper()
        if "BALANCE SHEET" in up and "GOVERNMENTAL FUNDS" in up and "GENERAL" in up:
            if "FUND BALANCE" in up and "CASH AND INVESTMENTS" in up:
                if re.search(r"\d{1,3},\d{3}", p):
                    return i
    return None


def find_net_position_candidates(pages):
    """Return list of (start_page, window_text) candidates for the
    government-wide Statement of Net Position/Assets. The caller picks
    the one whose parse yields the most rows — robust across compact
    ACFRs (title + 5 blocks) and FY 2010-2019 / FY 2023 layouts where
    pymupdf splits the schedule across 25+ short blocks.
    """
    TITLES = ("STATEMENT OF NET POSITION", "STATEMENT OF NET ASSETS")
    EXCLUDE = ("PROPRIETARY", "FIDUCIARY", "INTERNAL SERVICE", "AGENCY FUND")
    SCHEDULE_ITEMS = (
        "CASH AND INVESTMENTS",
        "ACCOUNTS RECEIVABLE",
        "CAPITAL ASSETS",
        "NOTES RECEIVABLE",
        "TOTAL LIABILITIES",
        "TOTAL NET POSITION",
        "TOTAL NET ASSETS",
    )
    WINDOW_SIZE = 40
    out = []
    for i, p in enumerate(pages):
        up = p.upper()
        if not any(t in up for t in TITLES):
            continue
        if any(x in up for x in EXCLUDE):
            continue
        if p.count("..") > 20:
            continue
        window = "\n".join(pages[i:min(i + WINDOW_SIZE, len(pages))])
        upw = window.upper()
        if "GOVERNMENTAL" not in upw or "BUSINESS-TYPE" not in upw:
            continue
        if "TOTAL ASSETS" not in upw:
            continue
        if not re.search(r"\d{3},\d{3},\d{3}", window):
            continue
        if sum(1 for it in SCHEDULE_ITEMS if it in upw) < 3:
            continue
        out.append((i, window))
    return out


def find_net_position_page(pages):
    """Government-wide Statement of Net Position / Net Assets.

    Returns (start_page, window_text). The window spans up to 8 pymupdf
    blocks forward from the title page, joined with newlines, so parsing
    works for both single-block layouts (FY 2020+ ACFRs) and the split
    multi-block layouts used in FY 2010-2019 AFRs where pymupdf puts the
    title on one block and the Total-Assets / Total-Liabilities rows
    several blocks later.

    Title terminology varies: pre-GASB 63 (FY ≤ 2012 for Oceanside) used
    "Statement of Net Assets"; later reports use "Statement of Net
    Position". We reject Proprietary / Fiduciary / Internal Service
    qualifiers — those are fund-level schedules, not government-wide.
    """
    TITLES = ("STATEMENT OF NET POSITION", "STATEMENT OF NET ASSETS")
    EXCLUDE = ("PROPRIETARY", "FIDUCIARY", "INTERNAL SERVICE", "AGENCY FUND")
    # Schedule-specific line items — their presence across the window
    # distinguishes the actual Statement of Net Position schedule from
    # MD&A narrative prose that merely *mentions* the Statement. MD&A
    # rarely contains the full list of individual asset rows.
    SCHEDULE_ITEMS = (
        "CASH AND INVESTMENTS",
        "ACCOUNTS RECEIVABLE",
        "CAPITAL ASSETS",
        "NOTES RECEIVABLE",
        "TOTAL LIABILITIES",
        "TOTAL NET POSITION",
        "TOTAL NET ASSETS",
    )
    WINDOW_SIZES = (40,)
    for i, p in enumerate(pages):
        up = p.upper()
        if not any(t in up for t in TITLES):
            continue
        if any(x in up for x in EXCLUDE):
            continue
        if p.count("..") > 20:  # TOC page, skip
            continue
        # Collect all candidate windows for this title page (start=i);
        # we'll pick the one that yields the most schedule rows after
        # parse_net_position does its thing. This two-step approach beats
        # a fixed-size window — FY 2010-2019 need 40+ pages (pymupdf
        # split the schedule across many blocks), FY 2020+ work at 8.
        candidates = []
        for wsize in WINDOW_SIZES:
            window = "\n".join(pages[i:min(i + wsize, len(pages))])
            upw = window.upper()
            if "GOVERNMENTAL" not in upw or "BUSINESS-TYPE" not in upw:
                continue
            if "TOTAL ASSETS" not in upw:
                continue
            if not re.search(r"\d{3},\d{3},\d{3}", window):
                continue
            if sum(1 for it in SCHEDULE_ITEMS if it in upw) < 3:
                continue
            candidates.append((i, window))
        if candidates:
            return candidates[-1]  # prefer the largest window (picks up
                                   # full schedule even when MD&A is in it)
    return None, None


GF_LINE_ITEMS = [
    # (case-insensitive marker, canonical name)
    ("total assets", "total_assets"),
    ("total liabilities", "total_liabilities"),
    ("total deferred inflows of resources", "total_deferred_inflows"),
    ("nonspendable", "fb_nonspendable"),
    ("restricted", "fb_restricted"),
    ("committed", "fb_committed"),
    ("assigned", "fb_assigned"),
    ("unassigned", "fb_unassigned"),
    ("total fund balances", "fb_total"),
]


def first_money_after(page: str, marker: str) -> float | None:
    """Find the first $ value appearing after the given marker (case-insensitive)."""
    low = page.lower()
    idx = low.find(marker.lower())
    if idx < 0:
        return None
    tail = page[idx + len(marker):idx + len(marker) + 400]
    m = MONEY_RE.search(tail)
    if not m:
        return None
    return parse_money(m.group(0))


def parse_gf_balance(page: str, fy: str, doc_id: str):
    rows = []
    for marker, canon in GF_LINE_ITEMS:
        v = first_money_after(page, marker)
        if v is None:
            continue
        rows.append({
            "fiscal_year": fy,
            "line_item": canon,
            "amount_usd": v,
            "source_doc_id": doc_id,
        })
    return rows


NP_LINE_ITEMS = [
    # Pre-GASB 63 (FY ≤ 2012) AFRs use "TOTAL ASSETS" / "TOTAL LIABILITIES"
    # in all-caps headers and "Total net assets" instead of "net position".
    # We search case-insensitively via .lower() so both casings match,
    # and accept either "net position" or "net assets" as canonical np_total.
    ("Total assets", "total_assets"),
    ("Total deferred outflows of resources", "total_deferred_outflows"),
    ("Total liabilities", "total_liabilities"),
    ("Total deferred inflows of resources", "total_deferred_inflows"),
    ("Net investment in capital assets", "np_net_invest_capital"),
    ("Invested in capital assets, net of related debt", "np_net_invest_capital"),
    ("Total net position", "np_total"),
    ("Total net assets", "np_total"),
]


def parse_net_position(page: str, fy: str, doc_id: str):
    """Net Position page has 3 columns: Governmental | Business-Type | Total.
    We collect all three as separate activity values. Values smaller than
    $10,000 are rejected as noise — real city net-position line items are
    in the millions/billions. MD&A summary tables use "$565.7" shorthand
    (meaning $565.7M) which would otherwise be parsed as $565.70 dollars.

    The page may contain multiple occurrences of a marker (e.g., "Total
    assets" appears both in MD&A narrative and in the actual schedule).
    We try each occurrence and keep the one that yields ≥2 valid values.
    """
    rows = []
    low = page.lower()
    for marker, canon in NP_LINE_ITEMS:
        mlow = marker.lower()
        search_start = 0
        best_vals: list[float] = []

        def _is_valid_match(idx: int) -> bool:
            """Reject matches where the marker is actually a prefix of a
            longer label like 'Total Liabilities, Deferred Inflows of
            Resources, and Net Position'. After a real match, the
            character is whitespace/newline, not ','/'and'."""
            after = page[idx + len(marker):idx + len(marker) + 40].lstrip(" \t")
            if after.startswith(",") or after.startswith(" and ") \
                    or after.lower().startswith("and "):
                return False
            return True
        # Score candidates by max magnitude, preferring value sets dominated
        # by full-resolution schedule values (hundreds of millions) over
        # MD&A shorthand (hundreds of thousands, misread as literal dollars).
        best_max_mag = 0.0
        while True:
            idx = low.find(mlow, search_start)
            if idx < 0:
                break
            search_start = idx + len(marker)
            if not _is_valid_match(idx):
                continue
            tail = page[idx + len(marker):idx + len(marker) + 600]
            vals = []
            for m in MONEY_RE.findall(tail):
                v = parse_money(m)
                if v is None:
                    continue
                if abs(v) != 0 and abs(v) < 10_000:
                    continue
                vals.append(v)
                if len(vals) >= 3:
                    break
            max_mag = max((abs(v) for v in vals), default=0.0)
            # Prefer higher-magnitude complete sets; among incomplete ones,
            # prefer more values. This picks schedule over MD&A robustly.
            is_better = False
            if len(vals) >= 3 and len(best_vals) < 3:
                is_better = True
            elif len(vals) >= 3 and max_mag > best_max_mag:
                is_better = True
            elif len(best_vals) < 3 and len(vals) > len(best_vals):
                is_better = True
            if is_better:
                best_vals = vals
                best_max_mag = max_mag
        vals = best_vals
        if len(vals) < 3:
            # Sometimes only "Total" column is meaningful (end-of-page)
            if vals:
                rows.append({
                    "fiscal_year": fy,
                    "activity": "Total",
                    "line_item": canon,
                    "amount_usd": vals[-1],
                    "source_doc_id": doc_id,
                })
            continue
        g, b, t = vals[:3]
        for act, val in (("Governmental", g), ("Business-Type", b), ("Total", t)):
            rows.append({
                "fiscal_year": fy,
                "activity": act,
                "line_item": canon,
                "amount_usd": val,
                "source_doc_id": doc_id,
            })
    return rows


def find_reconciliation_page(pages):
    """Reconciliation of Balance Sheet of Governmental Funds to Statement of
    Net Position — contains the Total Fund Balances line. Fallback data
    source when the main balance sheet didn't extract cleanly."""
    for i, p in enumerate(pages):
        up = p.upper()
        if "RECONCILIATION" in up and "BALANCE SHEET" in up and "GOVERNMENTAL FUNDS" in up:
            if "Total Fund Balances" in p and re.search(r"\d{1,3},\d{3}", p):
                return i
    return None


def parse_reconciliation(page: str, fy: str, doc_id: str):
    """Extract just Total Fund Balances - Governmental Funds."""
    idx = page.find("Total Fund Balances")
    if idx < 0:
        return []
    tail = page[idx:idx + 500]
    m = MONEY_RE.search(tail[len("Total Fund Balances"):])
    if not m:
        return []
    v = parse_money(m.group(0))
    if v is None or v <= 0:
        return []
    return [{
        "fiscal_year": fy,
        "line_item": "gov_funds_total_fb",
        "amount_usd": v,
        "source_doc_id": doc_id,
    }]


def main():
    inv = json.loads(INV.read_text())
    acfrs = sorted([r for r in inv if r["doc_type"] == "acfr"],
                   key=lambda r: r["fiscal_year"] or "")
    gf_rows, np_rows = [], []
    for r in acfrs:
        doc_id = r["doc_id"]
        fy = r["fiscal_year"]
        text_path = TEXT_DIR / f"{doc_id}.txt"
        if not text_path.exists():
            continue
        pages = text_path.read_text(encoding="utf-8", errors="replace").split("\x0c")

        gf_idx = find_gf_balance_page(pages)
        if gf_idx is not None:
            rs = parse_gf_balance(pages[gf_idx], fy, doc_id)
            gf_rows.extend(rs)
            print(f"[{fy}] GF balance page {gf_idx} rows={len(rs)}", file=sys.stderr)
        else:
            # Fallback: reconciliation page with Total Fund Balances only
            rec_idx = find_reconciliation_page(pages)
            if rec_idx is not None:
                rs = parse_reconciliation(pages[rec_idx], fy, doc_id)
                gf_rows.extend(rs)
                print(f"[{fy}] GF balance via reconciliation page {rec_idx} rows={len(rs)}", file=sys.stderr)
            else:
                print(f"[{fy}] NO GF PAGE (no reconciliation fallback)", file=sys.stderr)

        candidates = find_net_position_candidates(pages)
        if candidates:
            # Try each, pick the one that yields the most rows (max 18 =
            # 6 line items × 3 activities)
            best_rs: list[dict] = []
            best_idx = None
            for idx, win in candidates:
                rs = parse_net_position(win, fy, doc_id)
                if len(rs) > len(best_rs):
                    best_rs = rs
                    best_idx = idx
                if len(best_rs) >= 18:
                    break
            np_rows.extend(best_rs)
            print(f"[{fy}] net pos page {best_idx} rows={len(best_rs)} "
                  f"({len(candidates)} candidates)", file=sys.stderr)
        else:
            print(f"[{fy}] NO NET POSITION PAGE", file=sys.stderr)

    model = json.loads(MODEL.read_text())
    model["acfr_gf_balance"] = gf_rows
    model["acfr_net_position"] = np_rows
    MODEL.write_text(json.dumps(model, indent=2))
    print(f"wrote {len(gf_rows)} GF balance rows, {len(np_rows)} net position rows",
          file=sys.stderr)


if __name__ == "__main__":
    main()
