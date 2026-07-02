#!/usr/bin/env python3
"""Deploy data files to S3 for the stoside data service.

Syncs parquet files, API JSONs, and GeoJSON source data to the S3 bucket.
Does NOT deploy any HTML visualizations — those are handled by frontend apps.

Usage:
  python deploy_to_s3.py              # deploy everything
  python deploy_to_s3.py --dry-run    # show what would be uploaded
"""

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent.parent
ROOT = HERE.parent
EXPORTS = HERE / "exports"
BUCKET = "s3://stoside-data"
AWS_PROFILE = os.environ.get("AWS_PROFILE", "stoside")

SYNC_TARGETS = [
    # (local_dir_or_file, s3_prefix, description)
    (EXPORTS / "*.parquet",      "data/",    "Parquet data files"),
    (EXPORTS / "api/",           "api/",     "Pre-aggregated API JSONs"),
    (HERE / "raw_data/" / "*.geojson", "geojson/", "GeoJSON source data"),
]

CONTENT_TYPES = {
    ".parquet": "application/octet-stream",
    ".json":    "application/json",
    ".geojson": "application/geo+json",
    ".pmtiles": "application/octet-stream",
}


def sync_files(dry_run: bool = False):
    # Sync parquet files
    parquet_files = list(EXPORTS.glob("*.parquet"))
    print(f"\n=== Parquet files ({len(parquet_files)}) ===")
    for f in sorted(parquet_files):
        s3_key = f"data/{f.name}"
        cmd = ["aws", "s3", "cp", str(f), f"{BUCKET}/{s3_key}",
               "--profile", AWS_PROFILE,
               "--content-type", "application/octet-stream"]
        if dry_run:
            print(f"  [dry-run] {f.name} → {s3_key} ({f.stat().st_size / 1e6:.1f} MB)")
        else:
            print(f"  {f.name} → {s3_key}")
            subprocess.run(cmd, check=True)

    # Sync API JSONs
    api_dir = EXPORTS / "api"
    if api_dir.exists():
        api_files = list(api_dir.glob("*.json"))
        print(f"\n=== API JSONs ({len(api_files)}) ===")
        for f in sorted(api_files):
            s3_key = f"api/{f.name}"
            cmd = ["aws", "s3", "cp", str(f), f"{BUCKET}/{s3_key}",
                   "--profile", AWS_PROFILE,
                   "--content-type", "application/json",
                   "--cache-control", "public, max-age=3600"]
            if dry_run:
                print(f"  [dry-run] {f.name} → {s3_key} ({f.stat().st_size / 1e3:.1f} KB)")
            else:
                print(f"  {f.name} → {s3_key}")
                subprocess.run(cmd, check=True)

    # Sync GeoJSON files
    raw_dir = HERE / "raw_data"
    if raw_dir.exists():
        geo_files = list(raw_dir.glob("*.geojson"))
        print(f"\n=== GeoJSON files ({len(geo_files)}) ===")
        for f in sorted(geo_files):
            s3_key = f"geojson/{f.name}"
            cmd = ["aws", "s3", "cp", str(f), f"{BUCKET}/{s3_key}",
                   "--profile", AWS_PROFILE,
                   "--content-type", "application/geo+json"]
            if dry_run:
                print(f"  [dry-run] {f.name} → {s3_key} ({f.stat().st_size / 1e6:.1f} MB)")
            else:
                print(f"  {f.name} → {s3_key}")
                subprocess.run(cmd, check=True)

    # Sync PMTiles if they exist
    tiles = list(EXPORTS.glob("*.pmtiles")) + list((HERE / "exports").glob("tiles/*.pmtiles"))
    if tiles:
        print(f"\n=== PMTiles ({len(tiles)}) ===")
        for f in sorted(tiles):
            s3_key = f"tiles/{f.name}"
            cmd = ["aws", "s3", "cp", str(f), f"{BUCKET}/{s3_key}",
                   "--profile", AWS_PROFILE,
                   "--content-type", "application/octet-stream"]
            if dry_run:
                print(f"  [dry-run] {f.name} → {s3_key} ({f.stat().st_size / 1e6:.1f} MB)")
            else:
                print(f"  {f.name} → {s3_key}")
                subprocess.run(cmd, check=True)


def main():
    dry_run = "--dry-run" in sys.argv

    if not EXPORTS.exists():
        print("Error: exports/ not found. Run export_parquet.py first.")
        sys.exit(1)

    if dry_run:
        print("=== DRY RUN — nothing will be uploaded ===")

    sync_files(dry_run=dry_run)

    if dry_run:
        print("\nRun without --dry-run to deploy.")
    else:
        print("\nDeploy complete.")


if __name__ == "__main__":
    main()
