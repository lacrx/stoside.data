#!/usr/bin/env python3
"""MCP server for querying ArcGIS REST services.

Provides tools to explore and query any ArcGIS Server or ArcGIS Online service.
Pre-configured with Oceanside and SANDAG endpoints.

Auth: set env vars for token-protected layers:
  OCEANSIDE_GIS_USER — Oceanside portal username
  OCEANSIDE_GIS_PASS — Oceanside portal password
  SANDAG_GIS_TOKEN   — pre-generated SANDAG token (if needed)

Usage:
  python server.py                    # stdio transport (for Claude Code)
  python server.py --sse --port 8080  # SSE transport (for web clients)
"""

import json
import os
import time
import urllib.parse
import urllib.request
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "arcgis-explorer",
    instructions=(
        "Query ArcGIS REST services for GIS data. "
        "Pre-configured with Oceanside (gis.oceansideca.org) and "
        "SANDAG (geo.sandag.org) endpoints. Can query any ArcGIS server. "
        "Set OCEANSIDE_GIS_USER/OCEANSIDE_GIS_PASS env vars to access restricted layers."
    ),
)

TOKEN_ENDPOINTS = {
    "oceanside": "https://gis.oceansideca.org/portal/sharing/rest/generateToken",
}

_token_cache: dict[str, dict[str, Any]] = {}


def _get_token(server_key: str) -> str | None:
    if server_key == "sandag":
        return os.environ.get("SANDAG_GIS_TOKEN")

    if server_key == "oceanside":
        cached = _token_cache.get(server_key)
        if cached and cached["expires"] > time.time() * 1000:
            return cached["token"]

        user = os.environ.get("OCEANSIDE_GIS_USER")
        pwd = os.environ.get("OCEANSIDE_GIS_PASS")
        if not user or not pwd:
            return None

        token_url = TOKEN_ENDPOINTS[server_key]
        params = urllib.parse.urlencode({
            "username": user,
            "password": pwd,
            "client": "referer",
            "referer": "https://gis.oceansideca.org",
            "expiration": 60,
            "f": "json",
        }).encode()

        req = urllib.request.Request(token_url, data=params, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        if "token" in data:
            _token_cache[server_key] = {
                "token": data["token"],
                "expires": data.get("expires", time.time() * 1000 + 3_500_000),
            }
            return data["token"]
        return None

    return None


def _server_key_for_url(url: str) -> str | None:
    if "oceansideca.org" in url:
        return "oceanside"
    if "sandag.org" in url:
        return "sandag"
    return None

KNOWN_SERVERS = {
    "oceanside": "https://gis.oceansideca.org/gis/rest/services",
    "sandag": "https://geo.sandag.org/server/rest/services",
    "arcgis_online_oceanside": (
        "https://services5.arcgis.com/6UYc3MjsfrxiazMH/arcgis/rest/services"
    ),
}

OCEANSIDE_SHORTCUTS = {
    "water_mains": {
        "url": "https://gis.oceansideca.org/gis/rest/services/WaterOperations_WebService/MapServer/18",
        "description": "Water main pipes (31K+ segments): diameter, material, install year",
    },
    "water_laterals": {
        "url": "https://gis.oceansideca.org/gis/rest/services/WaterOperations_WebService/MapServer/19",
        "description": "Water lateral lines (service connections to parcels)",
    },
    "water_hydrants": {
        "url": "https://gis.oceansideca.org/gis/rest/services/WaterOperations_WebService/MapServer/6",
        "description": "Fire hydrants",
    },
    "water_meters": {
        "url": "https://gis.oceansideca.org/gis/rest/services/WaterOperations_WebService/MapServer/3",
        "description": "Water meters",
    },
    "water_valves": {
        "url": "https://gis.oceansideca.org/gis/rest/services/WaterOperations_WebService/MapServer/1",
        "description": "Water system valves",
    },
    "sewer_mains": {
        "url": "https://gis.oceansideca.org/gis/rest/services/SewerOperationsWebService/MapServer/7",
        "description": "Sewer main pipes (13K+ segments): diameter, material, install year",
    },
    "sewer_laterals": {
        "url": "https://gis.oceansideca.org/gis/rest/services/SewerOperationsWebService/MapServer/6",
        "description": "Sewer lateral lines (service connections to parcels)",
    },
    "sewer_manholes": {
        "url": "https://gis.oceansideca.org/gis/rest/services/SewerOperationsWebService/MapServer/4",
        "description": "Sewer manholes",
    },
    "storm_drains": {
        "url": "https://gis.oceansideca.org/gis/rest/services/WebService/MS4_all/FeatureServer/4",
        "description": "Storm drain pipes (MS4 network)",
    },
    "storm_inlets": {
        "url": "https://gis.oceansideca.org/gis/rest/services/WebService/MS4_all/FeatureServer/1",
        "description": "Storm drain inlets",
    },
    "storm_outlets": {
        "url": "https://gis.oceansideca.org/gis/rest/services/WebService/MS4_all/FeatureServer/2",
        "description": "Storm drain outlets",
    },
    "parcels": {
        "url": "https://geo.sandag.org/server/rest/services/Hosted/Parcels/FeatureServer/0",
        "description": "SD County parcels (1.09M features, filter SITUS_JURIS='OC' for Oceanside)",
    },
    "roads": {
        "url": "https://geo.sandag.org/server/rest/services/Hosted/Roads_All/FeatureServer/0",
        "description": "SD County street centerlines (filter LJURISDIC='OC' for Oceanside)",
    },
}


def _fetch_json(url: str, timeout: int = 30) -> dict:
    server_key = _server_key_for_url(url)
    token = _get_token(server_key) if server_key else None
    if token:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}token={token}"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read())


