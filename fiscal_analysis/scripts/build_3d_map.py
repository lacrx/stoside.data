#!/usr/bin/env python3
"""Build Urban3-style 3D choropleth of fiscal productivity per parcel.

Height = net $/acre (signed — assets extrude UP, losses extrude DOWN).
Red = loss (below ground), green = asset (above ground).

Consolidates stacked ownership (condos sharing identical polygons)
into single building features so multi-unit buildings render as one
extrusion with summed revenue/cost, not invisible slivers.
"""

import json
import math
from collections import defaultdict
from pathlib import Path

from shapely.geometry import shape
from shapely import wkt

HERE = Path(__file__).parent.parent
PARCEL_FILE = HERE / "parcels_oceanside.geojson"
V2_FILE = HERE / "fiscal_productivity_v2.json"
MARKET_FILE = HERE / "market_values.json"
WATER_FILE = HERE / "raw_data" / "water_mains_oceanside.geojson"
SEWER_FILE = HERE / "raw_data" / "sewer_mains_oceanside.geojson"
OUTPUT = HERE / "visuals" / "fiscal_3d_map.html"

HEIGHT_SCALE = 0.012
MAX_HEIGHT = 10000

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


def near_station(lon: float, lat: float) -> bool:
    for slon, slat in STATIONS.values():
        dlat = lat - slat
        dlon = (lon - slon) * math.cos(math.radians(slat))
        if math.sqrt(dlat**2 + dlon**2) * 69.0 <= 0.5:
            return True
    return False


