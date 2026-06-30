#!/usr/bin/env python3
"""Attribute water and sewer infrastructure costs to parcels.

Methodology:
  1. Load pipe geometry (water mains + sewer mains from Oceanside GIS)
  2. Compute annual replacement cost per pipe segment:
     replacement_cost = length_ft × cost_per_lf(diameter)
     annual_cost = replacement_cost / useful_life(material)
  3. Buffer each pipe segment by 150ft, find intersecting parcels
  4. Attribute pipe cost to parcels proportional to boundary intersection length
  5. Add EDU-based operating cost allocation
  6. Output: water + sewer cost per parcel

Inputs:
  - fiscal_analysis/raw_data/water_mains_oceanside.geojson (31,275 segments)
  - fiscal_analysis/raw_data/sewer_mains_oceanside.geojson (13,352 segments)
  - fiscal_analysis/parcels_oceanside.geojson (61,795 parcels)

Outputs:
  - fiscal_analysis/water_sewer_costs_by_parcel.json
  - fiscal_analysis/water_sewer_cost_summary.json
"""

import json
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely.strtree import STRtree

HERE = Path(__file__).parent.parent
WATER_FILE = HERE / "raw_data" / "water_mains_oceanside.geojson"
SEWER_FILE = HERE / "raw_data" / "sewer_mains_oceanside.geojson"
PARCELS_FILE = HERE / "parcels_oceanside.geojson"
OUTPUT = HERE / "water_sewer_costs_by_parcel.json"
SUMMARY_OUTPUT = HERE / "water_sewer_cost_summary.json"

BUFFER_FT = 150

# Pipe replacement cost per linear foot by diameter (inches)
# Source: RSMeans 2023, AWWA M28, adjusted for Southern California
WATER_COST_PER_LF = {
    2: 45, 4: 55, 6: 70, 8: 90, 10: 110, 12: 135,
    14: 160, 16: 190, 18: 220, 20: 250, 24: 310,
    30: 400, 36: 500, 42: 620, 48: 750,
}

SEWER_COST_PER_LF = {
    6: 65, 8: 85, 10: 105, 12: 130, 15: 170,
    18: 210, 21: 260, 24: 310, 27: 360, 30: 420,
    36: 520, 42: 640, 48: 780,
}

# Useful life by material code (from Oceanside GIS coded domains)
# Water: MATERIAL field is integer code
WATER_MATERIAL_LIFE = {
    1: 80,   # Cast Iron
    2: 80,   # Ductile Iron
    3: 100,  # PVC
    4: 80,   # Steel
    5: 75,   # Asbestos Cement
    6: 100,  # HDPE
    7: 80,   # Copper
    8: 75,   # Concrete
}
DEFAULT_WATER_LIFE = 80

# Sewer: MATERIAL field is also integer code
SEWER_MATERIAL_LIFE = {
    1: 75,   # Clay/VCP
    2: 100,  # PVC
    3: 80,   # Concrete
    4: 70,   # Cast Iron
    5: 80,   # Ductile Iron
    6: 100,  # HDPE
    7: 60,   # ABS
    8: 75,   # Reinforced Concrete
}
DEFAULT_SEWER_LIFE = 75

# EDU (Equivalent Dwelling Unit) multipliers for operating cost allocation
# SFR = 1.0 EDU baseline
EDU_BY_LAND_USE = {
    "SFR": 1.0,
    "MFR": 0.7,
    "Commercial": 1.5,
    "Industrial": 2.0,
    "Mixed Use": 1.0,
    "Agricultural": 0.5,
    "Institutional": 1.5,
    "Government": 1.0,
    "Recreation": 0.3,
    "Vacant": 0.0,
    "Open Space": 0.0,
    "Common Area": 0.0,
    "Exempt": 0.0,
    "Other": 0.5,
    "Unknown": 0.5,
}

# Annual O&M per EDU (estimated from typical CA utility budgets)
# Oceanside Water Utilities serves ~44K connections
# Typical water O&M: $400-600/connection/yr, sewer: $300-500/connection/yr
WATER_OM_PER_EDU = 500
SEWER_OM_PER_EDU = 400

