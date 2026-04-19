# `data/budget_history/` — Oceanside budget corpus and data model

A scraper + structured-data pipeline for every publicly-available City of
Oceanside budget document going back to **FY 2001** (the earliest material on
the city's Granicus CMS). This directory is the budget-side sibling of
`../vote_history/` (which tracks council meetings/votes).

The scope was extended from FY 2019-20 back to FY 2001 on 2026-04-18 to
support Strong Towns Finance Decoder analysis of long-term financial
sustainability. See the HISTORY.md "Data-quality notes" section for year-by-
year extraction coverage.

## Contents at a glance

```
budget_history/
├── HISTORY.md                  # Narrative walk-through, year by year
├── context.md                  # ← this file
├── inventory.json              # Filtered inventory: 189 docs since FY 2001
├── inventory_raw.json          # All 189 docs discovered from the portal
├── data_model.json             # All structured tables (see below)
├── budget_history.sqlite       # SQLite DB with 8 tables + 1 view
├── pdfs/                       # 189 PDFs (~495 MB)
├── text/                       # 189 text extracts + per-doc meta.json
├── by_year/                    # Reserved (empty)
└── scripts/                    # Scrapers, parsers, HTML fetches
    ├── fetch.sh                # Shared curl wrapper (browser headers for Akamai)
    ├── *.html                  # Saved category pages used for inventory
    ├── extract_inventory.py    # HTML → inventory.json
    ├── download_pdfs.sh        # curl download (urllib gets 403 from Akamai)
    ├── update_hashes.py        # Refresh size / sha256 after downloads
    ├── extract_text.py         # pymupdf text extraction → text/
    ├── decode_cid_shift.py     # Post-process CID-shifted ACFR/Measure X text
    ├── parse_financials.py     # Adopted-budget GF rev/exp + BiB FTE
    ├── parse_measure_x.py      # Measure X audits → revenue/exp/fund balance
    ├── parse_acfr.py           # ACFR GF Balance Sheet + Net Position
    ├── parse_quarterly.py      # Quarterly reports → YTD rev/exp/surplus
    ├── parse_cip.py            # FY25-26 CIP → 5-year program plan
    ├── parse_decoder_inputs.py # ACFR → Strong Towns Decoder 11 inputs
    ├── compute_decoder_metrics.py  # Compute the 7 Decoder metrics
    ├── write_decoder_xlsx.py   # Populate decoder/oceanside_decoder_output.xlsx
    └── build_db.py             # All JSON → SQLite
```

## Source of truth

All documents are scraped from **www.ci.oceanside.ca.us/government/financial-services**
and its subtrees. The city uses a Granicus Vision CMS. Key URL patterns:

- Document: `/home/showpublisheddocument/{doc_id}/{timestamp}` — `doc_id` is
  a stable integer, `timestamp` is .NET Ticks-format last-modified. We use
  `doc_id` as the primary key across all tables.
- Folder listing: `/government/financial-services/{category}/-folder-{id}` —
  Granicus' subfolder navigation. Quarterly reports, sales-tax newsletters,
  and component-unit financials live one folder-level deep by FY.

## Anatomy of each document type (where the data lives)

Knowing which pages to target saved hours of misdirected parsing:

| Doc type | Authoritative summary page(s) | What's there |
|---|---|---|
| `adopted_budget` | Around page 170–200 (of ~270) | "GENERAL FUND REVENUES" and "EXPENDITURE BY DEPARTMENT – GENERAL FUND" schedules, 4 cols (2 actuals + 2 adopted) |
| `adopted_budget` (detail) | Next page after summary | "REVENUES BY TYPE – GENERAL FUND" with 4101/4116-style account codes — skip this, use summary |
| `adopted_budget` (BiB overlay) | ~page 12 | Embedded Budget-in-Brief page containing "CITYWIDE STAFFING" — not the authoritative table |
| `budget_in_brief` | Page 1–2 | Revenue/Expenditure pie slices, FTE-by-department in a plain table |
| `acfr` | Balance Sheet - Governmental Funds (~p 40–180 depending on year); Statement of Net Position (~p 30–120) | 3-column Governmental / Business-Type / Total for Net Position; 4–5-column Governmental Funds for Balance Sheet |
| `acfr` (fallback) | "RECONCILIATION OF THE BALANCE SHEET" page | Contains `Total Fund Balances - Governmental Funds $X` as a single line — useful when the main table didn't extract |
| `measure_x_report` | Page 6 (Balance Sheet), page 7 (Statement of R/E/C) | 3 cols: Operating / Capital / Total. FY2019 report is single-column (pre-dates split) |
| `quarterly_q1..q4` | SYNOPSIS/BACKGROUND section at top | Narrative of adopted budget + YTD actuals + reported surplus |
| `cip` (FY 25-26) | Page 27 "Program Summary" | 5-year plan by funding program (TransNet, Water, Sewer, etc.) |

## Pipeline

```
11 category pages (fetch.sh: operating-budget, cafr, budget-in-brief,
│ quarterly + FY subfolders, single-audit, measure-x, component-unit,
│ sales-tax, CIP)
│
├──► extract_inventory.py
│    → inventory.json (102 docs since FY 2019)
│
├──► download_pdfs.sh  →  pdfs/
├──► update_hashes.py  (size + sha256)
├──► extract_text.py   →  text/{doc_id}.txt
├──► decode_cid_shift.py  (in-place, for garbled ACFR/Measure X pages)
│
├──► parse_financials.py   → data_model.json.general_fund + .fte_by_department
├──► parse_measure_x.py    → data_model.json.measure_x
├──► parse_acfr.py         → data_model.json.acfr_gf_balance + .acfr_net_position
├──► parse_quarterly.py    → data_model.json.quarterly
├──► parse_cip.py          → data_model.json.cip_program
│
└──► build_db.py → budget_history.sqlite
```

## SQLite schema

```sql
documents (doc_id PK, title, doc_type, source_category, fiscal_year,
           url, timestamp, local_path, size_bytes, sha256, pages, words)

-- General Fund revenue & expenditure line items, from adopted budgets.
-- Each adopted budget reports 2 historical actuals + 2 adopted years,
-- so rows are cross-validated across source docs.
gf_line_items (id PK, fiscal_year, basis, flow, category, amount_usd,
               source_doc_id FK, source_doc_fy, source_page)
    basis ∈ {actual, adopted, amended, proposed, projected}
    flow  ∈ {revenue, expenditure}

fte_by_department (id PK, fiscal_year, department, fte, source_doc_id FK)

-- Measure X Fund audit data (7 annual reports).
-- Three-column structure: Operating | Capital | Total.
measure_x (id PK, fiscal_year, line_item, kind, fund_type, amount_usd,
           source_doc_id FK)
    kind ∈ {revenue, expenditure, transfer, balance, net}
    fund_type ∈ {Operating, Capital, Total}

-- ACFR General Fund Balance Sheet rows (Nonspendable / Restricted /
-- Committed / Assigned / Unassigned / Total, plus assets + liabilities).
acfr_gf_balance (id PK, fiscal_year, line_item, amount_usd, source_doc_id FK)

-- ACFR government-wide Statement of Net Position: Governmental + Business-Type + Total.
acfr_net_position (id PK, fiscal_year, activity, line_item, amount_usd,
                   source_doc_id FK)
    activity ∈ {Governmental, Business-Type, Total}

-- Quarterly Financial Status Reports — narrative-extracted top-line metrics.
quarterly_status (id PK, fiscal_year, quarter, adopted_gf_revenue,
                  adopted_gf_expenditure, adopted_all_funds_revenue,
                  adopted_all_funds_expenditure, actual_gf_revenue,
                  actual_gf_expenditure, gf_surplus, source_doc_id FK)
    quarter ∈ {Q1, Q2, Q3, Q4}
    Q1–Q3 actuals are YTD; only Q4 is full-year.

-- Capital Improvement Program — FY 2025-26 5-year plan by funding program.
cip_program (id PK, fiscal_year, program, fund_id, amount_usd,
             source_doc_id FK, source_doc_fy, source_page)

-- Strong Towns Finance Decoder — 11 ACFR input line items per year.
acfr_decoder_inputs (id PK, fiscal_year,
    cap_not_dep_gov, cap_not_dep_biz, cap_not_dep_total,
    cap_net_dep_gov, cap_net_dep_biz, cap_net_dep_total,
    gov_expenses, gov_charges, gov_op_grants, gov_cap_grants,
    biz_expenses, biz_charges, biz_op_grants, biz_cap_grants,
    interest_on_debt, gen_revenues_total, change_in_np_total,
    gross_not_dep_gov, gross_not_dep_biz,
    gross_being_dep_gov, gross_being_dep_biz,
    source_doc_id FK, source_np_page, source_act_page)

-- Strong Towns Finance Decoder — 7 computed metrics per year.
decoder_metrics (id PK, fiscal_year,
    current_assets, capital_assets, total_assets,
    deferred_outflows, liabilities, deferred_inflows, total_liabilities,
    total_revenues, op_grants, cap_grants, interest_charges,
    net_book_tca, total_cost_tca,
    metric_1_net_financial_position,
    metric_2_financial_assets_to_liab,
    metric_3_total_assets_to_liab,
    metric_4_net_debt_to_revenues,
    metric_5_interest_to_revenues,
    metric_6_net_book_to_cost_tca,
    metric_7_transfers_to_revenues)

-- VIEW: most recent source for each (fy, basis, flow, category).
gf_authoritative
```

**Current row counts** (after FY 2001 extension, 2026-04-18):
189 documents, 1,238 GF line items, 247 FTE rows, 207 Measure X rows,
134 ACFR GF balance rows, 151 ACFR net position rows, 22 quarterly status
rows, 53 CIP program rows, 41 decoder input rows (one per AFR/ACFR doc,
FY 2001–FY 2025), 24 decoder metric rows (FY 2002–FY 2025 — most have
only partial metrics; see HISTORY.md data-quality notes for coverage).

## Document type conventions

| doc_type | Meaning | Corpus count |
|---|---|---:|
| `adopted_budget` | Annual operating budget PDF (~200–290 pp); FY 2010–present | 16 |
| `biennial_budget` | Biennial adopted budget (FY 2002-04, 2004-06) | 2 |
| `budget_supplement` | Per-department budget section (biennial-era), FY 2006-08 / 2008-10 | 12 |
| `budget_in_brief` | 1–2 page public summary | 12 |
| `cip` | Capital Improvement Program budget (FY 2006-08 and FY 2025-26 standalone) | 2 |
| `acfr` | Annual Comprehensive Financial Report / AFR (audited) | 30 |
| `single_audit` | Federal award compliance audit | 24 |
| `measure_x_report` | Annual Measure X fund audit | 7 |
| `quarterly_q1..q4` | Quarterly Financial Status Report | 25 |
| `component_unit` | Housing Authority / Harbor District financials | 18 |
| `sales_tax_newsletter` | HdL Companies' quarterly sales-tax analysis | 23 |

**AFR vs. ACFR terminology note**: Pre-FY 2019 audits are titled "Annual
Financial Report" (AFR); FY 2019+ are titled "Annual Comprehensive Financial
Report" (ACFR or CAFR). The `doc_type="acfr"` classification covers both.
Also, audits from FY 2002 through FY 2009 are split into three separate PDFs
per year (Introductory / Financial / Statistical sections); FY 2010+ are
single consolidated PDFs.

## Gotchas & hard-won lessons

Things that cost time to figure out; keep these in mind before making parser
changes.

### Akamai blocks bare Python clients

`urllib.request.urlopen` with a basic `User-Agent` gets **HTTP 403** from the
ci.oceanside.ca.us edge. curl works if you include browser-like headers:
`Accept: text/html,...`, `Accept-Language: en-US,en;q=0.9`, and the
`Sec-Fetch-*` set. `scripts/fetch.sh` encodes the minimal working recipe.
`scripts/download_pdfs.sh` does the same for PDF downloads.

### CID-shift font encoding (+29 glyph offset)

A subset of ACFR and Measure X PDFs — especially FY 2019-2022 — embed text
using a custom font where every glyph index is **+29 below its Unicode code
point**. pymupdf surfaces the raw glyph indices. This shows up in **two
source ranges** depending on which text element the font covers:

**Range A — Printable-ASCII source** (titles/headers). "CITY OF OCEANSIDE"
extracts as `&,7<2)2&($16,'(`:

| Raw char | ASCII | +29 | Decoded |
|---|---:|---:|---|
| `&` | 38 | 67 | `C` |
| `,` | 44 | 73 | `I` |
| `7` | 55 | 84 | `T` |
| `D` | 68 | 97 | `a` |

**Range B — Control-char source** (table bodies in the Notes section).
"CITY OF OCEANSIDE" extracts with `\x03` between words (space) and digits
encoded as `\x13`–`\x1c` (0–9):

| Raw char | ord | +29 | Decoded |
|---|---:|---:|---|
| `\x03` | 3 | 32 | space |
| `\x13` | 19 | 48 | `0` |
| `\x14` | 20 | 49 | `1` |
| `\x1c` | 28 | 57 | `9` |
| `\x0f` | 15 | 44 | `,` |

`decode_cid_shift.py` handles **both** ranges (as of 2026-04-18):

- Phase 1: `page_is_garbled()` whole-page check → Range-A shift via
  `shift_run()` when the page has no legitimate lowercase letters and high
  density of 68..93 source chars. Per-run detection was tried and rejected
  because clean uppercase titles like "CITY OF OCEANSIDE" give false
  positives (indistinguishable from Range-A garbled lowercase-source chars
  at the run level).
- Phase 2: `shift_range_b()` — always safe because control chars like
  `\x03`, `\x07`, `\x13` never appear in clean text. Unconditionally shifts
  0..8, 11, 14..31 by +29.

The phases must run in **this order**: if Range B ran first, its digit
outputs (48..57) would fall inside Range A's 33..97 window and corrupt
on a second pass. Range A first, Range B second has no overlap.

Consequence: for mixed-content pages (FY 2010–2019 AFRs where pymupdf
interleaves a Range-A garbled title with clean body text), the title
stays garbled but the body — and crucially the Range-B-encoded numeric
values — comes out clean. Parsers anchor on body markers
(e.g., `Capital assets, not being depreciated`), not titles.

Note: characters in range 33–64 decode to uppercase letters (garbled TITLES),
and characters in range 68–93 decode to lowercase letters (garbled body text).
Digits in range 48–57 are also used as glyph indices for letters — this means
you **cannot trust dollar amounts on garbled pages** (digits may become
letters after shifting, and real digits leave untouched).

`decode_cid_shift.py` lessons learned the hard way:

- **Page-level heuristic, not run-level.** Initial attempt: shift any run of
  non-lowercase ASCII. That corrupted clean uppercase headings ("ASSETS" →
  nonsense). Current rule: shift only if the *entire page* has essentially
  no lowercase (≤3 chars) AND ≥25% of non-whitespace chars are in the
  +29-to-lowercase range (68–93). Mixed-content pages (where pymupdf duplicates
  a physical page as one garbled and one clean extraction block) are left
  alone — the clean block wins naturally.
- **pymupdf "pages" in split text ≠ physical pages.** pymupdf can emit
  multiple form-feed-separated blocks per physical page when text regions
  aren't contiguous. The text file's `pages = text.split('\x0c')` may have
  1200+ "pages" for a 178-page PDF. This is why the CID-shift heuristic
  uses character density, not absolute counts.
- **Labels and values can split across blocks.** On some physical pages
  (e.g. FY 2021 ACFR page 148 Balance Sheet), pymupdf puts the row labels
  (`Total Assets`, `Cash and investments`) on one text-block "page" and the
  dollar values on another. Decoding alone doesn't fix this; you'd need
  per-character position-aware extraction via `page.get_text("rawdict")`
  to reconstruct the table cells.

### Summary table detection (adopted budgets)

Adopted budgets have multiple pages that *look* like the GF revenue table:

1. **Narrative/transmittal** (~page 8–15): prose with a `(in millions)` mini
   table. Values like `65.46` not `$65,463,722`.
2. **BiB overlay embedded in the budget** (~page 12): contains "CITYWIDE
   STAFFING" banner.
3. **Summary schedule** (~page 170–200): the authoritative one we want.
4. **Detail by account code** (1 page after summary): "REVENUES BY TYPE"
   with "4101 Prop Taxes- PY Secured" line items.
5. **Pie-chart legend** (bottom half of summary page): category names repeat
   with small percentages.

Detection rules in `parse_financials.find_gf_rev_page`:
- Must contain `Property Taxes` + `Sales & Use Taxes` + `Transient Occupancy`
- Must contain `Grand Total` or `Subtotal`
- Reject `CITYWIDE STAFFING` (BiB overlay)
- Reject pages with `\b41\d{2}\s+\w` (account-detail codes)
- Require all three category markers within 600 chars (cluster check)
- Require a $-amount within 200 chars of "Property Taxes" (rules out narratives)

The parser **stops walking after `Grand Total`** to avoid re-matching the
pie-chart category names (which would produce garbage like "Property Taxes
= 39%").

### Column header detection (vertical-glyph vs horizontal)

pymupdf renders budget headers two ways:

- **Horizontal**: `Actuals FY 2020-21 Actuals FY 2021-22 Adopted FY 2022-23`
  all on one line.
- **Vertical glyph**: one token per line — `Actuals\nFY 2020-21\nActuals\n
  FY 2021-22\nAdopted\nFY 2022-23`.

`parse_financials.parse_table` tries the vertical layout first (scans for
consecutive lines each fullmatching a header token), then falls back to
horizontal pattern-matching. Also handles **multi-word column labels** like
`Actual FY 2018-19` (singular) and `Adopted Budget FY 2020-21` (two words).

### Align-right heuristic for truncated rows

The FY 2021-22 Measure X row has only 3 values in a 4-column table (Measure X
didn't exist in FY 2018-19). If the parser collected fewer values than
columns, it **aligns right** — the missing column is assumed to be the
earliest year. This handles new categories correctly but does lose
information if the row is legitimately short for other reasons.

### Cross-source dedup + the `gf_authoritative` view

Each adopted budget reports 2 historical + 2 current years, so e.g. FY 2020-21
actuals appear in 3 different budgets. Minor numerical drift (rounding,
mid-year restatement) means the same `(fy, basis, flow, category)` can have
2-3 rows with slightly different `amount_usd`. The `gf_authoritative` SQL
view picks the most-recent source per key — generally the freshest value.

**Validation**: Measure X tax revenue in `gf_line_items` (from adopted
budgets' actual column) matches Measure X "Taxes" in the audited `measure_x`
table to the penny for FY 2020 → FY 2024. This is a strong cross-source
check that both parsers are reading the same ground truth.

### Quarterly report narrative parsing

The quarterly reports vary in format across years but all have a narrative
`SYNOPSIS/BACKGROUND` section that states adopted budget figures in prose:
"approved General Fund revenues of $204 million and expenditures of
$203.3 million". `parse_quarterly.py` uses regex to pull these out. Key
discipline: **require "General Fund" explicitly** in the capture group,
otherwise the pattern picks up the all-funds total ("$574.67 million in
revenues") from the adjacent sentence.

### Windows-specific: trailing `\r` (or `_`) in filenames

When Python prints a tab-separated line and a Bash loop reads it via
`while IFS=$'\t' read -r ...`, on Windows `\r\n` line endings leak a `\r`
into the last field. The file gets saved with a trailing `\r` in its name.
`os.listdir` on Git Bash / MSYS2 sometimes renders that character as a
literal underscore `_`, which is confusing to debug. Fix:
`download_pdfs.sh` now pipes through `tr -d '\r'` and also strips any
trailing space/CR via bash parameter expansion. The cleanup logic is
idempotent and safe to re-run.

### Pre-FY 2010 AFRs are split into three PDFs per year

FY 2002 through FY 2009 audits come as three separate files per year:
`AFR - Introductory Section`, `AFR - Financial Section`, and `AFR -
Statistical Section`. The decoder parser only wants the **Financial
Section** (has Statement of Net Assets + Activities + Notes). The
Introductory and Statistical sections are inventoried for completeness
but yield 0 decoder fields.

### Scanned image-only AFRs (FY 2001, 2003, 2004, 2006, 2007)

Five early-2000s AFRs are stored as image-only PDFs (one big image per
page, no embedded text). `extract_text.py` yields 0 words for those
docs. Parsing these requires OCR (Tesseract). Left as a follow-up — these
years pre-date Oceanside's full GASB 34 implementation anyway, so the
decoder inputs format doesn't cleanly apply to FY 2001 regardless.

## How to re-run the pipeline

Incremental refresh (new FY or amendments):

```bash
cd data/budget_history

# 1. Refresh category HTML pages (edit fetch.sh if new categories)
# 2. Rebuild inventory
python scripts/extract_inventory.py
# 3. Download any new PDFs
bash scripts/download_pdfs.sh
python scripts/update_hashes.py
# 4. Re-extract text
python scripts/extract_text.py
# 5. Post-process CID-shifted ACFR/Measure X pages
python scripts/decode_cid_shift.py
# 6. Re-parse all structured tables
python scripts/parse_financials.py
python scripts/parse_measure_x.py
python scripts/parse_acfr.py
python scripts/parse_quarterly.py
python scripts/parse_cip.py
python scripts/parse_decoder_inputs.py
python scripts/compute_decoder_metrics.py
# 7. Rebuild SQLite
python scripts/build_db.py
# 8. (Optional) Regenerate populated decoder worksheet
python scripts/write_decoder_xlsx.py
```

Every script is idempotent — re-running without source changes is a no-op
(existing PDFs and text files are preserved).

## Known gaps and TODOs

Edge cases that remain after the April 2026 gap-filling pass. Each includes
enough context to pick up the work cold.

### Strong Towns Finance Decoder

The [`decoder/`](decoder/) subdirectory contains:
- `Strong Towns Finance Decoder Worksheet - US 1.0.1.xlsx` — the original
  Strong Towns template.
- `Finance Decoder Instructions.docx` — their official how-to guide.
- `Finance Decoder Shareable Template/` — 7 PNG chart templates for
  publishing the metrics.
- `oceanside_decoder_output.xlsx` — **our populated output**, matching the
  worksheet's Input sheet layout.
- `DECODER_ANALYSIS.md` — narrative write-up of all 7 metrics, sources,
  validation, and remaining gaps.

The pipeline:

1. `parse_decoder_inputs.py` extracts 11 inputs per AFR/ACFR year from the
   Statement of Net Position (or "Net Assets" in pre-FY 2013 vintages),
   Statement of Activities, and Note 7 (Capital Assets). Handles both
   row-major and column-major layouts, plus the FY 2010–2019 AFR case
   where pymupdf splits the SNP across 5+ text blocks. Requires
   `decode_cid_shift.py` to have run first for Range-A/Range-B garbled
   pages.
2. `compute_decoder_metrics.py` derives Current Assets, Capital Assets,
   Total Liabilities, and Total Revenues, then computes the 7 metrics.
3. `write_decoder_xlsx.py` emits the populated worksheet.
4. `build_db.py` ingests both `acfr_decoder_inputs` and `decoder_metrics`
   tables.

**Coverage** (as of 2026-04-18, after full parser + OCR pass):

| FY range | Metrics available (of 7) | Notes |
|---|---|---|
| FY 2013–2018, 2020–2024 | 6–7 of 7 | Full structured coverage |
| FY 2019, 2025 | 5–6 | Note 7 partial / CNP missing |
| FY 2009–2012 | 4–5 | Pre-GASB 65 (no Deferred Inflows) so TA/L unavailable; activities + cap + Note 7 work |
| FY 2007–2008 | 3–4 | OCR (2007) or pre-GASB 65 layout |
| FY 2002–2006 | 2–4 | OCR quality limits for 2003/04/06; "Net Assets" era layout handled but gen-revenues not extracted |
| FY 2001 | 0 of 7 | Pre-GASB 34 — no government-wide reporting exists in the AFR |

Up from the pre-2026-04-18 state of 7 fiscal years (FY 2019–2025) with
partial data to **23 years (FY 2002–2024)** with meaningful decoder metrics.

Historical note: FY 2015 / FY 2016 show negative Net Financial Position
(−$99M). This is a real effect of GASB 68 implementation that year, which
forced Oceanside to recognize the full net pension liability on the
balance sheet (Total Liabilities jumped from $195M in FY 2014 to $357M in
FY 2015). FY 2017 onwards shows Net FP recovering.

Closed follow-ups (2026-04-18):
- ✅ **General Revenues + Change in Net Position for FY 2010–2025 AFRs**:
  parser now walks the labels-on-one-page / values-on-continuation-pages
  layout, counts closing rows dynamically, and uses
  `GARBLED_SIGNATURE_RE` to force Range-A shift on AFR continuation pages
  that wouldn't pass the density-based `page_is_garbled` test.
- ✅ **"Net Assets" era terminology (pre-GASB 63, FY ≤ 2012)**: parser
  accepts `Non depreciable assets` / `Depreciable assets, net` / `Capital
  assets, net` in addition to modern `Capital assets, not being
  depreciated` / `...net of accumulated depreciation`.
- ✅ **`parse_acfr.py` net position for all FY 2002–2025**: multi-pass
  detection scans candidate pages with a 40-block forward window, picks
  the one yielding the most valid rows. Handles title+values-on-same-page
  (FY 2020+) and title-on-one-page / rows-split-across-25+-blocks
  (FY 2010-2019, FY 2023) layouts. Rejects MD&A "$565.7" shorthand via a
  $10K per-value threshold.
- ✅ **Div-by-near-zero guards in compute_decoder_metrics**: `_nz()`
  treats < $1M as missing; `total_cost_tca` rejected if < `net_book_tca`;
  non-positive `total_revenues` rejected. Pre-GASB 65 missing
  `def_inflows` now treated as $0 not missing, so total_liabilities
  computes correctly for FY 2002–2013.
- ✅ **OCR applied to 5 image-only AFRs** (FY 2001, 2003, 2004, 2006,
  2007): Tesseract 5.4 installed via winget; `scripts/ocr_scanned_afrs.py`
  ran at 200 DPI producing ~25K words per doc. FY 2003, 2004, 2006, 2007
  now yield decoder metrics; FY 2001 is pre-GASB 34 so has no
  government-wide statement regardless of OCR quality.
- ✅ **OCR preservation in decode_cid_shift**: decoder now skips writing
  text-file content when PDF extract is near-empty AND existing file has
  substantial content (protects OCR'd text from being clobbered on
  subsequent pipeline runs).

Remaining gaps:
- **FY 2001 has no government-wide financial statement** (pre-GASB 34
  implementation in California). Fund-level data only; decoder metrics
  not applicable.
- **Some years are missing the Note 7 gross-cost row** (NB/TCA metric)
  due to alternate note format or OCR gaps in the rollforward table.
- **compute_decoder_metrics reports negative NetFP for FY 2015-2016** —
  this is historically accurate (GASB 68 pension accounting) but worth
  flagging in reports to explain the dip.

### Parser edge cases

- [ ] **FY 2021 ACFR GF Fund Balance breakdown** (doc_id 8308)
      - Current: only `gov_funds_total_fb = $183,854,588` extracted via the
        Reconciliation page fallback.
      - Missing: the 5-way Fund Balance classification (Nonspendable,
        Restricted, Committed, Assigned, Unassigned) plus Total Assets /
        Liabilities for the GF column.
      - Root cause: the Balance Sheet on PDF page ~148 is fully CID-shifted
        AND pymupdf splits labels from values across form-feed blocks, so
        even after +29 decoding the columns don't reassemble.
      - Fix path: use `page.get_text("rawdict")` to get per-character x/y
        positions, then reconstruct the column structure from coordinates.
        The problematic font is likely identifiable by name in the `rawdict`
        output and can be shifted selectively.

- [ ] **FY 2022 ACFR — no balance data extracted** (doc_id 11584)
      - Current: neither `acfr_gf_balance` nor `acfr_net_position` has FY
        2022 rows, and the reconciliation fallback also failed to match
        because the page is largely garbled.
      - Root cause: same CID-shift issue but more pervasive — labels that
        `parse_acfr.find_gf_balance_page` searches for (`BALANCE SHEET`,
        `GOVERNMENTAL FUNDS`, `FUND BALANCE`) all extract as `%DODQFH6KHHW`
        etc. Post-decode the text is readable but the locator strings would
        need to also be tried in pre-decoded form.
      - Fix path: apply `shift_run()` to locator strings and try both
        variants when searching. Alternatively, re-OCR the PDF with
        Tesseract (the visual rendering is fine).

- [ ] **FY 2019 / FY 2021 Net Position 3rd column partial** (doc_ids 8304, 8308)
      - Current: 12 rows each vs. 18 for fully-extracted years.
      - Root cause: for 4 of the 6 Net Position line items, only 2 of 3
        activity columns (Governmental / Business-Type / Total) had numeric
        values within the 600-char look-ahead window.
      - Fix path: extend the `parse_net_position` look-ahead window from 600
        to 1200 chars, or switch to line-by-line scan with a value-per-row
        cap.

### Scope expansions (larger, separate work)

- [ ] **Prior-year CIP tables** (FY 2020-21 through FY 2024-25)
      - Standalone CIP books don't exist pre-FY 2025-26; the CIP is embedded
        in the adopted budget as a "Capital Improvement Program" chapter
        starting around page 200 of each. Format varies year-to-year.
      - A starting point: the `DEVELOPMENT SERVICES – BUDGET SUMMARY –
        Expenditure Summary by Program` tables in each adopted budget list
        CIP line items with 4-year comparatives (see pages 117, 125, 104,
        etc. in docs 8120, 12786, 14804).
      - Schema change needed: `cip_program` currently assumes 5 forward
        years; an `adopted_cip_line` table keyed by (fiscal_year, program,
        account_code) with 4 columns (2 actuals + 2 adopted) would mirror
        `gf_line_items`.

- [ ] **ACFR sub-fund detail** (non–General Fund governmental and
      enterprise activities)
      - The Balance Sheet – Governmental Funds shows Special Revenue,
        Capital Projects, and Housing/ARPA as additional columns beyond GF.
        Component Unit financials (18 docs in corpus) audit the Housing
        Authority and Harbor District separately.
      - Useful for: tracking ARPA draws, Housing Assistance Program fund
        health, Harbor District operating ratio. Schema would extend
        `acfr_gf_balance` to include a `fund` column.

- [ ] **Quarterly "Attachment A — Budget Adjustments"**
      - Every quarterly report has a staff-report attachment listing the
        specific line-item budget amendments approved at that meeting.
        These are the in-year changes from adopted to amended.
      - Currently unstructured. Extracting would give a complete picture of
        how budgets shift during the year. Likely requires PDF attachment
        extraction (attachments may not be in the main text; need to
        verify).

- [ ] **Single Audit Report findings extraction**
      - 7 single-audit PDFs in corpus (`single_audit` doc type). These list
        federal-award-specific findings. Unstructured now; would require a
        schema like `single_audit_findings (fy, award_number, finding_type,
        severity, text)`.

- [ ] **Sales tax newsletters quarterly category splits**
      - 23 HdL sales-tax newsletters in corpus. Each has a breakdown by
        economic sector (autos, fuel, restaurants, etc.) — useful for
        drilling into why `Sales & Use Taxes` plateaued in FY 2023-24.
        Would need `sales_tax_by_sector` table.

### Validation / future cross-checks

- [ ] **Reconcile GF Adopted totals across BiB vs. adopted budget.** Both
      documents report the same FY's adopted totals but we only trust the
      adopted budget's summary schedule. A reconciliation row-by-row would
      catch any transcription issues in either document.
- [ ] **Validate ACFR's reported revenue against budget actuals column.** The
      ACFR Statement of Revenues/Expenditures should tie to the next year's
      adopted budget "Actuals FY X-Y" column. A mismatch flags either a
      restatement or an extraction error.
