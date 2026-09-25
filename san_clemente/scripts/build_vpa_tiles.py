#!/usr/bin/env python3
"""Compute value-per-acre and export as PMTiles for the stoside frontend.

Reads parcels_san_clemente.geojson, computes VPA = total assessed value / acres,
and writes a PMTiles archive suitable for the choropleth-3d-maplibre component.

The output PMTiles file contains a single layer "parcels" with properties:
  - vpa: value per acre (integer)
  - apn: assessment number
  - addr: site address
  - lu: land use code
  - tav: total assessed value
  - acres: parcel acreage

Dependencies: geopandas, shapely, pmtiles
"""

import json
import math
import struct
import gzip
from io import BytesIO
from pathlib import Path

import geopandas as gpd
import numpy as np

HERE = Path(__file__).parent.parent
INPUT = HERE / "parcels_san_clemente.geojson"
OUTPUT_GEOJSON = HERE / "parcels_vpa.geojson"
FRONTEND_VIZ_DIR = Path(__file__).parent.parent.parent.parent / "stoside.frontend" / "src" / "assets" / "visualizations" / "san-clemente-vpa-3d"

# OC Assessor DQ (DataQuick/CoreLogic) land use codes.
# Mapped from actual San Clemente parcel data. Code 163 is the dominant
# SFR code in OC, not "Commercial - Office" as in SD county.
DQ_LAND_USE = {
    "100": "SFR",
    "133": "Condo/Townhome",
    "163": "SFR",
    "200": "Commercial",
    "211": "Multi-Family",
    "300": "Industrial/Institutional",
    "500": "Open Space/Agriculture",
    "601": "Government/Exempt",
    "999": "Miscellaneous",
    "RMOB": "Mobile Home (zoning)",
    "MREC": "Recreation (zoning)",
    "RMFD": "Multi-Family (zoning)",
    "RMSC": "Multi-Family (zoning)",
    "RCON": "Condo (zoning)",
}


def classify_land_use(code: str) -> str:
    if code in DQ_LAND_USE:
        return DQ_LAND_USE[code]
    if not code or code in ("None", ""):
        return "Unknown"
    code_int = int(code) if code.isdigit() else -1
    if 100 <= code_int < 200:
        return "Residential"
    if 200 <= code_int < 300:
        return "Commercial"
    if 300 <= code_int < 400:
        return "Industrial"
    if 400 <= code_int < 600:
        return "Open Space"
    if 600 <= code_int < 700:
        return "Government"
    return "Other"


def main():
    print("Loading parcels...")
    gdf = gpd.read_file(INPUT)
    print(f"  {len(gdf):,} parcels loaded")

    # Compute acreage from Shape__Area (sq ft) or from geometry
    if "Shape__Area" in gdf.columns:
        gdf["acres"] = gdf["Shape__Area"].fillna(0) / 43560
    else:
        # Approximate from WGS84 geometry at San Clemente latitude (~33.4)
        # 1 degree lat ~ 364,000 ft, 1 degree lon ~ 305,000 ft
        gdf["acres"] = gdf.geometry.area * 305000 * 364000 / 43560

    # Compute VPA
    gdf["tav"] = gdf["tav"].fillna(0).astype(float)
    gdf["acres"] = gdf["acres"].clip(lower=0.01)
    gdf["vpa"] = (gdf["tav"] / gdf["acres"]).round(0).astype(int)

    # Classify land use
    gdf["lu_code"] = gdf["UseDqLanduse"].fillna("0").astype(str)
    gdf["lu_cat"] = gdf["lu_code"].apply(classify_land_use)

    # Filter out zero-value parcels (government, exempt, etc.)
    valid = gdf[gdf["tav"] > 0].copy()
    print(f"  {len(valid):,} parcels with nonzero assessed value")

    # Summary stats
    print(f"\n  Median VPA: ${valid['vpa'].median():,.0f}")
    print(f"  Mean VPA:   ${valid['vpa'].mean():,.0f}")
    print(f"  Max VPA:    ${valid['vpa'].max():,.0f}")
    print(f"  Min VPA:    ${valid['vpa'].min():,.0f}")

    print("\n  By land use category:")
    for cat, group in valid.groupby("lu_cat"):
        print(f"    {cat:30s}: {len(group):>5,} parcels, median VPA ${group['vpa'].median():>12,.0f}")

    # Build output GeoJSON with minimal properties for the frontend
    out_features = []
    for _, row in valid.iterrows():
        props = {
            "vpa": int(row["vpa"]),
            "apn": row.get("AssessmentNo", ""),
            "addr": row.get("SiteAddress", ""),
            "lu": row.get("lu_cat", ""),
            "tav": int(row["tav"]),
            "acres": round(row["acres"], 3),
        }
        out_features.append({
            "type": "Feature",
            "geometry": row.geometry.__geo_interface__,
            "properties": props,
        })

    out_geojson = {
        "type": "FeatureCollection",
        "features": out_features,
    }

    OUTPUT_GEOJSON.write_text(json.dumps(out_geojson, separators=(",", ":")))
    size_mb = OUTPUT_GEOJSON.stat().st_size / 1_048_576
    print(f"\n-> {OUTPUT_GEOJSON} ({size_mb:.1f} MB)")

    # Copy GeoJSON to frontend viz directory for direct loading
    FRONTEND_VIZ_DIR.mkdir(parents=True, exist_ok=True)
    frontend_geojson = FRONTEND_VIZ_DIR / "analysis.geojson"
    import shutil
    shutil.copy2(OUTPUT_GEOJSON, frontend_geojson)
    print(f"-> {frontend_geojson} (copied to frontend)")

    # PMTiles conversion (optional, for production performance)
    pmtiles_out = FRONTEND_VIZ_DIR / "parcels.pmtiles"
    print(f"\nTo generate PMTiles for production, run:")
    print(f"  tippecanoe -o {pmtiles_out} \\")
    print(f"    --layer=parcels \\")
    print(f"    --minimum-zoom=10 --maximum-zoom=15 \\")
    print(f"    --no-feature-limit --no-tile-size-limit \\")
    print(f"    --coalesce-densest-as-needed \\")
    print(f"    --force \\")
    print(f"    {OUTPUT_GEOJSON}")


if __name__ == "__main__":
    main()
