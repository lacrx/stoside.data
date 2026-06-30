#!/usr/bin/env python3
"""Compute revenue per acre for Oceanside parcels.

Inputs:
  - parcels_oceanside.geojson (from download_parcels.py)

Revenue model:
  - Property tax = assessed_value × 1% × city_share
  - City share of base 1% levy ≈ 16% (typical CA city, varies by TRA)
  - We use 16% as default; can refine with actual TRA rates later

Outputs:
  - revenue_per_acre.json: per-parcel revenue metrics
  - revenue_summary.json: aggregated by land use type
"""

import json
from pathlib import Path

import geopandas as gpd
import numpy as np

HERE = Path(__file__).parent.parent
INPUT = HERE / "parcels_oceanside.geojson"
OUTPUT = HERE / "revenue_per_acre.json"
SUMMARY_OUTPUT = HERE / "revenue_summary.json"

CITY_SHARE_OF_1PCT = 0.16

# SD County Assessor land use codes → readable categories
LAND_USE_MAP = {
    0: "Vacant / Unknown",
    6: "Commercial - Vacant",
    7: "Industrial / Utility",
    9: "Vacant Residential",
    10: "SFR - Large Lot / Rural",
    11: "SFR - Standard",
    12: "SFR - Mobile Home",
    13: "Duplex / Triplex",
    14: "Fourplex",
    15: "5-15 Units",
    16: "16-60 Units",
    17: "Condo / Townhome",
    18: "61+ Units",
    19: "Mixed Use Residential",
    20: "Commercial - General",
    21: "Commercial - Retail",
    22: "Commercial - Shopping Center",
    24: "Commercial - Office",
    25: "Commercial - Hotel/Motel",
    26: "Commercial - Auto",
    27: "Commercial - Restaurant",
    28: "Commercial - Service Station",
    29: "Commercial - Medical",
    30: "Industrial - Light",
    31: "Industrial - Heavy",
    32: "Industrial - Warehouse",
    33: "Industrial - Food Processing",
    34: "Industrial - High Tech",
    35: "Industrial - Other",
    36: "Industrial - Mini-Storage",
    37: "Industrial - Lumber Yard",
    38: "Industrial - Sand/Gravel",
    39: "Industrial - Mixed",
    40: "Agricultural - General",
    41: "Agricultural - Irrigated",
    43: "Agricultural - Dry Farm",
    44: "Agricultural - Livestock",
    45: "Agricultural - Poultry",
    46: "Agricultural - Orchard",
    47: "Agricultural - Nursery",
    49: "Agricultural - Other",
    50: "Institutional - General",
    51: "Institutional - Hospital",
    52: "Institutional - School",
    54: "Institutional - Military",
    57: "Institutional - Church",
    58: "Institutional - Cemetery",
    59: "Institutional - Other",
    61: "Recreational - General",
    62: "Recreational - Golf Course",
    70: "Government - Federal",
    71: "Government - State",
    72: "Government - County",
    73: "Government - City",
    75: "Government - Utility",
    76: "Government - Military",
    77: "Government - Public School",
    79: "Government - Other",
    80: "Open Space / Park",
    81: "Open Space - Preserved",
    82: "Open Space - Creek/Flood",
    83: "Open Space - Other",
    84: "Open Space - Road ROW",
    85: "Open Space - Water",
    86: "Common Area / HOA",
    88: "Exempt - Government",
    89: "Exempt - Other",
    90: "Miscellaneous",
}

LAND_USE_BROAD = {
    0: "Vacant",
    6: "Commercial",
    7: "Industrial",
    9: "Vacant",
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
    86: "Common Area",
    88: "Exempt", 89: "Exempt",
    90: "Other",
}

SQ_METERS_PER_ACRE = 4046.86