def _resolve_layer_url(layer_url: str) -> str:
    if layer_url in OCEANSIDE_SHORTCUTS:
        return OCEANSIDE_SHORTCUTS[layer_url]["url"]
    return layer_url


@mcp.tool()
def check_auth(server: str = "oceanside") -> str:
    """Check if credentials are configured and can generate a valid token.

    Args:
        server: Server to check ("oceanside" or "sandag")
    """
    if server == "oceanside":
        user = os.environ.get("OCEANSIDE_GIS_USER")
        if not user:
            return (
                "No credentials configured. Set env vars:\n"
                "  OCEANSIDE_GIS_USER=your_username\n"
                "  OCEANSIDE_GIS_PASS=your_password\n\n"
                "In .mcp.json, add to the arcgis server config:\n"
                '  "env": {"OCEANSIDE_GIS_USER": "...", "OCEANSIDE_GIS_PASS": "..."}'
            )
        token = _get_token("oceanside")
        if token:
            return f"Authenticated as {user}. Token obtained (expires in ~60 min)."
        return f"Credentials found for {user} but token generation failed."

    if server == "sandag":
        token = os.environ.get("SANDAG_GIS_TOKEN")
        if token:
            return "SANDAG token configured."
        return "No SANDAG_GIS_TOKEN env var set."

    return f"Unknown server: {server}"


@mcp.tool()
def list_restricted_folders(server_url: str = "oceanside") -> str:
    """List which folders require authentication on an ArcGIS Server.

    Args:
        server_url: Server URL or shortcut name
    """
    url = KNOWN_SERVERS.get(server_url, server_url)
    data = _fetch_json(f"{url}?f=json")
    folders = data.get("folders", [])

    accessible = []
    restricted = []
    for folder in folders:
        try:
            fd = _fetch_json(f"{url}/{folder}?f=json")
            if "error" in fd and "Token Required" in str(fd["error"]):
                restricted.append(folder)
            else:
                count = len(fd.get("services", []))
                accessible.append(f"{folder} ({count} services)")
        except Exception:
            restricted.append(f"{folder} (error)")

    lines = ["## Restricted (token required)"]
    for f in restricted:
        lines.append(f"- {f}")
    lines.append("\n## Accessible")
    for f in accessible:
        lines.append(f"- {f}")
    return "\n".join(lines)


@mcp.tool()
def list_known_servers() -> str:
    """List pre-configured ArcGIS server endpoints and layer shortcuts."""
    lines = ["## Known Servers"]
    for name, url in KNOWN_SERVERS.items():
        lines.append(f"- **{name}**: `{url}`")

    lines.append("\n## Layer Shortcuts (use as layer_url in other tools)")
    for name, info in OCEANSIDE_SHORTCUTS.items():
        lines.append(f"- **{name}**: {info['description']}")
        lines.append(f"  `{info['url']}`")

    return "\n".join(lines)


@mcp.tool()
def list_services(server_url: str = "oceanside") -> str:
    """List all services and folders on an ArcGIS Server.

    Args:
        server_url: Full URL to services root, or shortcut name
                    ("oceanside", "sandag", "arcgis_online_oceanside")
    """
    url = KNOWN_SERVERS.get(server_url, server_url)
    data = _fetch_json(f"{url}?f=json")

    lines = [f"## Services at {url}"]
    for svc in data.get("services", []):
        lines.append(f"- {svc['name']} ({svc['type']})")
    if data.get("folders"):
        lines.append("\n## Folders")
        for folder in data["folders"]:
            lines.append(f"- {folder}/")

    return "\n".join(lines)