def load_pipes(path: Path) -> list[dict]:
    with open(path) as f:
        geo = json.load(f)
    pipes = []
    for feat in geo["features"]:
        geom = feat.get("geometry")
        if not geom or geom["type"] not in ("LineString", "MultiLineString"):
            continue
        props = feat["properties"]
        d = props.get("DIAMETER")
        if d is None or (isinstance(d, float) and math.isnan(d)):
            d = 6
        d = int(d)
        if d <= 0 or d >= 999:
            d = 6
        if geom["type"] == "MultiLineString":
            coords_list = geom["coordinates"]
        else:
            coords_list = [geom["coordinates"]]
        for coords in coords_list:
            simplified = [[round(c[0], 5), round(c[1], 5)] for c in coords]
            if len(simplified) > 20:
                step = max(1, len(simplified) // 15)
                simplified = simplified[::step]
                if simplified[-1] != [round(coords[-1][0], 5), round(coords[-1][1], 5)]:
                    simplified.append([round(coords[-1][0], 5), round(coords[-1][1], 5)])
            pipes.append({"p": simplified, "d": d})
    return pipes


COLOR_STOPS = [
    (-30000, [200, 20, 20]),
    (-15000, [220, 60, 40]),
    (-5000,  [230, 130, 50]),
    (0,      [220, 210, 60]),
    (5000,   [150, 210, 60]),
    (15000,  [80, 200, 60]),
    (30000,  [40, 180, 50]),
    (50000,  [30, 160, 60]),
    (100000, [20, 130, 50]),
    (200000, [15, 100, 40]),
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


def polygon_key(geom) -> str:
    """Create a hashable key from polygon bounds + centroid for grouping."""
    b = geom.bounds
    c = geom.centroid
    return f"{b[0]:.6f},{b[1]:.6f},{b[2]:.6f},{b[3]:.6f},{c.x:.6f},{c.y:.6f}"


def consolidate_parcels(geo_features, v2_map, mv_map):
    """Group parcels sharing identical polygons. Sum their fiscal data."""

    # First pass: build polygon groups
    poly_groups = defaultdict(list)
    geom_cache = {}

    for feat in geo_features:
        props = feat["properties"]
        apn = props["APN"]
        fp = v2_map.get(apn)
        mp = mv_map.get(apn)
        if not fp or not mp:
            continue

        geom = shape(feat["geometry"])
        key = polygon_key(geom)
        geom_cache[key] = feat["geometry"]
        poly_groups[key].append((apn, fp, mp))

    # Second pass: consolidate
    consolidated = []
    n_consolidated = 0

    for key, group in poly_groups.items():
        geometry = geom_cache[key]
        geom = shape(geometry)

        # Compute real acres from projected geometry
        # WGS84 degrees to approximate sqft at Oceanside latitude (33.2°)
        # 1 degree lat ≈ 364,000 ft, 1 degree lon ≈ 305,000 ft at 33.2°
        b = geom.bounds
        width_ft = (b[2] - b[0]) * 305000
        height_ft = (b[3] - b[1]) * 364000
        approx_area_sqft = geom.area * 305000 * 364000
        acres = approx_area_sqft / 43560
        if acres < 0.005:
            acres = 0.01

        total_rev = sum(fp["revenue"]["gf_total"] for _, fp, _ in group)
        total_cost = sum(fp["gf_costs"]["total"] for _, fp, _ in group)
        total_assessed = sum(mp["assessed_total"] for _, _, mp in group)
        total_market = sum(mp["market_value"] for _, _, mp in group)
        total_units = sum(fp.get("units", 0) or 0 for _, fp, _ in group)

        # Weighted average suppression
        if total_market > 0:
            suppression = total_assessed / total_market
        else:
            suppression = 1.0

        # Market revenue: sum individual market revenues
        total_mkt_rev = 0
        for _, fp, mp in group:
            s = mp["suppression_ratio"]
            p13_ptax = fp["revenue"]["property_tax"]
            if s > 0 and s < 1.0:
                mkt_ptax = p13_ptax / s
            elif mp["market_value"] > 0 and mp["assessed_total"] > 0:
                mkt_ptax = p13_ptax * (mp["market_value"] / mp["assessed_total"])
            else:
                mkt_ptax = p13_ptax
            total_mkt_rev += fp["revenue"]["gf_total"] + (mkt_ptax - p13_ptax)

        p13_net = total_rev - total_cost
        p13_npa = p13_net / acres

        mkt_net = total_mkt_rev - total_cost
        mkt_npa = mkt_net / acres

        # Primary category: most common in group, or highest revenue
        cat_counts = defaultdict(int)
        for _, fp, _ in group:
            cat_counts[fp.get("land_use_broad", "Other")] += 1
        primary_cat = max(cat_counts, key=cat_counts.get)

        if primary_cat in ("Vacant", "Government", "Other"):
            continue

        if len(group) > 1:
            n_consolidated += len(group) - 1
            label = f"{group[0][0]}+{len(group)-1}"
        else:
            label = group[0][0]

        cx = geom.centroid.x
        cy = geom.centroid.y
        is_transit = near_station(cx, cy)

        consolidated.append({
            "geometry": geometry,
            "acres": acres,
            "apn": label,
            "cat": primary_cat,
            "units": total_units or len(group),
            "p13_npa": p13_npa,
            "mkt_npa": mkt_npa,
            "p13_net": p13_net,
            "mkt_net": mkt_net,
            "gf_rev": total_rev,
            "gf_cost": total_cost,
            "assessed": total_assessed,
            "market": total_market,
            "suppression": round(suppression, 3),
            "n_parcels": len(group),
            "transit": is_transit,
        })

    return consolidated, n_consolidated


def main():
    print("Loading data...")
    with open(PARCEL_FILE) as f:
        geo = json.load(f)

    with open(V2_FILE) as f:
        v2 = json.load(f)
    v2_map = {p["apn"]: p for p in v2["parcels"]}

    with open(MARKET_FILE) as f:
        mv = json.load(f)
    mv_map = {p["apn"]: p for p in mv["parcels"]}

    print("Consolidating stacked parcels...")
    consolidated, n_merged = consolidate_parcels(geo["features"], v2_map, mv_map)
    print(f"  {len(geo['features']):,} raw parcels → {len(consolidated):,} map features")
    print(f"  {n_merged:,} parcels merged into existing features")

    print("Building map features...")
    features = []
    loss_count = 0
    asset_count = 0

    for item in consolidated:
        p13_npa = item["p13_npa"]
        mkt_npa = item["mkt_npa"]

        if p13_npa >= 0:
            asset_count += 1
        else:
            loss_count += 1

        p13_h = p13_npa * HEIGHT_SCALE
        p13_h = max(min(p13_h, MAX_HEIGHT), -MAX_HEIGHT)
        if abs(p13_h) < 3:
            p13_h = 3 if p13_npa >= 0 else -3

        mkt_h = mkt_npa * HEIGHT_SCALE
        mkt_h = max(min(mkt_h, MAX_HEIGHT), -MAX_HEIGHT)
        if abs(mkt_h) < 3:
            mkt_h = 3 if mkt_npa >= 0 else -3
        p13_c = net_to_color(p13_npa)
        mkt_c = net_to_color(mkt_npa)

        coords = item["geometry"].get("coordinates", [])
        geom_type = item["geometry"].get("type", "")

        if geom_type == "MultiPolygon":
            polys = [ring for poly in coords for ring in [poly[0]]]
        elif geom_type == "Polygon":
            polys = [coords[0]]
        else:
            continue

        for poly in polys:
            simplified = [[round(c[0], 5), round(c[1], 5)] for c in poly]
            if len(simplified) > 30:
                step = max(1, len(simplified) // 25)
                simplified = simplified[::step]
                if simplified[-1] != simplified[0]:
                    simplified.append(simplified[0])

            features.append({
                "p": simplified,
                "h": round(p13_h, 1),
                "mh": round(mkt_h, 1),
                "c": p13_c,
                "mc": mkt_c,
                "npa": round(p13_npa),
                "mnpa": round(mkt_npa),
                "apn": item["apn"],
                "cat": item["cat"],
                "u": item["units"],
                "np": item["n_parcels"],
                "gr": round(item["gf_rev"]),
                "gc": round(item["gf_cost"]),
                "net": round(item["p13_net"]),
                "mnet": round(item["mkt_net"]),
                "av": item["assessed"],
                "mv": item["market"],
                "s": item["suppression"],
                "ac": round(item["acres"], 3),
                "t": 1 if item["transit"] else 0,
            })

    print(f"  {len(features):,} polygons")
    print(f"  Assets: {asset_count:,}  Losses: {loss_count:,}")

    OUTPUT.parent.mkdir(exist_ok=True)

    all_lons = []
    all_lats = []
    for f in features[:1000]:
        for c in f["p"][:4]:
            all_lons.append(c[0])
            all_lats.append(c[1])
    center_lon = sum(all_lons) / len(all_lons)
    center_lat = sum(all_lats) / len(all_lats)

    print("Loading pipes...")
    water_pipes = load_pipes(WATER_FILE)
    sewer_pipes = load_pipes(SEWER_FILE)
    print(f"  Water: {len(water_pipes):,} segments  Sewer: {len(sewer_pipes):,} segments")

    station_rings = []
    for name, (lon, lat) in STATIONS.items():
        ring = []
        for i in range(65):
            angle = 2 * math.pi * i / 64
            dx = HALF_MILE * math.cos(angle) / math.cos(math.radians(lat))
            dy = HALF_MILE * math.sin(angle)
            ring.append([round(lon + dx, 6), round(lat + dy, 6)])
        station_rings.append({"p": ring, "name": name, "lon": lon, "lat": lat})

    transit_count = sum(1 for f in features if f["t"])
    print(f"  Transit-area parcels: {transit_count:,}")

    data_json = json.dumps(features, separators=(',', ':'))
    water_json = json.dumps(water_pipes, separators=(',', ':'))
    sewer_json = json.dumps(sewer_pipes, separators=(',', ':'))
    stations_json = json.dumps(station_rings, separators=(',', ':'))

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Oceanside Fiscal Productivity — Net $/Acre</title>
<script src="https://unpkg.com/deck.gl@9.0.16/dist.min.js"></script>
<style>
  body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #080816; }}
  #container {{ width: 100vw; height: 100vh; position: relative; }}
  #tooltip {{
    position: absolute; z-index: 1; pointer-events: none;
    background: rgba(0,0,0,0.92); color: #fff; padding: 12px 16px;
    border-radius: 6px; font-size: 13px; line-height: 1.6;
    max-width: 360px; display: none; border: 1px solid rgba(255,255,255,0.12);
  }}
  .pos {{ color: #4ade80; font-weight: 600; }}
  .neg {{ color: #f87171; font-weight: 600; }}
  .muted {{ opacity: 0.5; font-size: 11px; }}
  #legend {{
    position: absolute; bottom: 20px; left: 20px; z-index: 1;
    background: rgba(0,0,0,0.88); color: #fff; padding: 16px 20px;
    border-radius: 8px; font-size: 12px; line-height: 1.8;
    border: 1px solid rgba(255,255,255,0.08);
  }}
  #legend h3 {{ margin: 0 0 10px 0; font-size: 14px; }}
  .lr {{ display: flex; align-items: center; gap: 8px; }}
  .sw {{ width: 18px; height: 14px; border-radius: 2px; flex-shrink: 0; }}
  .ld {{ border-top: 2px solid rgba(255,255,255,0.25); margin: 8px 0; }}
  #controls {{
    position: absolute; top: 20px; right: 20px; z-index: 1;
    background: rgba(0,0,0,0.88); color: #fff; padding: 16px 20px;
    border-radius: 8px; font-size: 13px; border: 1px solid rgba(255,255,255,0.08);
  }}
  #controls label {{ display: block; margin: 6px 0; cursor: pointer; }}
  #title {{
    position: absolute; top: 20px; left: 20px; z-index: 1;
    background: rgba(0,0,0,0.88); color: #fff; padding: 18px 22px;
    border-radius: 8px; border: 1px solid rgba(255,255,255,0.08);
  }}
  #title h2 {{ margin: 0 0 6px 0; font-size: 18px; }}
  #title p {{ margin: 0; font-size: 12px; opacity: 0.7; }}
  .cam-btn {{
    background: rgba(255,255,255,0.1); color: #fff; border: 1px solid rgba(255,255,255,0.2);
    border-radius: 4px; padding: 4px 10px; cursor: pointer; font-size: 11px;
  }}
  .cam-btn:hover {{ background: rgba(255,255,255,0.25); }}