LAND_USE_BROAD = {
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


def interpolate_cost(diameter: float, cost_table: dict) -> float:
    if diameter <= 0:
        return 0
    sizes = sorted(cost_table.keys())
    if diameter <= sizes[0]:
        return cost_table[sizes[0]]
    if diameter >= sizes[-1]:
        return cost_table[sizes[-1]] * (diameter / sizes[-1]) ** 1.3
    for i in range(len(sizes) - 1):
        if sizes[i] <= diameter <= sizes[i + 1]:
            frac = (diameter - sizes[i]) / (sizes[i + 1] - sizes[i])
            return cost_table[sizes[i]] + frac * (cost_table[sizes[i + 1]] - cost_table[sizes[i]])
    return cost_table[sizes[-1]]


def load_pipes(path: Path, cost_table: dict, material_life: dict,
               default_life: int) -> gpd.GeoDataFrame:
    print(f"Loading {path.name}...")
    gdf = gpd.read_file(path)
    print(f"  {len(gdf):,} segments loaded")

    gdf = gdf[gdf.geometry.notnull()].copy()
    active_field = "ACTIVEFLAG" if "ACTIVEFLAG" in gdf.columns else "Status"
    if active_field in gdf.columns:
        active_count = len(gdf)
        gdf = gdf[gdf[active_field] == 1].copy()
        print(f"  {len(gdf):,} active (filtered {active_count - len(gdf)} inactive)")

    projected = gdf.to_crs("EPSG:2230")

    diam_field = "DIAMETER" if "DIAMETER" in gdf.columns else "Diam_Ht"
    mat_field = "MATERIAL" if "MATERIAL" in gdf.columns else "Material"

    diameters = projected[diam_field].fillna(8).astype(float)
    materials = projected[mat_field].fillna(0)

    lengths_ft = projected.geometry.length

    costs_per_lf = diameters.apply(lambda d: interpolate_cost(d, cost_table))
    replacement_costs = lengths_ft * costs_per_lf

    def get_life(mat_val):
        if isinstance(mat_val, (int, float)) and not np.isnan(mat_val):
            return material_life.get(int(mat_val), default_life)
        return default_life

    useful_lives = materials.apply(get_life)
    annual_costs = replacement_costs / useful_lives

    projected["length_ft"] = lengths_ft
    projected["diameter"] = diameters
    projected["replacement_cost"] = replacement_costs
    projected["useful_life"] = useful_lives
    projected["annual_cost"] = annual_costs

    total_miles = lengths_ft.sum() / 5280
    total_replacement = replacement_costs.sum()
    total_annual = annual_costs.sum()
    print(f"  {total_miles:,.1f} miles, ${total_replacement:,.0f} replacement value, "
          f"${total_annual:,.0f}/yr annualized")

    return projected


def attribute_pipes_to_parcels(
    pipes: gpd.GeoDataFrame,
    parcels_proj: gpd.GeoDataFrame,
    label: str,
) -> dict[int, float]:
    """Attribute pipe costs to parcels by proximity/frontage."""
    print(f"\nAttributing {label} costs to parcels...")

    parcel_geoms = parcels_proj.geometry.values
    parcel_tree = STRtree(parcel_geoms)

    parcel_costs: dict[int, float] = defaultdict(float)
    attributed = 0
    skipped = 0

    total_pipes = len(pipes)
    report_interval = max(1, total_pipes // 20)

    for i, (_, pipe) in enumerate(pipes.iterrows()):
        if i % report_interval == 0:
            print(f"  {i:,}/{total_pipes:,} segments processed...", flush=True)

        geom = pipe.geometry
        if geom is None or geom.is_empty:
            skipped += 1
            continue

        buffer = geom.buffer(BUFFER_FT)
        candidate_idxs = parcel_tree.query(buffer)

        if len(candidate_idxs) == 0:
            skipped += 1
            continue

        intersections = []
        for idx in candidate_idxs:
            parcel_geom = parcel_geoms[idx]
            if buffer.intersects(parcel_geom):
                boundary = parcel_geom.boundary
                overlap = buffer.intersection(boundary).length
                if overlap > 0:
                    intersections.append((idx, overlap))

        if not intersections:
            skipped += 1
            continue

        total_overlap = sum(length for _, length in intersections)
        for idx, overlap in intersections:
            share = overlap / total_overlap
            parcel_costs[idx] += pipe.annual_cost * share

        attributed += 1

    print(f"  {attributed:,} pipes attributed, {skipped:,} skipped (no nearby parcels)")
    return dict(parcel_costs)


def compute_edu_costs(parcels_gdf: gpd.GeoDataFrame) -> tuple[dict[int, float], dict[int, float]]:
    """Compute EDU-based operating costs per parcel."""
    print("\nComputing EDU-based operating costs...")

    water_costs: dict[int, float] = {}
    sewer_costs: dict[int, float] = {}

    land_use_col = None
    for col in ["land_use_broad", "LAND_USE_BROAD"]:
        if col in parcels_gdf.columns:
            land_use_col = col
            break

    units_col = None
    for col in ["UNITQTY", "units"]:
        if col in parcels_gdf.columns:
            units_col = col
            break

    sqft_col = None
    for col in ["TOTAL_LVG_", "living_sqft"]:
        if col in parcels_gdf.columns:
            sqft_col = col
            break

    for i, row in parcels_gdf.iterrows():
        if land_use_col:
            lu = row[land_use_col] or "Unknown"
        else:
            lu = "Unknown"

        edu_mult = EDU_BY_LAND_USE.get(lu, 0.5)

        if edu_mult == 0:
            water_costs[i] = 0
            sewer_costs[i] = 0
            continue

        units = 1
        if units_col and row[units_col] and row[units_col] > 0:
            units = int(row[units_col])

        if lu in ("Commercial", "Industrial", "Institutional", "Government"):
            sqft = 0
            if sqft_col and row[sqft_col]:
                sqft = float(row[sqft_col])
            if sqft > 0:
                edu = edu_mult * (sqft / 1000)
            else:
                edu = edu_mult
        else:
            edu = edu_mult * units

        water_costs[i] = edu * WATER_OM_PER_EDU
        sewer_costs[i] = edu * SEWER_OM_PER_EDU

    total_water = sum(water_costs.values())
    total_sewer = sum(sewer_costs.values())
    print(f"  Water O&M total: ${total_water:,.0f}/yr")
    print(f"  Sewer O&M total: ${total_sewer:,.0f}/yr")

    return water_costs, sewer_costs


def main():
    print("Loading parcels...")
    parcels = gpd.read_file(PARCELS_FILE)
    print(f"  {len(parcels):,} parcels")

    parcels = add_land_use_broad(parcels)

    parcels_proj = parcels.to_crs("EPSG:2230")

    water_pipes = load_pipes(WATER_FILE, WATER_COST_PER_LF,
                             WATER_MATERIAL_LIFE, DEFAULT_WATER_LIFE)
    sewer_pipes = load_pipes(SEWER_FILE, SEWER_COST_PER_LF,
                             SEWER_MATERIAL_LIFE, DEFAULT_SEWER_LIFE)

    water_capital = attribute_pipes_to_parcels(water_pipes, parcels_proj, "water")
    sewer_capital = attribute_pipes_to_parcels(sewer_pipes, parcels_proj, "sewer")

    water_om, sewer_om = compute_edu_costs(parcels)

    print("\nBuilding per-parcel output...")
    sq_ft_per_acre = 43560
    parcels_proj_areas = parcels_proj.geometry.area

    geom_hashes = parcels_proj.geometry.apply(
        lambda g: hash(g.wkb) if g is not None else None
    )
    units_per_geom = geom_hashes.groupby(geom_hashes).transform("count")
    parcel_acres = (parcels_proj_areas / sq_ft_per_acre) / units_per_geom

    per_parcel = []
    total_water_cap = 0
    total_sewer_cap = 0
    total_water_om_sum = 0
    total_sewer_om_sum = 0

    for i in range(len(parcels)):
        w_cap = water_capital.get(i, 0)
        s_cap = sewer_capital.get(i, 0)
        w_om = water_om.get(i, 0)
        s_om = sewer_om.get(i, 0)
        w_total = w_cap + w_om
        s_total = s_cap + s_om
        acres = float(parcel_acres.iloc[i])

        total_water_cap += w_cap
        total_sewer_cap += s_cap
        total_water_om_sum += w_om
        total_sewer_om_sum += s_om

        per_parcel.append({
            "apn": parcels.iloc[i].get("APN", ""),
            "water_capital": round(w_cap, 2),
            "water_om": round(w_om, 2),
            "water_total": round(w_total, 2),
            "sewer_capital": round(s_cap, 2),
            "sewer_om": round(s_om, 2),
            "sewer_total": round(s_total, 2),
            "utility_total": round(w_total + s_total, 2),
            "utility_per_acre": round((w_total + s_total) / acres, 2) if acres > 0.001 else 0,
        })

    summary = {
        "methodology": {
            "capital_attribution": "buffer pipe segments 150ft, attribute by parcel boundary intersection length",
            "capital_cost_basis": "RSMeans 2023 replacement cost per LF by diameter, annualized over useful life by material",
            "operating_attribution": "EDU (equivalent dwelling unit) by land use type",
            "water_om_per_edu": WATER_OM_PER_EDU,
            "sewer_om_per_edu": SEWER_OM_PER_EDU,
            "buffer_ft": BUFFER_FT,
            "note": "Does not include stormwater. O&M rates are estimates pending actual utility budget data.",
        },
        "totals": {
            "water_capital_annual": round(total_water_cap),
            "water_om_annual": round(total_water_om_sum),
            "water_total_annual": round(total_water_cap + total_water_om_sum),
            "sewer_capital_annual": round(total_sewer_cap),
            "sewer_om_annual": round(total_sewer_om_sum),
            "sewer_total_annual": round(total_sewer_cap + total_sewer_om_sum),
            "combined_annual": round(total_water_cap + total_water_om_sum + total_sewer_cap + total_sewer_om_sum),
            "parcels_with_water_cost": sum(1 for p in per_parcel if p["water_total"] > 0),
            "parcels_with_sewer_cost": sum(1 for p in per_parcel if p["sewer_total"] > 0),
        },
        "pipe_inventory": {
            "water_segments": len(water_pipes),
            "water_miles": round(float(water_pipes["length_ft"].sum()) / 5280, 1),
            "water_replacement_value": round(float(water_pipes["replacement_cost"].sum())),
            "sewer_segments": len(sewer_pipes),
            "sewer_miles": round(float(sewer_pipes["length_ft"].sum()) / 5280, 1),
            "sewer_replacement_value": round(float(sewer_pipes["replacement_cost"].sum())),
        },
    }

    # By land use breakdown
    lu_stats: dict[str, dict] = defaultdict(lambda: {
        "count": 0, "water_total": 0, "sewer_total": 0, "acres": 0,
    })
    for i, p in enumerate(per_parcel):
        lu = "Unknown"
        if "land_use_broad" in parcels.columns:
            lu = parcels.iloc[i].get("land_use_broad", "Unknown") or "Unknown"
        stats = lu_stats[lu]
        stats["count"] += 1
        stats["water_total"] += p["water_total"]
        stats["sewer_total"] += p["sewer_total"]
        stats["acres"] += float(parcel_acres.iloc[i])

    by_land_use = []
    for cat, stats in lu_stats.items():
        combined = stats["water_total"] + stats["sewer_total"]
        by_land_use.append({
            "category": cat,
            "count": stats["count"],
            "total_acres": round(stats["acres"], 1),
            "water_annual": round(stats["water_total"]),
            "sewer_annual": round(stats["sewer_total"]),
            "combined_annual": round(combined),
            "cost_per_acre": round(combined / stats["acres"]) if stats["acres"] > 0.001 else 0,
        })
    by_land_use.sort(key=lambda x: -x["cost_per_acre"])
    summary["by_land_use"] = by_land_use

    output = {"summary": summary, "parcels": per_parcel}
    OUTPUT.write_text(json.dumps(output, indent=2))
    size_mb = OUTPUT.stat().st_size / 1_048_576
    print(f"\n→ {OUTPUT} ({size_mb:.1f} MB)")

    SUMMARY_OUTPUT.write_text(json.dumps(summary, indent=2))
    print(f"→ {SUMMARY_OUTPUT}")

    print(f"\n{'=' * 60}")
    t = summary["totals"]
    print(f"Water: ${t['water_capital_annual']:,}/yr capital + ${t['water_om_annual']:,}/yr O&M = ${t['water_total_annual']:,}/yr")
    print(f"Sewer: ${t['sewer_capital_annual']:,}/yr capital + ${t['sewer_om_annual']:,}/yr O&M = ${t['sewer_total_annual']:,}/yr")
    print(f"Combined: ${t['combined_annual']:,}/yr")
    print(f"\nParcels with water cost: {t['parcels_with_water_cost']:,}")
    print(f"Parcels with sewer cost: {t['parcels_with_sewer_cost']:,}")

    inv = summary["pipe_inventory"]
    print(f"\nWater: {inv['water_segments']:,} segments, {inv['water_miles']} mi, ${inv['water_replacement_value']:,} replacement")
    print(f"Sewer: {inv['sewer_segments']:,} segments, {inv['sewer_miles']} mi, ${inv['sewer_replacement_value']:,} replacement")

    print(f"\nBy land use ($/acre):")
    for cat in by_land_use:
        print(f"  {cat['category']:20s}  {cat['count']:>6,} parcels  "
              f"{cat['total_acres']:>8,.1f} ac  "
              f"${cat['cost_per_acre']:>8,}/ac")


def add_land_use_broad(gdf):
    """Add land_use_broad column from ASR_LANDUS code."""
    gdf = gdf.copy()
    codes = gdf["ASR_LANDUS"].fillna(0).astype(int)
    gdf["land_use_broad"] = codes.map(LAND_USE_BROAD).fillna("Unknown")
    return gdf


if __name__ == "__main__":
    main()
