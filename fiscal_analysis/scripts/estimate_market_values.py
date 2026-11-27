#!/usr/bin/env python3
"""Estimate market value for every Oceanside parcel.

Uses recent sales (2020-2025) as comps to estimate what each parcel
would be assessed at without Prop 13 suppression. Produces two views:

  1. Prop 13 (actual): current assessed values from tax roll
  2. Market value (estimated): what parcels would be assessed at
     if Prop 13 didn't exist (revenue-neutral scenario)

Methodology:
  - Group recent sales (DOCDATE 2020-2025) by land use code
  - Compute median assessed $/sqft and $/unit for each code
  - For each parcel, estimate market value using the better metric
    ($/sqft if living area > 0, else $/unit, else $/acre)
  - Parcels sold 2020-2025 keep their actual assessed value as market
  - Compute Prop 13 suppression ratio per parcel

Outputs:
  - market_values.json: per-parcel with both assessed and estimated market
  - market_values_summary.json: aggregated Prop 13 impact by category
"""

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent.parent
PARCEL_FILE = HERE / "parcels_oceanside.geojson"
OUTPUT = HERE / "market_values.json"
SUMMARY_OUTPUT = HERE / "market_values_summary.json"

LAND_USE_NAMES = {
    0: "Unknown", 6: "MH Park", 7: "MH Common", 9: "MH Unit",
    10: "SFR", 11: "SFR", 12: "SFR+Granny",
    13: "Duplex/Triplex", 14: "4-plex", 15: "MFR 5-15", 16: "MFR 16-60",
    17: "Condo/TH", 18: "MFR 61+", 19: "Common Area",
    20: "Commercial", 21: "Comm+Res", 22: "Office",
    24: "Shopping Ctr", 25: "Hotel/Motel", 26: "Motel",
    27: "Dept Store", 28: "Restaurant", 29: "Service Station",
    30: "Industrial", 31: "Ind Light", 32: "Storage", 35: "Ind Heavy",
    37: "Ind Large", 38: "Ind Other", 39: "Ind Other",
    40: "Mixed Use", 41: "Office Prof", 43: "Office Med",
    46: "Auto Sales", 47: "Misc Comm",
    50: "Institutional", 52: "Church", 57: "Club", 59: "Cemetery",
    60: "Government", 70: "Open Space", 71: "Park",
    80: "Vacant Res", 82: "Vacant Comm", 83: "Vacant Ind",
    86: "Vacant Res", 88: "Vacant Comm",
}

REFINED_CATEGORY = {
    10: "SFR", 11: "SFR", 12: "SFR",
    13: "Small MFR", 14: "Small MFR",
    15: "Large MFR", 16: "Large MFR", 18: "Large MFR",
    17: "Condo/TH", 19: "Common Area",
    6: "Mobile Home", 7: "Mobile Home", 9: "Mobile Home",
}


def parse_docdate(d: str) -> int | None:
    if not d or len(d) < 6 or d.strip() in ("", "000000"):
        return None
    try:
        yy = int(d[4:6])
        return 2000 + yy if yy <= 30 else 1900 + yy
    except (ValueError, IndexError):
        return None


def build_comp_tables(features: list[dict]) -> dict:
    """Build market value lookup tables from recent sales."""
    comps_by_code = defaultdict(list)
    comps_by_refined = defaultdict(list)

    for feat in features:
        p = feat["properties"]
        doc_yr = parse_docdate(p.get("DOCDATE", ""))
        if not doc_yr or doc_yr < 2020:
            continue

        assessed = p.get("ASR_TOTAL", 0)
        if assessed <= 0:
            continue

        code = p.get("ASR_LANDUS", 0)
        units = max(p.get("UNITQTY", 0), 1)
        sqft = p.get("TOTAL_LVG_", 0)
        acres = p.get("ACREAGE", 0) or 0.01

        entry = {
            "per_unit": assessed / units,
            "per_sqft": assessed / sqft if sqft > 0 else None,
            "per_acre": assessed / acres if acres > 0.001 else None,
        }
        comps_by_code[code].append(entry)

        refined = REFINED_CATEGORY.get(code)
        if refined:
            comps_by_refined[refined].append(entry)

    tables = {}
    for code, entries in comps_by_code.items():
        per_unit = [e["per_unit"] for e in entries]
        per_sqft = [e["per_sqft"] for e in entries if e["per_sqft"] is not None]
        per_acre = [e["per_acre"] for e in entries if e["per_acre"] is not None]

        tables[code] = {
            "n_sales": len(entries),
            "median_per_unit": float(np.median(per_unit)) if per_unit else 0,
            "median_per_sqft": float(np.median(per_sqft)) if per_sqft else 0,
            "median_per_acre": float(np.median(per_acre)) if per_acre else 0,
        }

    for refined, entries in comps_by_refined.items():
        per_unit = [e["per_unit"] for e in entries]
        per_sqft = [e["per_sqft"] for e in entries if e["per_sqft"] is not None]
        per_acre = [e["per_acre"] for e in entries if e["per_acre"] is not None]

        tables[f"refined_{refined}"] = {
            "n_sales": len(entries),
            "median_per_unit": float(np.median(per_unit)) if per_unit else 0,
            "median_per_sqft": float(np.median(per_sqft)) if per_sqft else 0,
            "median_per_acre": float(np.median(per_acre)) if per_acre else 0,
        }

    return tables


