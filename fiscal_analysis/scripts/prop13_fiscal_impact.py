#!/usr/bin/env python3
"""Recompute fiscal productivity ratios under market values.

Shows how Prop 13 distorts the Strong Towns value-per-acre analysis by
suppressing property tax revenue for older properties, making older MFR
(which rarely sells) look like a fiscal drain.

Loads:
  - fiscal_productivity_v2.json (per-parcel fiscal model)
  - market_values.json (estimated market values + suppression ratios)

Outputs:
  - prop13_fiscal_impact.json: summary comparing Prop 13 vs market value ratios
"""

import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent.parent
V2_FILE = HERE / "fiscal_productivity_v2.json"
MARKET_FILE = HERE / "market_values.json"
OUTPUT = HERE / "prop13_fiscal_impact.json"


def main():
    print("Loading v2 fiscal model...")
    with open(V2_FILE) as f:
        v2 = json.load(f)
    v2_parcels = {p["apn"]: p for p in v2["parcels"]}
    print(f"  {len(v2_parcels):,} parcels in fiscal model")

    print("Loading market values...")
    with open(MARKET_FILE) as f:
        mv = json.load(f)
    mv_parcels = {p["apn"]: p for p in mv["parcels"]}
    print(f"  {len(mv_parcels):,} parcels with market values")

    city_rate = mv["summary"]["methodology"]["city_tax_rate"]
    print(f"  City property tax rate: {city_rate:.4%}")

    # Match parcels and compute dual ratios
    cats = defaultdict(lambda: {
        "count": 0, "units": 0, "acres": 0,
        "prop13_revenue": 0, "market_revenue": 0,
        "gf_cost": 0,
        "prop13_property_tax": 0, "market_property_tax": 0,
        "assessed_total": 0, "market_total": 0,
        "by_era": defaultdict(lambda: {
            "count": 0, "prop13_revenue": 0, "market_revenue": 0,
            "gf_cost": 0, "assessed": 0, "market": 0,
        }),
    })

    matched = 0
    for apn, fp in v2_parcels.items():
        mp = mv_parcels.get(apn)
        if not mp:
            continue
        matched += 1

        cat = fp.get("land_use_broad", "Other")
        c = cats[cat]
        c["count"] += 1
        c["units"] += fp.get("units", 0) or 0
        c["acres"] += fp.get("acres", 0) or 0

        assessed = mp["assessed_total"]
        market = mp["market_value"]
        suppression = mp["suppression_ratio"]

        prop13_ptax = fp["revenue"]["property_tax"]
        if market > 0 and assessed > 0 and suppression > 0:
            market_ptax = prop13_ptax / suppression
        elif market > 0:
            market_ptax = market * city_rate
        else:
            market_ptax = prop13_ptax

        prop13_rev = fp["revenue"]["gf_total"]
        ptax_delta = market_ptax - prop13_ptax
        market_rev = prop13_rev + ptax_delta

        gf_cost = fp["gf_costs"]["total"]

        c["prop13_revenue"] += prop13_rev
        c["market_revenue"] += market_rev
        c["gf_cost"] += gf_cost
        c["prop13_property_tax"] += prop13_ptax
        c["market_property_tax"] += market_ptax
        c["assessed_total"] += assessed
        c["market_total"] += market

        yr = mp.get("sale_year")
        if yr:
            if yr < 1990:
                era = "pre-1990"
            elif yr < 2000:
                era = "1990s"
            elif yr < 2010:
                era = "2000s"
            elif yr < 2020:
                era = "2010s"
            else:
                era = "2020s"
            e = c["by_era"][era]
            e["count"] += 1
            e["prop13_revenue"] += prop13_rev
            e["market_revenue"] += market_rev
            e["gf_cost"] += gf_cost
            e["assessed"] += assessed
            e["market"] += market

    print(f"  Matched: {matched:,} parcels")

    # Build summary
    order = ["SFR", "Condo/TH", "Duplex", "3-4 Plex", "MFR 5-20",
             "MFR 21-100", "MFR 100+", "Commercial", "Industrial",
             "Mobile Home", "Vacant", "Other"]

    results = []
    for cat in order:
        c = cats.get(cat)
        if not c or c["count"] == 0:
            continue

        prop13_ratio = c["prop13_revenue"] / c["gf_cost"] if c["gf_cost"] > 0 else 0
        market_ratio = c["market_revenue"] / c["gf_cost"] if c["gf_cost"] > 0 else 0
        ratio_delta = market_ratio - prop13_ratio

        prop13_rpa = c["prop13_revenue"] / c["acres"] if c["acres"] > 0 else 0
        market_rpa = c["market_revenue"] / c["acres"] if c["acres"] > 0 else 0

        prop13_net = c["prop13_revenue"] - c["gf_cost"]
        market_net = c["market_revenue"] - c["gf_cost"]

        era_data = {}
        for era in ["pre-1990", "1990s", "2000s", "2010s", "2020s"]:
            e = c["by_era"].get(era)
            if not e or e["count"] == 0:
                continue
            e_p13_ratio = e["prop13_revenue"] / e["gf_cost"] if e["gf_cost"] > 0 else 0
            e_mkt_ratio = e["market_revenue"] / e["gf_cost"] if e["gf_cost"] > 0 else 0
            era_data[era] = {
                "count": e["count"],
                "prop13_ratio": round(e_p13_ratio, 3),
                "market_ratio": round(e_mkt_ratio, 3),
                "ratio_lift": round(e_mkt_ratio - e_p13_ratio, 3),
                "prop13_net": round(e["prop13_revenue"] - e["gf_cost"]),
                "market_net": round(e["market_revenue"] - e["gf_cost"]),
            }

        results.append({
            "category": cat,
            "count": c["count"],
            "units": c["units"],
            "acres": round(c["acres"]),
            "prop13": {
                "revenue": round(c["prop13_revenue"]),
                "property_tax": round(c["prop13_property_tax"]),
                "cost": round(c["gf_cost"]),
                "net": round(prop13_net),
                "ratio": round(prop13_ratio, 3),
                "revenue_per_acre": round(prop13_rpa),
            },
            "market_value": {
                "revenue": round(c["market_revenue"]),
                "property_tax": round(c["market_property_tax"]),
                "cost": round(c["gf_cost"]),
                "net": round(market_net),
                "ratio": round(market_ratio, 3),
                "revenue_per_acre": round(market_rpa),
            },
            "prop13_effect": {
                "ratio_delta": round(ratio_delta, 3),
                "revenue_suppressed": round(c["market_revenue"] - c["prop13_revenue"]),
                "assessment_suppression": round(c["assessed_total"] / c["market_total"], 3) if c["market_total"] > 0 else 1.0,
            },
            "by_era": era_data,
        })

    # Totals
    total_p13_rev = sum(c["prop13_revenue"] for c in cats.values())
    total_mkt_rev = sum(c["market_revenue"] for c in cats.values())
    total_cost = sum(c["gf_cost"] for c in cats.values())

    output = {
        "methodology": {
            "description": "Compares fiscal ratios under Prop 13 (actual assessed values) "
                          "vs estimated market values (what properties would be assessed at "
                          "if reassessed to current market).",
            "market_estimation": "Recent sales (2020-2025) as comps by land use code. "
                                "$/sqft primary, $/unit fallback, appreciation for no-comp.",
            "revenue_neutral": False,
            "note": "Market value scenario shows additional revenue that WOULD flow "
                   "to city if Prop 13 didn't cap assessments. Total revenue increases "
                   "because property tax is the delta.",
        },
        "totals": {
            "prop13_revenue": round(total_p13_rev),
            "market_revenue": round(total_mkt_rev),
            "revenue_suppressed": round(total_mkt_rev - total_p13_rev),
            "total_gf_cost": round(total_cost),
            "prop13_ratio": round(total_p13_rev / total_cost, 3) if total_cost > 0 else 0,
            "market_ratio": round(total_mkt_rev / total_cost, 3) if total_cost > 0 else 0,
        },
        "by_category": results,
    }

    OUTPUT.write_text(json.dumps(output, indent=2))
    print(f"\n→ {OUTPUT}")

    # Print comparison table
    print(f"\n{'='*90}")
    print("PROP 13 vs MARKET VALUE — FISCAL RATIO COMPARISON")
    print(f"{'='*90}")
    print(f"\n  Total GF Revenue (Prop 13):  ${total_p13_rev:>13,.0f}")
    print(f"  Total GF Revenue (Market):   ${total_mkt_rev:>13,.0f}")
    print(f"  Revenue suppressed:          ${total_mkt_rev - total_p13_rev:>13,.0f}")
    print(f"  Total GF Cost:               ${total_cost:>13,.0f}")

    print(f"\n  {'Category':>12s} {'Prop13':>8s} {'Market':>8s} {'Δ Ratio':>8s} "
          f"{'P13 Net':>12s} {'Mkt Net':>12s} {'Verdict':>12s}")
    print(f"  {'-'*12:>12s} {'-'*8:>8s} {'-'*8:>8s} {'-'*8:>8s} "
          f"{'-'*12:>12s} {'-'*12:>12s} {'-'*12:>12s}")

    for r in results:
        p = r["prop13"]
        m = r["market_value"]
        d = r["prop13_effect"]

        if p["ratio"] < 1.0 and m["ratio"] >= 1.0:
            verdict = "DRAIN→PAYS"
        elif p["ratio"] < 1.0 and m["ratio"] < 1.0:
            verdict = "STILL DRAIN"
        elif d["ratio_delta"] > 0.05:
            verdict = f"+{d['ratio_delta']:.0%} boost"
        else:
            verdict = "~same"

        print(f"  {r['category']:>12s} {p['ratio']:>7.2f}x {m['ratio']:>7.2f}x "
              f"{d['ratio_delta']:>+7.3f} ${p['net']:>11,.0f} ${m['net']:>11,.0f} "
              f"{verdict:>12s}")

    # Era breakdown for MFR categories
    mfr_cats = ["MFR 5-20", "MFR 21-100", "MFR 100+"]
    print(f"\n  MFR FISCAL RATIOS BY SALE ERA:")
    for r in results:
        if r["category"] not in mfr_cats:
            continue
        print(f"\n  {r['category']}:")
        for era in ["pre-1990", "1990s", "2000s", "2010s", "2020s"]:
            e = r["by_era"].get(era)
            if not e:
                continue
            lift = "→ PAYS" if e["prop13_ratio"] < 1.0 and e["market_ratio"] >= 1.0 else ""
            print(f"    {era:>10s}: {e['count']:>4} parcels, "
                  f"Prop13={e['prop13_ratio']:.2f}x → Market={e['market_ratio']:.2f}x "
                  f"(+{e['ratio_lift']:.3f}) {lift}")


if __name__ == "__main__":
    main()