def compute_acreage(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Compute acreage from polygon geometry, fixing condo stacking.

    Condos share polygon boundaries — N units all have the same polygon
    representing the complex footprint. Naively computing area gives
    N × complex_area instead of per-unit land share. Fix: group by
    geometry hash, divide polygon area by number of units sharing it.
    """
    projected = gdf.to_crs("EPSG:2230")  # CA State Plane Zone 6, feet
    sq_feet = projected.geometry.area
    gdf = gdf.copy()
    gdf["computed_acres_raw"] = sq_feet / 43560

    gdf["geom_hash"] = projected.geometry.apply(
        lambda g: hash(g.wkb) if g is not None else None
    )
    units_per_geom = gdf.groupby("geom_hash")["geom_hash"].transform("count")
    gdf["computed_acres"] = gdf["computed_acres_raw"] / units_per_geom

    gdf["acres"] = gdf.apply(
        lambda r: r["ACREAGE"] if r["ACREAGE"] and r["ACREAGE"] > 0
        else r["computed_acres"],
        axis=1,
    )
    gdf["condo_stacked"] = units_per_geom > 1
    return gdf


def compute_property_tax(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Compute estimated city property tax revenue per parcel."""
    gdf = gdf.copy()
    gdf["asr_total"] = gdf["ASR_TOTAL"].fillna(0).astype(float)
    gdf["property_tax_city"] = gdf["asr_total"] * 0.01 * CITY_SHARE_OF_1PCT
    return gdf


def add_land_use_labels(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf.copy()
    gdf["land_use_code"] = gdf["ASR_LANDUS"].fillna(0).astype(int)
    gdf["land_use"] = gdf["land_use_code"].map(LAND_USE_MAP).fillna("Unknown")
    gdf["land_use_broad"] = gdf["land_use_code"].map(LAND_USE_BROAD).fillna("Unknown")
    return gdf


def compute_revenue_per_acre(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf.copy()
    gdf["revenue_per_acre"] = np.where(
        gdf["acres"] > 0.001,
        gdf["property_tax_city"] / gdf["acres"],
        0,
    )
    gdf["assessed_per_acre"] = np.where(
        gdf["acres"] > 0.001,
        gdf["asr_total"] / gdf["acres"],
        0,
    )
    return gdf


def build_summary(gdf: gpd.GeoDataFrame) -> dict:
    taxable = gdf[
        (gdf["TAXSTAT"] == "T") &
        (gdf["asr_total"] > 0) &
        (gdf["acres"] > 0.001)
    ]

    total_stats = {
        "total_parcels": len(gdf),
        "taxable_parcels": len(taxable),
        "total_assessed_value": float(taxable["asr_total"].sum()),
        "total_acres": float(taxable["acres"].sum()),
        "total_city_property_tax": float(taxable["property_tax_city"].sum()),
        "avg_revenue_per_acre": float(taxable["revenue_per_acre"].mean()),
        "median_revenue_per_acre": float(taxable["revenue_per_acre"].median()),
    }

    by_broad = []
    for cat, group in taxable.groupby("land_use_broad"):
        by_broad.append({
            "category": cat,
            "count": len(group),
            "total_acres": round(float(group["acres"].sum()), 1),
            "total_assessed": round(float(group["asr_total"].sum())),
            "total_tax_revenue": round(float(group["property_tax_city"].sum())),
            "avg_assessed_per_acre": round(float(group["assessed_per_acre"].mean())),
            "median_assessed_per_acre": round(float(group["assessed_per_acre"].median())),
            "avg_revenue_per_acre": round(float(group["revenue_per_acre"].mean())),
            "median_revenue_per_acre": round(float(group["revenue_per_acre"].median())),
            "avg_lot_size_acres": round(float(group["acres"].mean()), 3),
        })
    by_broad.sort(key=lambda x: -x["median_revenue_per_acre"])

    percentiles = {}
    for p in [10, 25, 50, 75, 90, 95, 99]:
        percentiles[f"p{p}"] = round(float(np.percentile(taxable["revenue_per_acre"], p)))

    return {
        "methodology": {
            "revenue_type": "property_tax_only",
            "city_share_of_1pct": CITY_SHARE_OF_1PCT,
            "note": "Does not include sales tax, TOT, franchise fees, or special assessments",
            "acreage_source": "computed from polygon geometry (EPSG:2230 CA State Plane 6)",
        },
        "totals": total_stats,
        "revenue_per_acre_distribution": percentiles,
        "by_land_use": by_broad,
    }


def main():
    print("Loading parcels...")
    gdf = gpd.read_file(INPUT)
    print(f"  {len(gdf):,} parcels loaded")

    print("Computing acreage from geometry...")
    gdf = compute_acreage(gdf)

    print("Computing property tax revenue...")
    gdf = compute_property_tax(gdf)
    gdf = add_land_use_labels(gdf)
    gdf = compute_revenue_per_acre(gdf)

    print("Building summary...")
    summary = build_summary(gdf)

    per_parcel = []
    for _, row in gdf.iterrows():
        per_parcel.append({
            "apn": row["APN"],
            "address": f"{int(row['SITUS_ADDR'] or 0)} {row['SITUS_STRE'] or ''}".strip(),
            "land_use": row["land_use"],
            "land_use_broad": row["land_use_broad"],
            "land_use_code": int(row["land_use_code"]),
            "acres": round(float(row["acres"]), 4),
            "assessed_land": int(row["ASR_LAND"] or 0),
            "assessed_improvement": int(row["ASR_IMPR"] or 0),
            "assessed_total": int(row["asr_total"]),
            "property_tax_city": round(float(row["property_tax_city"]), 2),
            "revenue_per_acre": round(float(row["revenue_per_acre"]), 2),
            "assessed_per_acre": round(float(row["assessed_per_acre"]), 2),
            "tax_rate_area": row["TRANUM"],
            "taxable": row["TAXSTAT"] == "T",
            "units": int(row["UNITQTY"] or 0),
            "living_sqft": int(row["TOTAL_LVG_"] or 0),
        })

    output = {
        "summary": summary,
        "parcels": per_parcel,
    }
    OUTPUT.write_text(json.dumps(output, indent=2))
    size_mb = OUTPUT.stat().st_size / 1_048_576
    print(f"\n→ {OUTPUT} ({size_mb:.1f} MB)")

    SUMMARY_OUTPUT.write_text(json.dumps(summary, indent=2))
    print(f"→ {SUMMARY_OUTPUT}")

    print(f"\n{'=' * 60}")
    t = summary["totals"]
    print(f"Taxable parcels: {t['taxable_parcels']:,} of {t['total_parcels']:,}")
    print(f"Total assessed: ${t['total_assessed_value']:,.0f}")
    print(f"Total acres: {t['total_acres']:,.1f}")
    print(f"Est. city property tax: ${t['total_city_property_tax']:,.0f}")
    print(f"Avg revenue/acre: ${t['avg_revenue_per_acre']:,.0f}")
    print(f"Median revenue/acre: ${t['median_revenue_per_acre']:,.0f}")

    print(f"\nRevenue per acre distribution:")
    for k, v in summary["revenue_per_acre_distribution"].items():
        print(f"  {k}: ${v:,}")

    print(f"\nBy land use (median $/acre):")
    for cat in summary["by_land_use"]:
        print(f"  {cat['category']:20s}  {cat['count']:>6,} parcels  "
              f"{cat['total_acres']:>8,.1f} ac  "
              f"median ${cat['median_revenue_per_acre']:>8,}/ac")


if __name__ == "__main__":
    main()