def estimate_market_value(
    props: dict,
    comp_tables: dict,
    doc_yr: int | None,
) -> tuple[float, str]:
    """Estimate market value for a single parcel.

    Returns (estimated_value, method_used).
    """
    code = props.get("ASR_LANDUS", 0)
    units = max(props.get("UNITQTY", 0), 1)
    sqft = props.get("TOTAL_LVG_", 0)
    acres = props.get("ACREAGE", 0) or 0.01
    assessed = props.get("ASR_TOTAL", 0)

    if doc_yr and doc_yr >= 2020 and assessed > 0:
        return float(assessed), "recent_sale"

    comp = comp_tables.get(code)
    if not comp or comp["n_sales"] < 3:
        refined = REFINED_CATEGORY.get(code)
        if refined:
            comp = comp_tables.get(f"refined_{refined}")

    if not comp or comp["n_sales"] < 3:
        if assessed > 0 and doc_yr:
            years_since = max(2025 - doc_yr, 0)
            # Rough 5% annual appreciation
            appreciation = 1.05 ** years_since
            return float(assessed * appreciation), "appreciation"
        return float(assessed) if assessed > 0 else 0.0, "no_comp"

    if sqft > 0 and comp["median_per_sqft"] > 0:
        return float(sqft * comp["median_per_sqft"]), "per_sqft"
    elif units > 0 and comp["median_per_unit"] > 0:
        return float(units * comp["median_per_unit"]), "per_unit"
    elif acres > 0.001 and comp["median_per_acre"] > 0:
        return float(acres * comp["median_per_acre"]), "per_acre"

    return float(assessed) if assessed > 0 else 0.0, "fallback"


