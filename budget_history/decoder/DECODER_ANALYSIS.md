# Strong Towns Finance Decoder — Oceanside Analysis

Worksheet applied: `Strong Towns Finance Decoder Worksheet - US 1.0.1.xlsx`.
Raw data: `data/budget_history/budget_history.sqlite` (tables:
`acfr_decoder_inputs`, `decoder_metrics`).
Populated output: [`oceanside_decoder_output.xlsx`](oceanside_decoder_output.xlsx).

## Results: the 7 metrics

All 7 metrics computed for **FY 2024** and **FY 2025** (with FY 2023 partial
— missing Total Revenues denominator because FY 2022 Net Position didn't
extract cleanly).

| # | Metric | Type | FY 2023 | FY 2024 | FY 2025 |
|---|---|---|---:|---:|---:|
| 1 | Net Financial Position | Sustainability | **$159.0 M** | **$204.6 M** | **$285.7 M** |
| 2 | Financial Assets-to-Liabilities | Sustainability | 1.26× | 1.33× | **1.51×** |
| 3 | Total Assets-to-Liabilities | Sustainability | 2.97× | 3.11× | **3.39×** |
| 4 | Net Debt-to-Total Revenues | Sustainability | 0 %* | 0 %* | 0 %* |
| 5 | Interest-to-Total Revenues | Flexibility | —† | 0.28 % | 0.37 % |
| 6 | Net Book-to-Cost of TCA | Flexibility | **37.2 %** | **35.4 %** | **36.7 %** |
| 7 | Govt Transfers-to-Total Revenues | Vulnerability | —† | 15.6 % | 15.4 % |

\* Not applicable — Net Financial Position is positive, so there is no net debt to measure.
† FY 2023 Total Revenues couldn't be derived because FY 2022 Net Position didn't extract (CID-shift).

### What each metric says about Oceanside