</style>
</head>
<body>
<div id="container"></div>
<div id="tooltip"></div>
<div id="title">
  <h2>Oceanside — Net Fiscal Impact per Acre</h2>
  <p><span style="color:#28b432">Green/tall</span> = productive &nbsp;|&nbsp; <span style="color:#c81414">Red/low</span> = drain &nbsp;|&nbsp; Height = net $/acre</p>
  <p style="margin-top:4px; opacity:0.4">Drag to rotate &nbsp;|&nbsp; Scroll to zoom</p>
</div>
<div id="legend">
  <h3>Net $/Acre</h3>
  <div class="lr"><div class="sw" style="background:#0f6428"></div> +$200K+</div>
  <div class="lr"><div class="sw" style="background:#148232"></div> +$100K</div>
  <div class="lr"><div class="sw" style="background:#1ea03c"></div> +$50K</div>
  <div class="lr"><div class="sw" style="background:#28b432"></div> +$30K</div>
  <div class="lr"><div class="sw" style="background:#50c83c"></div> +$15K</div>
  <div class="lr"><div class="sw" style="background:#96d23c"></div> +$5K</div>
  <div class="ld"></div>
  <div class="lr" style="font-weight:600; color:#dcd23c">BREAK EVEN</div>
  <div class="ld"></div>
  <div class="lr"><div class="sw" style="background:#e68232"></div> −$5K</div>
  <div class="lr"><div class="sw" style="background:#dc3c28"></div> −$15K</div>
  <div class="lr"><div class="sw" style="background:#c81414"></div> −$30K+</div>
  <div class="ld"></div>
  <div style="font-size:11px; opacity:0.6;">
    <span style="color:#28b432">Green</span> = productive &nbsp;
    <span style="color:#c81414">Red</span> = drain<br>
    Height = magnitude of net impact
  </div>
  <div class="ld"></div>
  <div style="font-size:11px; opacity:0.6;">
    <span style="color:#3282dc">Blue lines</span> = water mains &nbsp;
    <span style="color:#b46428">Brown lines</span> = sewer mains
  </div>
