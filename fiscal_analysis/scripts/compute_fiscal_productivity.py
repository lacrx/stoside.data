#!/usr/bin/env python3
"""Compute net fiscal productivity per parcel.

Combines:
  - Phase 1: Property tax revenue per parcel
  - Phase 2: Road maintenance cost per parcel
  - Phase 3: Water/sewer infrastructure cost per parcel

Net fiscal impact = revenue - (road_cost + water_cost + sewer_cost)

Outputs:
  - fiscal_productivity.json: per-parcel net fiscal impact
  - fiscal_productivity_summary.json: aggregated analysis
"""

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent.parent
REVENUE_FILE = HERE / "revenue_per_acre.json"
ROADS_FILE = HERE / "road_costs_by_parcel.json"
WATER_SEWER_FILE = HERE / "water_sewer_costs_by_parcel.json"
OUTPUT = HERE / "fiscal_productivity.json"
SUMMARY_OUTPUT = HERE / "fiscal_productivity_summary.json"


def load_by_apn(path: Path, label: str) -> dict[str, dict]:
    with open(path) as f:
        data = json.load(f)
    parcels = data.get("parcels", [])
    print(f"  {label}: {len(parcels):,} parcels")
    return {p["apn"]: p for p in parcels}


def main():
    print("Loading datasets...")
    revenue = load_by_apn(REVENUE_FILE, "Revenue")
    roads = load_by_apn(ROADS_FILE, "Roads")
    water_sewer = load_by_apn(WATER_SEWER_FILE, "Water/Sewer")

    all_apns = set(revenue.keys())
    matched_roads = len(all_apns & set(roads.keys()))
    matched_ws = len(all_apns & set(water_sewer.keys()))
    print(f"\n  APNs in revenue: {len(all_apns):,}")
    print(f"  Matched to roads: {matched_roads:,}")
    print(f"  Matched to water/sewer: {matched_ws:,}")

    print("\nComputing net fiscal impact...")
    per_parcel = []

    for apn in all_apns:
        rev = revenue[apn]
        rd = roads.get(apn, {})
        ws = water_sewer.get(apn, {})

        prop_tax = rev.get("property_tax_city", 0)
        acres = rev.get("acres", 0)
        taxable = rev.get("taxable", False)

        road_cost = rd.get("road_cost_total", 0)
        water_cost = ws.get("water_total", 0)
        sewer_cost = ws.get("sewer_total", 0)
        utility_cost = water_cost + sewer_cost

        total_cost = road_cost + utility_cost
        net = prop_tax - total_cost
        fiscal_ratio = prop_tax / total_cost if total_cost > 0 else 0

        net_per_acre = net / acres if acres > 0.001 else 0
        cost_per_acre = total_cost / acres if acres > 0.001 else 0
        rev_per_acre = prop_tax / acres if acres > 0.001 else 0

        per_parcel.append({
            "apn": apn,
            "address": rev.get("address", ""),
            "land_use": rev.get("land_use", ""),
            "land_use_broad": rev.get("land_use_broad", "Unknown"),
            "land_use_code": rev.get("land_use_code", 0),
            "acres": round(acres, 4),
            "taxable": taxable,
            "units": rev.get("units", 0),
            "living_sqft": rev.get("living_sqft", 0),
            "assessed_total": rev.get("assessed_total", 0),
            "revenue": {
                "property_tax": round(prop_tax, 2),
                "per_acre": round(rev_per_acre, 2),
            },
            "costs": {
                "road": round(road_cost, 2),
                "water": round(water_cost, 2),
                "sewer": round(sewer_cost, 2),
                "total": round(total_cost, 2),
                "per_acre": round(cost_per_acre, 2),
            },
            "net": round(net, 2),
            "net_per_acre": round(net_per_acre, 2),
            "fiscal_ratio": round(fiscal_ratio, 3),
        })

    per_parcel.sort(key=lambda p: p["net_per_acre"])

    taxable = [p for p in per_parcel if p["taxable"] and p["assessed_total"] > 0 and p["acres"] > 0.001]
    nets = [p["net"] for p in taxable]
    nets_per_acre = [p["net_per_acre"] for p in taxable]
    ratios = [p["fiscal_ratio"] for p in taxable if p["fiscal_ratio"] > 0]

    contributors = [p for p in taxable if p["net"] > 0]
    drains = [p for p in taxable if p["net"] <= 0]

    total_rev = sum(p["revenue"]["property_tax"] for p in taxable)
    total_cost = sum(p["costs"]["total"] for p in taxable)
    total_net = sum(p["net"] for p in taxable)

    summary = {
        "methodology": {
            "revenue": "property_tax_only (assessed_value × 1% × 16% city share)",
            "costs_included": ["road_maintenance (PCI lifecycle)", "water_infrastructure", "sewer_infrastructure"],
            "costs_not_included": ["stormwater", "fire", "police", "parks", "general_government", "sales_tax_revenue", "TOT", "franchise_fees"],
            "note": "Partial model — includes ~40-50% of city costs and ~50-60% of city revenue. Net values will shift as more cost/revenue categories are added.",
        },
        "totals": {
            "total_parcels": len(per_parcel),
            "taxable_parcels": len(taxable),
            "total_revenue": round(total_rev),
            "total_cost": round(total_cost),
            "total_net": round(total_net),
            "cost_breakdown": {
                "roads": round(sum(p["costs"]["road"] for p in taxable)),
                "water": round(sum(p["costs"]["water"] for p in taxable)),
                "sewer": round(sum(p["costs"]["sewer"] for p in taxable)),
            },
            "net_contributors": len(contributors),
            "net_drains": len(drains),
            "pct_contributors": round(len(contributors) / len(taxable) * 100, 1),
        },
        "distribution": {
            "net_per_acre": {
                f"p{p}": round(float(np.percentile(nets_per_acre, p)))
                for p in [5, 10, 25, 50, 75, 90, 95]
            },
            "fiscal_ratio": {
                f"p{p}": round(float(np.percentile(ratios, p)), 2)
                for p in [5, 10, 25, 50, 75, 90, 95]
            },
        },
    }

    by_land_use = []
    lu_groups = defaultdict(list)
    for p in taxable:
        lu_groups[p["land_use_broad"]].append(p)

    for cat, group in lu_groups.items():
        g_nets = [p["net_per_acre"] for p in group]
        g_ratios = [p["fiscal_ratio"] for p in group if p["fiscal_ratio"] > 0]
        g_acres = sum(p["acres"] for p in group)
        g_rev = sum(p["revenue"]["property_tax"] for p in group)
        g_cost = sum(p["costs"]["total"] for p in group)
        g_contributors = sum(1 for p in group if p["net"] > 0)

        by_land_use.append({
            "category": cat,
            "count": len(group),
            "total_acres": round(g_acres, 1),
            "total_revenue": round(g_rev),
            "total_cost": round(g_cost),
            "total_net": round(g_rev - g_cost),
            "avg_net_per_acre": round(float(np.mean(g_nets))),
            "median_net_per_acre": round(float(np.median(g_nets))),
            "median_fiscal_ratio": round(float(np.median(g_ratios)), 2) if g_ratios else 0,
            "pct_contributors": round(g_contributors / len(group) * 100, 1),
            "revenue_per_acre": round(g_rev / g_acres) if g_acres > 0 else 0,
            "cost_per_acre": round(g_cost / g_acres) if g_acres > 0 else 0,
        })

    by_land_use.sort(key=lambda x: -x["median_net_per_acre"])
    summary["by_land_use"] = by_land_use

    # Cross-subsidy analysis
    cross_subsidy = []
    for cat_data in by_land_use:
        cat = cat_data["category"]
        net = cat_data["total_net"]
        cross_subsidy.append({
            "category": cat,
            "net_fiscal_impact": net,
            "role": "net contributor" if net > 0 else "net recipient",
            "magnitude": abs(net),
        })
    cross_subsidy.sort(key=lambda x: -x["net_fiscal_impact"])
    summary["cross_subsidy"] = cross_subsidy

    # Top/bottom parcels
    top_10 = taxable[-10:][::-1]
    bottom_10 = taxable[:10]
    summary["top_parcels"] = [{
        "apn": p["apn"], "address": p["address"],
        "land_use": p["land_use"], "acres": p["acres"],
        "net_per_acre": p["net_per_acre"], "fiscal_ratio": p["fiscal_ratio"],
    } for p in top_10]
    summary["bottom_parcels"] = [{
        "apn": p["apn"], "address": p["address"],
        "land_use": p["land_use"], "acres": p["acres"],
        "net_per_acre": p["net_per_acre"], "fiscal_ratio": p["fiscal_ratio"],
    } for p in bottom_10]

    output = {"summary": summary, "parcels": per_parcel}
    OUTPUT.write_text(json.dumps(output, indent=2))
    size_mb = OUTPUT.stat().st_size / 1_048_576
    print(f"\n→ {OUTPUT} ({size_mb:.1f} MB)")

    SUMMARY_OUTPUT.write_text(json.dumps(summary, indent=2))
    print(f"→ {SUMMARY_OUTPUT}")

    # Print results
    t = summary["totals"]
    print(f"\n{'=' * 70}")
    print(f"NET FISCAL PRODUCTIVITY — OCEANSIDE, CA")
    print(f"{'=' * 70}")
    print(f"Taxable parcels: {t['taxable_parcels']:,}")
    print(f"Total revenue (property tax):  ${t['total_revenue']:>12,}")
    print(f"Total costs (roads+water+sewer): ${t['total_cost']:>12,}")
    cb = t["cost_breakdown"]
    print(f"  Roads:  ${cb['roads']:>12,}")
    print(f"  Water:  ${cb['water']:>12,}")
    print(f"  Sewer:  ${cb['sewer']:>12,}")
    print(f"Net fiscal impact:             ${t['total_net']:>12,}")
    print(f"\nNet contributors: {t['net_contributors']:,} ({t['pct_contributors']}%)")
    print(f"Net drains:       {t['net_drains']:,} ({100 - t['pct_contributors']:.1f}%)")

    d = summary["distribution"]
    print(f"\nNet $/acre distribution:")
    for k, v in d["net_per_acre"].items():
        print(f"  {k}: ${v:,}")

    print(f"\nFiscal ratio distribution (revenue / cost):")
    for k, v in d["fiscal_ratio"].items():
        print(f"  {k}: {v:.2f}x")

    print(f"\nBy land use:")
    print(f"  {'Category':20s} {'Parcels':>8s} {'Acres':>9s} {'Rev/ac':>9s} {'Cost/ac':>9s} {'Net/ac':>10s} {'Ratio':>7s} {'%Contrib':>8s}")
    print(f"  {'-'*20} {'-'*8} {'-'*9} {'-'*9} {'-'*9} {'-'*10} {'-'*7} {'-'*8}")
    for cat in by_land_use:
        print(f"  {cat['category']:20s} {cat['count']:>8,} {cat['total_acres']:>9,.1f} "
              f"${cat['revenue_per_acre']:>8,} ${cat['cost_per_acre']:>8,} "
              f"${cat['median_net_per_acre']:>9,} {cat['median_fiscal_ratio']:>6.2f}x "
              f"{cat['pct_contributors']:>7.1f}%")

    print(f"\nCross-subsidy flows:")
    for cs in cross_subsidy:
        arrow = "→ contributes" if cs["net_fiscal_impact"] > 0 else "← receives"
        print(f"  {cs['category']:20s} {arrow} ${abs(cs['net_fiscal_impact']):>12,}")


if __name__ == "__main__":
    main()
