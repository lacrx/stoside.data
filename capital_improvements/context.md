# Oceanside Capital Improvements — Context

## Goals

1. **Active transportation spending.** How effectively are CIP funds used on active transportation (bike, pedestrian, safe-routes, trails, ADA, traffic calming, complete streets)?

2. **Car-infrastructure spending vs the true cost of maintaining it — backlog accumulation framing.** How big is the cumulative gap between what Oceanside has spent on car-infrastructure upkeep and the **true cost** of keeping its roads in steady-state condition?

   **Headline (SCS pavement + essential components, state-calibrated):** Cumulative deferred-maintenance backlog reaches **~$1.12B by FY2030** when benchmarked against the Save California Streets 2022 per-lane-mile needs for San Diego County. Under the City's own (narrower) overlay+slurry-only methodology the backlog is **$303M**; extending the state lens to include active transportation raises it to **$1.24B**.

   **Current model output** ([pavement_backlog.png](pavement_backlog.png), [pavement_backlog_model.json](pavement_backlog_model.json), [backlog_model.py](backlog_model.py)):
   - Network: **1,404 lane-miles** (407 centerline × 3.45 lanes avg), computed directly from the [PCI/Oceanside PCI.xlsx](PCI/Oceanside%20PCI.xlsx) workbook's Raw PCI sheet (4,311 City-owned segments)
   - Current mean PCI: **60** — *below* SCS's statewide mean of 65 ("at risk, positioned for rapid decline") and far below San Diego County's area-weighted 71 ("good"). The county average is flattered by large well-maintained cities; Oceanside is one of the drag terms.
   - **True annual cost** scenarios:
     - **City methodology** (overlay + slurry only, matches the FY20-21 calc in the PCI workbook's Breakdown sheet): **$20.0M/yr**
     - **SCS pavement only** (SD County 10-year need of $4.57B ÷ 18,852 lane-mi → $24.2K/lane-mi × Oceanside): **$34.0M/yr**
     - **SCS pavement + essential components** — **RECOMMENDED HEADLINE** (adds storm drains, curb/gutter, sidewalks, curb ramps, signals, streetlights, signs, ADA, NPDES): **$54.0M/yr**
     - **SCS full transportation** (+ active transportation, i.e. bike + ped facilities excluding sidewalks): **$58.9M/yr**
     - *Industry life-cycle scenarios (prior headlines, kept for comparison):* low $52.7M, mid $75.3M, high $97.9M. These use higher reconstruction unit costs ($1.5M/lane-mi) that bundle curb/drainage/ADA into pavement — functionally equivalent to the SCS pavement+EC combination.
   - **Actual annual spend** on car maintenance: ~$5M FY2006-11, ~$7M baseline through FY2019, ~$10-12M during Measure X era (FY2020-25), dropping back to **~$7.4M/year in the adopted FY25-30 plan**
   - **Cumulative deferred-maintenance backlog by FY2030:** $303M (city) / $639M (SCS pavement only) / **$1.12B (SCS pavement+EC, headline)** / $1.24B (SCS full transport) / $1.09B–$2.17B (industry low/mid/high)

   **Calibration anchors:**
   - **City-own FY20-21** ([PCI workbook Breakdown sheet](PCI/Oceanside%20PCI.xlsx)): actual spend $5.59M vs investment needed $20.05M → **$14.45M shortfall (72% underfunded)**. The `city_overlay_slurry` scenario matches exactly; serves as a conservative lower bound.
   - **Save California Streets 2022** ([state report](https://savecaliforniastreets.org/wp-content/uploads/2023/05/Statewide-Needs-2022-FINAL.pdf), local copy at [raw_pdfs/save_ca_streets_2022.pdf](raw_pdfs/save_ca_streets_2022.pdf), full-text extract at [raw_pdfs/scs_text_all.txt](raw_pdfs/scs_text_all.txt)) — this is the SB1-mandated biennial needs assessment cities submit to in exchange for state funding. San Diego County 10-year pavement need $4.57B / essential-components $2.68B / lane-miles 18,852 ⇒ $24.2K/lane-mi-yr pavement, $14.2K/lane-mi-yr essential components. Applied to Oceanside's 1,404 lane-miles, this frames both the headline annual need and the backlog.

   **New SCS-derived heuristics** (all in constant 2022 $, see `backlog_model.py` for full data):
   - **Unit costs ($/sq-yd, Table 2.2)**: preventive maintenance $6.86 major / $6.41 local; thin HMA overlay $26.86 / $26.02; thick HMA overlay $43.61 / $41.66; reconstruction $99.04 / $84.39.
   - **14× cost-escalation rule**: reconstructing a failed pavement (PCI<25) costs 14× more than preserving one in good condition (PCI≥70); modest resurfacing is 4× more than BMP preservation. Oceanside's PCI of 60 sits below the preservation threshold — every year of deferral moves more area onto the steep part of the cost curve.
   - **BMP goal** (PCI in 80s, zero backlog) is reachable in 10 years at the SCS state-lens rate; once reached, steady-state maintenance drops to ~$3.28B/yr statewide (equivalent to ~$14M/yr for Oceanside — right back near the current Measure X level, but from a healthier starting condition).
   - **Essential components alone** add **~48% on top of pavement-only needs** (statewide $39B EC / $81B pavement). Sidewalks, curb ramps, storm drains, ADA, and NPDES are routinely omitted from "pavement backlog" headlines but are legally required and statewide-underfunded.
   - **Active transportation** adds another ~14% ($11.2B / $81B), broken out separately for the first time in 2022.
   - **Complete streets incremental cost**: $82/sq-yd above standard repaving, with typical project range $12–86/sy (and outliers >$1,000/sy for full right-of-way reconstructions).
   - **Funding headwind**: SB1 is the largest state source but ZEV adoption is projected to cost CA $1.5B/yr in gas-tax revenue by 2035. Oceanside's reliance on state/federal transfers makes the FY25-30 drop back to ~$7.4M/yr (even below the pre-Measure X trendline) particularly risky.

   **City's own admission on the [Measure X Road Repair page](https://www.ci.oceanside.ca.us/government/financial-services/measure-x-sales-tax/measure-x-funds-road-repairs):** "approximately $7 million annually in pavement management… this funding level is not adequate to maintain conditions."

   **Methodology / assumptions (see [backlog_model.py](backlog_model.py) for exact numbers):**
   - Lane-miles counted directly from the PCI workbook — no longer an estimate.
   - Unit costs calibrated against Oceanside's own Measure X reports (FY2020: overlay $383K/lane-mile, slurry $21.5K/lane-mile).
   - Life cycles: slurry every 6 yrs, overlay every 18 yrs, reconstruction every 50 yrs (SoCal mild climate).
   - Pre-FY2021 actual spend modeled from the FY06-08 CIP Book (exact for FY07-11) plus the City's self-reported $7M/year baseline; FY26-30 actual spend from the adopted CIP Book `auto_maintenance` totals.

   **Open questions to revisit later** (user flagged — not blocking the analysis):
   - The "$7M baseline" blends CIP capital + operating maintenance; per-year actual-spend numbers may slightly undercount O&M.
   - Whether the "high" scenario's full reconstruction cycle is overly pessimistic for a mild-climate coastal city like Oceanside. Headline sticks with mid for now.
   - **Lane widths refinement** — current model uses each segment's actual (often wider-than-necessary) pavement width, which over-states the maintenance burden the *minimum-policy* road network would impose. A sibling folder for Oceanside's General Plan (TBD) will extract lane-width minimums from the Circulation Element; once available, we can rerun with "policy-minimum" lane-miles to show the savings from right-sizing lanes. **Do not attempt to fetch the Circulation Element from this folder — the sibling folder will handle it.**

## Datasets (primary outputs)

### [unified_cip.json](unified_cip.json) — merged observations across sources
**359 observations** across 4 sources. Use this as the starting point for analysis. Every record carries a `cip_class` field (`general` / `enterprise` / `unknown`) — always filter to `general` when comparing across eras, since enterprise-fund (Water/Sewer/Harbor) projects pre-FY25 were tracked differently.

**Active-transportation share of 5-year General CIP plan (apples-to-apples):**
- **FY 2006-07 → 2010-11 plan:** 5 AT projects / $1.84M of $85.0M = **2.2%**
- **FY 2025-26 → 2029-30 plan:** 28 AT projects / $15.12M of $98.3M = **15.4%**
- **AT share grew ~7×** from FY06-10 to FY25-30.

The GIS catalog (current/recent projects, no cost data) adds 20 more AT-flagged projects that overlap the FY25-30 plan. Review individual projects before publishing — the heuristic isn't ground truth.

### [oceanside_cip_projects.json](oceanside_cip_projects.json) / [.csv](oceanside_cip_projects.csv) — GIS catalog (current + recent)
**76 projects** from Oceanside's Engineering CIP ArcGIS feed. Active + recently completed (earliest begin_year 2021). Strong schedule / type / location / funding-source labels. **No cost data.**

### [fy2526_cip_projects.json](fy2526_cip_projects.json) / [fy2526_cip_funding_rows.csv](fy2526_cip_funding_rows.csv) — 5-year forward plan
**196 projects** from the FY 2025-26 Five-Year CIP Budget Book (FY25-26 through FY29-30). Full per-project cost, annual funding by source, prior-year spend, remaining need. Includes Water/Sewer/Harbor enterprise funds in addition to General CIP.
- 5-year planned total: **$144.3M**
- Active-transportation (heuristic): **28 projects, $15.1M (10.5%)**
- 19 projects cross-linked to the GIS catalog via fuzzy name match (`gis_project_number` field).

### [fy0608_cip_projects.json](fy0608_cip_projects.json) — historical 5-year plan (OCR'd)
**75 projects** from the scanned FY 2006-08 CIP Book (covers FY 2006-07 through FY 2010-11). Extracted via EasyOCR + custom structured-table parser.
- 5-year planned total (all funds): **$151.0M**
- General CIP subset (excluding Water/Sewer/Harbor): **$85.0M**, 5 AT projects @ **$1.84M (2.2%)**
- Highest-spend projects: Weese Plant Capacity Expansion ($30.7M, water), Pacific St bridge ($11M), Land Outfall ($8.9M, sewer), Street Restoration/Overlay ($8M), three fire/senior centers ($8M each), Mance Buchanon Park ($7.2M), Douglas + N Coast Hwy bridge seismic retrofits ($6.5M each).

**Caveat:** OCR is imperfect. The parser applies a pile of corrections:
- Letter-to-digit substitutions before trimming trailing noise (so `500,00o` → `500,000`)
- Period-vs-comma detection for tokens like `2.200,000` (German-style → `$2,200,000`)
- Trailing-digit strip only when the appended digit is non-zero (so `11,000,000` stays $11M but `2,500,0001` → $2.5M)
- Reconciliation: if yearly-sum diverges from stated 5-year total by >3×, prefer the yearly sum (flagged via `ocr_quality_note` field)
- Split source-name merging: if an OCR'd source label is followed by another label with no numbers in between, merge them (e.g., "Prop 40" + "Cal State" → "Prop 40 Cal State")

After corrections, all 75 projects' funding rows pass the yearly-sum = 5-year-total integrity check. Review the 2 projects with an `ocr_quality_note` field set (pages 10) before publishing. Also some titles have residual minor typos ("BicyclelPedestrian" vs "Bicycle/Pedestrian") from OCR character confusion.

### [legistar_cip_matters.json](legistar_cip_matters.json) — Legistar 2024 supplementary
12 matters with proper titles from Oceanside's Legistar, mostly 2024 grant appropriations and PSA approvals. Dollar amounts are extracted from the title strings. Pre-2020 legislation isn't indexed in Legistar (the city migrated to Legistar around 2020).

## Sources

| What | URL |
|---|---|
| GIS feature service (CIP catalog) | `https://services5.arcgis.com/6UYc3MjsfrxiazMH/arcgis/rest/services/CIP_Engineering_AGOL/FeatureServer` |
| Public CIP Dashboard | [ArcGIS dashboard](https://www.arcgis.com/apps/dashboards/e175467a55d74722b7b82f812605f5ce) |
| CIP Project page | [Projects | Oceanside, CA](https://www.ci.oceanside.ca.us/government/development-services/engineering/capital-improvement-program/current-projects) |
| FY 25-26 CIP Budget Book | [PDF, 311pp, 34MB](https://www.ci.oceanside.ca.us/home/showpublisheddocument/16819/638876730137700000) |
| FY 06-08 CIP Book (scanned) | Doc 8066 on the city CMS; retrieved via Wayback Machine |
| Operating Budget archive (FY02-04 → FY24-25) | [Operating Budget](https://www.ci.oceanside.ca.us/government/financial-services/operating-budget) |
| Legistar | [oceanside.legistar.com](https://oceanside.legistar.com) |
| **Save California Streets** — SB1-mandated biennial statewide LSR needs assessment | [savecaliforniastreets.org](https://savecaliforniastreets.org/) · [2022 Final Report PDF](https://savecaliforniastreets.org/wp-content/uploads/2023/05/Statewide-Needs-2022-FINAL.pdf) |

Note: `www.ci.oceanside.ca.us` returns 403 to most scripted fetchers. Use `web.archive.org/web/2024/<url>` as a pass-through (works for the `showpublisheddocument` PDFs too).

## Fiscal-year coverage

| Years | Per-project costs | Schedule/metadata | Source |
|---|---|---|---|
| **FY 2006-07 – 2010-11** | ✅ (OCR'd) | ✅ | FY06-08 CIP Book |
| FY 2011-12 – 2020-21 | ❌ | partial | Operating budget narrative sections only |
| **FY 2021-22 – 2025-26** | ❌ (GIS only) | ✅ | GIS feature service |
| **FY 2025-26 – 2029-30** | ✅ | ✅ | FY25-26 CIP Book |
| FY 2024-25 | Partial (grants) | — | Legistar 2024 matters |

**The FY 2012-2020 gap is the big unfilled hole.** Per-project detail for those years isn't in any text-extractable PDF we could find; would need:
- Targeted public records request to Finance for historical CIP Budget Books
- OR OCR of any scanned CIP books from that era if they exist in the records portal
- OR harvest of individual Legistar adoption resolutions (pre-2020 not indexed)

## Active-transportation heuristic (v3 — word-boundary aware)

Two keyword groups. Single-word tokens use **word-boundary** regex (so "trail" won't match "trailers", "bike" won't match "bike-rack assembly" but will match "bike path"). Multi-word phrases use plain substring match.

**Single-word set (word boundary):** bike, bicycle, bicyclist, bicycles, pedestrian, pedestrians, sidewalk, sidewalks, crosswalk, crosswalks, trail, trails, greenway, bikeway, bikeways, rrfb, srts, bike lane

**Phrase set (substring):** buffered lane, hawk signal, complete streets, safe routes, active transportation, ada ramp, pedestrian bridge, pedestrian crossing, traffic calming, speed control, school zone, rail trail, bike path

**Known edge case:** p43 FY06-08 "Mira Mar Mobile Home Community Slope Repair" is flagged because the description mentions "next to the City's bike path" — the project itself isn't AT but is adjacent to AT infrastructure. The analyst should decide whether "adjacent to" counts. All other v2 false positives (Fire Training Facility matching "trailers", Sewer force-main matching "crossing") were eliminated.

**Known false negatives to watch for:** corridor redesigns described without the specific AT keywords (e.g., "Coast Highway Corridor"), signal timing upgrades that benefit pedestrians, transit stop improvements ("Bus Benches and Shelters"), and generic "road diet" projects without the phrase.

## Scripts
- [extract_fy2526.py](extract_fy2526.py) — re-parse FY25-26 CIP Book (text-extractable)
- [ocr_fy0608.py](ocr_fy0608.py) — render + OCR + parse scanned FY06-08 CIP Book
- [scrape_legistar.py](scrape_legistar.py) — harvest Legistar 2015-2024 (most pre-2020 results are empty)
- [build_unified_dataset.py](build_unified_dataset.py) — merge all sources into unified_cip.json

## Schema details

### GIS per-project fields
`project_number` (CIPyy-nnnnn), `name`, `type` (Streets/Traffic/Parks/Facilities/Drainage/Other), `current_phase`, `description`, `location`, `district`, `schedule_begin_season`, `schedule_end_season`, `begin_year`, `end_year`, `fund_source_1`…`fund_source_6`, `utility_type`, `recent_update`, `project_manager`, `notice_complete_date`, `project_webpage`, `gis_geometry_types`, `likely_active_transportation`, `at_keywords_matched`, `cost_usd` (null).

### FY25-26 book per-project fields
`project_name`, `project_number` (12-digit accounting code like `902135500212`), `council_district`, `project_category` (TransNet/SB1/Misc City/Muni Bldgs/Drainage/Measure X/Thoroughfare/T&Signals/Parks/Water/Sewer/Harbor), `project_location`, `description`, `status`, `operating_budget_impact`, `funding_overview` (Prior Year Cost / Unused Funds / Five Year Plan / Remaining Needed), `funding_by_source` (list of `{fund_code, funding_source, fy2025_26…fy2029_30, total_5yr}`), `five_year_total`, `likely_active_transportation`, `gis_project_number` (fuzzy match), `gis_match_score`.

### FY06-08 book per-project fields
`project_name`, `management_dept`, `description`, `type_of_project`, `operating_budget_impact`, `funding_sources` (list of `{source, five_year_total, fy06_07…fy10_11}`), `cost_breakdown` (list of `{label, vals}`), `total_construction`, `five_year_total_funding`, `likely_active_transportation`.

## Gaps and caveats

### Data gaps
- **Cost data** exists only for FY06-11 (OCR'd from scanned CIP Book) and FY25-30 (clean text extraction). The 10-year gap in between has no per-project cost source; operating-budget PDFs of that era contain only narrative CIP sections.
- **Legistar coverage** begins ~2020; pre-2020 legislation is not in the Legistar system. Even 2020-2024 search results were attachment-stubs whose PDFs have been deleted from Legistar's file bank.
- **Schedule** in GIS is season-level (WINTER/SPRING/etc.), not exact dates.

### Cross-source joins
- **GIS ↔ FY25-26 book** uses fuzzy name match (19/196 match at ≥0.75 score). Manual review would raise that.
- **FY25-26 book project_number** is a 12-digit accounting code (Fund.Org.Project), not the CIPyy-nnnnn in the GIS catalog — the two systems don't share IDs by design.

### General CIP vs Enterprise Funds
- The City's published General CIP memo excludes Water, Sewer, and Harbor (enterprise funds). In `unified_cip.json` every record has a `cip_class` ∈ {`general`, `enterprise`, `unknown`} — **always filter to `general` for apples-to-apples era comparisons.**
  - FY06-08 book: 51 general / 24 enterprise (Water/Sewer/Outfall/WWTP/Harbor projects)
  - FY25-26 book: 113 general / 83 enterprise (Water Program / Sewer Program / Harbor categories)
  - GIS: all `general` (Water Utilities has a separate public feed not pulled here)
  - Legistar 2024: `unknown` (mixed grants/appropriations without clear classification)

### OCR quality (FY06-08 only)
- All 75 projects' funding rows pass the integrity check (yearly sum = stated 5-year total) after automated corrections.
- Projects with an `ocr_quality_note` set on any funding row had their total reconciled from the yearly sum — review before publishing (currently: p10 Street Restoration and Overlay, where OCR missed the leading digit of the $8M total).
- Project titles may still have OCR-level typos that the parser can't cleanly fix: `BicyclelPedestrian` (missing slash), `Sleeping_Indian`, `Pacific StreetILoma Alta` (I for /), `Tree_Trimming` (underscore for space), etc. Clean these up when publishing a public-facing analysis.

### Heuristic caveats
- AT heuristic v3 uses word boundaries but has the known edge case on p43 (Mira Mar — adjacent-to-AT, not AT itself). See heuristic section above.
- Unknown false-negative rate — the heuristic only catches keyword mentions, not semantic intent. Corridor rebuilds and transit improvements are likely under-counted.

## Refresh
To refresh:
1. Re-run the ArcGIS queries against the feature service (the code for this is inline in Git history).
2. Swap in the new CIP Budget Book PDF in `raw_pdfs/FY2526_CIP_budget.pdf` and re-run `extract_fy2526.py`.
3. Re-run `build_unified_dataset.py` to regenerate `unified_cip.json`.
