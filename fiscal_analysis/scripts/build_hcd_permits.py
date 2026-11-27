#!/usr/bin/env python3
"""Build Oceanside HCD building permit dataset from APR Table A2.

Source: HCD Annual Progress Report (APR) Table A2
        https://data.ca.gov (statewide building permits 2018-2025)

Downloads statewide APR data, filters to Oceanside, structures by APN,
and joins against our parcel data via APN match + spatial fallback.

Outputs:
  - hcd_permits.json: per-APN permit records with pipeline status
  - hcd_permits_summary.json: aggregated stats
  - hcd_parcel_enrichment.json: per-parcel HCD fields for fiscal model join
"""

import csv
import json
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point

HERE = Path(__file__).parent.parent
PARCEL_FILE = HERE / "parcels_oceanside.geojson"
OUTPUT = HERE / "hcd_permits.json"
SUMMARY_OUTPUT = HERE / "hcd_permits_summary.json"
ENRICHMENT_OUTPUT = HERE / "hcd_parcel_enrichment.json"

APR_URL = (
    "https://data.ca.gov/dataset/d037493e-1d5b-4a9b-b34a-f1871e282bef/"
    "resource/41e7f262-42f8-4a87-a7e6-e6eb1ea7e1ca/download/apr_tablea2.csv"
)

INCOME_FIELDS = [
    "ACUTELY_LOW_INCOME_DR", "ACUTELY_LOW_INCOME_NDR",
    "EXTREMELY_LOW_INCOME_DR", "EXTREMELY_LOW_INCOME_NDR",
    "VLOW_INCOME_DR", "VLOW_INCOME_NDR",
    "LOW_INCOME_DR", "LOW_INCOME_NDR",
    "MOD_INCOME_DR", "MOD_INCOME_NDR",
    "ABOVE_MOD_INCOME",
]


def safe_int(val: str) -> int:
    try:
        return int(val or 0)
    except (ValueError, TypeError):
        return 0


def count_units(rec: dict, prefix: str = "") -> int:
    return sum(safe_int(rec.get(f"{prefix}{f}", 0)) for f in INCOME_FIELDS)


def count_affordable(rec: dict, prefix: str = "") -> int:
    affordable_fields = [f for f in INCOME_FIELDS if f != "ABOVE_MOD_INCOME"]
    return sum(safe_int(rec.get(f"{prefix}{f}", 0)) for f in affordable_fields)


def download_apr(dest: Path) -> Path:
    if dest.exists():
        size_mb = dest.stat().st_size / 1_048_576
        print(f"APR data already cached: {dest} ({size_mb:.0f} MB)")
        return dest

    print("Downloading APR Table A2 (~280 MB)...")
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(APR_URL, dest)
    size_mb = dest.stat().st_size / 1_048_576
    print(f"  → {dest} ({size_mb:.0f} MB)")
    return dest


def load_oceanside_records(csv_path: Path) -> list[dict]:
    records = []
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            if row.get("JURIS_NAME") == "OCEANSIDE":
                records.append(row)
    print(f"Oceanside records: {len(records):,}")
    return records