</div>
<div id="controls">
  <strong>View Mode</strong>
  <label><input type="radio" name="mode" value="prop13" checked> Prop 13 (actual)</label>
  <label><input type="radio" name="mode" value="market"> Market value (no Prop 13)</label>
  <div style="margin-top:12px; border-top:1px solid rgba(255,255,255,0.15); padding-top:10px;">
    <strong>Infrastructure</strong>
    <label><input type="checkbox" id="showWater" checked> Water mains</label>
    <label><input type="checkbox" id="showSewer" checked> Sewer mains</label>
  </div>
  <div style="margin-top:12px; border-top:1px solid rgba(255,255,255,0.15); padding-top:10px;">
    <strong>Transit</strong>
    <label><input type="checkbox" id="transitOnly"> Transit stations only</label>
    <label><input type="checkbox" id="showBuffers"> Show half-mile buffers</label>
  </div>
  <label style="margin-top:12px"><input type="checkbox" id="flatMode"> Flat (2D) view</label>
  <div style="margin-top:14px; border-top:1px solid rgba(255,255,255,0.15); padding-top:10px;">
    <strong>Camera</strong>
    <div style="display:flex; flex-wrap:wrap; gap:4px; margin-top:6px;">
      <button class="cam-btn" data-pitch="0" data-bearing="0" data-zoom="12">Top</button>
      <button class="cam-btn" data-pitch="50" data-bearing="-25" data-zoom="12">Standard</button>
      <button class="cam-btn" data-pitch="72" data-bearing="-25" data-zoom="13">Dramatic</button>
      <button class="cam-btn" data-pitch="82" data-bearing="-40" data-zoom="14">Street</button>
    </div>
  </div>
