"""Extract Strong Towns Finance Decoder inputs from ACFRs.

For each ACFR year, extracts:
  - From Statement of Net Position: capital assets (not-depreciated, net-of-
    depreciation), for govt+bus+total columns.
  - From Statement of Activities: expenses, charges, operating grants,
    capital grants per function/activity; interest on long-term debt.
  - From Notes — Capital Assets: gross capital assets not-depreciated and
    being-depreciated, separate govt/bus columns.

Line-by-line parse (not regex-in-window) is used because pymupdf emits one
value per line for these tables, and "-" appears as a literal separator
indicating zero that the naive regex-in-window approach skips.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
TEXT_DIR = ROOT / "text"
INV = ROOT / "inventory.json"
MODEL = ROOT / "data_model.json"


_NUM_LINE = re.compile(r"^\$?-?\(?[\d,]+(?:\.\d+)?\)?\$?$")


def money(s: str) -> float | None:
    s = s.strip().replace("$", "").replace(",", "")
    if s == "" or s == "$":
        return None
    if s == "-":
        return 0.0
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def collect_lines_after_normalized(pages_text: str, marker: str, n: int, max_lookahead: int = 40) -> list[float]:
    """Like collect_lines_after, but first normalizes multi-line whitespace
    in the page text — runs of whitespace (including newlines and indented
    continuations) collapse to a single space. This makes multi-line labels
    like 'Total capital assets,\\n   not being depreciated' match a flat
    marker 'Total capital assets, not being depreciated'.

    After locating the marker in the normalized text, we map back to the
    original text's character offset and collect numeric values from
    subsequent lines there. Mapping preserves the original line structure
    needed by the numeric walker.
    """
    # Build a char-by-char mapping from normalized positions back to original.
    orig = pages_text
    norm_chars: list[str] = []
    orig_pos: list[int] = []
    prev_was_space = False
    for i, ch in enumerate(orig):
        if ch.isspace():
            if prev_was_space:
                continue
            norm_chars.append(" ")
            orig_pos.append(i)
            prev_was_space = True
        else:
            norm_chars.append(ch)
            orig_pos.append(i)
            prev_was_space = False
    norm = "".join(norm_chars)

    best: list[float] = []
    search_start = 0
    while True:
        pos = norm.find(marker, search_start)
        if pos == -1:
            break
        end_norm = pos + len(marker)
        # Map end_norm back to orig index
        if end_norm < len(orig_pos):
            orig_end = orig_pos[end_norm]
        else:
            orig_end = len(orig)
        # Value collection starts at the next newline after orig_end
        next_newline = orig.find("\n", orig_end)
        value_start = next_newline + 1 if next_newline != -1 else orig_end
        tail = orig[value_start:]
        lines = tail.splitlines()
        vals: list[float] = []
        steps = 0
        for ln in lines:
            if steps >= max_lookahead or len(vals) >= n:
                break
            s = ln.strip()
            steps += 1
            if s == "":
                continue
            if s == "-":
                vals.append(0.0)
                continue
            if s in ("$", "-$", "$-"):
                continue
            if _NUM_LINE.match(s):
                v = money(s)
                if v is not None:
                    vals.append(v)
                continue
            break
        if len(vals) >= n:
            return vals
        if len(vals) > len(best):
            best = vals
        search_start = end_norm
    return best


def collect_lines_after(pages_text: str, marker: str, n: int, max_lookahead: int = 40) -> list[float]:
    """Find each occurrence of `marker` (which may span multiple lines),
    then collect up to `n` numeric values from subsequent non-blank lines.
    '-' counts as 0. Stops when a non-value line is hit.

    Returns the first run yielding ≥ n values, else the best partial run.
    Walking all occurrences handles duplicate rows (Range-A garbled +
    clean copy) where one copy may have empty-cell dashes stripped.
    """
    best: list[float] = []
    # Find all occurrences of the marker (substring match, may span newlines)
    search_start = 0
    while True:
        pos = pages_text.find(marker, search_start)
        if pos == -1:
            break
        # Advance past the marker; find the rest of the *line* containing
        # the marker's end so value collection starts on the next line.
        end = pos + len(marker)
        next_newline = pages_text.find("\n", end)
        value_start = next_newline + 1 if next_newline != -1 else end
        tail = pages_text[value_start:]
        lines = tail.splitlines()
        vals: list[float] = []
        steps = 0
        for ln in lines:
            if steps >= max_lookahead or len(vals) >= n:
                break
            s = ln.strip()
            steps += 1
            if s == "":
                continue
            if s == "-":
                vals.append(0.0)
                continue
            if s in ("$", "-$", "$-"):
                continue
            if _NUM_LINE.match(s):
                v = money(s)
                if v is not None:
                    vals.append(v)
                continue
            break
        if len(vals) >= n:
            return vals
        if len(vals) > len(best):
            best = vals
        search_start = end
    return best


def find_page(pages, must_have_all, must_have_any=None):
    for i, p in enumerate(pages):
        if all(m in p for m in must_have_all):
            if must_have_any is None or any(m in p for m in must_have_any):
                return i
    return None


def find_gov_wide_snp_span(pages) -> tuple[int, int] | None:
    """Locate the government-wide Statement of Net Position across
    pymupdf pages (which can split a single physical page into multiple
    blocks). Returns (start_page, end_page_exclusive) for the span that
    contains the Capital assets + Total Net Position lines we need.

    The government-wide SNP has:
      - Title: 'STATEMENT OF NET POSITION' or 'Statement of Net Position'
      - 3-column layout: Governmental | Business-Type | Total
      - No 'PROPRIETARY' or 'FIDUCIARY' qualifier in the title
    Pymupdf may put the title on one page and the capital-assets rows
    on the next. We anchor on the title and include up to 4 following pages.
    """
    # Pre-GASB 63 (Oceanside: FY ≤ 2012 roughly) calls this "Statement of
    # Net Assets"; later reports call it "Statement of Net Position".
    TITLE_VARIANTS = (
        "STATEMENT OF NET POSITION", "Statement of Net Position",
        "STATEMENT OF NET ASSETS", "Statement of Net Assets",
    )
    EXCLUDE = ("PROPRIETARY", "Proprietary", "FIDUCIARY", "Fiduciary",
               "INTERNAL SERVICE", "Internal Service", "AGENCY FUND")
    # Label spelling varies across AFR vintages:
    #   FY 2018+:   'Capital assets, not being depreciated'
    #   FY 2010ish: 'Capital assets not being depreciated' (no comma)
    #   FY 2009 and earlier: 'Non depreciable assets' + 'Depreciable assets, net'
    CA_MARKERS = (
        "Capital assets, not being depreciated",
        "Capital assets not being depreciated",
        "Non depreciable assets",
        "Non-depreciable assets",
        "Nondepreciable assets",
    )

    for i, p in enumerate(pages):
        has_title = any(t in p for t in TITLE_VARIANTS)
        if not has_title:
            continue
        if any(x in p for x in EXCLUDE):
            continue
        # Reject TOC-style hits (page with many dotted-leader lines)
        if p.count("..") > 20:
            continue
        # Require three-column header markers somewhere in a small window
        window = "\n".join(pages[i:i + 5])
        has_gov = "Governmental" in window
        has_biz = "Business-Type" in window or "Business-type" in window
        if not (has_gov and has_biz):
            continue
        # Require the capital-assets rows within the window. On some AFRs
        # (e.g., FY 2022) the table is spread across many pymupdf blocks and
        # the capital-asset rows land further down — widen to 12 pages in
        # that case, stopping at the first 'LIABILITIES' or 'Total assets'
        # marker which terminates the asset list.
        if any(m in window for m in CA_MARKERS):
            return (i, min(i + 5, len(pages)))
        end = min(i + 12, len(pages))
        for j in range(i + 5, end):
            window_text = pages[j]
            if "LIABILITIES" in window_text or "Liabilities:" in window_text:
                break
            if any(m in window_text for m in CA_MARKERS):
                # Include a few more pages after the marker to capture
                # the values (pymupdf may split label/values across pages)
                return (i, min(j + 8, len(pages)))
    return None


def _detect_layout(p: str) -> str:
    """Row-major: values directly after each label.
    Column-major: all labels first, then values in column order."""
    lines = p.splitlines()
    ca_idx = net_idx = None
    not_dep_markers = (
        "Capital assets, not being depreciated",
        "Capital assets not being depreciated",
        "Non depreciable assets",
        "Non-depreciable assets",
        "Nondepreciable assets",
    )
    net_markers = (
        "Capital assets, net of accumulated depreciation",
        "Capital assets, net of depreciation",
        "Depreciable assets, net",
        "Depreciable assets - net",
        "Depreciable assets net",
        "Capital assets, net",
    )
    for i, ln in enumerate(lines):
        s = ln.strip()
        if any(m in s for m in not_dep_markers) and ca_idx is None:
            ca_idx = i
        if any(m in s for m in net_markers) and net_idx is None:
            net_idx = i
    if ca_idx is None or net_idx is None:
        return "unknown"
    between = [ln.strip() for ln in lines[ca_idx + 1:net_idx] if ln.strip()]
    has_num = any(re.match(r"\$?-?\(?[\d,]+", s) for s in between)
    return "row-major" if has_num else "column-major"


def _is_numeric_line(s: str) -> bool:
    s = s.strip()
    if not s:
        return False
    if s == "-":
        return True
    cleaned = s.replace(" ", "").replace(",", "").replace("$", "")
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = cleaned[1:-1]
    if cleaned == "":
        return False
    return cleaned.replace(".", "").replace("-", "").isdigit()


def _parse_numeric(s: str) -> float | None:
    s = s.strip()
    if s == "-":
        return 0.0
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    s = s.replace(" ", "").replace(",", "").replace("$", "").strip()
    if s == "":
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def _collect_column_major(p: str) -> dict:
    """For column-major layout (all labels first, then 3 value columns
    for Governmental / Business-Type / Total).

    Newer ACFRs (FY 2023+) use a sparse layout where Business-Type only
    has values for the asset types that apply to enterprise funds — so
    Column 2 has fewer values than Columns 1 and 3. We can't assume
    3 × N values total.

    Strategy: identify column boundaries by lines that begin with '$'
    (or are bare '$') — each such line marks the start of a new column.
    Within each column, the Capital-assets pair ('not being depreciated'
    + 'net of accumulated depreciation') are always the last two asset
    rows reported, so the last two values in each column are the pair
    we want — regardless of how many other rows came before.
    """
    lines = p.splitlines()
    # Section detection: start at 'ASSETS'/'Assets:' header, stop when we
    # hit the next major section break (DEFERRED, LIABILITIES, Total assets).
    assets_start = None
    for i, ln in enumerate(lines):
        s = ln.strip()
        if (s == "ASSETS" or s == "Assets:" or s == "Assets") and assets_start is None:
            assets_start = i
            break
    if assets_start is None:
        return {}

    # Confirm the asset block contains the two capital-asset markers
    # before starting the value walk. If not, this is not the block we want.
    not_dep_markers = (
        "Capital assets, not being depreciated",
        "Capital assets not being depreciated",
    )
    net_markers = (
        "Capital assets, net of accumulated depreciation",
        "Capital assets, net of depreciation",
    )
    block_text = "\n".join(lines[assets_start:assets_start + 100])
    if not any(m in block_text for m in not_dep_markers):
        return {}
    if not any(m in block_text for m in net_markers):
        return {}

    # Walk values after the labels, grouping by column-break '$' markers.
    # Each column is a list of floats.
    columns: list[list[float]] = []
    current: list[float] = []
    seen_first_value = False

    def flush():
        if current:
            columns.append(current.copy())
            current.clear()

    for i in range(assets_start + 1, len(lines)):
        s = lines[i].strip()
        if not s:
            continue
        # Labels section: skip non-numeric lines until we see the first number
        if not seen_first_value and not _is_numeric_line(s) and not s.startswith("$"):
            continue
        # A '$' line (either bare '$' or '$ <number>') marks a new column
        if s.startswith("$"):
            rest = s[1:].strip()
            if rest and _is_numeric_line(rest):
                # '$ <number>' — flush prior column, start a new one with this value
                flush()
                v = _parse_numeric(rest)
                if v is not None:
                    current.append(v)
                seen_first_value = True
                continue
            elif s == "$":
                # Bare '$' — column separator, no value attached
                flush()
                continue
            else:
                # Something weird; skip
                continue
        if _is_numeric_line(s):
            v = _parse_numeric(s)
            if v is not None:
                current.append(v)
                seen_first_value = True
            continue
        # Non-numeric line once we've seen values: end of the asset block.
        # Could be 'Total assets', 'DEFERRED ...', 'LIABILITIES', or a new label.
        break

    flush()
    if len(columns) < 3:
        return {}

    def last_two(col):
        if len(col) < 2:
            return None, None
        return col[-2], col[-1]

    gov_not, gov_net = last_two(columns[0])
    biz_not, biz_net = last_two(columns[1])
    tot_not, tot_net = last_two(columns[2])
    if None in (gov_not, gov_net, biz_not, biz_net, tot_not, tot_net):
        return {}
    return {
        "cap_not_dep_gov": gov_not,
        "cap_net_dep_gov": gov_net,
        "cap_not_dep_biz": biz_not,
        "cap_net_dep_biz": biz_net,
        "cap_not_dep_total": tot_not,
        "cap_net_dep_total": tot_net,
    }


def extract_net_position_capital(pages):
    """From Statement of Net Position, pull capital asset breakdown
    (govt, bus, total) for both 'not being depreciated' and 'net of
    accumulated depreciation' categories. Handles row-major and column-major
    layouts, including cases where pymupdf splits the SNP table across
    multiple text blocks (typical for FY 2010–2019 AFRs)."""
    # Prefer span-based lookup (strict filter: not MD&A summary, not
    # Proprietary/Fiduciary). Fall back to single-page match only if the
    # span scan fails (e.g., pymupdf put everything on one block already).
    span = find_gov_wide_snp_span(pages)
    if span is not None:
        pg = span[0]
        p = "\n".join(pages[span[0]:span[1]])
    else:
        pg = find_page(pages, ["Statement of Net Position", "Capital assets"],
                       ["Governmental", "Business-Type", "Governmental ", "Business-type"])
        if pg is None:
            return {}, None
        p = pages[pg]

    # Tolerate label spelling variants across AFR vintages.
    not_dep_markers = [
        "Capital assets, not being depreciated",
        "Capital assets not being depreciated",
        "Non depreciable assets",
        "Non-depreciable assets",
        "Nondepreciable assets",
    ]
    net_markers = [
        "Capital assets, net of accumulated depreciation",
        "Capital assets, net of depreciation",
        "Depreciable assets, net",
        "Depreciable assets - net",
        "Depreciable assets net",
        "Capital assets, net",  # FY 2005 layout: separate net-of-depreciation row
    ]
    layout = _detect_layout(p)
    if layout == "row-major":
        out = {}
        for m in not_dep_markers:
            v = collect_lines_after(p, m, 3)
            if len(v) >= 3:
                out["cap_not_dep_gov"] = v[0]
                out["cap_not_dep_biz"] = v[1]
                out["cap_not_dep_total"] = v[2]
                break
        for m in net_markers:
            v = collect_lines_after(p, m, 3)
            if len(v) >= 3:
                out["cap_net_dep_gov"] = v[0]
                out["cap_net_dep_biz"] = v[1]
                out["cap_net_dep_total"] = v[2]
                break
        return out, pg
    if layout == "column-major":
        return _collect_column_major(p), pg
    return {}, pg


def extract_statement_of_activities(pages):
    """From Statement of Activities, extract Total governmental + Total
    business-type rows (4 values each: Expenses, Charges, Op Grants, Cap
    Grants), plus Interest on long-term debt. Tolerates casing variants
    across AFR vintages ('Total Governmental Activities' in FY 2010+ AFRs,
    'Total governmental activities' in earlier and later ACFRs)."""
    TITLE_VARIANTS = ("Statement of Activities", "STATEMENT OF ACTIVITIES")
    FUNCTIONS_VARIANTS = ("Functions/Programs", "Functions / Programs")
    GOV_VARIANTS = ("Total governmental activities", "Total Governmental Activities")
    BIZ_VARIANTS = ("Total business-type activities", "Total Business-Type Activities",
                    "Total business-type Activities")

    pg = None
    # Prefer a page with both Title and Functions/Programs header (the
    # canonical schedule page). Walk both casings.
    for i, p in enumerate(pages):
        if any(t in p for t in TITLE_VARIANTS) and any(f in p for f in FUNCTIONS_VARIANTS):
            if any(g in p for g in GOV_VARIANTS):
                pg = i
                break
    if pg is None:
        # Looser fallback: any page with title + Total-Gov marker
        for i, p in enumerate(pages):
            if any(t in p for t in TITLE_VARIANTS) and any(g in p for g in GOV_VARIANTS):
                pg = i
                break
    if pg is None:
        return {}, None
    p = pages[pg]
    out = {}
    for variants, prefix in [(GOV_VARIANTS, "gov"), (BIZ_VARIANTS, "biz")]:
        for marker in variants:
            v = collect_lines_after(p, marker, 4)
            if len(v) >= 4:
                out[f"{prefix}_expenses"] = v[0]
                out[f"{prefix}_charges"] = v[1]
                out[f"{prefix}_op_grants"] = v[2]
                out[f"{prefix}_cap_grants"] = v[3]
                break
    v = collect_lines_after(p, "Interest on long-term debt", 1)
    if v:
        out["interest_on_debt"] = v[0]
    return out, pg


def _parse_num_anywhere(s: str) -> float | None:
    """Parse a numeric-looking string, tolerating leading '(' without matching
    close paren (pymupdf splits negative numbers across blocks: '(14,513,338'
    and ')' land on separate lines — we still want to treat the first as
    negative)."""
    s = s.strip()
    if s == "":
        return None
    if s == "-":
        return 0.0
    if s in ("$", "-$", "$-"):
        return None
    cleaned = s.replace("$", "").replace(",", "").strip()
    neg = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        neg = True
        cleaned = cleaned[1:-1]
    elif cleaned.startswith("("):
        neg = True
        cleaned = cleaned[1:]
    try:
        v = float(cleaned)
        return -v if neg else v
    except ValueError:
        return None


def extract_general_revenues(pages):
    """General revenues + change-in-net-position extraction handles two very
    different document layouts:

    (1) **FY 2019+ ACFR layout**: the label 'Total general revenues' appears
        on the same pymupdf text-block as its 3 values. Handled with a simple
        label-anchored scan.

    (2) **FY 2010-2018 AFR layout**: the labels live on one page ending with
        a short block (Total General Revenues and Transfers / Change in Net
        Position / NP Beginning / Restatements / NP Beginning Restated / NP
        End — 6 closing rows), and the *values* for those labels live on
        continuation pages in a 3-column Gov/Biz/Total format, with columns
        broken by '$' markers. We anchor on the SNP Total Net Position
        (which also appears as the very last 3 values in the activities
        stream) and count backwards by 18 positions (6 rows × 3 cols) to
        locate Total Gen Rev and +3 more to locate Change in NP.

    Casing / wording variants are handled for both layouts.
    """
    TOTAL_GR_VARIANTS = (
        "Total general revenues",
        "Total General Revenues",
        "Total General Revenues and Transfers",
        "Total general revenues and transfers",
        "Total General Revenues, Extraordinary Items",
        "Total general revenues, extraordinary items",
    )
    CNP_VARIANTS = (
        "Change in net position",
        "Change in Net Position",
        "Change in net assets",
        "Change in Net Assets",
    )

    # Layout (1): simple anchor + values on same block
    GR_ANCHORS = ("General revenues", "general revenues", "General Revenues",
                  "GENERAL REVENUES")
    for i, p in enumerate(pages):
        if not any(a in p for a in GR_ANCHORS):
            continue
        combined = "\n".join(pages[i:i + 4])
        if not any(v in combined for v in TOTAL_GR_VARIANTS):
            continue
        tmp = {}
        for m in TOTAL_GR_VARIANTS:
            v = collect_lines_after(combined, m, 3)
            if len(v) >= 3:
                tmp["gen_revenues_gov"] = v[0]
                tmp["gen_revenues_biz"] = v[1]
                tmp["gen_revenues_total"] = v[2]
                break
        for m in CNP_VARIANTS:
            v = collect_lines_after(combined, m, 3)
            if len(v) >= 3:
                tmp["change_in_np_gov"] = v[0]
                tmp["change_in_np_biz"] = v[1]
                tmp["change_in_np_total"] = v[2]
                break
        if tmp:
            return tmp, i

    # Layout (2): AFR labels-and-values-on-separate-pages layout.
    # Find a page containing at least 'Total General Revenues' and 'Change in
    # Net Position' closing labels (NP End is a good anchor but not every
    # AFR has "Net Position at the End" — some use "Net Position - Ending").
    NP_END_VARIANTS = (
        "Net Position at the End",
        "Net Position at End of Year",
        "Net Position - Ending",
        "Net Position-Ending",
        "Net Position-ending",
        "Net position-ending",
        "Net position - ending",
        "Net position at the End",
        "Net position at End of Year",
        "Net Assets at the End",
        "Net Assets at End of Year",
        "Net Assets - Ending",
        "Net Assets-Ending",
        "Net assets-ending",
        "Net assets at the End",
    )
    labels_page_idx = None
    for i, p in enumerate(pages):
        has_gr = any(v in p for v in TOTAL_GR_VARIANTS)
        has_cnp = any(v in p for v in CNP_VARIANTS)
        has_np_end = any(v in p for v in NP_END_VARIANTS)
        if has_gr and has_cnp and has_np_end:
            labels_page_idx = i
            break
    if labels_page_idx is None:
        return {}, None

    # Count closing-section rows on the labels page. Rows between and
    # including 'Total General Revenues...' and the 'Net Position End' label
    # are the closing section — one row per label. Typical counts:
    #   - FY 2010-2018 AFRs: 6 rows (Total GR, Change NP, NP Beg Orig,
    #     Restatements, NP Beg Restated, NP End)
    #   - FY 2020+ ACFRs: 4 rows (Total GR, Change NP, NP Beg, NP End)
    labels_text = pages[labels_page_idx]
    lines = labels_text.splitlines()
    # Find index of first Total-GR label line and last NP-End label line
    gr_line = None
    npend_line = None
    for k, ln in enumerate(lines):
        if gr_line is None and any(v in ln for v in TOTAL_GR_VARIANTS):
            gr_line = k
        if any(v in ln for v in NP_END_VARIANTS):
            npend_line = k
    if gr_line is None or npend_line is None or npend_line < gr_line:
        return {}, labels_page_idx
    # Count non-empty label lines between (inclusive). Multi-line labels
    # (e.g., 'Net Position at the Beginning of the Year,\nas Originally
    # Reported' or 'Net Position - Beginning') count as ONE label. We
    # recognize the multi-line case when a line doesn't start with a fresh
    # label and its predecessor ended with a comma or 'as'.
    n_rows = 0
    for ln in lines[gr_line:npend_line + 1]:
        s = ln.strip()
        if not s:
            continue
        # A line that starts with a lowercase letter (or connector like
        # "and ", "as ", "or ", "of ") is almost always a continuation of
        # the previous label ("Total General Revenues, Extraordinary Items /
        # and Transfers"; "Net Position at the Beginning of the Year, / as
        # Originally Reported").
        if s[0].islower():
            continue
        if s.startswith(("As ", "Restated", "Reported")):
            continue
        n_rows += 1

    # Walk forward from labels page, parsing all numeric values until we hit
    # a sentinel marking the end of the Statement of Activities continuation.
    # Intentionally do NOT stop on footer-like phrases ('See Notes to ...',
    # 'notes to financial statements') — those footers can appear mid-page
    # between the Net-Expense table and the Gen Revenues section in some
    # AFRs (FY 2010 in particular). Only definitive next-section headers
    # are used as stops.
    STOP_SENTINELS = (
        "GOVERNMENTAL FUND FINANCIAL",
        "Government Fund Financial",
        "BALANCE SHEET",
        "Balance Sheet",
        "INTENTIONALLY LEFT BLANK",
        "intentionally left blank",
        "RECONCILIATION OF THE",
        "Reconciliation of the",
    )
    MAX_VALS = 200
    vals: list[float] = []
    stopped = False
    for j in range(labels_page_idx + 1, min(labels_page_idx + 30, len(pages))):
        if stopped:
            break
        for ln in pages[j].splitlines():
            if len(vals) >= MAX_VALS:
                stopped = True
                break
            stripped = ln.strip()
            if any(s in stripped for s in STOP_SENTINELS):
                stopped = True
                break
            v = _parse_num_anywhere(stripped)
            if v is not None:
                # Skip small non-zero integer values (page numbers, footnote
                # markers) that leak into the stream. Zeros are kept — they
                # represent genuine '-' cells in sparse 3-column rows.
                if 0 < abs(v) < 1000 and v == int(v):
                    continue
                vals.append(v)

    # Need at least n_rows × 3 values (closing section) plus some preceding
    # rows for Net-Expense/Revenue + Gen Rev subcategories. Bail if too few.
    needed = n_rows * 3
    if needed < 6 or len(vals) < needed:
        return {}, labels_page_idx

    out = {}
    gr = vals[-needed:-needed + 3]
    cnp = vals[-needed + 3:-needed + 6]
    if all(abs(v) < 1e10 for v in gr + cnp):
        out["gen_revenues_gov"] = gr[0]
        out["gen_revenues_biz"] = gr[1]
        out["gen_revenues_total"] = gr[2]
        out["change_in_np_gov"] = cnp[0]
        out["change_in_np_biz"] = cnp[1]
        out["change_in_np_total"] = cnp[2]
    return out, labels_page_idx


def extract_capital_assets_note(pages):
    """From 'Note — Capital Assets' schedule, extract gross capital assets:
      - Total gross not being depreciated (govt + biz separately)
      - Total gross being depreciated (govt + biz separately)
    These feed Decoder rows 20–25.

    The note's schedule typically has rollforward columns (Balance Begin,
    Additions, Deletions, Balance End). We want the Balance End column —
    usually the LAST numeric value on each subtotal line.

    Label phrasing varies across ACFR vintages:
      - Pre-FY2024: 'Total capital assets, not being depreciated' /
                    'Total capital assets, being depreciated'
      - FY2024+:    'Total capital assets, non-depreciable' /
                    'Total capital assets, depreciable/amortizable'
    """
    # Note 7 subtotals — phrasing varies across ACFR vintages. The FY 2024+
    # format uses 'non-depreciable' / 'depreciable/amortizable' and pymupdf
    # often splits these into two lines (indented second word). We search
    # both variants and the collect_lines_after function tolerates the
    # multi-line case.
    # Note 7 subtotal phrasing varies heavily across AFR/ACFR vintages
    # (punctuation, indentation, 'not being depreciated' vs 'non-depreciable',
    # 'being depreciated' vs 'depreciable/amortizable'). Rather than enumerate
    # every whitespace variant, we normalize whitespace in the page text
    # first (collapse runs of spaces/newlines to single spaces) and then
    # match against canonical markers.
    NOT_DEP_MARKERS = (
        "Total capital assets, not being depreciated",
        "Total Capital Assets, Not Being Depreciated",  # FY 2017 title case
        "Total capital assets, non-depreciable",
        "Total capital assets not being depreciated",  # FY 2018 no comma
    )
    BEING_DEP_MARKERS = (
        "Total capital assets, being depreciated",
        "Total Capital Assets, Being Depreciated",  # FY 2017 title case
        "Total capital assets, depreciable/amortizable",
        "Total capital assets, depreciable",
        "Total capital assets being depreciated",  # FY 2018 no comma
    )
    # Strategy: find each occurrence of a subtotal marker, look backwards
    # to identify whether it's in the Governmental or Business-Type section
    # (via section header like 'Governmental Activities Capital Assets'
    # or 'A. Governmental Activities'), then take the LAST value on that
    # row — which is the Balance End column in the rollforward schedule.
    GOV_SECTION = ("Governmental Activities Capital Assets",
                   "A.  Governmental Activities Capital Assets",
                   "A. Governmental Activities Capital Assets",
                   "Governmental activities:",
                   "GOVERNMENTAL ACTIVITIES:")
    BIZ_SECTION = ("Business-Type Activities Capital Assets",
                   "Business-type Activities Capital Assets",
                   "B.  Business-Type Activities Capital Assets",
                   "B. Business-Type Activities Capital Assets",
                   "Business-type activities:",
                   "BUSINESS-TYPE ACTIVITIES:")
    out = {}
    result_pages = [None, None]

    def _find_section_start(before_page: int, sections: tuple) -> int | None:
        """Walk backwards from before_page to find the last preceding section
        header. Returns the page index, or None if not found."""
        for i in range(before_page, -1, -1):
            p = pages[i]
            if any(s in p for s in sections):
                return i
        return None

    # Normalize whitespace per-page once for marker detection across
    # multi-line label splits.
    def _norm_ws(s: str) -> str:
        import re as _re
        return _re.sub(r"\s+", " ", s)

    for marker_list, key_suffix in [(NOT_DEP_MARKERS, "not_dep"),
                                    (BEING_DEP_MARKERS, "being_dep")]:
        for m in marker_list:
            # Find all pages whose normalized text contains the marker
            for i, p in enumerate(pages):
                if m not in _norm_ws(p):
                    continue
                # Combine forward window to capture row values that pymupdf
                # may have split across blocks.
                window = "\n".join(pages[i:min(i + 12, len(pages))])
                v = collect_lines_after_normalized(window, m, 6, max_lookahead=40)
                if not v:
                    continue
                # Classify as Gov or Biz by walking back to the nearest
                # section header.
                gov_start = _find_section_start(i, GOV_SECTION)
                biz_start = _find_section_start(i, BIZ_SECTION)
                if biz_start is not None and (gov_start is None or biz_start > gov_start):
                    prefix = "biz"
                    result_pages[1] = i
                elif gov_start is not None:
                    prefix = "gov"
                    result_pages[0] = i
                else:
                    continue
                out_key = f"gross_{key_suffix}_{prefix}"
                # Only set first-seen value (first occurrence wins — that's
                # usually the primary schedule, not a summary recap).
                if out_key not in out:
                    out[out_key] = v[-1]
    return out, (result_pages[0], result_pages[1])


def extract_acfr(doc_id: str, fy: str) -> dict:
    text = (TEXT_DIR / f"{doc_id}.txt").read_text(encoding="utf-8", errors="replace")
    pages = text.split("\x0c")
    out = {"fiscal_year": fy, "source_doc_id": doc_id}
    np_data, np_pg = extract_net_position_capital(pages)
    out.update(np_data)
    if np_pg is not None:
        out["source_np_page"] = np_pg
    act_data, act_pg = extract_statement_of_activities(pages)
    out.update(act_data)
    if act_pg is not None:
        out["source_act_page"] = act_pg
    gr_data, _ = extract_general_revenues(pages)
    out.update(gr_data)
    cap_data, _ = extract_capital_assets_note(pages)
    out.update(cap_data)
    return out


def main():
    inv = json.loads(INV.read_text())
    acfrs = sorted([r for r in inv if r["doc_type"] == "acfr"],
                   key=lambda r: r["fiscal_year"] or "")
    model = json.loads(MODEL.read_text())
    existing = {r["fiscal_year"]: r for r in model.get("acfr_decoder_inputs", [])}
    rows = []
    for r in acfrs:
        out = extract_acfr(r["doc_id"], r["fiscal_year"])
        # Merge: new values override None, but preserve any manually-patched
        # values (existing non-zero) that the parser didn't re-extract.
        prev = existing.get(r["fiscal_year"], {})
        for k, v in prev.items():
            if k in ("fiscal_year", "source_doc_id"):
                continue
            if k not in out and v is not None:
                out[k] = v
        rows.append(out)
        nfields = sum(1 for k in out if k not in ("fiscal_year", "source_doc_id",
                                                   "source_np_page", "source_act_page"))
        print(f"[{r['fiscal_year']}] {nfields} fields", file=sys.stderr)
    model["acfr_decoder_inputs"] = rows
    MODEL.write_text(json.dumps(model, indent=2))
    print(f"wrote {len(rows)} rows", file=sys.stderr)


if __name__ == "__main__":
    main()