def structure_permits(records: list[dict]) -> dict:
    """Group HCD records by APN into structured permit objects."""
    by_apn = defaultdict(list)
    for rec in records:
        apn = rec.get("APN", "").strip()
        if not apn:
            continue
        by_apn[apn].append(rec)

    permits = {}
    for apn, recs in by_apn.items():
        ent_units = 0
        bp_units = 0
        co_units = 0
        ent_affordable = 0
        bp_affordable = 0
        co_affordable = 0
        categories = set()
        years = set()
        projects = set()
        bp_dates = []
        co_dates = []
        tenure_types = set()
        addresses = set()

        for rec in recs:
            ent_units += count_units(rec, "")
            bp_units += count_units(rec, "BP_")
            co_units += count_units(rec, "CO_")
            ent_affordable += count_affordable(rec, "")
            bp_affordable += count_affordable(rec, "BP_")
            co_affordable += count_affordable(rec, "CO_")

            categories.add(rec.get("UNIT_CAT", ""))
            years.add(rec.get("YEAR", ""))
            tenure_types.add(rec.get("TENURE", ""))

            proj = rec.get("PROJECT_NAME", "").strip()
            if proj:
                projects.add(proj)

            addr = rec.get("STREET_ADDRESS", "").strip()
            if addr:
                addresses.add(addr)

            bp_dt = rec.get("BP_ISSUE_DT1", "").strip()
            if bp_dt:
                bp_dates.append(bp_dt)

            co_dt = rec.get("CO_ISSUE_DT1", "").strip()
            if co_dt:
                co_dates.append(co_dt)

        earliest_bp = min(bp_dates) if bp_dates else None
        latest_bp = max(bp_dates) if bp_dates else None
        earliest_co = min(co_dates) if co_dates else None
        latest_co = max(co_dates) if co_dates else None

        if co_units > 0:
            status = "completed"
        elif bp_units > 0:
            status = "permitted"
        elif ent_units > 0:
            status = "entitled"
        else:
            status = "unknown"

        lat = None
        lon = None
        for rec in recs:
            try:
                lat = float(rec.get("LATITUDE", ""))
                lon = float(rec.get("LONGITUDE", ""))
                break
            except (ValueError, TypeError):
                pass

        permits[apn] = {
            "apn": apn,
            "status": status,
            "categories": sorted(categories - {""}),
            "reporting_years": sorted(years - {""}),
            "projects": sorted(projects),
            "addresses": sorted(addresses),
            "tenure": sorted(tenure_types - {""}),
            "entitled": {
                "units": ent_units,
                "affordable": ent_affordable,
                "market_rate": ent_units - ent_affordable,
            },
            "building_permits": {
                "units": bp_units,
                "affordable": bp_affordable,
                "market_rate": bp_units - bp_affordable,
                "earliest_date": earliest_bp,
                "latest_date": latest_bp,
            },
            "certificates_of_occupancy": {
                "units": co_units,
                "affordable": co_affordable,
                "market_rate": co_units - co_affordable,
                "earliest_date": earliest_co,
                "latest_date": latest_co,
            },
            "latitude": lat,
            "longitude": lon,
            "hcd_record_count": len(recs),
        }

    return permits


def spatial_match_unmatched(
    permits: dict,
    parcel_apns: set,
    gdf_parcels: gpd.GeoDataFrame,
) -> dict[str, list[str]]:
    """For HCD APNs not in parcel data, spatial join via lat/lon.

    Returns: {hcd_apn: [list of parcel APNs containing that point]}
    Many-to-many because subdivisions create multiple parcels at one point.
    """
    unmatched = {
        apn: perm for apn, perm in permits.items()
        if apn not in parcel_apns
        and perm["latitude"] is not None
        and perm["longitude"] is not None
    }
    if not unmatched:
        return {}

    points = []
    for apn, perm in unmatched.items():
        points.append({
            "geometry": Point(perm["longitude"], perm["latitude"]),
            "hcd_apn": apn,
        })

    gdf_points = gpd.GeoDataFrame(points, crs="EPSG:4326")
    joined = gpd.sjoin(gdf_points, gdf_parcels, how="left", predicate="within")

    spatial_map = defaultdict(set)
    for _, row in joined.iterrows():
        if row.get("index_right") is not None and not (
            isinstance(row["index_right"], float)
            and row["index_right"] != row["index_right"]
        ):
            parcel_apn = row.get("APN", "")
            if parcel_apn:
                spatial_map[row["hcd_apn"]].add(parcel_apn)

    result = {k: sorted(v) for k, v in spatial_map.items()}
    matched_count = sum(1 for v in result.values() if v)
    print(f"Spatial fallback: {matched_count:,} / {len(unmatched):,} "
          f"unmatched HCD APNs resolved to parcel(s)")
    return result


