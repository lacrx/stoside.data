#!/usr/bin/env python3
"""Normalize all fiscal analysis JSON into parquet files.

Reads the scattered per-topic JSON files and produces a normalized set of
parquet tables ready for DuckDB queries, S3 hosting, and API consumption.

Output goes to fiscal_analysis/exports/ (gitignored — regenerable).
"""

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

HERE = Path(__file__).parent.parent
ROOT = HERE.parent
EXPORTS = HERE / "exports"

PARCEL_GEO = HERE / "parcels_oceanside.geojson"
V2_FILE = HERE / "fiscal_productivity_v2.json"
MARKET_FILE = HERE / "market_values.json"
WATER_FILE = HERE / "raw_data" / "water_mains_oceanside.geojson"
SEWER_FILE = HERE / "raw_data" / "sewer_mains_oceanside.geojson"
BUDGET_FILE = ROOT / "budget_history" / "data_model.json"
CIP_FILE = ROOT / "capital_improvements" / "fy2526_cip_projects.json"
VOTES_FILE = ROOT / "vote_history" / "votes.csv"
HCD_FILE = HERE / "hcd_permits.json"

STATIONS = {
    'Oceanside Transit Center': (-117.3795, 33.1957),
    'Coast Highway': (-117.3690, 33.1900),
    'Crouch Street': (-117.3540, 33.1870),
    'Rancho Del Oro': (-117.3240, 33.2080),
    'College Blvd': (-117.3080, 33.2160),
    'El Camino Real': (-117.2960, 33.2200),
    'Melrose Drive': (-117.2830, 33.2260),
}


def near_station(lon: float, lat: float) -> tuple[bool, str]:
    best_name = ""
    best_dist = 999.0
    for name, (slon, slat) in STATIONS.items():
        dlat = lat - slat
        dlon = (lon - slon) * math.cos(math.radians(slat))
        dist = math.sqrt(dlat**2 + dlon**2) * 69.0
        if dist < best_dist:
            best_dist = dist
            best_name = name
    return best_dist <= 0.5, best_name if best_dist <= 0.5 else ""


def safe_float(v, default=0.0) -> float:
    if v is None:
        return default
    if isinstance(v, float) and math.isnan(v):
        return default
    return float(v)


def safe_int(v, default=0) -> int:
    if v is None:
        return default
    if isinstance(v, float) and math.isnan(v):
        return default
    try:
        return int(v)
    except (ValueError, TypeError):
        return default


def export_parcels():
    """Export normalized parcel table from GeoJSON + market values."""
    print("Loading parcel geometry...")
    with open(PARCEL_GEO) as f:
        geo = json.load(f)

    print("Loading market values...")
    with open(MARKET_FILE) as f:
        mv = json.load(f)
    mv_map = {p["apn"]: p for p in mv["parcels"]}

    print("Loading fiscal v2...")
    with open(V2_FILE) as f:
        v2 = json.load(f)
    v2_map = {p["apn"]: p for p in v2["parcels"]}

    rows = []
    for feat in geo["features"]:
        props = feat["properties"]
        apn = props["APN"]
        mp = mv_map.get(apn, {})
        fp = v2_map.get(apn, {})

        geom = feat.get("geometry")
        if not geom:
            continue

        from shapely.geometry import shape as shp
        try:
            g = shp(geom)
            cx, cy = g.centroid.x, g.centroid.y
        except Exception:
            cx, cy = 0.0, 0.0

        is_transit, station = near_station(cx, cy)

        rows.append({
            "apn": apn,
            "address": props.get("SITUS_ADDR", ""),
            "street": (props.get("SITUS_STRE", "") or "").strip(),
            "city": (props.get("SITUS_COMM", "") or "").strip(),
            "zip": (props.get("SITUS_ZIP", "") or "").strip(),
            "land_use_code": safe_int(props.get("ASR_LANDUS")),
            "land_use_name": fp.get("land_use", mp.get("land_use_name", "")),
            "land_use_broad": fp.get("land_use_broad", ""),
            "acres": safe_float(props.get("ACREAGE", fp.get("acres", 0))),
            "units": safe_int(fp.get("units", props.get("UNITQTY", 0))),
            "living_sqft": safe_int(fp.get("living_sqft", props.get("TOTAL_LVG_", 0))),
            "taxable": fp.get("taxable", props.get("TAXSTAT") == "T"),
            "assessed_land": safe_int(props.get("ASR_LAND", 0)),
            "assessed_building": safe_int(props.get("ASR_IMPR", 0)),
            "assessed_total": safe_int(props.get("ASR_TOTAL", 0)),
            "market_value": safe_int(mp.get("market_value", 0)),
            "suppression_ratio": round(safe_float(mp.get("suppression_ratio", 1.0)), 4),
            "centroid_lon": round(cx, 6),
            "centroid_lat": round(cy, 6),
            "near_transit": is_transit,
            "nearest_station": station,
            "geometry_type": geom.get("type", ""),
        })

    table = pa.Table.from_pylist(rows)
    out = EXPORTS / "parcels.parquet"
    pq.write_table(table, out, compression="snappy")
    print(f"  parcels.parquet: {len(rows):,} rows ({out.stat().st_size / 1e6:.1f} MB)")
    return rows