@mcp.tool()
def list_folder(server_url: str, folder: str) -> str:
    """List services inside a folder on an ArcGIS Server.

    Args:
        server_url: Server URL or shortcut name
        folder: Folder name (e.g. "Sewer", "Utilities", "PublicWorks")
    """
    url = KNOWN_SERVERS.get(server_url, server_url)
    data = _fetch_json(f"{url}/{folder}?f=json")

    lines = [f"## {folder}/ at {url}"]
    for svc in data.get("services", []):
        lines.append(f"- {svc['name']} ({svc['type']})")
    return "\n".join(lines)


@mcp.tool()
def list_layers(service_url: str) -> str:
    """List all layers in a MapServer or FeatureServer service.

    Args:
        service_url: Full URL to service (e.g.
            "https://gis.oceansideca.org/gis/rest/services/SewerOperationsWebService/MapServer")
    """
    data = _fetch_json(f"{service_url}?f=json")

    lines = [f"## Layers in {service_url}"]
    for layer in data.get("layers", []):
        lines.append(f"- Layer {layer['id']}: {layer['name']}")
    for table in data.get("tables", []):
        lines.append(f"- Table {table['id']}: {table['name']}")

    return "\n".join(lines)


@mcp.tool()
def get_layer_info(layer_url: str) -> str:
    """Get metadata about a specific layer: fields, geometry type, record count, spatial reference.

    Args:
        layer_url: Full URL to layer, or shortcut name (e.g. "water_mains", "sewer_mains")
    """
    url = _resolve_layer_url(layer_url)
    data = _fetch_json(f"{url}?f=json")

    count_data = _fetch_json(
        f"{url}/query?{urllib.parse.urlencode({'where': '1=1', 'returnCountOnly': 'true', 'f': 'json'})}"
    )

    sr = data.get("extent", {}).get("spatialReference", {})
    lines = [
        f"## {data.get('name', 'Unknown')}",
        f"- **Geometry**: {data.get('geometryType', 'N/A')}",
        f"- **Feature count**: {count_data.get('count', 'N/A'):,}",
        f"- **Spatial reference**: WKID {sr.get('wkid')} (latest: {sr.get('latestWkid')})",
        f"- **Max records per query**: {data.get('maxRecordCount', 'N/A')}",
        f"- **Capabilities**: {data.get('capabilities', 'N/A')}",
        "",
        "### Fields",
    ]
    for field in data.get("fields", []):
        alias = f" ({field['alias']})" if field.get("alias") and field["alias"] != field["name"] else ""
        lines.append(f"- `{field['name']}` — {field['type']}{alias}")
        if field.get("domain") and field["domain"].get("codedValues"):
            for cv in field["domain"]["codedValues"][:10]:
                lines.append(f"    - {cv['code']}: {cv['name']}")

    return "\n".join(lines)