def join_to_parcels(permits: dict, parcel_path: Path) -> tuple[dict, dict]:
    """Join HCD permits to parcel data via APN + spatial fallback.

    Returns (enriched_permits, parcel_hcd_map) where parcel_hcd_map
    maps each parcel APN to HCD data enrichment fields.
    """
    gdf_parcels = gpd.read_file(parcel_path)
    parcel_apns = set(gdf_parcels["APN"].values)

    parcel_props = {}
    with open(parcel_path) as f:
        geo = json.load(f)
    for feat in geo["features"]:
        p = feat["properties"]
        parcel_props[p["APN"]] = p

    # Phase 1: direct APN match
    matched = 0
    unmatched = 0
    for apn, permit in permits.items():
        parcel = parcel_props.get(apn)
        if parcel:
            matched += 1
            permit["match_type"] = "apn"
            permit["parcel_apns"] = [apn]
            permit["parcel"] = {
                "land_use_code": parcel.get("ASR_LANDUS", 0),
                "assessed_total": parcel.get("ASR_TOTAL", 0),
                "existing_units": parcel.get("UNITQTY", 0),
                "year_effective": parcel.get("YEAR_EFFEC", ""),
            }
        else:
            unmatched += 1
            permit["match_type"] = None
            permit["parcel_apns"] = []
            permit["parcel"] = None

    print(f"APN match: {matched:,} matched, {unmatched:,} unmatched "
          f"({matched / len(permits) * 100:.1f}%)")

    # Phase 2: spatial fallback for unmatched
    spatial_map = spatial_match_unmatched(permits, parcel_apns, gdf_parcels)

    spatial_resolved = 0
    for hcd_apn, parcel_apn_list in spatial_map.items():
        if parcel_apn_list and hcd_apn in permits:
            permits[hcd_apn]["match_type"] = "spatial"
            permits[hcd_apn]["parcel_apns"] = parcel_apn_list
            spatial_resolved += 1

    still_unmatched = sum(
        1 for p in permits.values() if p["match_type"] is None
    )
    print(f"After spatial: {spatial_resolved:,} resolved, "
          f"{still_unmatched:,} still unmatched")

    # Build parcel enrichment: for each parcel APN, aggregate HCD activity
    parcel_hcd = defaultdict(lambda: {
        "hcd_apns": [],
        "hcd_projects": [],
        "hcd_categories": set(),
        "hcd_bp_units": 0,
        "hcd_co_units": 0,
        "hcd_ent_units": 0,
        "hcd_affordable_units": 0,
        "hcd_earliest_bp": None,
        "hcd_latest_co": None,
        "hcd_status": None,
        "hcd_match_type": None,
    })

    for hcd_apn, perm in permits.items():
        if not perm["parcel_apns"]:
            continue

        n_parcels = len(perm["parcel_apns"])

        for parcel_apn in perm["parcel_apns"]:
            entry = parcel_hcd[parcel_apn]
            entry["hcd_apns"].append(hcd_apn)
            entry["hcd_projects"].extend(perm["projects"])
            entry["hcd_categories"].update(perm["categories"])
            entry["hcd_match_type"] = perm["match_type"]

            # For spatial matches (subdivisions), each child parcel
            # gets 1 unit attributed. For APN matches, full count.
            if perm["match_type"] == "spatial":
                entry["hcd_bp_units"] += max(
                    1, perm["building_permits"]["units"] // n_parcels
                )
                entry["hcd_co_units"] += max(
                    1, perm["certificates_of_occupancy"]["units"] // n_parcels
                ) if perm["certificates_of_occupancy"]["units"] > 0 else 0
                entry["hcd_ent_units"] += max(
                    1, perm["entitled"]["units"] // n_parcels
                ) if perm["entitled"]["units"] > 0 else 0
                entry["hcd_affordable_units"] += max(
                    0, perm["building_permits"]["affordable"] // n_parcels
                )
            else:
                entry["hcd_bp_units"] += perm["building_permits"]["units"]
                entry["hcd_co_units"] += perm["certificates_of_occupancy"]["units"]
                entry["hcd_ent_units"] += perm["entitled"]["units"]
                entry["hcd_affordable_units"] += perm["building_permits"]["affordable"]

            bp_dt = perm["building_permits"]["earliest_date"]
            if bp_dt:
                if entry["hcd_earliest_bp"] is None or bp_dt < entry["hcd_earliest_bp"]:
                    entry["hcd_earliest_bp"] = bp_dt

            co_dt = perm["certificates_of_occupancy"]["latest_date"]
            if co_dt:
                if entry["hcd_latest_co"] is None or co_dt > entry["hcd_latest_co"]:
                    entry["hcd_latest_co"] = co_dt

            entry["hcd_status"] = perm["status"]

    # Serialize sets
    enrichment = {}
    for parcel_apn, entry in parcel_hcd.items():
        entry["hcd_categories"] = sorted(entry["hcd_categories"])
        entry["hcd_projects"] = sorted(set(entry["hcd_projects"]))
        entry["hcd_apns"] = sorted(set(entry["hcd_apns"]))
        enrichment[parcel_apn] = entry

    print(f"Parcel enrichment: {len(enrichment):,} parcels have HCD activity")

    return permits, enrichment


