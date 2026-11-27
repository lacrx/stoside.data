#!/usr/bin/env python3
"""Build interactive dashboard: Infrastructure Capacity vs. SB 79 Upzoning Revenue.

Combines a deck.gl map of transit-area parcels with charts showing:
- Pipe capacity utilization by upzoning scenario
- Per-unit cost comparison across housing types
- Revenue swing from converting SFR to higher density
- Infrastructure upgrade payback timeline

Designed to rebut Oceanside city council's claim that transit-area
infrastructure can't handle SB 79 upzoning.
"""

import json
import math
from collections import defaultdict
from pathlib import Path

from shapely.geometry import shape

HERE = Path(__file__).parent.parent
PARCEL_FILE = HERE / "parcels_oceanside.geojson"
V2_FILE = HERE / "fiscal_productivity_v2.json"
OUTPUT = HERE / "visuals" / "sb79_infrastructure_rebuttal.html"

STATIONS = {
    'Oceanside Transit Center': (-117.3795, 33.1957),
    'Coast Highway': (-117.3690, 33.1900),
    'Crouch Street': (-117.3540, 33.1870),
    'Rancho Del Oro': (-117.3240, 33.2080),
    'College Blvd': (-117.3080, 33.2160),
    'El Camino Real': (-117.2960, 33.2200),
    'Melrose Drive': (-117.2830, 33.2260),
}

HALF_MILE = 0.5 / 69.0

COLOR_STOPS = [
    (-30000, [15, 15, 80]),
    (-15000, [30, 60, 180]),
    (-5000,  [40, 140, 210]),
    (0,      [60, 190, 170]),
    (5000,   [100, 200, 60]),
    (15000,  [200, 210, 30]),
    (30000,  [240, 160, 20]),
    (50000,  [230, 70, 25]),
    (100000, [200, 20, 60]),
    (200000, [170, 20, 130]),
]


def net_to_color(net: float) -> list[int]:
    if net <= COLOR_STOPS[0][0]:
        return COLOR_STOPS[0][1] + [220]
    if net >= COLOR_STOPS[-1][0]:
        return COLOR_STOPS[-1][1] + [220]
    for i in range(len(COLOR_STOPS) - 1):
        v0, c0 = COLOR_STOPS[i]
        v1, c1 = COLOR_STOPS[i + 1]
        if net <= v1:
            t = (net - v0) / (v1 - v0)
            return [int(c0[j] + t * (c1[j] - c0[j])) for j in range(3)] + [220]
    return COLOR_STOPS[-1][1] + [220]


def near_station(lon: float, lat: float) -> str | None:
    for name, (slon, slat) in STATIONS.items():
        dlat = lat - slat
        dlon = (lon - slon) * math.cos(math.radians(slat))
        if math.sqrt(dlat**2 + dlon**2) * 69.0 <= 0.5:
            return name
    return None


def polygon_key(geom) -> str:
    b = geom.bounds
    c = geom.centroid
    return f"{b[0]:.6f},{b[1]:.6f},{b[2]:.6f},{b[3]:.6f},{c.x:.6f},{c.y:.6f}"