def main():
    print("Loading parcel data...")
    with open(PARCEL_FILE) as f:
        geo = json.load(f)

    features = geo["features"]
    print(f"  {len(features):,} parcels")

    print("Building comp tables from 2020-2025 sales...")
    comp_tables = build_comp_tables(features)

    residential_codes = {10, 11, 12, 13, 14, 15, 16, 17, 18}
    for code in sorted(residential_codes):
        comp = comp_tables.get(code, {})
        name = LAND_USE_NAMES.get(code, "?")
        print(f"  Code {code:>2} ({name:15s}): {comp.get('n_sales', 0):>5} sales, "
              f"${comp.get('median_per_unit', 0):>10,.0f}/unit, "
              f"${comp.get('median_per_sqft', 0):>6,.0f}/sqft")

    print("\nEstimating market values...")
    parcels = []
    method_counts = defaultdict(int)

    for feat in features:
        props = feat["properties"]
        apn = props["APN"]
        doc_yr = parse_docdate(props.get("DOCDATE", ""))
        assessed = props.get("ASR_TOTAL", 0)
        code = props.get("ASR_LANDUS", 0)
        units = max(props.get("UNITQTY", 0), 1)
        sqft = props.get("TOTAL_LVG_", 0)
        acres = props.get("ACREAGE", 0) or 0.01

        market_value, method = estimate_market_value(props, comp_tables, doc_yr)
        method_counts[method] += 1

        suppression = assessed / market_value if market_value > 0 else 1.0
        prop13_discount = 1.0 - suppression if suppression < 1.0 else 0.0

        parcels.append({
            "apn": apn,
            "land_use_code": code,
            "land_use_name": LAND_USE_NAMES.get(code, f"Code {code}"),
            "units": props.get("UNITQTY", 0),
            "sqft": sqft,
            "acres": round(acres, 4),
            "sale_year": doc_yr,
            "assessed_total": assessed,
            "assessed_land": props.get("ASR_LAND", 0),
            "assessed_impr": props.get("ASR_IMPR", 0),
            "market_value": round(market_value),
            "market_method": method,
            "suppression_ratio": round(suppression, 3),
            "prop13_discount_pct": round(prop13_discount * 100, 1),
        })

    print(f"\nEstimation methods:")
    for method, count in sorted(method_counts.items(), key=lambda x: -x[1]):
        print(f"  {method:15s}: {count:>7,}")

    # Build summary by refined category
    MFR_CATS = {"Condo/TH", "Duplex", "3-4 Plex", "MFR 5-20", "MFR 21-100", "MFR 100+"}
    ALL_RES = MFR_CATS | {"SFR"}

    def refined_cat(code, units):
        if code in (10, 11, 12):
            return "SFR"
        elif code == 17:
            return "Condo/TH"
        elif code in (13,) and units <= 2:
            return "Duplex"
        elif code in (13, 14) and units <= 4:
            return "3-4 Plex"
        elif code == 15 or (code in (13, 14) and units >= 5 and units <= 20):
            return "MFR 5-20"
        elif code == 16 or (21 <= units <= 100):
            return "MFR 21-100"
        elif code == 18 or units > 100:
            return "MFR 100+"
        elif code in (20, 21, 22, 24, 25, 26, 27, 28, 29, 40, 41, 43, 46, 47):
            return "Commercial"
        elif code in (30, 31, 32, 35, 37, 38, 39):
            return "Industrial"
        elif code in (6, 7, 9):
            return "Mobile Home"
        elif code in (80, 82, 83, 86, 88):
            return "Vacant"
        elif code in (50, 52, 57, 59):
            return "Institutional"
        elif code in (60,):
            return "Government"
        elif code in (70, 71):
            return "Open Space"
        else:
            return "Other"

    cats = defaultdict(lambda: {
        "count": 0, "units": 0, "acres": 0,
        "total_assessed": 0, "total_market": 0,
        "suppression_ratios": [],
        "by_era": defaultdict(lambda: {"count": 0, "assessed": 0, "market": 0}),
    })

    for p in parcels:
        if p["assessed_total"] <= 0 and p["market_value"] <= 0:
            continue

        cat = refined_cat(p["land_use_code"], p["units"] or 0)
        c = cats[cat]
        c["count"] += 1
        c["units"] += p["units"] or 0
        c["acres"] += p["acres"]
        c["total_assessed"] += p["assessed_total"]
        c["total_market"] += p["market_value"]
        if p["suppression_ratio"] > 0:
            c["suppression_ratios"].append(p["suppression_ratio"])

        yr = p["sale_year"]
        if yr:
            if yr < 1990:
                era = "pre-1990"
            elif yr < 2000:
                era = "1990s"
            elif yr < 2010:
                era = "2000s"
            elif yr < 2020:
                era = "2010s"
            else:
                era = "2020s"
            c["by_era"][era]["count"] += 1
            c["by_era"][era]["assessed"] += p["assessed_total"]
            c["by_era"][era]["market"] += p["market_value"]

    summary_cats = []
    for cat in ["SFR", "Condo/TH", "Duplex", "3-4 Plex", "MFR 5-20",
                "MFR 21-100", "MFR 100+", "Commercial", "Industrial",
                "Mobile Home", "Vacant", "Institutional", "Government",
                "Open Space", "Other"]:
        c = cats.get(cat)
        if not c or c["count"] == 0:
            continue

        sr = c["suppression_ratios"]
        agg_suppression = c["total_assessed"] / c["total_market"] if c["total_market"] > 0 else 1.0
        revenue_gap = c["total_market"] - c["total_assessed"]

        era_summary = {}
        for era in ["pre-1990", "1990s", "2000s", "2010s", "2020s"]:
            e = c["by_era"].get(era)
            if e and e["count"] > 0:
                era_suppression = e["assessed"] / e["market"] if e["market"] > 0 else 1.0
                era_summary[era] = {
                    "count": e["count"],
                    "assessed": round(e["assessed"]),
                    "market": round(e["market"]),
                    "suppression": round(era_suppression, 3),
                }

        summary_cats.append({
            "category": cat,
            "count": c["count"],
            "units": c["units"],
            "acres": round(c["acres"]),
            "total_assessed": round(c["total_assessed"]),
            "total_market": round(c["total_market"]),
            "revenue_gap": round(revenue_gap),
            "aggregate_suppression": round(agg_suppression, 3),
            "median_suppression": round(float(np.median(sr)), 3) if sr else 1.0,
            "by_era": era_summary,
        })

    # City-rate for revenue impact
    total_assessed = sum(c["total_assessed"] for c in cats.values())
    total_market = sum(c["total_market"] for c in cats.values())
    city_rate = 92_800_000 / total_assessed if total_assessed > 0 else 0.00191

    summary = {
        "methodology": {
            "comp_period": "2020-2025 sales",
            "fallback": "5% annual appreciation from sale year",
            "city_tax_rate": round(city_rate, 6),
            "note": "Market values estimated from recent comparable sales. "
                    "Revenue-neutral scenario holds total city revenue constant "
                    "and redistributes based on market values.",
        },
        "totals": {
            "parcels": sum(c["count"] for c in cats.values()),
            "total_assessed": round(total_assessed),
            "total_market": round(total_market),
            "aggregate_suppression": round(total_assessed / total_market, 3) if total_market > 0 else 1.0,
            "total_revenue_gap": round(total_market - total_assessed),
            "prop13_at_current_rate": round((total_market - total_assessed) * city_rate),
        },
        "by_category": summary_cats,
    }

    output = {"parcels": parcels, "summary": summary}
    OUTPUT.write_text(json.dumps(output, indent=2))
    size_mb = OUTPUT.stat().st_size / 1_048_576
    print(f"\n→ {OUTPUT} ({size_mb:.1f} MB)")

    SUMMARY_OUTPUT.write_text(json.dumps(summary, indent=2))
    print(f"→ {SUMMARY_OUTPUT}")

    # Print results
    print(f"\n{'='*80}")
    print("PROP 13 IMPACT — OCEANSIDE PARCEL-LEVEL ANALYSIS")
    print(f"{'='*80}")

    t = summary["totals"]
    print(f"\n  Total assessed (Prop 13):  ${t['total_assessed']:>15,}")
    print(f"  Total market (estimated):  ${t['total_market']:>15,}")
    print(f"  Suppression ratio:         {t['aggregate_suppression']:.3f}")
    print(f"  Revenue gap at city rate:  ${t['prop13_at_current_rate']:>15,}")

    print(f"\n  {'Category':>15s} {'Parcels':>8s} {'Assessed':>13s} {'Market':>13s} "
          f"{'Suppr':>7s} {'Rev Gap':>12s}")
    print(f"  {'-'*15:>15s} {'-'*8:>8s} {'-'*13:>13s} {'-'*13:>13s} "
          f"{'-'*7:>7s} {'-'*12:>12s}")

    for c in summary_cats:
        rev_gap = c["revenue_gap"] * city_rate
        print(f"  {c['category']:>15s} {c['count']:>8,} ${c['total_assessed']:>12,} "
              f"${c['total_market']:>12,} {c['aggregate_suppression']:>6.2f}x "
              f"${rev_gap:>11,.0f}")

    # Prop 13 by era for key categories
    print(f"\n  SUPPRESSION BY SALE ERA:")
    for cat_data in summary_cats:
        if cat_data["category"] not in ("SFR", "Condo/TH", "MFR 21-100", "MFR 100+", "Commercial"):
            continue
        print(f"\n  {cat_data['category']}:")
        for era in ["pre-1990", "1990s", "2000s", "2010s", "2020s"]:
            e = cat_data["by_era"].get(era)
            if not e:
                continue
            gap = (e["market"] - e["assessed"]) * city_rate
            print(f"    {era:>10s}: {e['count']:>6,} parcels, "
                  f"suppression={e['suppression']:.2f}x, "
                  f"revenue gap=${gap:>10,.0f}")


if __name__ == "__main__":
    main()
