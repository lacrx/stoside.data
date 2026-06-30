#!/usr/bin/env python3
"""Download water, sewer, and storm drain pipe geometry from Oceanside GIS.

Source: gis.oceansideca.org ArcGIS Server (public, no auth required)

Services:
  - Water Mains: WaterOperations_WebService/MapServer/18 (31,275 features)
  - Sewer Mains: SewerOperationsWebService/MapServer/7 (13,352 features)
  - Storm Drains: WebService/MS4_all/FeatureServer/4 (count TBD)

All layers use EPSG:2230 (CA State Plane Zone 6, feet) natively.
Output as GeoJSON in EPSG:4326.
"""

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent.parent
RAW_DIR = HERE / "raw_data"

BASE_URL = "https://gis.oceansideca.org/gis/rest/services"

LAYERS = {
    "water": {
        "url": f"{BASE_URL}/WaterOperations_WebService/MapServer/18",
        "output": "water_mains_oceanside.geojson",
        "page_size": 2000,
        "fields": [
            "OBJECTID", "FACILITYID", "DIAMETER", "MATERIAL", "WATERTYPE",
            "TRANSMISS", "PRESSURECLASS", "ACTIVEFLAG", "OWNEDBY",
            "INSTALLYEAR", "Shape.STLength()",
        ],
    },
    "sewer": {
        "url": f"{BASE_URL}/SewerOperationsWebService/MapServer/7",
        "output": "sewer_mains_oceanside.geojson",
        "page_size": 2000,
        "fields": [
            "OBJECTID", "FACILITYID", "DIAMETER", "MATERIAL", "WATERTYPE",
            "FORCEMAIN", "ACTIVEFLAG", "OWNEDBY", "INSTALLYEAR",
            "FIELDLENGTH", "TRUNKLINE", "Shape.STLength()",
        ],
    },
    "storm": {
        "url": f"{BASE_URL}/WebService/MS4_all/FeatureServer/4",
        "output": "storm_drains_oceanside.geojson",
        "page_size": 1000,
        "fields": "*",
    },
}


def download_layer(name: str, config: dict) -> list[dict]:
    url = config["url"]
    page_size = config["page_size"]
    fields = config["fields"]

    count_params = urllib.parse.urlencode({
        "where": "1=1",
        "returnCountOnly": "true",
        "f": "json",
    })
    with urllib.request.urlopen(f"{url}/query?{count_params}", timeout=30) as resp:
        total = json.loads(resp.read())["count"]
    print(f"{name}: {total:,} features")

    out_fields = ",".join(fields) if isinstance(fields, list) else fields
    all_features = []
    offset = 0

    while offset < total:
        print(f"  fetching {offset:,}-{min(offset + page_size, total):,}...",
              end="", flush=True)
        params = urllib.parse.urlencode({
            "where": "1=1",
            "outFields": out_fields,
            "outSR": "4326",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": page_size,
        })
        with urllib.request.urlopen(f"{url}/query?{params}", timeout=120) as resp:
            page = json.loads(resp.read())

        features = page.get("features", [])
        if not features:
            break
        all_features.extend(features)
        print(f" got {len(features)}")
        offset += page_size
        time.sleep(0.3)

    return all_features


def save_geojson(features: list[dict], output_path: Path, name: str, url: str):
    geojson = {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "source": "City of Oceanside GIS (gis.oceansideca.org)",
            "service_url": url,
            "layer": name,
            "total_features": len(features),
        },
    }
    output_path.write_text(json.dumps(geojson))
    size_mb = output_path.stat().st_size / 1_048_576
    print(f"  → {output_path} ({size_mb:.1f} MB)")


def summarize(features: list[dict], name: str):
    diameters: dict[float, int] = {}
    materials: dict[str, int] = {}
    years: dict[int, int] = {}
    total_length = 0.0

    for f in features:
        p = f.get("properties", {})
        d = p.get("DIAMETER")
        if d:
            diameters[d] = diameters.get(d, 0) + 1
        m = p.get("MATERIAL")
        if m is not None:
            materials[str(m)] = materials.get(str(m), 0) + 1
        y = p.get("INSTALLYEAR")
        if y and y > 1900:
            decade = (y // 10) * 10
            years[decade] = years.get(decade, 0) + 1
        length = p.get("Shape.STLength()") or p.get("FIELDLENGTH") or p.get("Shape__Length") or 0
        total_length += float(length)

    print(f"\n  {name} summary:")
    print(f"    total pipe-feet: {total_length:,.0f} ({total_length / 5280:,.1f} miles)")

    if diameters:
        top = sorted(diameters.items(), key=lambda x: -x[1])[:8]
        diam_strs = [f'{d:.0f}"({c})' for d, c in top]
        print(f"    top diameters (inches): {', '.join(diam_strs)}")

    if years:
        sorted_decades = sorted(years.items())
        print(f"    by decade: {', '.join(f'{d}s({c})' for d, c in sorted_decades)}")


def main():
    parser = argparse.ArgumentParser(description="Download Oceanside pipe geometry")
    parser.add_argument("layers", nargs="*", default=["all"],
                        choices=["water", "sewer", "storm", "all"],
                        help="Which layers to download (default: all)")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    targets = list(LAYERS.keys()) if "all" in args.layers else args.layers

    for name in targets:
        config = LAYERS[name]
        output_path = RAW_DIR / config["output"]

        if output_path.exists():
            size_mb = output_path.stat().st_size / 1_048_576
            print(f"{name}: using cached {output_path} ({size_mb:.1f} MB)")
            with open(output_path) as f:
                data = json.load(f)
            summarize(data["features"], name)
            continue

        features = download_layer(name, config)
        save_geojson(features, output_path, name, config["url"])
        summarize(features, name)
        print()


if __name__ == "__main__":
    main()
