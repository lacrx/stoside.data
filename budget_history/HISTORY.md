# City of Oceanside — Budget History, FY 2001–02 through FY 2025–26

A narrative walk-through of Oceanside's General Fund budget, built from
189 primary-source documents downloaded from the City of Oceanside's financial
services portal. Every figure in this document is traceable to a specific line
in a specific PDF — see the `budget_history.sqlite` `gf_line_items` table.

The narrative sections below (FY 2019-20 onwards) are the FY range of the
original corpus. The corpus was extended back to **FY 2001** on 2026-04-18 to
support long-term Strong Towns Finance Decoder analysis. Pre-FY 2019 years
have partial structured coverage — see the data-quality notes for details.

## Contents

- [1. Corpus summary](#1-corpus-summary)
- [2. Top-line trajectory](#2-top-line-trajectory)
- [3. Year-by-year history](#3-year-by-year-history)
- [4. Revenue trends](#4-revenue-trends)
- [5. Expenditure and staffing trends](#5-expenditure-and-staffing-trends)
- [6. Measure X](#6-measure-x)
- [7. Data-quality notes](#7-data-quality-notes)

---

## 1. Corpus summary

| Type | Count | Years covered | Notes |
|---|---|---|---|
| Adopted Operating Budget | 16 | FY 2010-11 → FY 2025-26 | Authoritative budget document (~170–290 pages each) |
| Biennial Adopted Budget | 2 | FY 2002-04, FY 2004-06 | Two-year budget cycle before FY 2010 |
| Budget Supplements | 12 | FY 2006-08, FY 2008-10 | Per-department sections (biennial era) |
| Budget-in-Brief | 12 | FY 2002-04 → FY 2025-26 | 1–2 page public summary |
| Capital Improvement Program | 2 | FY 2006-08, FY 2025-26 | Standalone CIP (other years: embedded in operating budget) |
| Annual Financial Report / ACFR | 30 | FY 2001 → FY 2025 | Audited year-end financials; pre-FY 2010 split into 3 PDFs (Intro / Financial / Statistical) |
| Single Audit Report | 24 | FY 2002 → FY 2025 | Federal award compliance |
| Measure X Fund Report | 7 | FY 2019 → FY 2025 | Dedicated sales-tax fund audit (Measure X passed Nov 2018) |
| Quarterly Financial Status Reports | 25 | FY 2019-20 → FY 2025-26 Q1 | Q1–Q4 per year (pre-FY 2019 quarterlies not on the portal) |
| Sales Tax Newsletters | 23 | CY 2020 → CY 2025 Q3 | HdL-produced quarterly sales-tax analysis |
| Component Unit Financial Statements | 18 | 2020 → 2025 | Housing Authority / Harbor District audits |

**Total:** 189 PDFs, ~10,670 pages, ~2.26 million words of primary text.
The full inventory lives in [inventory.json](inventory.json); every PDF is under
[pdfs/](pdfs/), with plain-text extracts in [text/](text/). The narrative
sections (§3 onward) focus on FY 2019-20 and later, since that's where the
structured data is fully parsed; pre-FY 2019 is available as raw PDFs + text
for direct inspection.

---

## 2. Top-line trajectory

General Fund (including the Measure X sales-tax fund), in millions of dollars:

| FY | Rev. Adopted | Rev. Actual | Exp. Adopted | Exp. Actual | Adopted surplus/(deficit) |
|---|---:|---:|---:|---:|---:|
| 2019-20 | $173.48 | $186.57 | $172.86 | $183.68 | +$0.62 |
| 2020-21 | $170.85 | $192.81 | $170.16 | $168.13 | +$0.69 |
| 2021-22 | $187.40 | $213.63 | $188.18 | $205.83 | (−$0.78) |
| 2022-23 | $207.46 | $233.74 | $208.89 | $229.70 | (−$1.43) |
| 2023-24 | $223.45 | $247.49 | $223.80 | $201.97 | (−$0.35) |
| 2024-25 | $236.36 | — | $246.39 | — | (−$10.03) |
| 2025-26 | $252.57 | — | $230.16 | — | +$22.41 |

Sources: each row's *Adopted* columns come from that FY's own adopted budget
summary schedule; *Actual* columns are pulled from the two-prior-year historical
columns in subsequent adopted budgets. FY 2024-25 actuals are not yet closed;
FY 2023-24 actuals have been partially reported.

Over the six fiscal years from FY 2019-20 to FY 2025-26 the adopted GF budget
grew from **$172.9 M to $230.2 M**, roughly **+33 %** nominal growth — in an
environment where CPI cumulatively rose about 24 %, so real growth was modest.

---

## 3. Year-by-year history

### FY 2019-20 — "Measure X arrives, Healthy City Reserve at $20.4M"

*Adopted: rev $173.48 M / exp $172.86 M.*

The FY 2019-20 budget was the first to include revenue from **Measure X**, the
**½-cent local sales & use tax** voters approved in November 2018. Measure X was
a seven-year temporary tax (sunsetting 2026) earmarked for general city services.
In the FY 2019-20 adopted budget, Measure X contributed **$13.89 M in new
revenue**, with a matching $13.89 M in Measure X-funded projects authorized.

The budget included **$1.1 M in one-time funding** for initiatives including
an Arts Master Plan allotment, a social worker for housing, fire plan-check
services, police equipment, and parking license-plate readers. Reserves were
healthy: the Healthy City Reserve (policy minimum 12% of operating expenditures)
stood at **$20.4 M** as of July 1, 2019.

Narrative tone: cautious optimism. The City Manager's transmittal letter warned
of "potential for deficits in future years as outlined in the City's Five-Year
Forecast."

### FY 2020-21 — COVID-19 response

*Adopted: rev $170.85 M / exp $170.16 M. Amended mid-year. Actual rev $192.81 M.*

The FY 2020-21 budget was adopted in June 2020 as COVID-19 was hammering city
revenues. The Budget-in-Brief explicitly stated: *"The COVID-19 pandemic and
resulting economic changes impacted all major revenue categories. As a result,
the revenue forecasted in January has been reduced by $8.89M…"*

Concrete cost-containment measures in the adopted budget:

- Freeze on recruitment and replacement hiring
- Freeze on employee travel
- **10% reduction in M&O (maintenance & operations) budgets**
- Increased contracting where cheaper than in-house

The budget was balanced **without using one-time money**. Transient Occupancy
Tax (TOT) — the most tourism-sensitive revenue — was projected to fall from
$8.34M adopted the prior year to **$5.90M** for FY 2020-21, a 29 % cut.

**What actually happened:** revenue came in at $192.8 M (vs. $170.9 M adopted),
well above the pandemic-era forecast. TOT actually recovered to **$9.28 M** by
year-end — higher than the pre-pandemic forecast.

### FY 2021-22 — "The City is weathering the pandemic"

*Adopted: rev $187.40 M / exp $188.18 M. Actual rev $213.63 M / exp $205.83 M.*

The FY 2021-22 Budget-in-Brief's executive summary: *"The revenue projections
were conservatively estimated based on the best available information and
uncertainty about the COVID-19 pandemic's impact… With three additional months
of financial data available, it is clear that the City is weathering the
pandemic in a stronger financial position than anticipated and sales tax
revenue continues to be strong."*

Key moves:

- **Restoration of the 10 % M&O budget cuts** instituted the prior year
- Compared to the pre-COVID FY 2019-20 adopted budget, expenditures increased
  $12.79 M (of which $11.23 M was personnel, $1.56 M M&O)
- Adopted budget again used **no one-time money**

Actuals dramatically over-performed adopted: revenue beat budget by $26 M,
expenditures beat (came in over) budget by $17 M.

### FY 2022-23 — Inflation shock, department reorganization

*Adopted: rev $207.46 M / exp $208.89 M. Actual rev $233.74 M / exp $229.70 M.*

The FY 2022-23 budget was adopted in a **9.1 % CPI environment** — the highest
inflation in 40 years. The Budget-in-Brief acknowledged the challenge: *"To
address inflation, staff added a 5% cost of living to the Maintenance and
Operations expenses."*

Major **organizational changes** visible in the FTE tables:

- **Parks and Recreation Department created** (23.0 FTE), split out from
  previously combined structure
- Public Works grew **+23 FTE** (95.4 → 118.7), absorbing some functions
- Neighborhood Services contracted sharply **−21 FTE** (46.0 → 25.0)
- Measure X staffing **tripled**: 19.6 → 47.6 FTE

Revenue growth was strong: property tax budgeted at $79.79 M (+7 % y/y),
sales & use tax at $27.55 M (+14 % y/y), TOT at $11.00 M (+55 % y/y).

The budget ran a small **−$1.43 M adopted deficit** — the first overtly
structurally-unbalanced year in the series.

### FY 2023-24 — Structural deficit narrows

*Adopted: rev $223.45 M / exp $223.80 M. Partial actual rev $247.49 M.*

Executive summary: *"The General Fund, approximately 36 percent of the total
operating appropriations, supports the majority of City services. Revenues,
projected at $204.02M were conservatively estimated… Revenue growth is primarily
attributed to strong property tax, sales tax and transient occupancy tax."*

The budget cited use of **HdL Companies** (the City's sales-tax consultant)
for revenue forecasts. GF expenditures of $203.29 M included a $0.95 M transfer
to CIP. A **3.5 % cost-of-living increase** was applied to M&O (down from 5 % the
prior year as inflation cooled).

Fire grew materially (152.4 FTE, up 13 from the prior year), Library added
3 FTE (28 → 31), and Measure X continued growing (47.6 → 57.6 FTE).

### FY 2024-25 — Largest adopted deficit in the series

*Adopted: rev $236.36 M / exp $246.39 M. Adopted deficit $10.03 M.*

Executive summary: *"The General Fund expenditures budget is $218.71M; $215.28M
are ongoing expenditures and $3.43M are one-time costs from reserves. Therefore,
it is a structurally balanced budget."* Note: those figures refer to the General
Fund excluding Measure X; the total including Measure X had the larger headline
deficit shown above.

Context from the Budget-in-Brief: *"Efficiently managing the City's increasing
CalPERS costs remains a top priority. The City has been taking proactive measures
to mitigate its rising cost."* CalPERS pension costs are an emerging pressure.

Notable movement: **Police FTE dropped from 324 to 303** in FY 2023-24 and held
at 304 in FY 2024-25, one of the larger FTE shifts of the decade.

### FY 2025-26 — Back to structural surplus

*Adopted: rev $252.57 M / exp $230.16 M. Budgeted surplus: $22.41 M.*

The FY 2025-26 adopted budget headline: GF revenue of $252.6 M vs. GF
expenditures of $234.5 M (including $4.4 M in one-time/reserves draws), for a
structural surplus. Measure X revenue is budgeted at $18.80 M with $17.97 M in
Measure X-funded expenditures — the Measure X sunset (per the 2018 ballot
measure, seven-year term) lands in this budget year, and the **FY 2025-26 CIP
was separately published** for the first time in the series.

Total FTE: **1,064 (plus 405 hourly, grand total 1,469)**. Fire Department
position strength: 152 FTE, the highest in the series.

---

## 4. Revenue trends

General Fund revenue by major category, actuals in $ millions:

| Category | FY19-20 | FY20-21 | FY21-22 | FY22-23 | FY23-24 | 4-yr Δ |
|---|---:|---:|---:|---:|---:|---:|
| Property Taxes | $68.4 | $72.7 | $76.7 | $82.3 | $87.4 | **+28%** |
| Sales & Use Taxes | $23.8 | $27.0 | $30.8 | $31.8 | $31.6 | **+33%** |
| Transient Occupancy Tax | $7.4 | $9.3 | $14.8 | $16.4 | $17.9 | **+142%** |
| Measure X (½-cent local sales tax) | $13.2 | $16.4 | $18.2 | $18.8 | $18.7 | **+42%** |

**Key takeaways:**

1. **Property tax is the reliable workhorse**, growing steadily at ~6 %/year.
   This is capped by Prop 13's 2 % CPI rule, so the growth comes primarily from
   reassessments on property sales.
2. **Transient Occupancy Tax more than doubled** post-pandemic, reflecting
   Oceanside's tourism-economy pivot and hotel development. This is now
   ~7–8 % of GF revenue, up from ~4 %.
3. **Sales & use tax plateaued in FY 2023-24** — the first visible
   post-pandemic softening. The 23 quarterly sales-tax newsletters from
   HdL in the corpus track this in detail.
4. **Measure X growth mirrors general sales tax** but is scaled to the
   ½-cent rate; once its seven-year sunset lands in late 2025, the City
   would lose this revenue stream unless voters renew the tax.

---

## 5. Expenditure and staffing trends

Adopted General Fund expenditures by major department ($M):

| Department | FY22-23 | FY23-24 | FY24-25 | FY25-26 | 4-yr Δ |
|---|---:|---:|---:|---:|---:|
| Police | $72.8 | $75.1 | $79.0 | $78.7 | +8% |
| Fire | $40.1 | $48.1 | $51.3 | $54.4 | **+36%** |
| Public Works | $19.7 | $22.9 | $25.0 | $25.9 | +31% |
| Development Services | $14.2 | $15.3 | $17.7 | $18.8 | +32% |
| Library | $6.2 | $6.6 | $6.9 | $7.4 | +19% |
| Neighborhood Services | $2.2 | $2.5 | $2.9 | $2.5 | +14% |

**Fire is the standout.** The +36 % four-year growth likely reflects a mix of
(a) new fire stations/apparatus, (b) ambulance-transport expansion (see
Ambulance Billing revenue rising from $5.3 M actual FY 19-20 to $10.3 M actual
FY 23-24), and (c) wage pressure in a tight labor market for firefighter/
paramedic staff.

FTE by department, since FY 2019-20:

| Department | FY19-20 | FY20-21 | FY21-22 | FY22-23 | FY23-24 | FY24-25 | FY25-26 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Police | 325.0 | 326.0 | 324.0 | 324.0 | **303.0** | 304.0 | 304.0 |
| Fire | 125.4 | 125.4 | 129.4 | 139.4 | 152.4 | 151.0 | 152.0 |
| Public Works | 95.8 | 95.4 | 95.4 | **118.7** | 119.8 | 123.0 | 125.0 |
| Development Services | 58.0 | 58.6 | 73.7 | 77.8 | 76.5 | 77.0 | 76.0 |
| Water Utilities | 149.9 | 149.9 | 162.4 | 163.2 | 165.2 | 170.0 | 172.0 |
| Measure X | 18.6 | 19.6 | 19.6 | **47.6** | 57.6 | 40.6 | 44.6 |
| Parks and Recreation | — | — | — | **23.0** | 24.0 | 24.0 | 26.0 |
| Neighborhood Services | 60.0 | 59.0 | 46.0 | **25.0** | 27.0 | 27.0 | 29.0 |
| Library | 26.0 | 26.0 | 27.0 | 28.0 | 31.0 | 31.0 | 31.0 |
| **Total (General Fund)** | **984** | **985** | **1,002** | **1,056** | **1,061** | **1,052** | **1,064** |

Bold cells mark meaningful structural shifts:

- **FY 2022-23 department reorganization** — Parks & Rec spun out of
  Neighborhood Services (which shed 21 FTE); Public Works absorbed 23 FTE;
  Measure X more than doubled its staff count.
- **FY 2023-24 Police drop** — Lost 21 FTE from 324 → 303. The FY 2023-24
  adopted budget's executive summary does not directly explain this; the
  Department-level narrative pages in that budget would be the primary source.
- **Measure X personnel spike in FY 2023-24 (57.6 FTE)** — Coincides with the
  full ramp of Measure X-funded programs before the sunset approach.

---

## 6. Measure X

Voters passed Measure X in November 2018, a **½-cent temporary local sales &
use tax for seven years** effective April 2019. The tax was designed to
sunset; as of the FY 2025-26 adopted budget (which covers July 2025 –
June 2026), the expiration is imminent.

Measure X's audited financial footprint (from the 7 annual Measure X Fund
reports), combined Operating + Capital funds:

| FY end | Tax Revenue | Capital Outlay | Fund Balance (ending) |
|---|---:|---:|---:|
| 6/30/2019 (partial yr) | $2.7M | — | — |
| 6/30/2020 | $13.2M | $1.0M | $12.7M |
| 6/30/2021 | $16.4M | $2.0M | $21.3M |
| 6/30/2022 | $18.2M | $2.8M | **$30.3M** |
| 6/30/2023 | $18.8M | $8.6M | $29.0M |
| 6/30/2024 | $18.7M | $15.4M | $24.0M |
| 6/30/2025 | $18.8M | $6.5M | $26.9M |

The audit data tells a clear story: **Measure X revenue stabilized around
$18.5–19M/year starting FY 2022, but capital deployment lagged**. The fund
built up a $30.3M balance by mid-2022 as revenue outpaced spending. Then
capital outlay ramped from $2.8M (FY22) → $8.6M (FY23) → **$15.4M (FY24)**
— the year the City visibly pushed projects out the door — drawing the
balance down to $24M. FY25 saw capital fall back to $6.5M as the peak-project
backlog cleared. The $26.9M ending balance at 6/30/2025 is the "runway"
available as the tax sunsets.

The **2018 ballot language** structured Measure X as General Fund revenue
(not earmarked). Per the audits, the City has consistently transferred
Measure X operating surplus into a capital fund for council-designated
infrastructure projects; that internal transfer is why the capital outlay
grew independently of annual revenue.

---

## 7. Government-wide financial position (from ACFRs)

The audited **Statement of Net Position** gives the city's total economic
resources minus obligations. Total Net Position (governmental + business-type
activities combined):

| 6/30 | Total Net Position |
|---|---:|
| 2020 | $995.2M |
| 2023 | $1,195.0M |
| 2024 | $1,294.6M |
| 2025 | $1,354.6M |

Net Position grew **+36 % over 5 years** — the city's balance sheet is
healthier than the operating-surplus story alone suggests. A big contributor
is the capital-asset build via CIP + Measure X spending, net of depreciation.

(FY 2019 and FY 2021 Net Position totals did not fully extract from those
ACFRs' 3-column tables — see Data-quality notes.)

**General Fund balance** (the key liquidity metric for day-to-day
operations), from the audited Balance Sheet - Governmental Funds:

| 6/30 | GF Fund Balance Total | Notes |
|---|---:|---|
| 2019 | $79.6M | |
| 2020 | $83.4M | COVID onset — balance held |
| 2021 | — | Only total-all-governmental-funds ($183.9M) extracted |
| 2023 | $118.9M | |
| 2024 | $142.8M | +20 % y/y, reflects FY23-24 $18.8M Q4 surplus |
| 2025 | $142.6M | Essentially flat — drawdown offsets surplus |

The GF balance grew roughly **$60M** from FY 2019 → FY 2024. Most of the
growth came in the two strong surplus years (FY 2020-21, FY 2023-24).

---

## 8. Quarterly fiscal trajectory

From the 22 quarterly financial status reports staff presented to Council,
here are the reported end-of-year General Fund surpluses (Q4 reports):

| FY | Q4 reported GF surplus |
|---|---:|
| 2020-21 | $19.4M — "strong recovery, pandemic forecasts proved conservative" |
| 2021-22 | $1.4M — "tight year, M&O restoration used reserve" |
| 2022-23 | $9.7M — "higher-than-expected property/sales/TOT revenue" |
| 2023-24 | $18.8M — "interest earnings ~4 %, catch-up ambulance billing" |

Per Council Policy 200-13, **50 % of year-end surpluses go to reducing
long-term unfunded liabilities** (CalPERS / OPEB). That policy puts
mechanical downward pressure on the GF balance growth rate even in good
years — you see roughly half of the surpluses turning into pension paydowns
rather than reserve accumulation.

---

## 9. Capital Improvement Program

The standalone **FY 2025-26 CIP Budget Book** (33 MB, 311 pages) is the
first such document separately published since at least 2016. Prior CIPs
were embedded as chapters in the operating budget. The FY 2025-26 CIP
presents a 5-year plan totaling roughly **$638M across 11 programs**, with
$203M budgeted for FY 2025-26:

| Program (fund) | FY25-26 | 5-yr total |
|---|---:|---:|
| Sewer (722 + 726) | $47.3M | $280.7M |
| Water (712 + 715) | $31.8M | $125.3M |
| Misc City Projects (501) | $35.7M | $46.3M |
| Measure X | $29.4M | $64.7M |
| TransNet (212) | $15.0M | $35.2M |
| Thoroughfare (561) | $10.9M | $12.1M |
| Parks (598) | $10.3M | $11.4M |
| Muni Buildings (503 + 581) | $7.3M | $11.9M |
| SB1-RMRA Gas Tax (265) | $7.1M | $23.2M |
| Citywide Drainage (516) | $5.4M | $7.4M |
| Thoroughfare/Signals (562) | $2.5M | $6.1M |

**Sewer dominates** the 5-year capital plan — $280.7M reflects the
centralization of wastewater infrastructure mentioned in the FY 2025-26
executive summary. The City is spending aggressively now to replace aging
systems. Water is the second-largest program at $125M.

The narrative summary separately states the "$213.5 million plan" —
this appears to reference the non-enterprise portion (excluding Water +
Sewer Enterprise Funds), which would net out to roughly that figure.

---

## 10. Data-quality notes

The structured tables in `budget_history.sqlite` are derived from the
summary schedules on each document's authoritative pages. The
scraper/parser trades perfect fidelity for broad coverage across 102 PDFs.
Known caveats:

1. **Cross-source reconciliation.** Each adopted budget reports 2 years of
   historical Actuals + 2 years of Adopted figures. The same fiscal year
   therefore appears in multiple source documents, sometimes with minor
   numeric drift (mid-year restatements, rounding). All rows are retained;
   the `gf_authoritative` view keeps the freshest source.
2. **CID-shift font encoding in some ACFRs.** A wide range of ACFRs/AFRs
   (roughly FY 2010 through FY 2022) use a custom font whose glyph
   indices are off-by-29 from Unicode — "CITY" extracts as "&,7<" for the
   Range-A form, and digits/punctuation in table bodies extract as control
   chars (`\x03`, `\x07`, `\x13`-`\x1c`) for the Range-B form.
   `scripts/decode_cid_shift.py` reverses both ranges (as of 2026-04-18):
   Range A on fully-garbled pages (whole-page heuristic), Range B
   unconditionally (safe — control chars never appear in clean text).
   Mixed-content pages (tables with a Range-A garbled title AND clean body
   content) still have garbled titles; parsers anchor on body markers
   instead. Remaining visible impacts:
   - FY 2021 ACFR GF Fund Balance: only the all-governmental-funds total
     ($183.9M) extracted, not the 5-way breakdown (Restricted / Committed
     / Assigned / etc.)
   - FY 2022 ACFR: Balance Sheet extracted only via reconciliation
     fallback ($1 row); no Net Position rows.

3. **Pre-FY 2010 audit format.** AFRs from FY 2001 through FY 2009 are
   split into three separate PDFs per year (Introductory / Financial /
   Statistical sections). The decoder parser processes only the Financial
   Section — the other two are inventoried but yield 0 structured fields.
   Also, FY 2001–FY 2009 use GASB's pre-GASB 63 terminology ("Statement of
   Net Assets" rather than "Statement of Net Position") and a different
   column-major layout; current decoder coverage for those years is
   partial (activities only, no capital assets).

4. **Image-only AFRs.** FY 2001, 2003, 2004, 2006, and 2007 AFR Financial
   Sections are scanned PDFs (one big image per page, no embedded text).
   pymupdf extracts 0 words for these. OCR via Tesseract would be needed
   to unlock them; deferred as a follow-up.
3. **ACFR actuals vs. budget actuals.** The ACFR's "General Fund balance"
   (from the Balance Sheet) reflects the full accounting fund balance.
   The budget document's "actuals" reflect operating results. These differ
   because the balance includes accumulated surplus/deficit across years,
   while operating actuals are annual flows.
4. **Measure X Fund Report FY2019 only has a single-column total** — the
   FY 2019 audit was structured differently (pre-dates the 3-column
   Operating/Capital/Total layout that became standard in FY 2020+).
5. **Quarterly report Q1–Q3 figures are YTD, not annualized.** The
   `quarterly_status` table's `actual_gf_revenue` at Q1 represents
   3-month year-to-date collections, not full-year actuals. Only the Q4
   numbers are full-year.
6. **CIP coverage is single-year.** Only the FY 2025-26 CIP Budget Book
   was published as a standalone document; `cip_program` therefore only
   has that 5-year plan. Prior-year CIPs are embedded in the operating
   budgets and not structured.

For authoritative figures on any line item, the workflow is:

```sql
-- Find the document + page containing a given year's GF revenue table
SELECT d.title, d.local_path, g.source_page
FROM gf_line_items g JOIN documents d ON d.doc_id = g.source_doc_id
WHERE g.fiscal_year = 'FY2023-2024' AND g.basis = 'actual'
  AND g.flow = 'revenue' AND g.category = 'Grand Total';

-- Cross-check ACFR fund balance
SELECT fiscal_year, line_item, amount_usd
FROM acfr_gf_balance
WHERE fiscal_year = 'FY2024' ORDER BY line_item;

-- Measure X fund trajectory
SELECT fiscal_year,
  SUM(CASE WHEN line_item='Taxes' AND fund_type='Total' THEN amount_usd END) AS taxes,
  SUM(CASE WHEN line_item='Capital Outlay' AND fund_type='Total' THEN amount_usd END) AS capital,
  SUM(CASE WHEN line_item='Fund Balance Ending' AND fund_type='Total' THEN amount_usd END) AS fb_end
FROM measure_x GROUP BY fiscal_year ORDER BY fiscal_year;
```