@mcp.tool()
def query_layer(
    layer_url: str,
    where: str = "1=1",
    out_fields: str = "*",
    limit: int = 10,
    out_sr: int = 4326,
    return_geometry: bool = True,
    geometry_filter: str = "",
    order_by: str = "",
) -> str:
    """Query features from an ArcGIS layer.

    Args:
        layer_url: Full URL to layer, or shortcut name (e.g. "water_mains")
        where: SQL where clause (e.g. "DIAMETER > 12", "MATERIAL = 4")
        out_fields: Comma-separated field names, or "*" for all
        limit: Max features to return (default 10, max 2000)
        out_sr: Output spatial reference WKID (default 4326 = WGS84)
        return_geometry: Include geometry in results
        geometry_filter: Optional bbox as "xmin,ymin,xmax,ymax" in out_sr coordinates
        order_by: Optional ORDER BY clause (e.g. "DIAMETER DESC")
    """
    url = _resolve_layer_url(layer_url)
    limit = min(limit, 2000)

    params: dict[str, Any] = {
        "where": where,
        "outFields": out_fields,
        "resultRecordCount": limit,
        "outSR": out_sr,
        "returnGeometry": str(return_geometry).lower(),
        "f": "json",
    }

    if geometry_filter:
        parts = [float(x) for x in geometry_filter.split(",")]
        params["geometry"] = json.dumps({
            "xmin": parts[0], "ymin": parts[1],
            "xmax": parts[2], "ymax": parts[3],
            "spatialReference": {"wkid": out_sr},
        })
        params["geometryType"] = "esriGeometryEnvelope"
        params["spatialRel"] = "esriSpatialRelIntersects"
        params["inSR"] = out_sr

    if order_by:
        params["orderByFields"] = order_by

    encoded = urllib.parse.urlencode(params)
    data = _fetch_json(f"{url}/query?{encoded}", timeout=60)

    if "error" in data:
        return f"Error: {data['error'].get('message', data['error'])}"

    features = data.get("features", [])
    lines = [f"## Query results: {len(features)} features (limit={limit})"]

    for feat in features:
        attrs = feat.get("attributes", {})
        geom = feat.get("geometry", {})
        attr_str = ", ".join(f"{k}={v}" for k, v in attrs.items() if v is not None)
        geom_summary = ""
        if geom:
            if "paths" in geom:
                pts = sum(len(p) for p in geom["paths"])
                geom_summary = f" [line: {len(geom['paths'])} paths, {pts} points]"
            elif "x" in geom:
                geom_summary = f" [point: {geom['x']:.6f}, {geom['y']:.6f}]"
            elif "rings" in geom:
                geom_summary = f" [polygon: {len(geom['rings'])} rings]"
        lines.append(f"- {attr_str}{geom_summary}")

    return "\n".join(lines)


@mcp.tool()
def query_count(layer_url: str, where: str = "1=1") -> str:
    """Get count of features matching a where clause.

    Args:
        layer_url: Full URL to layer, or shortcut name
        where: SQL where clause
    """
    url = _resolve_layer_url(layer_url)
    params = urllib.parse.urlencode({
        "where": where,
        "returnCountOnly": "true",
        "f": "json",
    })
    data = _fetch_json(f"{url}/query?{params}")
    return f"Count: {data.get('count', 'N/A'):,}"


@mcp.tool()
def query_distinct(layer_url: str, field: str, where: str = "1=1") -> str:
    """Get distinct values for a field, with counts.

    Args:
        layer_url: Full URL to layer, or shortcut name
        field: Field name to get distinct values for
        where: Optional SQL where clause
    """
    url = _resolve_layer_url(layer_url)
    params = urllib.parse.urlencode({
        "where": where,
        "outFields": field,
        "returnGeometry": "false",
        "outStatistics": json.dumps([{
            "statisticType": "count",
            "onStatisticField": field,
            "outStatisticFieldName": "cnt",
        }]),
        "groupByFieldsForStatistics": field,
        "orderByFields": "cnt DESC",
        "f": "json",
    })
    data = _fetch_json(f"{url}/query?{params}", timeout=60)

    if "error" in data:
        return f"Error: {data['error'].get('message', data['error'])}"

    features = data.get("features", [])
    lines = [f"## Distinct values for `{field}` ({len(features)} unique)"]
    for feat in features:
        attrs = feat.get("attributes", {})
        val = attrs.get(field, "NULL")
        cnt = attrs.get("cnt", 0)
        lines.append(f"- {val}: {cnt:,}")

    return "\n".join(lines)


@mcp.tool()
def search_arcgis_online(query: str, num: int = 15) -> str:
    """Search ArcGIS Online for datasets, maps, and services.

    Args:
        query: Search query (e.g. "oceanside water", "orgid:6UYc3MjsfrxiazMH sewer")
        num: Number of results (default 15, max 100)
    """
    params = urllib.parse.urlencode({
        "q": query,
        "f": "json",
        "num": min(num, 100),
    })
    data = _fetch_json(
        f"https://www.arcgis.com/sharing/rest/search?{params}",
        timeout=30,
    )

    results = data.get("results", [])
    lines = [f"## Search results for '{query}': {data.get('total', 0)} total, showing {len(results)}"]

    for r in results:
        lines.append(f"- **{r['title']}** — {r['type']} (owner: {r['owner']})")
        if r.get("url"):
            lines.append(f"  URL: {r['url']}")
        if r.get("snippet"):
            lines.append(f"  {r['snippet'][:120]}")

    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    if "--sse" in sys.argv:
        port = 8080
        for i, arg in enumerate(sys.argv):
            if arg == "--port" and i + 1 < len(sys.argv):
                port = int(sys.argv[i + 1])
        mcp.run(transport="sse", sse_params={"port": port})
    else:
        mcp.run(transport="stdio")
