"""Lambda handler for dynamic DuckDB queries on parquet data.

Endpoints:
  GET /query/parcel/{apn}         — single parcel detail
  GET /query/parcels?bbox=...     — parcels in bounding box
  GET /query/parcels?land_use=... — filter by land use
  GET /query/pipes?type=...       — infrastructure segments
  GET /query/votes?member=...     — votes by council member
  GET /query/budget?year=...      — budget by fiscal year
  GET /query/permits?year=...     — building permits (from yimby.watchdog)
  GET /query/permits/downtown?year=... — downtown density cap zone permits
  GET /query/permits/trend        — yearly permit aggregation
  GET /query/projects?name=...    — permit projects
  GET /query/housing?name=...     — unified housing projects (cross-referenced)
  GET /query/housing/trend        — housing project aggregation by status
  GET /query/filings?year=...     — HCD APR housing unit filings
  GET /query/filings/trend        — yearly filing aggregation
  GET /query/filings/downtown?year=... — downtown filings
  GET /query/str?status=Active    — short-term rental licenses
  GET /query/str/trend            — STR aggregation by area/type
"""

import json
import os
import tempfile

import boto3
import duckdb

BUCKET = os.environ["DATA_BUCKET"]
s3 = boto3.client("s3")
CACHE = {}


def get_parquet(name: str) -> str:
    if name in CACHE:
        return CACHE[name]
    local = f"/tmp/{name}"
    if not os.path.exists(local):
        s3.download_file(BUCKET, f"data/{name}", local)
    CACHE[name] = local
    return local


def respond(status: int, body: dict | list) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=60",
        },
        "body": json.dumps(body, default=str),
    }


def query_rows(db, sql: str) -> list[dict]:
    rel = db.sql(sql)
    cols = [d[0] for d in rel.description]
    return [dict(zip(cols, row)) for row in rel.fetchall()]