</div>
<script>
const DATA = {data_json};
const WP = {water_json};
const SP = {sewer_json};
const ST = {stations_json};
let currentMode = 'prop13';
let flatMode = false;
let transitOnly = false;
let showBuffers = false;
let showWater = true;
let showSewer = true;

function fmt(n) {{
  if (n >= 0) return '+$' + n.toLocaleString();
  return '−$' + Math.abs(n).toLocaleString();
}}

const tooltip = document.getElementById('tooltip');

const BASE = 200;

const deckgl = new deck.DeckGL({{
  container: 'container',
  initialViewState: {{
    longitude: {center_lon},
    latitude: {center_lat},
    zoom: 12,
    pitch: 55,
    bearing: -25,
    maxPitch: 85,
  }},
  controller: true,
  layers: [],
  onHover: ({{object, x, y}}) => {{
    if (object) {{
      const isMarket = currentMode === 'market';
      const npa = isMarket ? object.mnpa : object.npa;
      const net = isMarket ? object.mnet : object.net;
      const cls = npa >= 0 ? 'pos' : 'neg';
      const multi = object.np > 1 ? `<br><span class="muted">${{object.np}} parcels consolidated (${{object.u}} units)</span>` : '';
      tooltip.style.display = 'block';
      tooltip.style.left = (x + 14) + 'px';
      tooltip.style.top = (y + 14) + 'px';
      tooltip.innerHTML = `
        <strong>${{object.apn}}</strong> — ${{object.cat}}${{multi}}<br>
        <span class="${{cls}}" style="font-size:16px">${{fmt(npa)}}/acre</span> on ${{object.ac}} acres<br>
        Net: ${{fmt(net)}}<br>
        <hr style="border-color:rgba(255,255,255,0.12);margin:6px 0">
        GF Revenue: $${{object.gr.toLocaleString()}}<br>
        GF Cost: $${{object.gc.toLocaleString()}}<br>
        <hr style="border-color:rgba(255,255,255,0.12);margin:6px 0">
        Assessed: $${{object.av.toLocaleString()}}<br>
        Market: $${{object.mv.toLocaleString()}}<br>
        <span class="muted">Prop 13 suppression: ${{object.s}}x</span>
      `;
    }} else {{
      tooltip.style.display = 'none';
    }}
  }},
}});

function pipeWidth(d) {{
  if (d >= 36) return 60; if (d >= 24) return 42;
  if (d >= 16) return 28; if (d >= 12) return 20;
  if (d >= 8) return 14; if (d >= 6) return 9;
  return 5;
}}

