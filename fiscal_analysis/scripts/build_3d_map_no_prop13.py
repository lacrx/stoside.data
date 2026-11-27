#!/usr/bin/env python3
"""Build 3D choropleth showing Oceanside WITHOUT Prop 13.

All parcels assessed at estimated market value.
Height = net $/acre (signed — assets UP, losses DOWN below ground).
Consolidates stacked ownership (condos) into single building features.
"""

import json
from collections import defaultdict
from pathlib import Path

from shapely.geometry import shape

HERE = Path(__file__).parent.parent
PARCEL_FILE = HERE / "parcels_oceanside.geojson"
V2_FILE = HERE / "fiscal_productivity_v2.json"
MARKET_FILE = HERE / "market_values.json"
OUTPUT = HERE / "visuals" / "fiscal_3d_no_prop13.html"

HEIGHT_SCALE = 0.012
MAX_HEIGHT = 10000


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


def polygon_key(geom) -> str:
    b = geom.bounds
    c = geom.centroid
    return f"{b[0]:.6f},{b[1]:.6f},{b[2]:.6f},{b[3]:.6f},{c.x:.6f},{c.y:.6f}"


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
    poly_groups = defaultdict(list)
    geom_cache = {}

    for feat in geo["features"]:
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

    features = []
    total_p13_rev = 0
    total_mkt_rev = 0
    total_cost = 0
    loss_count = 0
    asset_count = 0
    n_merged = 0

    for key, group in poly_groups.items():
        geometry = geom_cache[key]
        geom = shape(geometry)

        approx_area_sqft = geom.area * 305000 * 364000
        acres = approx_area_sqft / 43560
        if acres < 0.005:
            acres = 0.01

        gf_rev = sum(fp["revenue"]["gf_total"] for _, fp, _ in group)
        gf_cost = sum(fp["gf_costs"]["total"] for _, fp, _ in group)
        assessed = sum(mp["assessed_total"] for _, _, mp in group)
        market = sum(mp["market_value"] for _, _, mp in group)
        units = sum(fp.get("units", 0) or 0 for _, fp, _ in group)

        mkt_rev = 0
        for _, fp, mp in group:
            s = mp["suppression_ratio"]
            p13_ptax = fp["revenue"]["property_tax"]
            if s > 0 and s < 1.0:
                mkt_ptax = p13_ptax / s
            elif mp["market_value"] > 0 and mp["assessed_total"] > 0:
                mkt_ptax = p13_ptax * (mp["market_value"] / mp["assessed_total"])
            else:
                mkt_ptax = p13_ptax
            mkt_rev += fp["revenue"]["gf_total"] + (mkt_ptax - p13_ptax)

        total_p13_rev += gf_rev
        total_mkt_rev += mkt_rev
        total_cost += gf_cost

        p13_net = gf_rev - gf_cost
        p13_npa = p13_net / acres
        mkt_net = mkt_rev - gf_cost
        mkt_npa = mkt_net / acres

        if mkt_npa >= 0:
            asset_count += 1
        else:
            loss_count += 1

        if len(group) > 1:
            n_merged += len(group) - 1

        cat_counts = defaultdict(int)
        for _, fp, _ in group:
            cat_counts[fp.get("land_use_broad", "Other")] += 1
        primary_cat = max(cat_counts, key=cat_counts.get)

        if primary_cat in ("Vacant", "Government", "Other"):
            continue

        height = mkt_npa * HEIGHT_SCALE
        height = max(min(height, MAX_HEIGHT), -MAX_HEIGHT)
        if abs(height) < 3:
            height = 3 if mkt_npa >= 0 else -3
        color = net_to_color(mkt_npa)
        suppression = assessed / market if market > 0 else 1.0

        label = f"{group[0][0]}+{len(group)-1}" if len(group) > 1 else group[0][0]

        coords = geometry.get("coordinates", [])
        geom_type = geometry.get("type", "")
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
                "h": round(height, 1),
                "c": color,
                "npa": round(mkt_npa),
                "p13npa": round(p13_npa),
                "apn": label,
                "cat": primary_cat,
                "u": units or len(group),
                "np": len(group),
                "gr": round(mkt_rev),
                "gc": round(gf_cost),
                "net": round(mkt_net),
                "p13net": round(p13_net),
                "av": assessed,
                "mv": market,
                "s": round(suppression, 2),
                "ac": round(acres, 3),
                "ptd": round(mkt_rev - gf_rev),
            })

    print(f"  {len(geo['features']):,} raw → {len(poly_groups):,} features ({n_merged:,} merged)")
    print(f"  Assets: {asset_count:,}  Losses: {loss_count:,}")
    print(f"  Prop 13 rev: ${total_p13_rev:>13,.0f}")
    print(f"  Market rev:  ${total_mkt_rev:>13,.0f}")
    print(f"  Additional:  ${total_mkt_rev - total_p13_rev:>13,.0f}")

    OUTPUT.parent.mkdir(exist_ok=True)

    all_lons = [c[0] for f in features[:1000] for c in f["p"][:4]]
    all_lats = [c[1] for f in features[:1000] for c in f["p"][:4]]
    center_lon = sum(all_lons) / len(all_lons)
    center_lat = sum(all_lats) / len(all_lats)

    data_json = json.dumps(features, separators=(',', ':'))

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Oceanside Without Prop 13 — Net Fiscal Impact</title>
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
  #title {{
    position: absolute; top: 20px; left: 20px; z-index: 1;
    background: rgba(0,0,0,0.88); color: #fff; padding: 18px 22px;
    border-radius: 8px; border: 1px solid rgba(255,255,255,0.08);
  }}
  #title h2 {{ margin: 0 0 6px 0; font-size: 20px; letter-spacing: -0.3px; }}
  #title p {{ margin: 0; font-size: 12px; opacity: 0.7; }}
  #stats {{
    position: absolute; top: 20px; right: 20px; z-index: 1;
    background: rgba(0,0,0,0.88); color: #fff; padding: 16px 20px;
    border-radius: 8px; font-size: 13px; line-height: 1.8;
    border: 1px solid rgba(255,255,255,0.08);
  }}
  #stats strong {{ font-size: 14px; }}
  .stat-val {{ font-weight: 600; font-size: 15px; }}
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
  <h2>Oceanside Without Prop 13</h2>
  <p>Every parcel assessed at estimated market value</p>
  <p><span style="color:#e64619">Hot/tall</span> = productive &nbsp;|&nbsp; <span style="color:#1e3cb4">Cold/low</span> = drain &nbsp;|&nbsp; Height = net $/acre</p>
  <p style="margin-top:4px; opacity:0.4">Drag to rotate &nbsp;|&nbsp; Scroll to zoom</p>