def build_summary(permits: dict, enrichment: dict) -> dict:
    """Aggregate stats across all permits."""
    by_category = defaultdict(lambda: {
        "records": 0, "apns": 0,
        "entitled": 0, "permitted": 0, "completed": 0,
        "affordable_permitted": 0,
        "apn_matched": 0, "spatial_matched": 0, "unmatched": 0,
    })
    by_year = defaultdict(lambda: {
        "entitled": 0, "permitted": 0, "completed": 0,
    })
    by_status = defaultdict(int)

    total_ent = 0
    total_bp = 0
    total_co = 0

    for perm in permits.values():
        for cat in perm["categories"]:
            s = by_category[cat]
            s["apns"] += 1
            s["records"] += perm["hcd_record_count"]
            s["entitled"] += perm["entitled"]["units"]
            s["permitted"] += perm["building_permits"]["units"]
            s["completed"] += perm["certificates_of_occupancy"]["units"]
            s["affordable_permitted"] += perm["building_permits"]["affordable"]
            if perm["match_type"] == "apn":
                s["apn_matched"] += 1
            elif perm["match_type"] == "spatial":
                s["spatial_matched"] += 1
            else:
                s["unmatched"] += 1

        for yr in perm["reporting_years"]:
            by_year[yr]["entitled"] += perm["entitled"]["units"]
            by_year[yr]["permitted"] += perm["building_permits"]["units"]
            by_year[yr]["completed"] += perm["certificates_of_occupancy"]["units"]

        by_status[perm["status"]] += 1
        total_ent += perm["entitled"]["units"]
        total_bp += perm["building_permits"]["units"]
        total_co += perm["certificates_of_occupancy"]["units"]

    # Pipeline gap
    permitted_no_co = []
    for perm in permits.values():
        bp = perm["building_permits"]["units"]
        co = perm["certificates_of_occupancy"]["units"]
        if bp > 0 and co == 0:
            permitted_no_co.append({
                "apn": perm["apn"],
                "units": bp,
                "projects": perm["projects"],
                "bp_date": perm["building_permits"]["earliest_date"],
                "match_type": perm["match_type"],
                "categories": perm["categories"],
            })
    permitted_no_co.sort(key=lambda x: -x["units"])

    # Enrichment stats
    enrichment_by_match = Counter()
    enrichment_units = 0
    for entry in enrichment.values():
        enrichment_by_match[entry["hcd_match_type"]] += 1
        enrichment_units += entry["hcd_bp_units"]

    total_match = sum(
        1 for p in permits.values() if p["match_type"] is not None
    )

    return {
        "source": "HCD APR Table A2 (2018-2025)",
        "jurisdiction": "OCEANSIDE",
        "total_hcd_apns": len(permits),
        "total_records": sum(p["hcd_record_count"] for p in permits.values()),
        "match_rates": {
            "apn_matched": sum(
                1 for p in permits.values() if p["match_type"] == "apn"
            ),
            "spatial_matched": sum(
                1 for p in permits.values() if p["match_type"] == "spatial"
            ),
            "unmatched": sum(
                1 for p in permits.values() if p["match_type"] is None
            ),
            "total_match_rate": round(total_match / len(permits) * 100, 1),
        },
        "pipeline_totals": {
            "entitled_units": total_ent,
            "permitted_units": total_bp,
            "completed_units": total_co,
            "pipeline_gap": total_bp - total_co,
        },
        "enrichment": {
            "parcels_enriched": len(enrichment),
            "by_match_type": dict(enrichment_by_match),
            "total_bp_units_attributed": enrichment_units,
        },
        "by_status": dict(by_status),
        "by_category": {k: dict(v) for k, v in sorted(by_category.items())},
        "by_year": {k: dict(v) for k, v in sorted(by_year.items())},
        "permitted_not_completed": permitted_no_co[:30],
    }


