"""Parse General Fund revenue/expenditure tables from adopted budgets + BiBs.

Output: data_model.json with rows of (fiscal_year, basis, category, amount_usd,
source_doc_id, source_page_idx, flow).
Also extracts FTE-by-department from BiBs.
flow in {revenue, expenditure, transfer}.
basis in {actual, adopted, proposed, amended, projected}.

The underlying text varies: early budgets use millions ($158.24), later budgets
use absolute dollars ($158,243,917). We normalize everything to USD.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
TEXT_DIR = ROOT / "text"
INV = ROOT / "inventory.json"
OUT = ROOT / "data_model.json"


GF_REV_CATEGORIES = [
    "Property Taxes",
    "Sales & Use Taxes",
    "Transient Occupancy Tax",
    "All Other Taxes",
    "Ambulance Billing",
    "Charges for Service",
    "Fines and Forfeitures",
    "Fines & Forfeitures",
    "Intergovernmental",
    "Licenses and Permits",
    "Other Revenue and Transfers",
    "Other Revenue & Transfers",
    "Franchise Fees",
    "Use of Money & Property",
    "Use of Money and Property",
    "Subtotal",
    "Investment Clearing",
    "Measure X - Local Sales & Use Tax",
    "Measure X",
    "Grand Total",
    "Total",
]

GF_EXP_CATEGORIES = [
    "City Council",
    "City Clerk",
    "City Treasurer",
    "City Manager",
    "City Attorney",
    "Non Departmental",
    "Non-Departmental",
    "Financial Services",
    "Human Resources",
    "Information Technologies",
    "Police",
    "Police Department",
    "Fire",
    "Fire Department",
    "Public Works",
    "Development Services",
    "Neighborhood Services",
    "Parks and Recreation",
    "Library",
    "General Services",
    "Harbor",
    "Water Utilities",
    "Measure X",
    "Subtotal",
    "Investment Clearing",
    "One-Time/Reserves",
    "Grand Total",
    "Total",
]


CANON_REV = {
    "property taxes": "Property Taxes",
    "sales & use taxes": "Sales & Use Taxes",
    "transient occupancy tax": "Transient Occupancy Tax",
    "all other taxes": "All Other Taxes",
    "ambulance billing": "Ambulance Billing",
    "charges for service": "Charges for Service",
    "fines and forfeitures": "Fines & Forfeitures",
    "fines & forfeitures": "Fines & Forfeitures",
    "intergovernmental": "Intergovernmental",
    "licenses and permits": "Licenses and Permits",
    "other revenue and transfers": "Other Revenue & Transfers",
    "other revenue & transfers": "Other Revenue & Transfers",
    "franchise fees": "Franchise Fees",
    "use of money & property": "Use of Money & Property",
    "use of money and property": "Use of Money & Property",
    "subtotal": "Subtotal",
    "investment clearing": "Investment Clearing",
    "measure x - local sales & use tax": "Measure X",
    "measure x": "Measure X",
    "grand total": "Grand Total",
    "total": "Grand Total",
}

CANON_EXP = {
    "city council": "City Council",
    "city clerk": "City Clerk",
    "city treasurer": "City Treasurer",
    "city manager": "City Manager",
    "city attorney": "City Attorney",
    "non departmental": "Non-Departmental",
    "non-departmental": "Non-Departmental",
    "financial services": "Financial Services",
    "human resources": "Human Resources",
    "information technologies": "Information Technologies",
    "police": "Police",
    "police department": "Police",
    "fire": "Fire",
    "fire department": "Fire",
    "public works": "Public Works",
    "development services": "Development Services",
    "neighborhood services": "Neighborhood Services",
    "parks and recreation": "Parks and Recreation",
    "library": "Library",
    "general services": "General Services",
    "harbor": "Harbor",
    "water utilities": "Water Utilities",
    "measure x": "Measure X",
    "subtotal": "Subtotal",
    "investment clearing": "Investment Clearing",
    "one-time/reserves": "One-Time/Reserves",
    "grand total": "Grand Total",
    "total": "Grand Total",
}


def parse_money(s: str) -> float | None:
    """Parse a dollar amount. Handles '$', commas, parens, trailing minus, '-'."""
    s = s.strip()
    if not s or s in {"-", "$-"}:
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    s = s.replace("$", "").replace(",", "").strip()
    if s.endswith("-"):
        neg = True
        s = s[:-1].strip()
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


MONEY_RE = re.compile(r"\(?-?\$?\(?-?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?|\(?-?\$?\d+\.\d{1,2}\)?|\(?-?\$?\d{4,}\)?")


_BIGNUM_RE = re.compile(r"\d{1,3}(?:,\d{3}){1,}")


def find_gf_rev_page(pages):
    """Pick the page that looks most like a clean GF revenue summary schedule.

    Must: have Property Taxes + Sales & Use + Transient Occupancy markers
    clustered in the same table, contain Grand Total/Subtotal, contain a
    bignum DOLLAR amount within 120 chars of "Property Taxes", NOT be a
    narrative/transmittal page (which has prose around the category names),
    NOT be the detailed account-level page (4101-style account codes), and
    NOT be the BiB overlay overview (CITYWIDE STAFFING).
    """
    for i, p in enumerate(pages):
        if "......" in p[:800]:
            continue
        if "CITYWIDE STAFFING" in p:
            continue
        if "Property Taxes" not in p:
            continue
        if not re.search(r"Sales\s*&\s*Use\s*Taxes", p):
            continue
        if not re.search(r"Transient\s*Occupancy", p):
            continue
        if not re.search(r"(Grand Total|Subtotal)", p):
            continue
        if not _BIGNUM_RE.search(p):
            continue
        # Reject the detailed page (4101-style account codes)
        if re.search(r"\b41\d{2}\s+\w", p):
            continue
        # Cluster check
        p_idx = p.find("Property Taxes")
        s_idx = p.find("Sales & Use Taxes")
        if p_idx < 0 or s_idx < 0 or abs(s_idx - p_idx) > 600:
            continue
        # Require a bignum $ amount within 120 chars after "Property Taxes"
        # (rules out narrative pages where PT is followed by prose)
        window = p[p_idx:p_idx + 200]
        if not _BIGNUM_RE.search(window):
            continue
        return i
    return None


def find_gf_exp_page(pages):
    """First page with GF expenditure summary signature."""
    depts = ["Police", "Fire", "Public Works", "Library", "Development Services",
             "Financial Services", "Neighborhood Services"]
    for i, p in enumerate(pages):
        if "......" in p[:800]:
            continue
        if "CITYWIDE STAFFING" in p:
            continue
        if sum(1 for d in depts if d in p) < 5:
            continue
        if "City Council" not in p:
            continue
        if not re.search(r"(Grand Total|Subtotal)", p):
            continue
        score = len(_BIGNUM_RE.findall(p))
        if score < 5:
            continue
        # Dept names should be in same table area
        cc = p.find("City Council")
        pol = p.find("Police")
        if cc < 0 or pol < 0 or abs(pol - cc) > 2500:
            continue
        # Reject the per-department detail page by checking for sub-account lines
        if re.search(r"\b5\d{3}\s+\w", p):
            continue
        return i
    return None


def parse_columns(header_line: str, primary_fy: str):
    """Return list of (fy_str, basis) from headers like:
       'Actuals FY 2020-21 Actuals FY 2021-22 Adopted'
       'Actual FY 2018-19 Actual FY 2019-20 Adopted Budget FY 2020-21 Adopted Budget FY 2021-22'
    """
    cols = []
    # Accept "Actual" or "Actuals", and allow "Adopted Budget" / "Amended Budget" etc.
    # FY token optional — the last Adopted often has no FY next to it (the budget's own FY).
    parts = re.findall(
        r"(Actuals?|Amended(?:\s*Budget)?|Adopted(?:\s*Budget)?|Proposed(?:\s*Budget)?|Projected)"
        r"\s*(?:FY\s*(\d{4}[-/]\d{2,4}))?",
        header_line, re.IGNORECASE,
    )
    for basis_word, fy in parts:
        w = basis_word.lower()
        if w.startswith("actual"):
            basis = "actual"
        elif w.startswith("amended"):
            basis = "amended"
        elif w.startswith("adopted"):
            basis = "adopted"
        elif w.startswith("proposed"):
            basis = "proposed"
        elif w.startswith("projected"):
            basis = "projected"
        else:
            continue
        if not fy:
            fy = primary_fy
        else:
            m = re.match(r"(\d{4})[-/](\d{2,4})", fy)
            if m:
                a, b = m.group(1), m.group(2)
                if len(b) == 2:
                    b = a[:2] + b
                fy = f"FY{a}-{b}"
        cols.append((fy, basis))
    return cols


def lines_of(page: str):
    return [ln.rstrip() for ln in page.splitlines() if ln.strip()]


def parse_table(page: str, canon_map: dict, primary_fy: str, flow: str):
    """Extract rows from a page. Return list of (fiscal_year, basis, category, amount, raw)."""
    lines = lines_of(page)
    header_idx = None
    header_line = ""

    # Strategy A: vertical layout — find the FIRST cluster of consecutive lines each
    # containing just one header token. This is common in pymupdf output.
    tok_re = re.compile(
        r"^(Actuals?|Adopted(?:\s*Budget)?|Proposed(?:\s*Budget)?|"
        r"Amended(?:\s*Budget)?|Projected|Budget|FY\s*\d{4}[-/]\d{2,4})$",
        re.IGNORECASE,
    )
    i = 0
    best_cluster = None
    while i < len(lines):
        j = i
        cluster = []
        while j < len(lines) and tok_re.fullmatch(lines[j].strip()):
            cluster.append((j, lines[j].strip()))
            j += 1
        if len(cluster) >= 3 and (best_cluster is None or len(cluster) > len(best_cluster)):
            best_cluster = cluster
        i = max(j, i + 1)
    if best_cluster:
        header_idx = best_cluster[-1][0]
        header_line = " ".join(ln for _, ln in best_cluster)
    else:
        # Strategy B: horizontal — a line with TWO header words, or one header + FY
        for i, ln in enumerate(lines):
            if re.search(r"(Actuals|Adopted|Proposed|Amended|Projected).*?(Actuals|Adopted|Proposed|Amended|Projected)", ln, re.IGNORECASE):
                header_idx = i
                header_line = ln
                break
        if header_idx is None:
            return []

    cols = parse_columns(header_line, primary_fy)
    if not cols:
        return []

    rows = []
    # Walk the rest of the lines looking for a category, then collect ncols numbers.
    # Budget text may have category and numbers interleaved across several lines.
    i = header_idx + 1
    while i < len(lines):
        ln = lines[i].strip()
        if not ln:
            i += 1
            continue
        # Find a category in this line
        cat_match = None
        for raw_cat in sorted(canon_map.keys(), key=lambda x: -len(x)):
            # Check as full line or as prefix
            if ln.lower() == raw_cat or ln.lower().startswith(raw_cat + " ") or ln.lower().startswith("  " + raw_cat):
                cat_match = raw_cat
                break
            if raw_cat in ln.lower():
                cat_match = raw_cat
                break
        if not cat_match:
            i += 1
            continue

        # Collect numeric values: same line after category + subsequent lines until we have ncols values
        remainder = ln[ln.lower().find(cat_match) + len(cat_match):]
        vals_str = [remainder]
        j = i + 1
        while j < len(lines):
            ln2 = lines[j].strip()
            # Stop if another category is recognized on this line
            if any(ln2.lower() == c or ln2.lower().startswith(c + " ") for c in canon_map.keys()):
                break
            vals_str.append(ln2)
            # Extract tentative values so far
            so_far = " ".join(vals_str)
            found = MONEY_RE.findall(so_far)
            if len(found) >= len(cols):
                break
            j += 1
        values = MONEY_RE.findall(" ".join(vals_str))
        # Clean values
        clean = []
        for v in values:
            n = parse_money(v)
            if n is not None:
                clean.append(n)
        canon = canon_map[cat_match]
        if len(clean) >= len(cols):
            values_for_cols = clean[: len(cols)]
            for (fy, basis), amt in zip(cols, values_for_cols):
                rows.append({
                    "fiscal_year": fy,
                    "basis": basis,
                    "flow": flow,
                    "category": canon,
                    "amount_raw": amt,
                })
        elif 0 < len(clean) < len(cols):
            # Align-right: later columns filled, earlier columns missing
            # (e.g. Measure X revenue didn't exist before FY 2019-20).
            offset = len(cols) - len(clean)
            for (fy, basis), amt in zip(cols[offset:], clean):
                rows.append({
                    "fiscal_year": fy,
                    "basis": basis,
                    "flow": flow,
                    "category": canon,
                    "amount_raw": amt,
                })
        # Stop after the Grand Total row — the pie-chart legend below would
        # re-match category names with small percentage numbers.
        if canon == "Grand Total" and len(clean) > 0:
            break
        i = max(j, i + 1)
    # Dedupe: keep FIRST row per (fy, basis, category, flow) — the main table
    seen = set()
    deduped = []
    for r in rows:
        key = (r["fiscal_year"], r["basis"], r["category"], r["flow"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    return deduped


def normalize_amounts(rows, scale_hint: str):
    """If scale_hint == 'millions', multiply by 1e6."""
    mult = 1_000_000 if scale_hint == "millions" else 1
    for r in rows:
        r["amount_usd"] = round(r["amount_raw"] * mult, 2)
        del r["amount_raw"]
    return rows


def detect_scale(page: str) -> str:
    if re.search(r"in\s*millions", page, re.IGNORECASE):
        return "millions"
    # If the largest plausible amount we see is < 1000, it's millions
    nums = [parse_money(x) for x in MONEY_RE.findall(page)]
    nums = [n for n in nums if n is not None and n > 0]
    if nums and max(nums) < 1000:
        return "millions"
    return "dollars"


def parse_bib_fte(text: str, fy: str, doc_id: str):
    """Parse FTE-by-department from BiB text."""
    # Pattern: "Department\n   FTE        % of total\n<dept>\n <fte> <pct>" etc.
    # Lines look like: "City Attorney\n            8.95             0.90%" OR "City Attorney\n8.88\n...\n0.84%"
    depts = [
        "City Attorney", "City Clerk", "City Council", "City Manager", "City Treasurer",
        "Development Services", "Fire Department", "Financial Services", "General Services",
        "Harbor", "Human Resources", "Information Technologies", "Library", "Measure X",
        "Neighborhood Services", "Parks and Recreation", "Police Department",
        "Public Works", "Water Utilities",
    ]
    rows = []
    lower = text.lower()
    for dept in depts:
        dl = dept.lower()
        idx = 0
        while True:
            pos = lower.find(dl, idx)
            if pos < 0:
                break
            tail = text[pos + len(dept):pos + len(dept) + 100]
            m = re.match(r"\s*([\d,]+\.\d{2})\s*[\d,.%\s]*", tail)
            if m:
                fte = parse_money(m.group(1))
                if fte and fte < 1000:  # sanity
                    rows.append({
                        "fiscal_year": fy,
                        "department": dept.replace(" Department", ""),
                        "fte": fte,
                    })
                    break
            idx = pos + len(dept)
    # Dedupe by dept (keep first)
    seen = set()
    out = []
    for r in rows:
        if r["department"] not in seen:
            out.append(r)
            seen.add(r["department"])
    return out


def main():
    recs = json.loads(INV.read_text())
    gf_rows = []
    fte_rows = []

    # Adopted budgets
    for r in recs:
        if r["doc_type"] != "adopted_budget":
            continue
        doc_id = r["doc_id"]
        fy = r["fiscal_year"]
        path = TEXT_DIR / f"{doc_id}.txt"
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        pages = text.split("\x0c")

        rev_page = find_gf_rev_page(pages)
        if rev_page is not None:
            scale = detect_scale(pages[rev_page])
            rows = parse_table(pages[rev_page], CANON_REV, fy, flow="revenue")
            rows = normalize_amounts(rows, scale)
            for row in rows:
                row["source_doc_id"] = doc_id
                row["source_page_idx"] = rev_page
                row["source_doc_fy"] = fy
                row["scale"] = scale
            gf_rows.extend(rows)
            print(f"[{fy}] rev page {rev_page} scale={scale} rows={len(rows)}", file=sys.stderr)
        else:
            print(f"[{fy}] NO REV PAGE", file=sys.stderr)

        exp_page = find_gf_exp_page(pages)
        if exp_page is not None:
            scale = detect_scale(pages[exp_page])
            rows = parse_table(pages[exp_page], CANON_EXP, fy, flow="expenditure")
            rows = normalize_amounts(rows, scale)
            for row in rows:
                row["source_doc_id"] = doc_id
                row["source_page_idx"] = exp_page
                row["source_doc_fy"] = fy
                row["scale"] = scale
            gf_rows.extend(rows)
            print(f"[{fy}] exp page {exp_page} scale={scale} rows={len(rows)}", file=sys.stderr)
        else:
            print(f"[{fy}] NO EXP PAGE", file=sys.stderr)

    # Budget-in-Briefs — FTE only (others vary too much)
    for r in recs:
        if r["doc_type"] != "budget_in_brief":
            continue
        doc_id = r["doc_id"]
        fy = r["fiscal_year"]
        path = TEXT_DIR / f"{doc_id}.txt"
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        rows = parse_bib_fte(text, fy, doc_id)
        for row in rows:
            row["source_doc_id"] = doc_id
        fte_rows.extend(rows)
        print(f"[FTE {fy}] rows={len(rows)}", file=sys.stderr)

    out = {
        "general_fund": gf_rows,
        "fte_by_department": fte_rows,
    }
    OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {len(gf_rows)} GF rows, {len(fte_rows)} FTE rows -> {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