</div>
<div id="legend">
  <h3>Net $/Acre</h3>
  <div class="lr"><div class="sw" style="background:#aa1482"></div> +$200K+</div>
  <div class="lr"><div class="sw" style="background:#c8143c"></div> +$100K</div>
  <div class="lr"><div class="sw" style="background:#e64619"></div> +$50K</div>
  <div class="lr"><div class="sw" style="background:#f0a014"></div> +$30K</div>
  <div class="lr"><div class="sw" style="background:#c8d21e"></div> +$15K</div>
  <div class="lr"><div class="sw" style="background:#64c83c"></div> +$5K</div>
  <div class="ld"></div>
  <div class="lr" style="font-weight:600; color:#3cbeaa">BREAK EVEN</div>
  <div class="ld"></div>
  <div class="lr"><div class="sw" style="background:#288cd2"></div> −$5K</div>
  <div class="lr"><div class="sw" style="background:#1e3cb4"></div> −$15K</div>
  <div class="lr"><div class="sw" style="background:#0f0f50"></div> −$30K+</div>
  <div class="ld"></div>
  <div style="font-size:11px; opacity:0.6;">
    <span style="color:#e64619">Hot</span> = productive &nbsp;
    <span style="color:#1e3cb4">Cold</span> = drain<br>
    Height = magnitude of net impact
  </div>
</div>
<div id="stats">
  <strong>Prop 13 Removed</strong><br>
  <span class="muted">Additional GF revenue:</span><br>
  <span class="stat-val pos">+${round(total_mkt_rev - total_p13_rev):,}/yr</span><br>
  <span class="muted">Total GF revenue:</span><br>
  <span class="stat-val">${round(total_mkt_rev):,}/yr</span><br>
  <span class="muted">Total GF cost:</span><br>
  <span class="stat-val">${round(total_cost):,}/yr</span><br>
  <span class="muted">Assets / Losses:</span><br>
  <span class="pos">{asset_count:,}</span> / <span class="neg">{loss_count:,}</span>
  <div style="margin-top:10px; border-top:1px solid rgba(255,255,255,0.15); padding-top:8px;">
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

function fmt(n) {{
  if (n >= 0) return '+$' + n.toLocaleString();
  return '−$' + Math.abs(n).toLocaleString();
}}

const tooltip = document.getElementById('tooltip');

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
  layers: [
    new deck.PolygonLayer({{
      id: 'parcels',
      data: DATA,
      _full3d: true,
      getPolygon: d => {{
        const z = d.h >= 0 ? 800 : 800 + d.h;
        return d.p.map(c => [c[0], c[1], z]);
      }},
      getElevation: d => Math.abs(d.h) || 5,
      getFillColor: d => d.c,
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
    }}),
  ],
  onHover: ({{object, x, y}}) => {{
    if (object) {{
      const cls = object.npa >= 0 ? 'pos' : 'neg';
      const p13cls = object.p13npa >= 0 ? 'pos' : 'neg';
      const dcls = object.ptd >= 0 ? 'pos' : 'neg';
      const multi = object.np > 1 ? `<br><span class="muted">${{object.np}} parcels consolidated (${{object.u}} units)</span>` : '';
      tooltip.style.display = 'block';
      tooltip.style.left = (x + 14) + 'px';
      tooltip.style.top = (y + 14) + 'px';
      tooltip.innerHTML = `
        <strong>${{object.apn}}</strong> — ${{object.cat}}${{multi}}<br>
        <span class="${{cls}}" style="font-size:16px">${{fmt(object.npa)}}/acre</span>
        <span class="muted">&nbsp;without Prop 13</span><br>
        <span class="${{p13cls}}">${{fmt(object.p13npa)}}/acre</span>
        <span class="muted">&nbsp;with Prop 13</span><br>
        <hr style="border-color:rgba(255,255,255,0.12);margin:6px 0">
        Net: ${{fmt(object.net)}} on ${{object.ac}} acres<br>
        GF Revenue: $${{object.gr.toLocaleString()}} &nbsp;
        GF Cost: $${{object.gc.toLocaleString()}}<br>
        <hr style="border-color:rgba(255,255,255,0.12);margin:6px 0">
        <span class="${{dcls}}">Removing Prop 13: ${{fmt(object.ptd)}}/yr</span><br>
        Assessed: $${{object.av.toLocaleString()}} →
        Market: $${{object.mv.toLocaleString()}}<br>
        <span class="muted">Suppression: ${{object.s}}x</span>
      `;
    }} else {{
      tooltip.style.display = 'none';
    }}
  }},
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
</script>
</body>
</html>"""

    OUTPUT.write_text(html)
    size_mb = OUTPUT.stat().st_size / 1_048_576
    print(f"\n→ {OUTPUT} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