def export_fiscal():
    """Export normalized fiscal profile per parcel."""
    print("Loading fiscal v2...")
    with open(V2_FILE) as f:
        v2 = json.load(f)

    rows = []
    for p in v2["parcels"]:
        rev = p.get("revenue", {})
        costs = p.get("gf_costs", {})
        ent = p.get("enterprise_costs", {})
        rows.append({
            "apn": p["apn"],
            "gf_revenue": round(safe_float(rev.get("gf_total")), 2),
            "property_tax": round(safe_float(rev.get("property_tax")), 2),
            "sales_tax": round(safe_float(rev.get("sales_tax")), 2),
            "measure_x": round(safe_float(rev.get("measure_x")), 2),
            "tot": round(safe_float(rev.get("tot")), 2),
            "franchise_fees": round(safe_float(rev.get("franchise_fees")), 2),
            "business_license": round(safe_float(rev.get("business_license")), 2),
            "cost_police": round(safe_float(costs.get("police")), 2),
            "cost_fire": round(safe_float(costs.get("fire")), 2),
            "cost_roads": round(safe_float(costs.get("roads")), 2),
            "cost_parks": round(safe_float(costs.get("parks")), 2),
            "cost_library": round(safe_float(costs.get("library")), 2),
            "cost_stormwater": round(safe_float(costs.get("stormwater")), 2),
            "cost_general_govt": round(safe_float(costs.get("general_govt")), 2),
            "cost_gf_total": round(safe_float(costs.get("total")), 2),
            "cost_water": round(safe_float(ent.get("water")), 2),
            "cost_sewer": round(safe_float(ent.get("sewer")), 2),
            "cost_enterprise_total": round(safe_float(ent.get("total")), 2),
            "gf_net": round(safe_float(p.get("gf_net")), 2),
            "gf_net_per_acre": round(safe_float(p.get("gf_net_per_acre")), 2),
            "gf_ratio": round(safe_float(p.get("gf_ratio")), 4),
        })

    table = pa.Table.from_pylist(rows)
    out = EXPORTS / "fiscal.parquet"
    pq.write_table(table, out, compression="snappy")
    print(f"  fiscal.parquet: {len(rows):,} rows ({out.stat().st_size / 1e6:.1f} MB)")


def export_infrastructure(
    path: Path,
    name: str,
    extra_int_fields: list[str] | None = None,
    extra_bool_fields: list[str] | None = None,
):
    """Export pipe infrastructure from GeoJSON to parquet."""
    with open(path) as f:
        geo = json.load(f)

    rows = []
    for feat in geo["features"]:
        geom = feat.get("geometry")
        if not geom:
            continue
        props = feat["properties"]
        row = {
            "segment_id": safe_int(props.get("OBJECTID")),
            "facility_id": str(props.get("FACILITYID", "")),
            "diameter": safe_int(props.get("DIAMETER")),
            "material": safe_int(props.get("MATERIAL")),
            "install_year": safe_int(props.get("INSTALLYEAR")),
            "length_ft": round(safe_float(props.get("Shape.STLength()", props.get("FIELDLENGTH", 0))), 1),
            "active": safe_int(props.get("ACTIVEFLAG", 1)),
            "water_type": str(props.get("WATERTYPE", "")),
        }
        if extra_int_fields:
            for ef in extra_int_fields:
                row[ef.lower()] = safe_int(props.get(ef))
        if extra_bool_fields:
            for ef in extra_bool_fields:
                val = props.get(ef)
                row[ef.lower()] = val in ("Y", "Yes", 1, True)

        d = row["diameter"]
        if d <= 0 or d >= 999:
            d = 6
        cap = 588 * math.pow(d / 8, 8 / 3)
        row["capacity_edu"] = round(cap, 0)

        rows.append(row)

    table = pa.Table.from_pylist(rows)
    out = EXPORTS / f"infrastructure_{name}.parquet"
    pq.write_table(table, out, compression="snappy")
    print(f"  infrastructure_{name}.parquet: {len(rows):,} rows ({out.stat().st_size / 1e6:.1f} MB)")


