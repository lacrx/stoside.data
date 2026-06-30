#!/usr/bin/env python3
"""Download street centerline data from SanGIS/SANDAG Regional Data Warehouse.

Source: Roads_All — 164,675 street centerline segments, county-wide
Download: https://geo.sandag.org/server/rest/directories/downloads/Roads_All_shapefile.zip
Filter locally to Oceanside using jurisdiction field.
"""

import subprocess
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent.parent
RAW_DIR = HERE / "raw_data"
OUTPUT = HERE / "raw_data" / "streets_oceanside.geojson"

DOWNLOAD_URL = "https://geo.sandag.org/server/rest/directories/downloads/Roads_All_shapefile.zip"


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = RAW_DIR / "Roads_All_shapefile.zip"

    if not zip_path.exists():
        print(f"Downloading Roads_All shapefile (103 MB)...")
        urllib.request.urlretrieve(DOWNLOAD_URL, zip_path)
        size_mb = zip_path.stat().st_size / 1_048_576
        print(f"  saved: {zip_path} ({size_mb:.1f} MB)")
    else:
        size_mb = zip_path.stat().st_size / 1_048_576
        print(f"  using cached: {zip_path} ({size_mb:.1f} MB)")

    print("Listing layers in shapefile...")
    result = subprocess.run(
        ["ogrinfo", "-so", f"/vsizip/{zip_path}"],
        capture_output=True, text=True,
    )
    print(result.stdout[:500])

    layer = None
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped and stripped[0].isdigit() and ":" in stripped:
            # Format: "1: Roads_All (3D Line String)"
            after_colon = stripped.split(":", 1)[1].strip()
            layer = after_colon.split("(")[0].strip()
            break

    if not layer:
        layer = "Roads_All"

    print(f"Using layer: {layer}")
    print(f"Extracting Oceanside streets...")

    subprocess.run([
        "ogr2ogr",
        "-f", "GeoJSON",
        str(OUTPUT),
        f"/vsizip/{zip_path}",
        layer,
        "-where", "LJURISDIC='OC' OR RJURISDIC='OC'",
        "-t_srs", "EPSG:4326",
    ], check=True)

    size_mb = OUTPUT.stat().st_size / 1_048_576
    print(f"\n→ {OUTPUT} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