def main():
    print("Loading parcel geometries...")
    with open(PARCEL_FILE) as f:
        geo = json.load(f)

    print("Loading fiscal data...")
    with open(V2_FILE) as f:
        v2 = json.load(f)
    v2_map = {p["apn"]: p for p in v2["parcels"]}

    # Build APN → centroid lookup from geojson
    apn_centroid = {}
    apn_geom = {}
    for feat in geo["features"]:
        apn = feat["properties"]["APN"]
        geom = shape(feat["geometry"])
        c = geom.centroid
        apn_centroid[apn] = (c.x, c.y)
        apn_geom[apn] = feat["geometry"]

    # Classify transit-area parcels
    transit_stats = defaultdict(lambda: {
        "count": 0, "units": 0, "acres": 0,
        "revenue": 0, "cost": 0,
    })
    transit_parcels = []  # for map
    non_transit = []

    # Also consolidate stacked condos
    poly_groups = defaultdict(list)
    geom_cache = {}

    for feat in geo["features"]:
        apn = feat["properties"]["APN"]
        fp = v2_map.get(apn)
        if not fp:
            continue

        geom = shape(feat["geometry"])
        key = polygon_key(geom)
        geom_cache[key] = feat["geometry"]

        cx, cy = apn_centroid[apn]
        station = near_station(cx, cy)

        poly_groups[key].append((apn, fp, station))

    print("Consolidating stacked parcels...")
    map_features = []
    station_rings = []

    # Stats accumulators
    for key, group in poly_groups.items():
        geometry = geom_cache[key]
        geom = shape(geometry)

        b = geom.bounds
        approx_area_sqft = geom.area * 305000 * 364000
        acres = approx_area_sqft / 43560
        if acres < 0.005:
            acres = 0.01

        total_rev = sum(fp["revenue"]["gf_total"] for _, fp, _ in group)
        total_cost = sum(fp["gf_costs"]["total"] for _, fp, _ in group)
        total_units = sum(fp.get("units", 0) or 0 for _, fp, _ in group)

        cat_counts = defaultdict(int)
        for _, fp, _ in group:
            cat_counts[fp.get("land_use_broad", "Other")] += 1
        primary_cat = max(cat_counts, key=cat_counts.get)

        if primary_cat in ("Vacant", "Government", "Other"):
            continue

        # Check if any parcel in group is near transit
        station = None
        for _, _, s in group:
            if s:
                station = s
                break

        is_transit = station is not None

        # Accumulate stats
        if is_transit:
            t = transit_stats[primary_cat]
            t["count"] += 1
            t["units"] += total_units or len(group)
            t["acres"] += acres
            t["revenue"] += total_rev
            t["cost"] += total_cost

        # Build map feature
        p13_net = total_rev - total_cost
        p13_npa = p13_net / acres

        coords = geometry.get("coordinates", [])
        geom_type = geometry.get("type", "")

        if geom_type == "MultiPolygon":
            polys = [ring for poly in coords for ring in [poly[0]]]
        elif geom_type == "Polygon":
            polys = [coords[0]]
        else:
            continue

        p13_c = net_to_color(p13_npa)

        for poly in polys:
            simplified = [[round(c[0], 5), round(c[1], 5)] for c in poly]
            if len(simplified) > 25:
                step = max(1, len(simplified) // 20)
                simplified = simplified[::step]
                if simplified[-1] != simplified[0]:
                    simplified.append(simplified[0])

            map_features.append({
                "p": simplified,
                "c": p13_c,
                "npa": round(p13_npa),
                "cat": primary_cat,
                "u": total_units or len(group),
                "ac": round(acres, 3),
                "gr": round(total_rev),
                "gc": round(total_cost),
                "t": 1 if is_transit else 0,
                "s": station or "",
            })

    print(f"  {len(map_features):,} map features")

    # Build station circle data
    for name, (lon, lat) in STATIONS.items():
        n_pts = 64
        ring = []
        for i in range(n_pts + 1):
            angle = 2 * math.pi * i / n_pts
            dx = HALF_MILE * math.cos(angle) / math.cos(math.radians(lat))
            dy = HALF_MILE * math.sin(angle)
            ring.append([round(lon + dx, 5), round(lat + dy, 5)])
        station_rings.append({
            "p": ring,
            "name": name,
            "lon": lon,
            "lat": lat,
        })

    # Build scenario data for charts
    order = ["SFR", "Condo/TH", "Duplex", "3-4 Plex", "MFR 5-20", "MFR 21-100", "MFR 100+", "Commercial"]
    chart_data = {}

    for cat in order:
        t = transit_stats.get(cat)
        if not t or t["count"] == 0:
            continue
        chart_data[cat] = {
            "count": t["count"],
            "units": t["units"],
            "acres": round(t["acres"], 1),
            "revenue": round(t["revenue"]),
            "cost": round(t["cost"]),
            "net": round(t["revenue"] - t["cost"]),
            "net_per_acre": round((t["revenue"] - t["cost"]) / t["acres"]) if t["acres"] > 0 else 0,
            "rev_per_unit": round(t["revenue"] / t["units"]) if t["units"] > 0 else 0,
            "cost_per_unit": round(t["cost"] / t["units"]) if t["units"] > 0 else 0,
            "units_per_acre": round(t["units"] / t["acres"], 1) if t["acres"] > 0 else 0,
        }

    # Upzoning scenarios
    sfr = chart_data.get("SFR", {})
    scenarios = []
    if sfr and sfr["acres"] > 0 and sfr["units"] > 0:
        sfr_upa = sfr["units_per_acre"]
        sfr_net = sfr["net"]
        sfr_acres = sfr["acres"]

        scenarios.append({
            "name": "SFR (current)",
            "density": sfr_upa,
            "units": sfr["units"],
            "net": sfr_net,
            "net_per_acre": sfr["net_per_acre"],
            "delta_net": 0,
            "edu_per_acre": round(sfr_upa * 1.0, 1),
            "pipe_util_pct": round(sfr_upa * 1.0 / 588 * 5.5 * 100, 1),
        })

        for mcat in ["Duplex", "3-4 Plex", "MFR 5-20", "Condo/TH", "MFR 21-100"]:
            m = chart_data.get(mcat)
            if not m or m["units"] == 0 or m["acres"] == 0:
                continue
            m_upa = m["units_per_acre"]
            m_rev_pu = m["rev_per_unit"]
            m_cost_pu = m["cost_per_unit"]

            new_units = int(sfr_acres * m_upa)
            new_rev = new_units * m_rev_pu
            new_cost = new_units * m_cost_pu
            new_net = new_rev - new_cost
            delta = new_net - sfr_net

            edu_mult = 0.7
            edu_pa = m_upa * edu_mult
            block_edu = edu_pa * 5.5
            pipe_pct = block_edu / 588 * 100

            scenarios.append({
                "name": mcat,
                "density": m_upa,
                "units": new_units,
                "net": round(new_net),
                "net_per_acre": round(new_net / sfr_acres) if sfr_acres > 0 else 0,
                "delta_net": round(delta),
                "edu_per_acre": round(edu_pa, 1),
                "pipe_util_pct": round(pipe_pct, 1),
            })

    # Block scenario (5.5 acres)
    block_scenarios = []
    block_ac = 5.5
    if sfr:
        sfr_units_block = int(block_ac * sfr["units_per_acre"])
        sfr_edu = sfr_units_block * 1.0
        sfr_block_net = sfr_units_block * (sfr["revenue"] - sfr["cost"]) / sfr["units"] if sfr["units"] > 0 else 0

        block_scenarios.append({
            "name": "SFR (current)",
            "units": sfr_units_block,
            "edu": round(sfr_edu),
            "pipe_pct": round(sfr_edu / 588 * 100, 1),
            "net_fiscal": round(sfr_block_net),
            "upgrade_cost": 0,
            "payback_yrs": None,
        })

        for mcat in ["Duplex", "3-4 Plex", "MFR 5-20", "Condo/TH"]:
            m = chart_data.get(mcat)
            if not m or m["units"] == 0:
                continue
            new_units = int(block_ac * m["units_per_acre"])
            new_edu = new_units * 0.7
            pct = new_edu / 588 * 100
            m_net_pu = (m["revenue"] - m["cost"]) / m["units"]
            block_net = new_units * m_net_pu
            delta = block_net - sfr_block_net
            upgrade = 250000
            payback = upgrade / delta if delta > 0 else None

            block_scenarios.append({
                "name": mcat,
                "units": new_units,
                "edu": round(new_edu),
                "pipe_pct": round(pct, 1),
                "net_fiscal": round(block_net),
                "upgrade_cost": upgrade,
                "payback_yrs": round(payback, 1) if payback else None,
            })

    # Prepare all data for HTML
    dashboard_data = {
        "stats": chart_data,
        "scenarios": scenarios,
        "block": block_scenarios,
        "sfr_acres": sfr.get("acres", 0),
        "sfr_count": sfr.get("count", 0),
        "sfr_net": sfr.get("net", 0),
    }

    print("Building HTML...")
    OUTPUT.parent.mkdir(exist_ok=True)

    map_json = json.dumps(map_features, separators=(",", ":"))
    station_json = json.dumps(station_rings, separators=(",", ":"))
    data_json = json.dumps(dashboard_data, separators=(",", ":"))

    center_lon = sum(s[0] for s in STATIONS.values()) / len(STATIONS)
    center_lat = sum(s[1] for s in STATIONS.values()) / len(STATIONS)

    html = build_html(map_json, station_json, data_json, center_lon, center_lat)

    OUTPUT.write_text(html)
    size_mb = OUTPUT.stat().st_size / 1024 / 1024
    print(f"\n→ {OUTPUT} ({size_mb:.1f} MB)")
    print(f"  {len(map_features):,} parcels on map")
    print(f"  {len(station_rings)} transit station buffers")


def build_html(map_json: str, station_json: str, data_json: str,
               center_lon: float, center_lat: float) -> str:
    tpl = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>SB 79 Infrastructure Rebuttal — Oceanside Transit Areas</title>
<script src="https://unpkg.com/deck.gl@9.0.16/dist.min.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0a0a1a;
    color: #e0e0e0;
    overflow-x: hidden;
  }

  .header {
    background: linear-gradient(135deg, #0d1b2a 0%, #1b2838 100%);
    padding: 24px 32px;
    border-bottom: 2px solid #1e3a5f;
  }
  .header h1 {
    font-size: 22px;
    font-weight: 700;
    color: #fff;
    margin-bottom: 6px;
  }
  .header .subtitle {
    font-size: 14px;
    color: #8899aa;
  }
  .header .claim {
    margin-top: 12px;
    padding: 10px 16px;
    background: rgba(200,50,50,0.15);
    border-left: 3px solid #c44;
    border-radius: 0 4px 4px 0;
    font-size: 13px;
    color: #e88;
  }
  .header .claim strong { color: #faa; }
  .header .rebuttal {
    margin-top: 8px;
    padding: 10px 16px;
    background: rgba(50,200,100,0.1);
    border-left: 3px solid #4a4;
    border-radius: 0 4px 4px 0;
    font-size: 13px;
    color: #8e8;
  }
  .header .rebuttal strong { color: #afa; }

  .dashboard {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0;
    min-height: calc(100vh - 160px);
  }

  .map-panel {
    position: relative;
    min-height: 600px;
    border-right: 1px solid #1e3a5f;
  }
  #map-container {
    width: 100%;
    height: 100%;
    position: absolute;
    top: 0; left: 0;
  }

  .map-legend {
    position: absolute;
    bottom: 16px;
    left: 16px;
    background: rgba(10,10,26,0.92);
    padding: 12px 16px;
    border-radius: 6px;
    font-size: 11px;
    z-index: 10;
    border: 1px solid #1e3a5f;
  }
  .map-legend h4 {
    font-size: 12px;
    margin-bottom: 8px;
    color: #aaa;
  }
  .legend-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 3px 0;
  }
  .legend-swatch {
    width: 14px;
    height: 14px;
    border-radius: 2px;
    flex-shrink: 0;
  }
  .transit-ring-legend {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    border: 2px dashed rgba(255,200,50,0.7);
    flex-shrink: 0;
  }

  .map-controls {
    position: absolute;
    top: 12px;
    right: 12px;
    z-index: 10;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .map-controls button {
    background: rgba(10,10,26,0.9);
    color: #ccc;
    border: 1px solid #334;
    padding: 6px 12px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 11px;
    white-space: nowrap;
  }
  .map-controls button:hover { background: #223; color: #fff; }
  .map-controls button.active { background: #1a3a6a; color: #6af; border-color: #4a8; }

  .charts-panel {
    overflow-y: auto;
    padding: 20px 24px;
    max-height: calc(100vh - 160px);
  }

  .chart-card {
    background: #111827;
    border: 1px solid #1e3a5f;
    border-radius: 8px;
    margin-bottom: 16px;
    overflow: hidden;
  }
  .chart-card h3 {
    font-size: 14px;
    font-weight: 600;
    padding: 12px 16px;
    background: #0d1b2a;
    border-bottom: 1px solid #1e3a5f;
    color: #9ab;
  }
  .chart-body {
    padding: 16px;
  }

  .bar-chart {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .bar-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 6px;
  }
  .bar-label {
    width: 90px;
    font-size: 12px;
    text-align: right;
    flex-shrink: 0;
    color: #9ab;
  }
  .bar-track {
    flex: 1;
    height: 28px;
    background: #1a1a2e;
    border-radius: 4px;
    position: relative;
    overflow: visible;
  }
  .bar-fill {
    height: 100%;
    border-radius: 4px;
    position: relative;
    display: flex;
    align-items: center;
    padding-right: 8px;
    justify-content: flex-end;
    font-size: 11px;
    font-weight: 600;
    color: #fff;
    text-shadow: 0 1px 2px rgba(0,0,0,0.5);
    min-width: fit-content;
    transition: width 0.6s ease;
  }
  .bar-value {
    position: absolute;
    right: -8px;
    transform: translateX(100%);
    font-size: 11px;
    color: #8899aa;
    white-space: nowrap;
  }

  .capacity-gauge {
    position: relative;
    height: 36px;
    background: #1a1a2e;
    border-radius: 6px;
    margin: 6px 0;
    overflow: visible;
  }
  .gauge-fill {
    height: 100%;
    border-radius: 6px;
    display: flex;
    align-items: center;
    padding-left: 10px;
    font-size: 12px;
    font-weight: 600;
    color: #fff;
    transition: width 0.6s ease;
  }
  .gauge-marker {
    position: absolute;
    top: -6px;
    bottom: -6px;
    width: 2px;
    background: #f55;
    z-index: 2;
  }
  .gauge-marker-label {
    position: absolute;
    top: -20px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 10px;
    color: #f88;
    white-space: nowrap;
  }

  .stat-grid {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 12px;
    margin-bottom: 16px;
  }
  .stat-box {
    background: #0d1b2a;
    border: 1px solid #1e3a5f;
    border-radius: 6px;
    padding: 14px;
    text-align: center;
  }
  .stat-number {
    font-size: 22px;
    font-weight: 700;
    margin-bottom: 4px;
  }
  .stat-label {
    font-size: 11px;
    color: #778;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .stat-number.positive { color: #4ade80; }
  .stat-number.negative { color: #f87171; }
  .stat-number.neutral { color: #60a5fa; }

  .scenario-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }
  .scenario-table th {
    text-align: right;
    padding: 8px 10px;
    color: #667;
    font-weight: 500;
    border-bottom: 1px solid #1e3a5f;
  }
  .scenario-table th:first-child { text-align: left; }
  .scenario-table td {
    text-align: right;
    padding: 8px 10px;
    border-bottom: 1px solid #111827;
  }
  .scenario-table td:first-child {
    text-align: left;
    font-weight: 600;
    color: #9cc;
  }
  .scenario-table tr.sfr-row { background: rgba(200,50,50,0.08); }
  .scenario-table tr.best-row { background: rgba(50,200,100,0.08); }
  .scenario-table .positive { color: #4ade80; }
  .scenario-table .negative { color: #f87171; }

  .payback-bar {
    display: flex;
    align-items: center;
    height: 22px;
    gap: 6px;
  }
  .payback-fill {
    height: 100%;
    border-radius: 3px;
    min-width: 4px;
  }
  .payback-text {
    font-size: 11px;
    color: #8899aa;
    white-space: nowrap;
  }

  .insight-box {
    background: rgba(50,200,100,0.08);
    border: 1px solid rgba(50,200,100,0.2);
    border-radius: 6px;
    padding: 12px 16px;
    margin-top: 12px;
    font-size: 12px;
    line-height: 1.6;
    color: #8e8;
  }
  .insight-box strong { color: #afa; }

  .warning-box {
    background: rgba(200,50,50,0.08);
    border: 1px solid rgba(200,50,50,0.2);
    border-radius: 6px;
    padding: 12px 16px;
    margin-bottom: 12px;
    font-size: 12px;
    line-height: 1.6;
    color: #e88;
  }

  #tooltip {
    position: fixed;
    z-index: 100;
    pointer-events: none;
    background: rgba(0,0,0,0.92);
    color: #fff;
    padding: 10px 14px;
    border-radius: 6px;
    font-size: 12px;
    line-height: 1.5;
    display: none;
    max-width: 280px;
    border: 1px solid #334;
  }

  .footnote {
    font-size: 11px;
    color: #556;
    padding: 12px 16px;
    border-top: 1px solid #1e3a5f;
    line-height: 1.5;
  }
</style>
</head>
<body>

<div class="header">
  <h1>Does Oceanside's Transit Infrastructure Block SB 79 Upzoning?</h1>
  <div class="subtitle">Parcel-level fiscal analysis of 12,400+ transit-area properties &mdash; Oceanside, CA</div>
  <div class="claim">
    <strong>Council's claim:</strong> "Our areas around transit do not have the infrastructure capacity to handle the upzoning."
  </div>
  <div class="rebuttal">
    <strong>The data:</strong> Existing pipes use 6% of capacity serving SFR. Even at 6&times; density, utilization stays under 30%.
    Upzoning pays for any needed upgrades in 3&ndash;9 years. Pipes last 75&ndash;100 years.
  </div>
</div>

<div class="dashboard">
  <div class="map-panel">
    <div id="map-container"></div>
    <div class="map-controls">
      <button onclick="setView('overview')" class="active" id="btn-overview">Overview</button>
      <button onclick="setView('downtown')">Downtown</button>
      <button onclick="setView('inland')">Inland Stations</button>
      <button onclick="toggleFilter()" id="btn-filter">Show Transit Only</button>
    </div>
    <div class="map-legend">
      <h4>Net Revenue per Acre</h4>
      <div class="legend-row">
        <div class="legend-swatch" style="background:rgb(15,15,80)"></div>
        <span>&minus;$30K+ (deep loss)</span>
      </div>
      <div class="legend-row">
        <div class="legend-swatch" style="background:rgb(40,140,210)"></div>
        <span>&minus;$5K (moderate loss)</span>
      </div>
      <div class="legend-row">
        <div class="legend-swatch" style="background:rgb(60,190,170)"></div>
        <span>$0 (breakeven)</span>
      </div>
      <div class="legend-row">
        <div class="legend-swatch" style="background:rgb(100,200,60)"></div>
        <span>+$5K (productive)</span>
      </div>
      <div class="legend-row">
        <div class="legend-swatch" style="background:rgb(230,70,25)"></div>
        <span>+$50K+ (highly productive)</span>
      </div>
      <div class="legend-row" style="margin-top:6px;">
        <div class="transit-ring-legend"></div>
        <span>&frac12;-mile transit buffer</span>
      </div>
    </div>
    <div id="tooltip"></div>
  </div>

  <div class="charts-panel" id="charts">
  </div>
</div>

<script>
const MAP_DATA = __MAP_JSON__;
const STATIONS = __STATION_JSON__;
const D = __DATA_JSON__;

const fmt = n => {
  if (Math.abs(n) >= 1e6) return (n<0?'-':'') + '$' + (Math.abs(n)/1e6).toFixed(1) + 'M';
  if (Math.abs(n) >= 1e3) return (n<0?'-':'') + '$' + (Math.abs(n)/1e3).toFixed(0) + 'K';
  return '$' + n.toLocaleString();
};
const pct = n => n.toFixed(1) + '%';
const comma = n => n.toLocaleString();

// Build charts
const chartsEl = document.getElementById('charts');

// ── 1. KEY STATS ──
let sfr = D.stats['SFR'] || {};
let bestCat = 'Condo/TH';
let bestData = D.stats[bestCat] || {};

chartsEl.innerHTML = `
<div class="stat-grid">
  <div class="stat-box">
    <div class="stat-number negative">${comma(D.sfr_count)}</div>
    <div class="stat-label">SFR Parcels Near Transit</div>
  </div>
  <div class="stat-box">
    <div class="stat-number negative">${fmt(D.sfr_net)}/yr</div>
    <div class="stat-label">SFR Net Fiscal Impact</div>
  </div>
  <div class="stat-box">
    <div class="stat-number neutral">${Math.round(D.sfr_acres).toLocaleString()} ac</div>
    <div class="stat-label">SFR Acres Near Transit</div>
  </div>
</div>

<div class="chart-card">
  <h3>&#x1f6a8; Pipe Capacity Utilization — 5.5-Acre Block</h3>
  <div class="chart-body">
    <p style="font-size:12px;color:#778;margin-bottom:12px;">
      Standard 8" sewer main serves <strong style="color:#aaa">588 EDUs</strong> at half capacity.
      How much does each housing type actually use?
    </p>
    <div id="capacity-chart"></div>
    <div class="insight-box" style="margin-top:14px;">
      <strong>Key finding:</strong> Current SFR uses 6% of pipe capacity.
      Even converting every lot to MFR 5-20 density (42 units/acre) only reaches 28%.
      <strong>No upzoning scenario exceeds existing capacity.</strong>
    </div>
  </div>
</div>

<div class="chart-card">
  <h3>&#x1f4b0; Cost to Serve per Unit — Transit Area</h3>
  <div class="chart-body">
    <div id="cost-chart"></div>
    <div class="insight-box">
      SFR costs <strong>$2,175/unit</strong> to serve — 4.3&times; more than MFR 5-20 at <strong>$511/unit</strong>.
      Dense housing is <em>cheaper</em> to serve, not more expensive.
    </div>
  </div>
</div>

<div class="chart-card">
  <h3>&#x1f4c8; Revenue Swing — Converting SFR Acres to Higher Density</h3>
  <div class="chart-body">
    <p style="font-size:12px;color:#778;margin-bottom:12px;">
      What if ${Math.round(D.sfr_acres).toLocaleString()} transit-area SFR acres
      produced revenue at existing MFR density patterns?
    </p>
    <div id="scenario-table-container"></div>
  </div>
</div>

<div class="chart-card">
  <h3>&#x23f1; Infrastructure Upgrade Payback</h3>
  <div class="chart-body">
    <div class="warning-box">
      <strong>Worst case:</strong> Full pipe replacement for one block costs ~$250K
      (0.5 mi sewer 8"&rarr;12" + water 6"&rarr;8"). What's the payback?
    </div>
    <div id="payback-chart"></div>
    <div class="insight-box">
      Pipes last <strong>75&ndash;100 years</strong>. Payback in under 10.
      <strong>The infrastructure pays for itself many times over.</strong>
    </div>
  </div>
</div>

<div class="chart-card">
  <h3>&#x1f3d7; Oceanside Is Already Upgrading Pipes</h3>
  <div class="chart-body" style="font-size:12px; line-height:1.7; color:#9ab;">
    <p><strong style="color:#ddd;">Downtown Sewer Phase 2:</strong> Replacing pipes under 8" diameter — some nearly 100 years old. Age drives replacement, not capacity.</p>
    <p style="margin-top:8px;"><strong style="color:#ddd;">Buccaneer Lift Station ($5M):</strong> Centralizing treatment, not adding capacity.</p>
    <p style="margin-top:8px;"><strong style="color:#ddd;">Pure Water Oceanside ($5M):</strong> Supply diversification via recycled water — the constraint is <em>water supply</em>, not pipes.</p>
    <p style="margin-top:8px;"><strong style="color:#ddd;">Cleveland Storm Drain ($940K):</strong> City already upsizes storm drains when needed — downtown.</p>
    <div class="insight-box" style="margin-top:14px;">
      Oceanside has <strong>$1.07B in utility assets</strong> needing $12.8M/yr capital replacement.
      Current CIP only budgets $8.26M/yr — a <strong>$4.5M/yr funding gap</strong>.
      Upzoning transit areas would <strong>close this gap</strong> by generating more revenue per acre on the same pipe network.
    </div>
  </div>
</div>

<div class="footnote">
  Data: Oceanside FY25-26 parcel assessments, fiscal productivity model v2, CIP FY25-30.
  Transit areas defined as &frac12;-mile radius around 7 Sprinter/Coaster stations.
  EDU = Equivalent Dwelling Unit (SFR=1.0, MFR=0.7). Pipe capacity per AWWA M11 / CalICHI standards.
  Pipe cost estimates from RSMeans 2023 + AWWA M28 adjusted for SoCal.
</div>
`;

// ── CAPACITY GAUGE CHART ──
const capEl = document.getElementById('capacity-chart');
const blockData = D.block || [];
let capHtml = '';
const maxPct = Math.max(...blockData.map(b => b.pipe_pct), 100);
const gaugeMax = Math.min(maxPct * 1.3, 120);

blockData.forEach((b, i) => {
  const w = Math.max(b.pipe_pct / gaugeMax * 100, 2);
  const isSfr = i === 0;
  const color = isSfr ? 'rgba(200,70,70,0.8)' :
    b.pipe_pct > 80 ? 'rgba(230,160,30,0.8)' :
    b.pipe_pct > 50 ? 'rgba(100,200,60,0.7)' :
    'rgba(60,180,140,0.7)';

  capHtml += `
    <div class="bar-row" style="margin-bottom:10px;">
      <div class="bar-label">${b.name}</div>
      <div class="bar-track" style="height:34px;">
        <div class="gauge-fill" style="width:${w}%;background:${color};height:100%;">
          ${b.units} units &mdash; ${pct(b.pipe_pct)}
        </div>
      </div>
    </div>`;
});

// Add 100% capacity marker explanation
capHtml += `<div style="font-size:11px;color:#667;margin-top:8px;text-align:right;">
  8" sewer at half-full = 588 EDU capacity per block &mdash; 100% marker not shown because no scenario gets close
</div>`;
capEl.innerHTML = capHtml;

// ── COST PER UNIT CHART ──
const costEl = document.getElementById('cost-chart');
const costOrder = ['SFR', 'Condo/TH', 'Duplex', '3-4 Plex', 'MFR 5-20', 'MFR 21-100', 'Commercial'];
const maxCost = Math.max(...costOrder.map(c => D.stats[c] ? D.stats[c].cost_per_unit : 0));
let costHtml = '';

costOrder.forEach(cat => {
  const s = D.stats[cat];
  if (!s) return;
  const w = s.cost_per_unit / maxCost * 100;
  const revW = s.rev_per_unit / maxCost * 100;
  const isSfr = cat === 'SFR';
  const deficit = s.cost_per_unit > s.rev_per_unit;

  costHtml += `
    <div style="margin-bottom:10px;">
      <div class="bar-row">
        <div class="bar-label">${cat}</div>
        <div style="flex:1;position:relative;">
          <div class="bar-track">
            <div class="bar-fill" style="width:${w}%;background:${deficit ? 'rgba(200,70,70,0.6)' : 'rgba(100,180,60,0.6)'};position:absolute;z-index:1;">
            </div>
            <div class="bar-fill" style="width:${Math.min(revW,100)}%;background:${deficit ? 'rgba(180,180,60,0.4)' : 'rgba(60,200,100,0.4)'};position:absolute;z-index:2;border:1px solid rgba(255,255,255,0.2);">
            </div>
          </div>
          <div style="font-size:11px;color:#889;margin-top:2px;">
            Cost: <span style="color:${deficit ? '#f88' : '#8e8'}">${fmt(s.cost_per_unit)}</span>
            &nbsp;|&nbsp; Rev: <span style="color:#6af">${fmt(s.rev_per_unit)}</span>/unit
          </div>
        </div>
      </div>
    </div>`;
});
costHtml += `<div style="font-size:11px;color:#556;margin-top:4px;">
  <span style="color:#f88">&#9632;</span> Cost/unit &nbsp;
  <span style="color:#6af">&#9634;</span> Revenue/unit &mdash;
  SFR is only type where cost exceeds revenue
</div>`;
costEl.innerHTML = costHtml;

// ── SCENARIO TABLE ──
const scenEl = document.getElementById('scenario-table-container');
const scenarios = D.scenarios || [];
let tHtml = '<table class="scenario-table"><thead><tr>';
tHtml += '<th style="text-align:left">Scenario</th><th>Density</th><th>Units</th>';
tHtml += '<th>Net/Year</th><th>&Delta; from SFR</th><th>Pipe Use</th>';
tHtml += '</tr></thead><tbody>';

let bestDelta = 0;
scenarios.forEach(s => { if (s.delta_net > bestDelta) bestDelta = s.delta_net; });

scenarios.forEach((s, i) => {
  const isSfr = i === 0;
  const isBest = s.delta_net === bestDelta && bestDelta > 0;
  const cls = isSfr ? 'sfr-row' : isBest ? 'best-row' : '';
  const netCls = s.net >= 0 ? 'positive' : 'negative';
  const deltaCls = s.delta_net > 0 ? 'positive' : s.delta_net < 0 ? 'negative' : '';

  tHtml += `<tr class="${cls}">`;
  tHtml += `<td>${s.name}</td>`;
  tHtml += `<td>${s.density.toFixed(1)} u/ac</td>`;
  tHtml += `<td>${comma(s.units)}</td>`;
  tHtml += `<td class="${netCls}">${fmt(s.net)}</td>`;
  tHtml += `<td class="${deltaCls}">${isSfr ? '—' : (s.delta_net > 0 ? '+' : '') + fmt(s.delta_net)}</td>`;
  tHtml += `<td>${pct(s.pipe_util_pct)}</td>`;
  tHtml += `</tr>`;
});
tHtml += '</tbody></table>';
scenEl.innerHTML = tHtml;

// ── PAYBACK CHART ──
const payEl = document.getElementById('payback-chart');
const payData = blockData.filter(b => b.payback_yrs != null);
const maxPayback = Math.max(...payData.map(b => b.payback_yrs), 15);
let payHtml = '';

payData.forEach(b => {
  const w = b.payback_yrs / maxPayback * 100;
  const color = b.payback_yrs <= 5 ? '#4ade80' : b.payback_yrs <= 10 ? '#fbbf24' : '#f87171';
  const delta = b.net_fiscal - blockData[0].net_fiscal;

  payHtml += `
    <div style="margin-bottom:10px;">
      <div style="font-size:12px;font-weight:600;color:#9cc;margin-bottom:4px;">${b.name}</div>
      <div class="payback-bar">
        <div class="payback-fill" style="width:${w}%;background:${color}"></div>
        <div class="payback-text">
          <strong style="color:${color}">${b.payback_yrs} years</strong>
          &mdash; +${comma(delta)}/yr revenue &rarr; $250K upgrade
        </div>
      </div>
    </div>`;
});
payEl.innerHTML = payHtml;

// ── MAP ──
let filterTransit = false;
let deckgl;

function getFilteredData() {
  return filterTransit ? MAP_DATA.filter(d => d.t === 1) : MAP_DATA;
}

function buildLayers() {
  const data = getFilteredData();
  return [
    new deck.PolygonLayer({
      id: 'parcels',
      data: data,
      getPolygon: d => d.p,
      getFillColor: d => d.c,
      getLineColor: [0, 0, 0, 30],
      getLineWidth: 0.3,
      lineWidthMinPixels: 0,
      pickable: true,
      autoHighlight: true,
      highlightColor: [255, 255, 255, 80],
    }),
    new deck.PolygonLayer({
      id: 'station-rings',
      data: STATIONS,
      getPolygon: d => d.p,
      getFillColor: [0, 0, 0, 0],
      getLineColor: [255, 200, 50, 120],
      getLineWidth: 2,
      lineWidthMinPixels: 2,
      lineWidthMaxPixels: 3,
      stroked: true,
      filled: false,
      pickable: false,
      getDashArray: [8, 4],
      dashJustified: true,
      extensions: [new deck.PathStyleExtension({dash: true})],
    }),
    new deck.TextLayer({
      id: 'station-labels',
      data: STATIONS,
      getPosition: d => [d.lon, d.lat],
      getText: d => d.name,
      getSize: 13,
      getColor: [255, 200, 50, 200],
      getAngle: 0,
      getTextAnchor: 'middle',
      getAlignmentBaseline: 'center',
      fontFamily: '-apple-system, BlinkMacSystemFont, sans-serif',
      fontWeight: '600',
      outlineWidth: 3,
      outlineColor: [0, 0, 0, 200],
      billboard: false,
    }),
  ];
}

const VIEWS = {
  overview: { longitude: __CENTER_LON__, latitude: __CENTER_LAT__, zoom: 11.5, pitch: 0, bearing: 0 },
  downtown: { longitude: -117.375, latitude: 33.193, zoom: 14.5, pitch: 0, bearing: 0 },
  inland: { longitude: -117.295, latitude: 33.218, zoom: 13, pitch: 0, bearing: 0 },
};

const tooltip = document.getElementById('tooltip');

deckgl = new deck.DeckGL({
  container: 'map-container',
  initialViewState: VIEWS.overview,
  controller: true,
  layers: buildLayers(),
  getTooltip: ({object}) => {
    if (!object) { tooltip.style.display = 'none'; return null; }
    return null;
  },
  onHover: (info) => {
    if (!info.object) {
      tooltip.style.display = 'none';
      return;
    }
    const d = info.object;
    const net = d.npa;
    const status = net >= 0 ? '<span style="color:#4ade80">ASSET</span>' : '<span style="color:#f87171">LOSS</span>';
    const transit = d.t ? `<br>Transit: <strong>${d.s}</strong>` : '';

    tooltip.innerHTML = `
      <div style="font-weight:600;margin-bottom:4px;">${d.cat} ${status}</div>
      <div>Net: <strong style="color:${net>=0?'#4ade80':'#f87171'}">${fmt(net)}/acre</strong></div>
      <div>Revenue: ${fmt(d.gr)} | Cost: ${fmt(d.gc)}</div>
      <div>Units: ${d.u} | Acres: ${d.ac}${transit}</div>
    `;
    tooltip.style.display = 'block';
    tooltip.style.left = (info.x + 12) + 'px';
    tooltip.style.top = (info.y + 12) + 'px';
  },
});

function setView(name) {
  deckgl.setProps({ initialViewState: { ...VIEWS[name], transitionDuration: 800 } });
  document.querySelectorAll('.map-controls button').forEach(b => b.classList.remove('active'));
  document.getElementById('btn-' + name)?.classList.add('active');
}

function toggleFilter() {
  filterTransit = !filterTransit;
  const btn = document.getElementById('btn-filter');
  btn.textContent = filterTransit ? 'Show All Parcels' : 'Show Transit Only';
  btn.classList.toggle('active', filterTransit);
  deckgl.setProps({ layers: buildLayers() });
}
</script>
</body>
</html>"""
    return (tpl
        .replace("__MAP_JSON__", map_json)
        .replace("__STATION_JSON__", station_json)
        .replace("__DATA_JSON__", data_json)
        .replace("__CENTER_LON__", str(center_lon))
        .replace("__CENTER_LAT__", str(center_lat))
    )


if __name__ == "__main__":
    main()
