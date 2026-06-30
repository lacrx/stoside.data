#!/usr/bin/env python3
"""Download Oceanside parcel data from SanGIS/SANDAG Regional Data Warehouse.

Official source: geo.sandag.org (authoritative SD County GIS data)
Full county: ~1.09M parcels, shapefile 439 MB
Filter: SITUS_JURIS = 'OC' for Oceanside (~64K parcels)

Two modes:
  --full: download full county shapefile (439 MB), filter locally (recommended)
  --api:  page through ArcGIS REST API for Oceanside-only GeoJSON (smaller download)
"""

import argparse
import json
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent.parent
RAW_DIR = HERE / "raw_data"
OUTPUT = HERE / "parcels_oceanside.geojson"

OFFICIAL_URL = "https://geo.sandag.org/server/rest/directories/downloads/Parcels_shapefile.zip"
OFFICIAL_REST = "https://geo.sandag.org/server/rest/services/Hosted/Parcels/FeatureServer/0"

FALLBACK_REST = (
    "https://services7.arcgis.com/3kQCXzNCo2WKILzp/arcgis/rest/services/"
    "SanGIS_Parcels/FeatureServer/0"
)

FIELDS = [
    "APN", "APN_8", "PARCELID",
    "SITUS_ADDR", "SITUS_STRE", "SITUS_SUFF", "SITUS_PRE_",
    "SITUS_COMM", "SITUS_ZIP", "SITUS_JURI",
    "ASR_LAND", "ASR_IMPR", "ASR_TOTAL",
    "ACREAGE", "ASR_LANDUS", "ASR_ZONE",
    "TRANUM", "TAXSTAT", "OWNEROCC",
    "UNITQTY", "TOTAL_LVG_", "BEDROOMS", "BATHS",
    "NUCLEUS_ZO", "NUCLEUS_US", "NUCLEUS_SI",
    "YEAR_EFFEC", "DOCDATE",
]

PAGE_SIZE = 2000


def download_api(service_url: str):
    """Page through ArcGIS REST API for Oceanside parcels only."""
    juris_field = "SITUS_JURIS" if "geo.sandag.org" in service_url else "SITUS_COMM"
    juris_value = "OC" if "geo.sandag.org" in service_url else "OCEANSIDE"

    count_params = urllib.parse.urlencode({
        "where": f"{juris_field}='{juris_value}'",
        "returnCountOnly": "true",
        "f": "json",
    })
    with urllib.request.urlopen(f"{service_url}/query?{count_params}", timeout=30) as resp:
        total = json.loads(resp.read())["count"]
    print(f"Oceanside parcels: {total:,}")

    all_features = []
    offset = 0
    while offset < total:
        print(f"  fetching {offset:,}-{min(offset + PAGE_SIZE, total):,}...", end="", flush=True)
        params = urllib.parse.urlencode({
            "where": f"{juris_field}='{juris_value}'",
            "outFields": ",".join(FIELDS),
            "outSR": "4326",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": PAGE_SIZE,
        })
        with urllib.request.urlopen(f"{service_url}/query?{params}", timeout=60) as resp:
            page = json.loads(resp.read())
        features = page.get("features", [])
        if not features:
            break
        all_features.extend(features)
        print(f" got {len(features)}")
        offset += PAGE_SIZE
        time.sleep(0.5)

    return all_features


def download_full_shapefile():
    """Download full county shapefile and filter with ogr2ogr."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = RAW_DIR / "Parcels_shapefile.zip"

    if not zip_path.exists():
        print(f"Downloading full county shapefile (439 MB)...")
        urllib.request.urlretrieve(OFFICIAL_URL, zip_path)
        print(f"  saved to {zip_path}")
    else:
        print(f"  using cached {zip_path}")

    print("Extracting Oceanside parcels with ogr2ogr...")
    subprocess.run([
        "ogr2ogr",
        "-f", "GeoJSON",
        str(OUTPUT),
        f"/vsizip/{zip_path}",
        "-where", "SITUS_JURIS='OC'",
        "-t_srs", "EPSG:4326",
    ], check=True)


def summarize(features: list[dict]):
    land_use_counts: dict[int, int] = {}
    total_assessed = 0
    zero_acreage = 0
    for f in features:
        p = f["properties"]
        lu = p.get("ASR_LANDUS", 0) or 0
        land_use_counts[lu] = land_use_counts.get(lu, 0) + 1
        total_assessed += p.get("ASR_TOTAL", 0) or 0
        if not p.get("ACREAGE"):
            zero_acreage += 1

    print(f"\nTotal assessed value: ${total_assessed:,.0f}")
    print(f"Parcels with zero/null acreage: {zero_acreage:,}")
    print(f"\nLand use distribution (top 15):")
    for lu, count in sorted(land_use_counts.items(), key=lambda x: -x[1])[:15]:
        print(f"  code {lu:3d}: {count:,} parcels")


def main():
    parser = argparse.ArgumentParser(description="Download Oceanside parcel data")
    parser.add_argument("--full", action="store_true",
                        help="Download full county shapefile (recommended)")
    parser.add_argument("--official", action="store_true",
                        help="Use official geo.sandag.org REST API")
    args = parser.parse_args()

    if args.full:
        download_full_shapefile()
        import geopandas as gpd
        gdf = gpd.read_file(OUTPUT)
        features = json.loads(gdf.to_json())["features"]
    else:
        service = OFFICIAL_REST if args.official else FALLBACK_REST
        print(f"Using: {service}")
        features = download_api(service)

        geojson = {
            "type": "FeatureCollection",
            "features": features,
            "metadata": {
                "source": "SanGIS/SANDAG Regional Data Warehouse",
                "service_url": service,
                "filter": "Oceanside parcels",
                "total_features": len(features),
            },
        }
        OUTPUT.write_text(json.dumps(geojson))

    size_mb = OUTPUT.stat().st_size / 1_048_576
    print(f"\n{len(features):,} parcels → {OUTPUT} ({size_mb:.1f} MB)")
    summarize(features)


if __name__ == "__main__":
    main()
