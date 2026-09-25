#!/usr/bin/env python3
"""Download San Clemente parcel data from OC Treasurer-Tax Collector.

Source: OC Treasurer-Tax Collector Secured Property Tax Information
Endpoint: https://ocgis.com/arcpub/rest/services/Treasurer_Tax_Collector/
          Secured_Property_Tax_Information/FeatureServer/0

San Clemente parcels use APN book prefixes 688, 690, 691, 692.
Approximately 9,600 parcels total.

The service returns geometry in CA State Plane Zone 6 (feet, WKID 2230).
We request output in WGS84 (4326) for web mapping.
"""

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent.parent
OUTPUT = HERE / "parcels_san_clemente.geojson"

SERVICE_URL = (
    "https://ocgis.com/arcpub/rest/services/Treasurer_Tax_Collector/"
    "Secured_Property_Tax_Information/FeatureServer/0"
)

SC_APN_PREFIXES = ["688", "690", "691", "692"]
WHERE_CLAUSE = " OR ".join(f"AssessmentNo LIKE '{p}-%'" for p in SC_APN_PREFIXES)

FIELDS = [
    "AssessmentNo", "APN2", "SiteAddress",
    "UseDqLanduse", "tav", "alv", "aiv", "ta",
    "Shape__Area",
]

PAGE_SIZE = 1000


def get_count() -> int:
    params = urllib.parse.urlencode({
        "where": WHERE_CLAUSE,
        "returnCountOnly": "true",
        "f": "json",
    })
    with urllib.request.urlopen(f"{SERVICE_URL}/query?{params}", timeout=30) as resp:
        return json.loads(resp.read())["count"]


def download_pages(total: int) -> list[dict]:
    all_features = []
    offset = 0
    while offset < total:
        end = min(offset + PAGE_SIZE, total)
        print(f"  fetching {offset:,}-{end:,}...", end="", flush=True)
        params = urllib.parse.urlencode({
            "where": WHERE_CLAUSE,
            "outFields": ",".join(FIELDS),
            "outSR": "4326",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": PAGE_SIZE,
        })
        with urllib.request.urlopen(f"{SERVICE_URL}/query?{params}", timeout=60) as resp:
            page = json.loads(resp.read())
        features = page.get("features", [])
        if not features:
            print(" (empty page, stopping)")
            break
        all_features.extend(features)
        print(f" got {len(features)}")
        offset += PAGE_SIZE
        time.sleep(0.3)
    return all_features


def summarize(features: list[dict]):
    land_use_counts: dict[str, int] = {}
    total_assessed = 0
    zero_area = 0
    for f in features:
        p = f["properties"]
        lu = str(p.get("UseDqLanduse", ""))
        land_use_counts[lu] = land_use_counts.get(lu, 0) + 1
        total_assessed += p.get("tav", 0) or 0
        area = p.get("Shape__Area", 0) or 0
        if area == 0:
            zero_area += 1

    print(f"\nTotal assessed value: ${total_assessed:,.0f}")
    print(f"Parcels with zero/null area: {zero_area:,}")
    print(f"\nLand use distribution (top 15):")
    for lu, count in sorted(land_use_counts.items(), key=lambda x: -x[1])[:15]:
        print(f"  code {lu:>5s}: {count:,} parcels")


def main():
    print(f"Querying San Clemente parcels (prefixes: {', '.join(SC_APN_PREFIXES)})...")
    total = get_count()
    print(f"San Clemente parcels: {total:,}")

    features = download_pages(total)

    geojson = {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "source": "OC Treasurer-Tax Collector FeatureServer",
            "service_url": SERVICE_URL,
            "filter": f"San Clemente (APN prefixes {', '.join(SC_APN_PREFIXES)})",
            "total_features": len(features),
        },
    }
    OUTPUT.write_text(json.dumps(geojson))

    size_mb = OUTPUT.stat().st_size / 1_048_576
    print(f"\n{len(features):,} parcels -> {OUTPUT} ({size_mb:.1f} MB)")
    summarize(features)


if __name__ == "__main__":
    main()
