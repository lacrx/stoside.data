#!/usr/bin/env python3
"""Compute comprehensive net fiscal productivity per parcel (v2).

Enhanced model incorporating all major revenue and cost categories,
with proper General Fund vs Enterprise Fund separation.

Revenue (per parcel):
  - Property tax (assessed value × 1% × city share)
  - Sales tax (attributed to commercial parcels by sqft)
  - TOT (attributed to hotel/motel parcels)
  - Franchise fees (distributed by assessed value)
  - Business license tax (attributed to commercial/industrial)
  - Measure X (distributed like sales tax)

General Fund costs (per parcel):
  - Police (by land use call-for-service rates)
  - Fire (by land use structural risk)
  - Public works / roads (from Phase 2 attribution)
  - Parks & recreation (per dwelling unit)
  - Stormwater (by impervious surface proxy)
  - General government (proportional to assessed value)
  - Library (per dwelling unit)

Enterprise Fund costs (per parcel, self-funded by rates):
  - Water infrastructure (from Phase 3 attribution)
  - Sewer infrastructure (from Phase 3 attribution)

Source: FY2025 ACFR actuals + FY2025-26 adopted budget
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent.parent
REVENUE_FILE = HERE / "revenue_per_acre.json"
ROADS_FILE = HERE / "road_costs_by_parcel.json"
WATER_SEWER_FILE = HERE / "water_sewer_costs_by_parcel.json"
OUTPUT = HERE / "fiscal_productivity_v2.json"
SUMMARY_OUTPUT = HERE / "fiscal_productivity_v2_summary.json"

# ---------------------------------------------------------------------------
# FY2025 ACFR actuals (governmental activities)
# ---------------------------------------------------------------------------
PROPERTY_TAX_TOTAL = 92_767_885
SALES_TAX_TOTAL = 49_923_733
TOT_TOTAL = 15_954_415
FRANCHISE_TAX_TOTAL = 4_100_642
BUSINESS_LICENSE_TAX_TOTAL = 4_720_181
MEASURE_X_TOTAL = 18_795_917  # from FY25-26 budget (ACFR doesn't split)

# FY2025 ACFR expense actuals (General Fund services)
POLICE_EXPENSE = 74_366_183
FIRE_EXPENSE = 49_380_363
PUBLIC_WORKS_EXPENSE = 32_544_970
GENERAL_GOVT_EXPENSE = 35_721_192

# FY2025-26 budget (for categories not split in ACFR)
PARKS_REC_BUDGET = 8_612_802
LIBRARY_BUDGET = 7_358_732
STORMWATER_BUDGET = 2_735_662

# Enterprise fund actuals (self-funded, shown separately)
WATER_EXPENSE = 83_118_909
SEWER_EXPENSE = 42_718_253

LAND_USE_BROAD_BASE = {
    0: "Vacant", 6: "Commercial", 7: "Industrial", 9: "Vacant",
    10: "SFR", 11: "SFR", 12: "SFR",
    13: "MFR", 14: "MFR", 15: "MFR", 16: "MFR", 17: "MFR", 18: "MFR",
    19: "Mixed Use",
    20: "Commercial", 21: "Commercial", 22: "Commercial",
    24: "Commercial", 25: "Commercial", 26: "Commercial",
    27: "Commercial", 28: "Commercial", 29: "Commercial",
    30: "Industrial", 31: "Industrial", 32: "Industrial",
    33: "Industrial", 34: "Industrial", 35: "Industrial",
    36: "Industrial", 37: "Industrial", 38: "Industrial", 39: "Industrial",
    40: "Agricultural", 41: "Agricultural", 43: "Agricultural",
    44: "Agricultural", 45: "Agricultural", 46: "Agricultural",
    47: "Agricultural", 49: "Agricultural",
    50: "Institutional", 51: "Institutional", 52: "Institutional",
    54: "Institutional", 57: "Institutional", 58: "Institutional",
    59: "Institutional",
    61: "Recreation", 62: "Recreation",
    70: "Government", 71: "Government", 72: "Government",
    73: "Government", 75: "Government", 76: "Government",
    77: "Government", 79: "Government",
    80: "Open Space", 81: "Open Space", 82: "Open Space",
    83: "Open Space", 84: "Open Space", 85: "Open Space",
    86: "Common Area", 88: "Exempt", 89: "Exempt", 90: "Other",
}

MFR_CODES = {13, 14, 15, 16, 17, 18}
CONDO_CODE = 17


def refine_land_use(land_use_code: int, units: int) -> str:
    """Split MFR into subcategories by unit count and ownership type."""
    base = LAND_USE_BROAD_BASE.get(land_use_code, "Unknown")
    if base != "MFR":
        return base
    if land_use_code == CONDO_CODE:
        return "Condo/TH"
    if units <= 2:
        return "Duplex"
    if units <= 4:
        return "3-4 Plex"
    if units <= 20:
        return "MFR 5-20"
    if units <= 100:
        return "MFR 21-100"
    return "MFR 100+"

# Hotel/motel land use code
HOTEL_CODE = 25

# ---------------------------------------------------------------------------
# Police/fire/parks/library allocation: geographic (per acre served)
#
# Strong Towns methodology: cost burden = maintenance / acres served.
# Police patrol beats, fire station coverage, road maintenance, stormwater
# are all geographic infrastructure costs. The cost of covering an acre
# does not scale with the number of units on it — you patrol the same
# streets, staff the same fire station, maintain the same pipes.
#
# Academic basis:
#   - Compact development is cheaper to serve per acre (Goodman 2019,
#     Carruthers & Ulfarsson 2003, TCRP Report 74)
#   - U-shaped density-cost curve ascending limb only at >24K ppl/sq mi
#     (Ahlfeldt & Pietrostefani 2017) — irrelevant for Oceanside
#   - "Suburban infrastructure costs more to serve per acre than it
#     generates in revenue" (policy-knowledge-docs)
#
# Land use weights reflect that some land uses require more coverage
# intensity (commercial > residential > agricultural > vacant).
# ---------------------------------------------------------------------------
POLICE_ACRE_WEIGHT = {
    "SFR": 1.0, "Condo/TH": 1.0, "Duplex": 1.0, "3-4 Plex": 1.0,
    "MFR 5-20": 1.0, "MFR 21-100": 1.0, "MFR 100+": 1.0,
    "Commercial": 1.5, "Industrial": 0.8,
    "Mixed Use": 1.2, "Agricultural": 0.2, "Institutional": 0.5,
    "Government": 0.5, "Recreation": 0.2, "Vacant": 0.1,
    "Open Space": 0.05, "Common Area": 0.05, "Exempt": 0.1,
    "Other": 0.3, "Unknown": 0.3,
}
FIRE_ACRE_WEIGHT = {
    "SFR": 1.0, "Condo/TH": 1.0, "Duplex": 1.0, "3-4 Plex": 1.0,
    "MFR 5-20": 1.0, "MFR 21-100": 1.0, "MFR 100+": 1.0,
    "Commercial": 1.2, "Industrial": 1.5,
    "Mixed Use": 1.0, "Agricultural": 0.3, "Institutional": 1.0,
    "Government": 0.8, "Recreation": 0.2, "Vacant": 0.05,
    "Open Space": 0.1, "Common Area": 0.05, "Exempt": 0.2,
    "Other": 0.3, "Unknown": 0.3,
}
PARKS_ACRE_WEIGHT = {
    "SFR": 1.0, "Condo/TH": 1.0, "Duplex": 1.0, "3-4 Plex": 1.0,
    "MFR 5-20": 1.0, "MFR 21-100": 1.0, "MFR 100+": 1.0,
    "Commercial": 0.1, "Industrial": 0.05,
    "Mixed Use": 0.5, "Agricultural": 0.1, "Institutional": 0.3,
    "Government": 0.2, "Recreation": 0.1, "Vacant": 0.05,
    "Open Space": 0.02, "Common Area": 0.05, "Exempt": 0.1,
    "Other": 0.1, "Unknown": 0.1,
}

# Impervious surface fraction by land use (for stormwater)
IMPERVIOUS_FRACTION = {
    "SFR": 0.45,
    "Condo/TH": 0.70,
    "Duplex": 0.55,
    "3-4 Plex": 0.65,
    "MFR 5-20": 0.75,
    "MFR 21-100": 0.80,
    "MFR 100+": 0.85,
    "Commercial": 0.85,
    "Industrial": 0.80,
    "Mixed Use": 0.80,
    "Agricultural": 0.10,
    "Institutional": 0.60,
    "Government": 0.60,
    "Recreation": 0.20,
    "Vacant": 0.05,
    "Open Space": 0.02,
    "Common Area": 0.15,
    "Exempt": 0.30,
    "Other": 0.30,
    "Unknown": 0.30,
}


def load_by_apn(path: Path, label: str) -> dict[str, dict]:
    with open(path) as f:
        data = json.load(f)
    parcels = data.get("parcels", [])
    print(f"  {label}: {len(parcels):,} parcels")
    return {p["apn"]: p for p in parcels}


def compute_sales_tax_shares(revenue: dict[str, dict]) -> dict[str, float]:
    """Attribute sales tax to commercial parcels proportional to sqft."""
    commercial_sqft = {}
    total_sqft = 0
    for apn, rev in revenue.items():
        lu = rev.get("land_use_broad", "")
        if lu in ("Commercial", "Mixed Use"):
            sqft = max(rev.get("living_sqft", 0), 1000)
            commercial_sqft[apn] = sqft
            total_sqft += sqft

    shares = {}
    if total_sqft > 0:
        for apn, sqft in commercial_sqft.items():
            shares[apn] = sqft / total_sqft
    return shares


def compute_tot_shares(revenue: dict[str, dict]) -> dict[str, float]:
    """Attribute TOT to hotel/motel parcels proportional to assessed value."""
    hotel_values = {}
    total_value = 0
    for apn, rev in revenue.items():
        if rev.get("land_use_code") == HOTEL_CODE:
            val = max(rev.get("assessed_total", 0), 1)
            hotel_values[apn] = val
            total_value += val

    shares = {}
    if total_value > 0:
        for apn, val in hotel_values.items():
            shares[apn] = val / total_value
    return shares


def compute_acre_shares(
    revenue: dict[str, dict],
    acre_weights: dict[str, float],
) -> dict[str, float]:
    """Allocate cost by geographic area (acres × land use weight)."""
    weighted = {}
    total_weight = 0
    for apn, rev in revenue.items():
        lu = rev.get("land_use_broad", "Unknown")
        acres = max(rev.get("acres", 0), 0.001)
        w = acres * acre_weights.get(lu, 0.3)
        weighted[apn] = w
        total_weight += w

    if total_weight > 0:
        for apn in weighted:
            weighted[apn] /= total_weight
    return weighted


def main():
    print("Loading datasets...")
    revenue = load_by_apn(REVENUE_FILE, "Revenue")
    roads = load_by_apn(ROADS_FILE, "Roads")
    water_sewer = load_by_apn(WATER_SEWER_FILE, "Water/Sewer")

    all_apns = sorted(revenue.keys())
    print(f"\n  Total parcels: {len(all_apns):,}")

    # Refine MFR into subcategories by unit count
    for rev in revenue.values():
        code = rev.get("land_use_code", 0)
        units = rev.get("units", 0)
        rev["land_use_broad"] = refine_land_use(code, units)

    lu_counts = Counter(r["land_use_broad"] for r in revenue.values())
    for lu in ["SFR", "Condo/TH", "Duplex", "3-4 Plex", "MFR 5-20", "MFR 21-100", "MFR 100+"]:
        if lu in lu_counts:
            print(f"  {lu}: {lu_counts[lu]:,}")

    # Pre-compute allocation shares
    print("\nComputing allocation shares...")
    sales_tax_shares = compute_sales_tax_shares(revenue)
    print(f"  Sales tax: {len(sales_tax_shares):,} commercial parcels")

    tot_shares = compute_tot_shares(revenue)
    print(f"  TOT: {len(tot_shares):,} hotel/motel parcels")

    police_shares = compute_acre_shares(revenue, POLICE_ACRE_WEIGHT)
    fire_shares = compute_acre_shares(revenue, FIRE_ACRE_WEIGHT)

    # Business license + franchise: proportional to assessed value
    total_assessed = sum(r.get("assessed_total", 0) for r in revenue.values())
    assessed_shares = {
        apn: r.get("assessed_total", 0) / total_assessed
        for apn, r in revenue.items()
    } if total_assessed > 0 else {}

    # Stormwater: by impervious area
    imperv_areas = {}
    total_imperv = 0
    for apn, rev in revenue.items():
        lu = rev.get("land_use_broad", "Unknown")
        acres = rev.get("acres", 0)
        frac = IMPERVIOUS_FRACTION.get(lu, 0.3)
        ia = acres * frac
        imperv_areas[apn] = ia
        total_imperv += ia

    imperv_shares = {
        apn: ia / total_imperv for apn, ia in imperv_areas.items()
    } if total_imperv > 0 else {}

    # Parks + library: geographic (parks maintain acreage, libraries serve areas)
    parks_shares = compute_acre_shares(revenue, PARKS_ACRE_WEIGHT)
    library_shares = compute_acre_shares(revenue, PARKS_ACRE_WEIGHT)

    # Road costs from Phase 2: use Public Works budget minus estimated
    # non-road share. Phase 2 already computes granular road costs.
    # General government: proportional to assessed value

    print("Computing per-parcel fiscal productivity...")
    per_parcel = []

    for apn in all_apns:
        rev = revenue[apn]
        rd = roads.get(apn, {})
        ws = water_sewer.get(apn, {})

        acres = rev.get("acres", 0)
        taxable = rev.get("taxable", False)
        lu = rev.get("land_use_broad", "Unknown")
        units = max(rev.get("units", 0), 1)

        # === REVENUE ===
        prop_tax = rev.get("property_tax_city", 0)

        # Scale property tax to match ACFR actual
        # Our model: assessed × 1% × 16%. ACFR actual: $92.8M.
        # Our Phase 1 total: ~$50M. Ratio ≈ 1.85.
        # Rather than rescale, use actual city share implied by ACFR.
        assessed = rev.get("assessed_total", 0)
        actual_city_rate = PROPERTY_TAX_TOTAL / total_assessed if total_assessed > 0 else 0.0016
        prop_tax_calibrated = assessed * actual_city_rate

        sales_tax = SALES_TAX_TOTAL * sales_tax_shares.get(apn, 0)
        measure_x = MEASURE_X_TOTAL * sales_tax_shares.get(apn, 0)
        tot = TOT_TOTAL * tot_shares.get(apn, 0)
        franchise = FRANCHISE_TAX_TOTAL * assessed_shares.get(apn, 0)
        biz_license = BUSINESS_LICENSE_TAX_TOTAL * assessed_shares.get(apn, 0)

        total_gf_revenue = prop_tax_calibrated + sales_tax + measure_x + tot + franchise + biz_license

        # === GENERAL FUND COSTS ===
        police = POLICE_EXPENSE * police_shares.get(apn, 0)
        fire = FIRE_EXPENSE * fire_shares.get(apn, 0)
        road_cost = rd.get("road_cost_total", 0)
        parks = PARKS_REC_BUDGET * parks_shares.get(apn, 0)
        library = LIBRARY_BUDGET * library_shares.get(apn, 0)
        stormwater = STORMWATER_BUDGET * imperv_shares.get(apn, 0)
        gen_govt = GENERAL_GOVT_EXPENSE * assessed_shares.get(apn, 0)

        total_gf_cost = police + fire + road_cost + parks + library + stormwater + gen_govt

        # === ENTERPRISE FUND (informational) ===
        water_cost = ws.get("water_total", 0)
        sewer_cost = ws.get("sewer_total", 0)
        enterprise_cost = water_cost + sewer_cost

        # === NET ===
        gf_net = total_gf_revenue - total_gf_cost
        full_net = total_gf_revenue - total_gf_cost - enterprise_cost
        gf_ratio = total_gf_revenue / total_gf_cost if total_gf_cost > 0 else 0
        gf_net_per_acre = gf_net / acres if acres > 0.001 else 0

        per_parcel.append({
            "apn": apn,
            "address": rev.get("address", ""),
            "land_use": rev.get("land_use", ""),
            "land_use_broad": lu,
            "land_use_code": rev.get("land_use_code", 0),
            "acres": round(acres, 4),
            "taxable": taxable,
            "units": rev.get("units", 0),
            "living_sqft": rev.get("living_sqft", 0),
            "assessed_total": assessed,
            "revenue": {
                "property_tax": round(prop_tax_calibrated, 2),
                "sales_tax": round(sales_tax, 2),
                "measure_x": round(measure_x, 2),
                "tot": round(tot, 2),
                "franchise_fees": round(franchise, 2),
                "business_license": round(biz_license, 2),
                "gf_total": round(total_gf_revenue, 2),
                "gf_per_acre": round(total_gf_revenue / acres, 2) if acres > 0.001 else 0,
            },
            "gf_costs": {
                "police": round(police, 2),
                "fire": round(fire, 2),
                "roads": round(road_cost, 2),
                "parks": round(parks, 2),
                "library": round(library, 2),
                "stormwater": round(stormwater, 2),
                "general_govt": round(gen_govt, 2),
                "total": round(total_gf_cost, 2),
                "per_acre": round(total_gf_cost / acres, 2) if acres > 0.001 else 0,
            },
            "enterprise_costs": {
                "water": round(water_cost, 2),
                "sewer": round(sewer_cost, 2),
                "total": round(enterprise_cost, 2),
            },
            "gf_net": round(gf_net, 2),
            "gf_net_per_acre": round(gf_net_per_acre, 2),
            "gf_ratio": round(gf_ratio, 3),
        })

    per_parcel.sort(key=lambda p: p["gf_net_per_acre"])

    # === BUILD SUMMARY ===
    taxable = [p for p in per_parcel if p["taxable"] and p["assessed_total"] > 0 and p["acres"] > 0.001]

    gf_nets = [p["gf_net_per_acre"] for p in taxable]
    gf_ratios = [p["gf_ratio"] for p in taxable if p["gf_ratio"] > 0]

    contributors = [p for p in taxable if p["gf_net"] > 0]
    drains = [p for p in taxable if p["gf_net"] <= 0]

    total_gf_rev = sum(p["revenue"]["gf_total"] for p in taxable)
    total_gf_cost = sum(p["gf_costs"]["total"] for p in taxable)

    summary = {
        "methodology": {
            "revenue_sources": [
                "property_tax (calibrated to ACFR actual $92.8M)",
                "sales_tax ($49.9M, attributed to commercial by sqft)",
                "measure_x ($18.8M, attributed like sales tax)",
                "tot ($16.0M, attributed to hotel/motel parcels)",
                "franchise_fees ($4.1M, proportional to assessed value)",
                "business_license ($4.7M, proportional to assessed value)",
            ],
            "gf_cost_sources": [
                "police ($74.4M, per acre × land use weight — patrol/coverage is geographic)",
                "fire ($49.4M, per acre × land use weight — station coverage is geographic)",
                "roads ($17.5M from Phase 2 PCI/frontage attribution)",
                "parks_rec ($8.6M, per acre × residential weight)",
                "library ($7.4M, per acre × residential weight)",
                "stormwater ($2.7M, by impervious surface area proxy)",
                "general_govt ($35.7M, proportional to assessed value)",
            ],
            "enterprise_fund_note": "Water ($83.1M) and sewer ($42.7M) are enterprise funds, self-funded by utility rates. Shown separately — not included in GF fiscal ratio.",
            "data_source": "FY2025 ACFR actuals + FY2025-26 adopted budget",
        },
        "totals": {
            "total_parcels": len(per_parcel),
            "taxable_parcels": len(taxable),
            "gf_total_revenue": round(total_gf_rev),
            "gf_total_cost": round(total_gf_cost),
            "gf_total_net": round(total_gf_rev - total_gf_cost),
            "revenue_breakdown": {
                "property_tax": round(sum(p["revenue"]["property_tax"] for p in taxable)),
                "sales_tax": round(sum(p["revenue"]["sales_tax"] for p in taxable)),
                "measure_x": round(sum(p["revenue"]["measure_x"] for p in taxable)),
                "tot": round(sum(p["revenue"]["tot"] for p in taxable)),
                "franchise_fees": round(sum(p["revenue"]["franchise_fees"] for p in taxable)),
                "business_license": round(sum(p["revenue"]["business_license"] for p in taxable)),
            },
            "cost_breakdown": {
                "police": round(sum(p["gf_costs"]["police"] for p in taxable)),
                "fire": round(sum(p["gf_costs"]["fire"] for p in taxable)),
                "roads": round(sum(p["gf_costs"]["roads"] for p in taxable)),
                "parks": round(sum(p["gf_costs"]["parks"] for p in taxable)),
                "library": round(sum(p["gf_costs"]["library"] for p in taxable)),
                "stormwater": round(sum(p["gf_costs"]["stormwater"] for p in taxable)),
                "general_govt": round(sum(p["gf_costs"]["general_govt"] for p in taxable)),
            },
            "net_contributors": len(contributors),
            "net_drains": len(drains),
            "pct_contributors": round(len(contributors) / len(taxable) * 100, 1),
            "overall_gf_ratio": round(total_gf_rev / total_gf_cost, 3) if total_gf_cost > 0 else 0,
        },
        "distribution": {
            "gf_net_per_acre": {
                f"p{p}": round(float(np.percentile(gf_nets, p)))
                for p in [5, 10, 25, 50, 75, 90, 95]
            },
            "gf_ratio": {
                f"p{p}": round(float(np.percentile(gf_ratios, p)), 2)
                for p in [5, 10, 25, 50, 75, 90, 95]
            },
        },
    }

    # By land use
    lu_groups = defaultdict(list)
    for p in taxable:
        lu_groups[p["land_use_broad"]].append(p)

    by_land_use = []
    for cat, group in lu_groups.items():
        g_acres = sum(p["acres"] for p in group)
        g_rev = sum(p["revenue"]["gf_total"] for p in group)
        g_cost = sum(p["gf_costs"]["total"] for p in group)
        g_net = g_rev - g_cost
        g_ratios = [p["gf_ratio"] for p in group if p["gf_ratio"] > 0]
        g_nets = [p["gf_net_per_acre"] for p in group]
        g_contribs = sum(1 for p in group if p["gf_net"] > 0)

        by_land_use.append({
            "category": cat,
            "count": len(group),
            "total_acres": round(g_acres, 1),
            "gf_revenue": round(g_rev),
            "gf_cost": round(g_cost),
            "gf_net": round(g_net),
            "revenue_per_acre": round(g_rev / g_acres) if g_acres > 0 else 0,
            "cost_per_acre": round(g_cost / g_acres) if g_acres > 0 else 0,
            "median_net_per_acre": round(float(np.median(g_nets))),
            "median_gf_ratio": round(float(np.median(g_ratios)), 2) if g_ratios else 0,
            "pct_contributors": round(g_contribs / len(group) * 100, 1),
        })

    by_land_use.sort(key=lambda x: -x["median_net_per_acre"])
    summary["by_land_use"] = by_land_use

    # Cross-subsidy
    cross_subsidy = sorted(
        [{"category": c["category"], "gf_net": c["gf_net"]} for c in by_land_use],
        key=lambda x: -x["gf_net"],
    )
    summary["cross_subsidy"] = cross_subsidy

    output = {"summary": summary, "parcels": per_parcel}
    OUTPUT.write_text(json.dumps(output, indent=2))
    size_mb = OUTPUT.stat().st_size / 1_048_576
    print(f"\n→ {OUTPUT} ({size_mb:.1f} MB)")

    SUMMARY_OUTPUT.write_text(json.dumps(summary, indent=2))
    print(f"→ {SUMMARY_OUTPUT}")

    # === PRINT RESULTS ===
    t = summary["totals"]
    print(f"\n{'=' * 75}")
    print(f"COMPREHENSIVE FISCAL PRODUCTIVITY — OCEANSIDE, CA (FY2025)")
    print(f"{'=' * 75}")
    print(f"Taxable parcels: {t['taxable_parcels']:,}")

    print(f"\nGENERAL FUND REVENUE: ${t['gf_total_revenue']:>14,}")
    rb = t["revenue_breakdown"]
    for k, v in rb.items():
        print(f"  {k:20s} ${v:>12,}")

    print(f"\nGENERAL FUND COSTS:  ${t['gf_total_cost']:>14,}")
    cb = t["cost_breakdown"]
    for k, v in cb.items():
        print(f"  {k:20s} ${v:>12,}")

    print(f"\nGF NET:              ${t['gf_total_net']:>14,}")
    print(f"Overall GF ratio:    {t['overall_gf_ratio']:.3f}x")

    print(f"\nNet contributors: {t['net_contributors']:,} ({t['pct_contributors']}%)")
    print(f"Net drains:       {t['net_drains']:,} ({100 - t['pct_contributors']:.1f}%)")

    d = summary["distribution"]
    print(f"\nGF Net $/acre distribution:")
    for k, v in d["gf_net_per_acre"].items():
        print(f"  {k}: ${v:,}")

    print(f"\nGF Ratio distribution:")
    for k, v in d["gf_ratio"].items():
        print(f"  {k}: {v:.2f}x")

    print(f"\n{'Category':20s} {'#':>7s} {'Acres':>9s} {'Rev/ac':>9s} {'Cost/ac':>9s} "
          f"{'Net/ac':>10s} {'Ratio':>7s} {'%Cont':>7s}")
    print(f"{'-'*20} {'-'*7} {'-'*9} {'-'*9} {'-'*9} {'-'*10} {'-'*7} {'-'*7}")
    for cat in by_land_use:
        print(f"{cat['category']:20s} {cat['count']:>7,} {cat['total_acres']:>9,.1f} "
              f"${cat['revenue_per_acre']:>8,} ${cat['cost_per_acre']:>8,} "
              f"${cat['median_net_per_acre']:>9,} {cat['median_gf_ratio']:>6.2f}x "
              f"{cat['pct_contributors']:>6.1f}%")

    print(f"\nCross-subsidy flows (GF only):")
    for cs in cross_subsidy:
        arrow = "→ contributes" if cs["gf_net"] > 0 else "← receives"
        print(f"  {cs['category']:20s} {arrow} ${abs(cs['gf_net']):>12,}")


if __name__ == "__main__":
    main()