function updateLayers() {{
  const isMarket = currentMode === 'market';
  const filtered = transitOnly ? DATA.filter(d => d.t) : DATA;
  const hasPipes = showWater || showSewer;
  const layers = [];

  if (showWater) {{
    layers.push(new deck.PathLayer({{
      id: 'water-pipes',
      data: WP,
      getPath: d => d.p,
      getWidth: d => pipeWidth(d.d),
      getColor: [50, 130, 220, 200],
      widthMinPixels: 0.5,
      widthMaxPixels: 14,
      capRounded: true,
      jointRounded: true,
      pickable: false,
    }}));
  }}
  if (showSewer) {{
    layers.push(new deck.PathLayer({{
      id: 'sewer-pipes',
      data: SP,
      getPath: d => d.p,
      getWidth: d => pipeWidth(d.d),
      getColor: [180, 100, 40, 200],
      widthMinPixels: 0.5,
      widthMaxPixels: 14,
      capRounded: true,
      jointRounded: true,
      pickable: false,
    }}));
  }}

  layers.push(new deck.PolygonLayer({{
    id: 'parcels',
    data: filtered,
    _full3d: true,
    getPolygon: d => {{
      if (flatMode) return d.p.map(c => [c[0], c[1], BASE]);
      const h = isMarket ? d.mh : d.h;
      const z = h >= 0 ? BASE : BASE + h;
      return d.p.map(c => [c[0], c[1], z]);
    }},
    getElevation: d => {{
      if (flatMode) return 5;
      const h = isMarket ? d.mh : d.h;
      return Math.abs(h);
    }},
    getFillColor: d => {{
      const c = isMarket ? d.mc : d.c;
      return hasPipes ? [c[0], c[1], c[2], 150] : c;
    }},
    extruded: true,
    wireframe: false,
    elevationScale: 1,
    pickable: true,
    autoHighlight: true,
    highlightColor: [255, 255, 255, 70],
    material: {{
      ambient: 0.35,
      diffuse: 0.65,
      shininess: 25,
      specularColor: [200, 200, 200],
    }},
    updateTriggers: {{
      getFillColor: [currentMode, hasPipes],
      getElevation: [currentMode, flatMode],
      getPolygon: [currentMode, flatMode],
    }},
  }}));

  if (showBuffers) {{
    layers.push(new deck.PolygonLayer({{
      id: 'buffers',
      data: ST,
      getPolygon: d => d.p.map(c => [c[0], c[1], BASE]),
      getFillColor: [255, 200, 50, 12],
      getLineColor: [255, 200, 50, 120],
      getLineWidth: 2,
      lineWidthMinPixels: 1,
      stroked: true,
      filled: true,
      extruded: false,
    }}));
    layers.push(new deck.TextLayer({{
      id: 'station-labels',
      data: ST,
      getPosition: d => [d.lon, d.lat, BASE + 100],
      getText: d => d.name,
      getSize: 13,
      getColor: [255, 200, 50, 220],
      getTextAnchor: 'middle',
      getAlignmentBaseline: 'center',
      fontFamily: '-apple-system, sans-serif',
      fontWeight: '600',
      outlineWidth: 3,
      outlineColor: [0, 0, 0, 220],
      billboard: true,
    }}));
  }}
  deckgl.setProps({{ layers }});
}}

document.querySelectorAll('input[name="mode"]').forEach(el => {{
  el.addEventListener('change', e => {{
    currentMode = e.target.value;
    updateLayers();
  }});
}});

document.getElementById('flatMode').addEventListener('change', e => {{
  flatMode = e.target.checked;
  updateLayers();
}});

document.getElementById('transitOnly').addEventListener('change', e => {{
  transitOnly = e.target.checked;
  updateLayers();
}});

document.getElementById('showBuffers').addEventListener('change', e => {{
  showBuffers = e.target.checked;
  updateLayers();
}});

document.getElementById('showWater').addEventListener('change', e => {{
  showWater = e.target.checked;
  updateLayers();
}});

document.getElementById('showSewer').addEventListener('change', e => {{
  showSewer = e.target.checked;
  updateLayers();
}});

document.querySelectorAll('.cam-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    deckgl.setProps({{
      initialViewState: {{
        longitude: {center_lon},
        latitude: {center_lat},
        zoom: parseFloat(btn.dataset.zoom),
        pitch: parseFloat(btn.dataset.pitch),
        bearing: parseFloat(btn.dataset.bearing),
        maxPitch: 85,
        transitionDuration: 1000,
      }},
    }});
  }});
}});

updateLayers();
</script>
</body>
</html>"""

    OUTPUT.write_text(html)
    size_mb = OUTPUT.stat().st_size / 1_048_576
    print(f"\n→ {OUTPUT} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