def lambda_handler(event, context):
    path = event.get("rawPath", "")
    qs = event.get("queryStringParameters") or {}

    db = duckdb.connect()

    try:
        # GET /query/parcel/{apn}
        if path.startswith("/query/parcel/"):
            apn = path.split("/query/parcel/")[1].strip("/")
            pf = get_parquet("parcels.parquet")
            ff = get_parquet("fiscal.parquet")
            rows = query_rows(db, f"""
                SELECT p.*, f.gf_revenue, f.property_tax, f.sales_tax,
                       f.cost_gf_total, f.gf_net, f.gf_net_per_acre, f.gf_ratio,
                       f.cost_police, f.cost_fire, f.cost_roads,
                       f.cost_water, f.cost_sewer
                FROM '{pf}' p
                JOIN '{ff}' f ON p.apn = f.apn
                WHERE p.apn = '{apn}'
            """)
            if not rows:
                return respond(404, {"error": "parcel not found"})
            return respond(200, rows[0])

        # GET /query/parcels?bbox=minlon,minlat,maxlon,maxlat
        if path.startswith("/query/parcels"):
            pf = get_parquet("parcels.parquet")
            ff = get_parquet("fiscal.parquet")

            where = "1=1"
            if "bbox" in qs:
                parts = qs["bbox"].split(",")
                if len(parts) == 4:
                    minlon, minlat, maxlon, maxlat = [float(x) for x in parts]
                    where = f"p.centroid_lon BETWEEN {minlon} AND {maxlon} AND p.centroid_lat BETWEEN {minlat} AND {maxlat}"

            if "land_use" in qs:
                lu = qs["land_use"].replace("'", "")
                where += f" AND p.land_use_broad = '{lu}'"

            if "transit" in qs:
                where += " AND p.near_transit = true"

            limit = min(int(qs.get("limit", "1000")), 5000)

            rows = query_rows(db, f"""
                SELECT p.apn, p.address, p.street, p.land_use_broad,
                       p.acres, p.centroid_lon, p.centroid_lat, p.near_transit,
                       f.gf_revenue, f.cost_gf_total, f.gf_net, f.gf_net_per_acre
                FROM '{pf}' p
                JOIN '{ff}' f ON p.apn = f.apn
                WHERE {where}
                LIMIT {limit}
            """)
            return respond(200, {"count": len(rows), "parcels": rows})

        # GET /query/pipes?type=water|sewer
        if path.startswith("/query/pipes"):
            pipe_type = qs.get("type", "water")
            name = f"infrastructure_{pipe_type}.parquet"
            pf = get_parquet(name)

            where = "1=1"
            if "min_diameter" in qs:
                where += f" AND diameter >= {int(qs['min_diameter'])}"

            limit = min(int(qs.get("limit", "1000")), 5000)

            rows = query_rows(db, f"""
                SELECT segment_id, diameter, material, install_year,
                       length_ft, capacity_edu
                FROM '{pf}'
                WHERE {where}
                LIMIT {limit}
            """)
            return respond(200, {"count": len(rows), "pipes": rows})

        # GET /query/votes?member=SANCHEZ&outcome=Passed
        if path.startswith("/query/votes"):
            vf = get_parquet("votes.parquet")

            where = "1=1"
            if "member" in qs:
                member = qs["member"].upper().replace("'", "")
                where += f" AND member_positions LIKE '%\"{member}\":\"Yes\"%'"
            if "outcome" in qs:
                outcome = qs["outcome"].replace("'", "")
                where += f" AND outcome = '{outcome}'"

            rows = query_rows(db, f"""
                SELECT meeting_date, item_number, item_title,
                       motion_summary, outcome, vote_count_for,
                       vote_count_against, member_positions
                FROM '{vf}'
                WHERE {where}
                ORDER BY meeting_date DESC
            """)
            return respond(200, {"count": len(rows), "votes": rows})

        # GET /query/budget?year=2024&flow=revenue
        if path.startswith("/query/budget"):
            bf = get_parquet("budget.parquet")

            where = "1=1"
            if "year" in qs:
                where += f" AND fiscal_year = {int(qs['year'])}"
            if "flow" in qs:
                flow = qs["flow"].replace("'", "")
                where += f" AND flow = '{flow}'"

            rows = query_rows(db, f"""
                SELECT fiscal_year, basis, flow, category, amount_usd
                FROM '{bf}'
                WHERE {where}
                ORDER BY fiscal_year, flow, category
            """)
            return respond(200, {"count": len(rows), "items": rows})

        # GET /query/permits?year=2026&type=BLD+MULTI+FAMILY&zone=D-5&downtown=true
        if path.startswith("/query/permits/downtown"):
            pmf = get_parquet("permits.parquet")
            pf = get_parquet("parcels.parquet")

            where = "pm.is_downtown = true"
            if "year" in qs:
                where += f" AND pm.year = {int(qs['year'])}"
            if "type" in qs:
                ptype = qs["type"].replace("'", "")
                where += f" AND pm.type = '{ptype}'"

            rows = query_rows(db, f"""
                SELECT pm.permit_no, pm.year, pm.type, pm.description,
                       pm.status, pm.applied, pm.zone_code, pm.zone_category,
                       pm.max_density, pm.max_height,
                       pm.owner, pm.project_id, pm.apn, pm.address,
                       p.land_use_broad, p.acres, p.near_transit
                FROM '{pmf}' pm
                LEFT JOIN '{pf}' p ON pm.apn = p.apn
                WHERE {where}
                ORDER BY pm.applied DESC
            """)
            return respond(200, {"count": len(rows), "permits": rows})

        if path.startswith("/query/permits/trend"):
            pmf = get_parquet("permits.parquet")

            where = "1=1"
            if "downtown" in qs:
                where += " AND is_downtown = true"
            if "type" in qs:
                ptype = qs["type"].replace("'", "")
                where += f" AND type = '{ptype}'"

            rows = query_rows(db, f"""
                SELECT year, type, is_downtown,
                       COUNT(*) as permit_count
                FROM '{pmf}'
                WHERE {where}
                GROUP BY year, type, is_downtown
                ORDER BY year, type
            """)
            return respond(200, {"count": len(rows), "trend": rows})

        if path.startswith("/query/permits"):
            pmf = get_parquet("permits.parquet")
            pf = get_parquet("parcels.parquet")

            where = "1=1"
            if "year" in qs:
                where += f" AND pm.year = {int(qs['year'])}"
            if "type" in qs:
                ptype = qs["type"].replace("'", "")
                where += f" AND pm.type = '{ptype}'"
            if "zone" in qs:
                zone = qs["zone"].replace("'", "")
                where += f" AND pm.zone_code = '{zone}'"
            if "downtown" in qs:
                where += " AND pm.is_downtown = true"
            if "apn" in qs:
                apn = qs["apn"].replace("'", "")
                where += f" AND pm.apn = '{apn}'"
            if "project" in qs:
                proj = qs["project"].replace("'", "")
                where += f" AND pm.project_id LIKE '%{proj}%'"

            limit = min(int(qs.get("limit", "1000")), 5000)

            rows = query_rows(db, f"""
                SELECT pm.permit_no, pm.year, pm.type, pm.description,
                       pm.status, pm.applied, pm.zone_code, pm.zone_category,
                       pm.max_density, pm.max_height, pm.is_downtown,
                       pm.owner, pm.project_id, pm.apn, pm.address,
                       p.land_use_broad, p.acres
                FROM '{pmf}' pm
                LEFT JOIN '{pf}' p ON pm.apn = p.apn
                WHERE {where}
                ORDER BY pm.applied DESC
                LIMIT {limit}
            """)
            return respond(200, {"count": len(rows), "permits": rows})

        # GET /query/housing/trend?downtown=true
        if path.startswith("/query/housing/trend"):
            hf = get_parquet("housing_projects.parquet")

            where = "1=1"
            if "downtown" in qs:
                where += " AND is_downtown = true"
            if "status" in qs:
                status = qs["status"].replace("'", "")
                where += f" AND status = '{status}'"

            rows = query_rows(db, f"""
                SELECT status, is_downtown, density_bonus,
                       COUNT(*) as project_count,
                       SUM(units_best) as total_units,
                       SUM(income_very_low + income_low) as affordable_units,
                       SUM(income_above_moderate) as market_rate_units
                FROM '{hf}'
                WHERE {where}
                GROUP BY status, is_downtown, density_bonus
                ORDER BY status, is_downtown
            """)
            return respond(200, {"count": len(rows), "trend": rows})

        # GET /query/housing?name=melrose&status=permitted&downtown=true&min_units=50
        if path.startswith("/query/housing"):
            hf = get_parquet("housing_projects.parquet")

            where = "1=1"
            if "name" in qs:
                name = qs["name"].upper().replace("'", "")
                where += f" AND UPPER(project_name) LIKE '%{name}%'"
            if "status" in qs:
                status = qs["status"].replace("'", "")
                where += f" AND status = '{status}'"
            if "downtown" in qs:
                where += " AND is_downtown = true"
            if "min_units" in qs:
                where += f" AND units_best >= {int(qs['min_units'])}"
            if "apn" in qs:
                apn = qs["apn"].replace("'", "")
                where += f" AND apn = '{apn}'"

            limit = min(int(qs.get("limit", "500")), 1000)

            rows = query_rows(db, f"""
                SELECT project_id, project_name, agency, address, apn,
                       latitude, longitude, is_downtown,
                       zone_code, zone_category, max_density, max_height,
                       units_best, units_source, units_apr_proposed,
                       units_apr_approved, units_permit_estimated,
                       income_very_low, income_low, income_moderate,
                       income_above_moderate,
                       status, density_bonus, sb35,
                       first_activity, last_activity,
                       permit_count, planning_refs,
                       apr_tracking_ids, meeting_mention_count
                FROM '{hf}'
                WHERE {where}
                ORDER BY units_best DESC
                LIMIT {limit}
            """)
            return respond(200, {"count": len(rows), "projects": rows})

        # GET /query/projects?name=monarch
        if path.startswith("/query/projects"):
            pjf = get_parquet("permit_projects.parquet")

            where = "1=1"
            if "name" in qs:
                name = qs["name"].upper().replace("'", "")
                where += f" AND UPPER(project_name) LIKE '%{name}%'"
            if "apn" in qs:
                apn = qs["apn"].replace("'", "")
                where += f" AND apn = '{apn}'"

            rows = query_rows(db, f"""
                SELECT project_id, project_name, source, permit_count,
                       estimated_units, apn, owner, address,
                       first_applied, last_applied, entitlement_refs
                FROM '{pjf}'
                WHERE {where}
                ORDER BY permit_count DESC
            """)
            return respond(200, {"count": len(rows), "projects": rows})

        # GET /query/filings/downtown?year=2022
        if path.startswith("/query/filings/downtown"):
            af = get_parquet("apr_filings.parquet")

            where = "is_downtown = true"
            if "year" in qs:
                where += f" AND year = {int(qs['year'])}"

            rows = query_rows(db, f"""
                SELECT year, apn, street_address, project_name, unit_cat,
                       tot_proposed_units, tot_approved_units, tot_disapproved_units,
                       affordable_units, above_mod_income, application_status,
                       has_building_permit, zones
                FROM '{af}'
                WHERE {where}
                ORDER BY tot_proposed_units DESC
            """)
            return respond(200, {"count": len(rows), "filings": rows})

        # GET /query/filings/trend?downtown=true
        if path.startswith("/query/filings/trend"):
            af = get_parquet("apr_filings.parquet")

            where = "1=1"
            if "downtown" in qs:
                where += " AND is_downtown = true"

            rows = query_rows(db, f"""
                SELECT year, is_downtown, unit_cat,
                       COUNT(*) as filing_count,
                       SUM(tot_proposed_units) as units_proposed,
                       SUM(tot_approved_units) as units_approved,
                       SUM(affordable_units) as affordable,
                       SUM(above_mod_income) as market_rate,
                       SUM(CASE WHEN has_building_permit THEN tot_proposed_units ELSE 0 END) as units_with_permit
                FROM '{af}'
                WHERE {where}
                GROUP BY year, is_downtown, unit_cat
                ORDER BY year, is_downtown, unit_cat
            """)
            return respond(200, {"count": len(rows), "trend": rows})

        # GET /query/filings?year=2022&downtown=true&unit_cat=5+
        if path.startswith("/query/filings"):
            af = get_parquet("apr_filings.parquet")

            where = "1=1"
            if "year" in qs:
                where += f" AND year = {int(qs['year'])}"
            if "downtown" in qs:
                where += " AND is_downtown = true"
            if "unit_cat" in qs:
                cat = qs["unit_cat"].replace("'", "")
                where += f" AND unit_cat = '{cat}'"
            if "apn" in qs:
                apn = qs["apn"].replace("'", "")
                where += f" AND apn = '{apn}'"

            limit = min(int(qs.get("limit", "1000")), 5000)

            rows = query_rows(db, f"""
                SELECT year, apn, street_address, project_name, unit_cat, tenure,
                       tot_proposed_units, tot_approved_units, tot_disapproved_units,
                       affordable_units, above_mod_income, application_status,
                       project_type, is_downtown, zones,
                       has_building_permit, match_method,
                       latitude, longitude
                FROM '{af}'
                WHERE {where}
                ORDER BY year DESC, tot_proposed_units DESC
                LIMIT {limit}
            """)
            return respond(200, {"count": len(rows), "filings": rows})

        # GET /query/str/trend
        if path.startswith("/query/str/trend"):
            sf = get_parquet("str_licenses.parquet")

            rows = query_rows(db, f"""
                SELECT business_area, rental_type, license_status,
                       COUNT(*) as license_count
                FROM '{sf}'
                GROUP BY business_area, rental_type, license_status
                ORDER BY business_area, license_count DESC
            """)
            return respond(200, {"count": len(rows), "trend": rows})

        # GET /query/str?status=Active&area=Coastal+Zone
        if path.startswith("/query/str"):
            sf = get_parquet("str_licenses.parquet")

            where = "1=1"
            if "status" in qs:
                status = qs["status"].replace("'", "")
                where += f" AND license_status = '{status}'"
            if "area" in qs:
                area = qs["area"].replace("'", "")
                where += f" AND business_area = '{area}'"
            if "apn" in qs:
                apn = qs["apn"].replace("'", "")
                where += f" AND apn = '{apn}'"

            limit = min(int(qs.get("limit", "1000")), 5000)

            rows = query_rows(db, f"""
                SELECT account, business, license_status, business_area,
                       rental_type, address, apn, property_manager,
                       latitude, longitude
                FROM '{sf}'
                WHERE {where}
                ORDER BY address
                LIMIT {limit}
            """)
            return respond(200, {"count": len(rows), "licenses": rows})

        return respond(404, {"error": "unknown endpoint", "path": path})

    except Exception as e:
        return respond(500, {"error": str(e)})