- **Net Financial Position (#1)** — The city's most conservative solvency
  indicator: liquid assets minus all obligations. Positive and **growing
  +$127 M over 2 years** (from $159 M to $286 M). Strong Towns considers a
  positive Net FP a baseline requirement; Oceanside clears it comfortably.
- **Financial Assets-to-Liabilities (#2)** — Can Oceanside cover all its
  obligations from non-capital assets? Moved from 1.26× → 1.33× → 1.51×.
  Above 1.0× is healthy; trending up is ideal.
- **Total Assets-to-Liabilities (#3)** — Broadest balance-sheet ratio. 3×
  range is superficially strong but Strong Towns notes this is the *least*
  informative metric because infrastructure can't be sold to pay debts.
- **Net Debt-to-Revenues (#4)** — Only applies when Net FP is negative;
  Oceanside has never hit that, so this metric is moot here.
- **Interest-to-Revenues (#5)** — Below 0.5 %. Oceanside's debt-service
  burden is negligible. Main fixed-rate debt: 2015 Taxable Pension
  Obligation Refunding Bonds ($32 M original issuance, 1.4–4.275 % rates).
- **Net Book-to-Cost of TCA (#6)** — **The infrastructure-aging indicator
  Strong Towns specifically emphasizes.** At ~36 %, Oceanside's capital
  assets are roughly 64 % depreciated on a gross-cost basis. Strong Towns
  would read this as the city being "two-thirds of the way through" the
  useful life of its infrastructure on average. This is normal for a city
  of Oceanside's age (incorporated 1888) but it does underscore the
  importance of the $638 M 5-year CIP plan (see `../HISTORY.md`) — the
  replacement bill comes due.
- **Govt Transfers-to-Revenues (#7)** — ~15 %. Moderate grant dependency.
  Not over-reliant on state/federal transfers, but they're meaningful.

### The trend story

Between FY 2023 and FY 2025, **every sustainability metric that we can
track improved**:

| Metric | FY 2023 → FY 2025 change |
|---|---|
| Net Financial Position | $159.0 M → $285.7 M (+80 %) |
| Financial Assets-to-Liabilities | 1.26× → 1.51× (+20 %) |
| Total Assets-to-Liabilities | 2.97× → 3.39× (+14 %) |
| Net Book-to-Cost of TCA | 37.2 % → 36.7 % (−1.4 pp, roughly flat) |

Net Book-to-Cost of TCA barely moving (37 → 36 → 37 %) means new capital
investment is **roughly keeping pace with depreciation** on average — neither
meaningfully improving nor worsening the infrastructure-aging picture. This
matches the FY 2025-26 CIP's stated emphasis on maintenance and replacement
of existing systems (sewer, water, streets) rather than greenfield expansion.

## Full populated input worksheet

Row numbers match the Decoder worksheet's Input sheet:

| Row | Decoder Line | FY 2023 | FY 2024 | FY 2025 |
|---:|---|---:|---:|---:|
| 6 | Current Assets (derived) | $766.8 M | $819.5 M | $851.6 M |
| 7 | Capital Assets (derived) | $931.6 M | $980.3 M | $980.4 M |
| 8 | **Total Assets** | $1,698.3 M | $1,799.8 M | $1,832.0 M |
| 9 | Deferred Outflows | $104.4 M | $109.7 M | $88.4 M |
| 10 | Liabilities | $531.5 M | $542.0 M | $538.4 M |
| 11 | Deferred Inflows | $76.2 M | $72.8 M | $27.4 M |
| 12 | **Total Liabilities** (10 + 11) | $607.7 M | $614.9 M | $565.8 M |
| 13 | **Net Position** (8 + 9 − 12) | $1,195.0 M | $1,294.6 M | $1,354.6 M |
| 14 | Total Revenues (derived) | — | $519.9 M | $542.5 M |
| 15 | Operating Grants & Contributions | $61.2 M | $75.6 M | $78.7 M |
| 16 | Capital Grants & Contributions | $4.2 M | $5.6 M | $4.8 M |
| 18 | Interest Charges | $1.5 M | $1.5 M | $2.0 M |
| 19 | Net Book TCA | $673.5 M | $669.2 M | $708.4 M |
| 20–25 | Gross TCA components (gov/biz × not-dep/dep) | all extracted | all extracted | all extracted |
| 26 | **Total Cost of TCA** | $1,811.4 M | $1,890.5 M | $1,929.0 M |

Reconciliation check: Net Position (row 13) equals `acfr_net_position.np_total`
(activity='Total') for all three years. ✓

## Where the numbers came from

| Input | Source |
|---|---|
| Current Assets | Derived: `total_assets` − `capital_assets` |
| Capital Assets | Statement of Net Position: `cap_not_dep_total` + `cap_net_dep_total` |
| Total Assets, Def. Outflows, Liabilities, Def. Inflows | `acfr_net_position` table |
| Total Revenues | Derived: Change-in-Net-Position + Total Expenses (gov + biz) |
| Operating/Capital Grants | Statement of Activities "Total governmental activities" row, columns 3 and 4 |
| Interest Charges | Statement of Activities, "Interest on long-term debt" (FY19-24) / "Interest expense and fiscal charges" (FY25) |
| Net Book TCA | Statement of Net Position, "Capital assets, net of accumulated depreciation/amortization", Total column |
| Gross TCA components | **Capital Assets Note (Note 7)** rollforward schedules — Balance-End column, Total capital assets rows. Extraction uses the same +29 CID-shift as the main ACFR pages but on the `\x01`–`\x20` control-char range (see note below) |

### The second CID-shift variant

While extracting Note 7 we discovered a **second CID-shift variant** affecting
the Notes sections of FY 2019–FY 2024 ACFRs: the font maps digits (0–9) and
space to the control-character range `\x13`–`\x1c` and `\x03`, respectively.
This is the *same* +29 shift as the earlier-documented `&,7<` → `CITY`
issue, just applied to a different source range:

| Raw char | ord | +29 | Decoded |
|---|---:|---:|---|
| `\x03` | 3 | 32 | space |
| `\x13` | 19 | 48 | `0` |
| `\x14` | 20 | 49 | `1` |
| ... | ... | ... | ... |
| `\x1c` | 28 | 57 | `9` |
| `\x0f` | 15 | 44 | `,` |

The existing `decode_cid_shift.py` only handles the printable-ASCII range
(33–97); the Notes pages need the control-char range (1–31) handled too.
For this analysis, the Note 7 extraction applied the shift directly in
an ad-hoc script. Folding this into `decode_cid_shift.py` is a TODO (would
unblock FY 2019–FY 2022 if combined with layout-aware table parsing).

## Cross-validation

The **Total Revenues = Change in NP + Total Expenses** derivation can be
validated against the direct Statement of Activities value where we have
both:

| FY | Derived TR | Program Rev. | Gen. Rev. | Sum | Match |
|---|---:|---:|---:|---:|---|
| FY 2024 | $519.9 M | $288.1 M | $231.8 M | $519.9 M | ✓ |

Measure X tax revenue in `measure_x.Taxes` (audited) = GF Measure X actual
in `gf_line_items` for every overlapping year (FY 2020 → FY 2024) to the
penny. The decoder pipeline shares source data with these cross-validated
tables.

## SQL convenience

```sql
-- Time series of the 7 metrics
SELECT fiscal_year,
       metric_1_net_financial_position,
       metric_2_financial_assets_to_liab,
       metric_3_total_assets_to_liab,
       metric_4_net_debt_to_revenues,
       metric_5_interest_to_revenues,
       metric_6_net_book_to_cost_tca,
       metric_7_transfers_to_revenues
FROM decoder_metrics
ORDER BY fiscal_year;

-- Drill down: all 11 inputs for a specific year
SELECT * FROM decoder_metrics WHERE fiscal_year = 'FY2024';
SELECT * FROM acfr_decoder_inputs WHERE fiscal_year = 'FY2024';
```

## Remaining TODOs

- [ ] **FY 2019–FY 2022 metrics** — Require fixing the `acfr_net_position`
      extraction for those years. The underlying issue is a mix of CID-shifted
      text + column-major layout where pymupdf renders labels and values in
      separate text blocks. Two paths:
      1. Use `page.get_text("rawdict")` and reconstruct the table from
         per-character x/y coordinates (slower but precise).
      2. OCR each PDF page as an image via Tesseract (simple fallback).
- [ ] **FY 2023 Total Revenues** — unblocked only by fixing FY 2022 `np_total`
      (since TR is derived from np delta + expenses).
- [ ] **Fold control-char CID-shift into `decode_cid_shift.py`** —
      currently the Note 7 extraction applies the shift ad-hoc; extending
      the main decoder to cover both 33–97 and 1–31 ranges would make the
      pipeline clean again.
- [ ] **Populate the 7 PNG chart templates** in
      `Finance Decoder Shareable Template/` with the computed metrics.
      Currently only 2 clean data points per chart (FY 2024 + FY 2025);
      Strong Towns conventions prefer 5+ years. Fixing the earlier-year
      gap unlocks this.

## Bottom line

**Oceanside's Strong Towns Decoder metrics for FY 2024–FY 2025 paint a
healthy picture**: positive and growing Net Financial Position, improving
asset coverage ratios, negligible interest burden, moderate grant
dependency, and infrastructure aging neither accelerating nor reversing.
The city is **neither distressed nor building obvious hidden liabilities**,
at least over the 2-year window we can measure cleanly.

The one asterisk: Net Book-to-Cost of TCA at ~36 % means the city is already
2/3 through the useful life of its capital stock on a gross-cost basis.
This is normal for a mature city but reinforces why the FY 2025-26
Capital Improvement Program's $638 M 5-year plan — 44 % of it sewer
($281 M) — is appropriately sized. The replacement bills are coming due;
Oceanside's balance sheet currently has the capacity to fund them without
distress, but only as long as revenue growth holds.
