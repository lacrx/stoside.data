#!/usr/bin/env python3
"""Generate pre-aggregated JSON files for the static API layer.

Reads normalized parquet files and produces summary JSONs that can be
served directly from S3/CloudFront with zero compute latency.

Output goes to fiscal_analysis/exports/api/ (gitignored — regenerable).
"""

import json
from pathlib import Path

import duckdb

EXPORTS = Path(__file__).parent.parent / "exports"
API = EXPORTS / "api"


def q(db: duckdb.DuckDBPyConnection, sql: str):
    return db.sql(sql).fetchall()


def qd(db: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    rel = db.sql(sql)
    cols = [d[0] for d in rel.description]
    return [dict(zip(cols, row)) for row in rel.fetchall()]


def write_json(name: str, data: dict | list):
    out = API / name
    out.write_text(json.dumps(data, indent=2, default=str))
    print(f"  {name}: {out.stat().st_size / 1e3:.1f} KB")


def generate_summary(db):
    parcels = q(db, f"""
        SELECT count(*) as n,
               sum(CASE WHEN taxable THEN 1 ELSE 0 END) as taxable,
               sum(assessed_total) as assessed,
               sum(market_value) as market,
               sum(acres) as acres,
               sum(CASE WHEN near_transit THEN 1 ELSE 0 END) as transit
        FROM '{EXPORTS}/parcels.parquet'
    """)[0]

    fiscal = q(db, f"""
        SELECT sum(gf_revenue) as rev,
               sum(cost_gf_total) as cost,
               sum(gf_net) as net,
               sum(property_tax) as ptax,
               sum(sales_tax) as stax,
               avg(gf_net_per_acre) as avg_npa,
               median(gf_net_per_acre) as med_npa,
               sum(CASE WHEN gf_net >= 0 THEN 1 ELSE 0 END) as contributors,
               sum(CASE WHEN gf_net < 0 THEN 1 ELSE 0 END) as drains
        FROM '{EXPORTS}/fiscal.parquet'
    """)[0]

    water = q(db, f"""
        SELECT count(*) as segments, sum(length_ft)/5280 as miles
        FROM '{EXPORTS}/infrastructure_water.parquet'
    """)[0]

    sewer = q(db, f"""
        SELECT count(*) as segments, sum(length_ft)/5280 as miles
        FROM '{EXPORTS}/infrastructure_sewer.parquet'
    """)[0]

    write_json("summary.json", {
        "city": "Oceanside, CA",
        "parcels": {
            "total": parcels[0],
            "taxable": parcels[1],
            "assessed_total": round(parcels[2]),
            "market_total": round(parcels[3]),
            "total_acres": round(parcels[4], 1),
            "near_transit": parcels[5],
        },
        "fiscal": {
            "gf_revenue": round(fiscal[0]),
            "gf_cost": round(fiscal[1]),
            "gf_net": round(fiscal[2]),
            "property_tax": round(fiscal[3]),
            "sales_tax": round(fiscal[4]),
            "avg_net_per_acre": round(fiscal[5]),
            "median_net_per_acre": round(fiscal[6]),
            "net_contributors": fiscal[7],
            "net_drains": fiscal[8],
        },
        "infrastructure": {
            "water_segments": water[0],
            "water_miles": round(water[1]),
            "sewer_segments": sewer[0],
            "sewer_miles": round(sewer[1]),
        },
    })


def generate_by_land_use(db):
    rows = qd(db, f"""
        SELECT p.land_use_broad as land_use,
               count(*) as parcels,
               round(sum(p.acres), 1) as acres,
               round(sum(f.gf_revenue)) as gf_revenue,
               round(sum(f.cost_gf_total)) as gf_cost,
               round(sum(f.gf_net)) as gf_net,
               round(avg(f.gf_net_per_acre)) as avg_net_per_acre,
               round(median(f.gf_net_per_acre)) as median_net_per_acre,
               sum(CASE WHEN f.gf_net >= 0 THEN 1 ELSE 0 END) as contributors,
               sum(CASE WHEN f.gf_net < 0 THEN 1 ELSE 0 END) as drains,
               round(avg(f.gf_ratio), 3) as avg_fiscal_ratio
        FROM '{EXPORTS}/parcels.parquet' p
        JOIN '{EXPORTS}/fiscal.parquet' f ON p.apn = f.apn
        WHERE p.land_use_broad != ''
        GROUP BY p.land_use_broad
        ORDER BY gf_net DESC
    """)
    write_json("by_land_use.json", rows)


def generate_transit_impact(db):
    def stats_for(where: str) -> dict:
        r = q(db, f"""
            SELECT count(*) as n,
                   round(sum(p.acres), 1) as acres,
                   round(sum(f.gf_revenue)) as rev,
                   round(sum(f.cost_gf_total)) as cost,
                   round(sum(f.gf_net)) as net,
                   round(avg(f.gf_net_per_acre)) as avg_npa,
                   round(median(f.gf_net_per_acre)) as med_npa
            FROM '{EXPORTS}/parcels.parquet' p
            JOIN '{EXPORTS}/fiscal.parquet' f ON p.apn = f.apn
            WHERE {where}
        """)[0]
        return {
            "parcels": r[0], "acres": r[1],
            "gf_revenue": r[2], "gf_cost": r[3], "gf_net": r[4],
            "avg_net_per_acre": r[5], "median_net_per_acre": r[6],
        }

    transit = stats_for("p.near_transit = true")
    non_transit = stats_for("p.near_transit = false")

    by_use = qd(db, f"""
        SELECT p.land_use_broad as land_use,
               count(*) as parcels,
               round(sum(f.gf_net)) as gf_net,
               round(avg(f.gf_net_per_acre)) as avg_net_per_acre
        FROM '{EXPORTS}/parcels.parquet' p
        JOIN '{EXPORTS}/fiscal.parquet' f ON p.apn = f.apn
        WHERE p.near_transit = true AND p.land_use_broad != ''
        GROUP BY p.land_use_broad
        ORDER BY gf_net DESC
    """)

    write_json("transit_impact.json", {
        "transit_area": transit,
        "non_transit": non_transit,
        "transit_by_land_use": by_use,
    })


def generate_infrastructure_capacity(db):
    def pipe_stats(table: str) -> list[dict]:
        return qd(db, f"""
            SELECT
                CASE
                    WHEN diameter >= 36 THEN '36+'
                    WHEN diameter >= 24 THEN '24-36'
                    WHEN diameter >= 12 THEN '12-24'
                    WHEN diameter >= 8 THEN '8-12'
                    ELSE 'Under 8'
                END as size_class,
                count(*) as segments,
                round(sum(length_ft)/5280, 1) as miles,
                round(avg(capacity_edu)) as avg_capacity_edu
            FROM '{EXPORTS}/{table}'
            WHERE diameter > 0 AND diameter < 999
            GROUP BY size_class
            ORDER BY min(diameter)
        """)

    write_json("infrastructure_capacity.json", {
        "water": pipe_stats("infrastructure_water.parquet"),
        "sewer": pipe_stats("infrastructure_sewer.parquet"),
    })


def generate_budget_trend(db):
    rows = qd(db, f"""
        SELECT fiscal_year,
               sum(CASE WHEN flow = 'revenue' AND basis = 'actual' THEN amount_usd ELSE 0 END) as actual_revenue,
               sum(CASE WHEN flow = 'expenditure' AND basis = 'actual' THEN amount_usd ELSE 0 END) as actual_expenditure,
               sum(CASE WHEN flow = 'revenue' AND basis = 'adopted' THEN amount_usd ELSE 0 END) as adopted_revenue,
               sum(CASE WHEN flow = 'expenditure' AND basis = 'adopted' THEN amount_usd ELSE 0 END) as adopted_expenditure
        FROM '{EXPORTS}/budget.parquet'
        WHERE fiscal_year > 0
        GROUP BY fiscal_year
        ORDER BY fiscal_year
    """)
    write_json("budget_trend.json", rows)


def generate_decoder_metrics(db):
    rows = qd(db, f"""
        SELECT fiscal_year, metric_name, value
        FROM '{EXPORTS}/budget_health.parquet'
        ORDER BY fiscal_year, metric_name
    """)
    by_year = {}
    for r in rows:
        fy = r["fiscal_year"]
        if fy not in by_year:
            by_year[fy] = {"fiscal_year": fy}
        by_year[fy][r["metric_name"]] = r["value"]

    write_json("decoder_metrics.json", list(by_year.values()))


def main():
    API.mkdir(parents=True, exist_ok=True)
    db = duckdb.connect()

    print("=== Generating API JSONs ===")
    generate_summary(db)
    generate_by_land_use(db)
    generate_transit_impact(db)
    generate_infrastructure_capacity(db)
    generate_budget_trend(db)
    generate_decoder_metrics(db)

    total = sum(f.stat().st_size for f in API.glob("*.json"))
    print(f"\nTotal: {len(list(API.glob('*.json')))} API files, {total / 1e3:.1f} KB")


if __name__ == "__main__":
    main()