def export_budget():
    """Export budget time series from data_model.json."""
    with open(BUDGET_FILE) as f:
        data = json.load(f)

    def parse_fy(v) -> int:
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.startswith("FY"):
            parts = v.replace("FY", "").split("-")
            return safe_int(parts[0])
        return safe_int(v)

    gf_rows = []
    for item in data.get("general_fund", []):
        gf_rows.append({
            "fiscal_year": parse_fy(item.get("fiscal_year")),
            "basis": str(item.get("basis", "")),
            "flow": str(item.get("flow", "")),
            "category": str(item.get("category", "")),
            "amount_usd": safe_float(item.get("amount_usd")),
        })

    table = pa.Table.from_pylist(gf_rows)
    out = EXPORTS / "budget.parquet"
    pq.write_table(table, out, compression="snappy")
    print(f"  budget.parquet: {len(gf_rows):,} rows ({out.stat().st_size / 1e6:.1f} MB)")

    fte_rows = []
    for item in data.get("fte_by_department", []):
        fte_rows.append({
            "fiscal_year": parse_fy(item.get("fiscal_year")),
            "department": str(item.get("department", "")),
            "fte": safe_float(item.get("fte")),
        })

    table = pa.Table.from_pylist(fte_rows)
    out = EXPORTS / "budget_staffing.parquet"
    pq.write_table(table, out, compression="snappy")
    print(f"  budget_staffing.parquet: {len(fte_rows):,} rows ({out.stat().st_size / 1e6:.1f} MB)")

    decoder_rows = []
    for item in data.get("decoder_metrics", []):
        fy = parse_fy(item.get("fiscal_year"))
        for k, v in item.items():
            if k in ("fiscal_year", "source_doc_id") or not k.startswith("metric_"):
                continue
            decoder_rows.append({
                "fiscal_year": fy,
                "metric_name": k,
                "value": safe_float(v),
            })

    if decoder_rows:
        table = pa.Table.from_pylist(decoder_rows)
        out = EXPORTS / "budget_health.parquet"
        pq.write_table(table, out, compression="snappy")
        print(f"  budget_health.parquet: {len(decoder_rows):,} rows ({out.stat().st_size / 1e6:.1f} MB)")


def export_cip():
    """Export CIP projects."""
    with open(CIP_FILE) as f:
        data = json.load(f)

    rows = []
    for p in data.get("projects", []):
        rows.append({
            "project_number": str(p.get("project_number", "")),
            "project_name": str(p.get("project_name", "")),
            "project_category": str(p.get("project_category", "")),
            "council_district": str(p.get("council_district", "")),
            "total_5yr": safe_float(p.get("total_5yr", 0)),
            "likely_active_transportation": bool(p.get("likely_active_transportation", False)),
            "funding_sources": json.dumps(p.get("funding_by_source", []), separators=(",", ":")),
        })

    table = pa.Table.from_pylist(rows)
    out = EXPORTS / "cip_projects.parquet"
    pq.write_table(table, out, compression="snappy")
    print(f"  cip_projects.parquet: {len(rows):,} rows ({out.stat().st_size / 1e6:.1f} MB)")


def export_votes():
    """Export council votes from CSV."""
    rows = []
    with open(VOTES_FILE, newline="") as f:
        reader = csv.DictReader(f)
        members = ["SANCHEZ", "KEIM", "JOYCE", "ROBINSON", "WEISS", "FIGUEROA", "RODRIGUEZ"]
        for row in reader:
            positions = {m: row.get(m, "") for m in members}
            rows.append({
                "meeting_date": row.get("meeting_date", ""),
                "meeting_id": row.get("meeting_id", ""),
                "item_number": row.get("item_number", ""),
                "item_title": row.get("item_title", ""),
                "motion_summary": row.get("motion_summary", ""),
                "outcome": row.get("outcome", ""),
                "vote_count_for": safe_int(row.get("vote_count_for")),
                "vote_count_against": safe_int(row.get("vote_count_against")),
                "mover": row.get("mover", ""),
                "seconder": row.get("seconder", ""),
                "member_positions": json.dumps(positions, separators=(",", ":")),
                "notes": row.get("notes", ""),
            })

    table = pa.Table.from_pylist(rows)
    out = EXPORTS / "votes.parquet"
    pq.write_table(table, out, compression="snappy")
    print(f"  votes.parquet: {len(rows):,} rows ({out.stat().st_size / 1e6:.1f} MB)")


def main():
    EXPORTS.mkdir(exist_ok=True)

    print("=== Exporting parcel data ===")
    export_parcels()

    print("\n=== Exporting fiscal data ===")
    export_fiscal()

    print("\n=== Exporting infrastructure ===")
    export_infrastructure(WATER_FILE, "water", extra_bool_fields=["TRANSMISS"])
    export_infrastructure(SEWER_FILE, "sewer", extra_int_fields=["TRUNKLINE", "FORCEMAIN"])

    print("\n=== Exporting budget data ===")
    export_budget()

    print("\n=== Exporting CIP projects ===")
    export_cip()

    print("\n=== Exporting votes ===")
    export_votes()

    total_size = sum(f.stat().st_size for f in EXPORTS.glob("*.parquet"))
    print(f"\n{'='*50}")
    print(f"Total: {len(list(EXPORTS.glob('*.parquet')))} parquet files, {total_size / 1e6:.1f} MB")
    print(f"Output: {EXPORTS}/")


if __name__ == "__main__":
    main()