def main():
    cache_dir = Path("/tmp/claude-1000/hcd_cache")
    csv_path = cache_dir / "apr_tablea2.csv"

    existing = Path(
        "/tmp/claude-1000/-home-thomas-repos-stoside-data/"
        "cb70b43a-110f-4a0f-a88f-3233ca64478b/scratchpad/apr_tablea2.csv"
    )
    if existing.exists():
        csv_path = existing
        print(f"Using cached APR data: {csv_path}")
    else:
        csv_path = download_apr(csv_path)

    records = load_oceanside_records(csv_path)
    permits = structure_permits(records)
    print(f"Structured into {len(permits):,} unique APNs")

    permits, enrichment = join_to_parcels(permits, PARCEL_FILE)
    summary = build_summary(permits, enrichment)

    OUTPUT.write_text(json.dumps(
        {"permits": list(permits.values()), "summary": summary},
        indent=2,
    ))
    size_mb = OUTPUT.stat().st_size / 1_048_576
    print(f"\n→ {OUTPUT} ({size_mb:.1f} MB)")

    SUMMARY_OUTPUT.write_text(json.dumps(summary, indent=2))
    print(f"→ {SUMMARY_OUTPUT}")

    ENRICHMENT_OUTPUT.write_text(json.dumps(enrichment, indent=2))
    enrich_mb = ENRICHMENT_OUTPUT.stat().st_size / 1_048_576
    print(f"→ {ENRICHMENT_OUTPUT} ({enrich_mb:.1f} MB)")

    # Print summary
    s = summary
    print(f"\n{'=' * 65}")
    print(f"HCD BUILDING PERMITS — OCEANSIDE (2018-2025)")
    print(f"{'=' * 65}")
    print(f"Total HCD APNs: {s['total_hcd_apns']:,}")
    m = s["match_rates"]
    print(f"Match: {m['apn_matched']:,} APN + {m['spatial_matched']:,} spatial "
          f"+ {m['unmatched']:,} unmatched = {m['total_match_rate']}%")

    t = s["pipeline_totals"]
    print(f"\nPipeline:")
    print(f"  Entitled:   {t['entitled_units']:>6,} units")
    print(f"  Permitted:  {t['permitted_units']:>6,} units")
    print(f"  Completed:  {t['completed_units']:>6,} units")
    print(f"  Gap:        {t['pipeline_gap']:>6,} units")

    e = s["enrichment"]
    print(f"\nParcel enrichment:")
    print(f"  Parcels with HCD data: {e['parcels_enriched']:,}")
    print(f"  BP units attributed:   {e['total_bp_units_attributed']:,}")

    print(f"\nBy category:")
    print(f"  {'Cat':>8s} {'APNs':>6s} {'Entitled':>9s} {'BP':>7s} "
          f"{'CO':>7s} {'APN%':>5s} {'Spat%':>6s}")
    for cat, data in sorted(s["by_category"].items()):
        total = data["apn_matched"] + data["spatial_matched"] + data["unmatched"]
        apn_pct = data["apn_matched"] / total * 100 if total else 0
        spat_pct = data["spatial_matched"] / total * 100 if total else 0
        print(f"  {cat:>8s} {data['apns']:>6,} {data['entitled']:>9,} "
              f"{data['permitted']:>7,} {data['completed']:>7,} "
              f"{apn_pct:>4.0f}% {spat_pct:>5.0f}%")

    print(f"\nLargest permitted-not-completed:")
    for p in s["permitted_not_completed"][:10]:
        proj = p["projects"][0] if p["projects"] else "unnamed"
        mt = p["match_type"] or "NONE"
        print(f"  {p['apn']} — {p['units']:>4} units — {proj[:30]:30s} [{mt}]")


if __name__ == "__main__":
    main()
