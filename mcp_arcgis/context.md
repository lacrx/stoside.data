# MCP ArcGIS Explorer

MCP server for querying ArcGIS REST services. Provides tools to explore and query any ArcGIS Server or ArcGIS Online service, with pre-configured endpoints for Oceanside and SANDAG.

## Setup

Add to Claude Code settings (`~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "arcgis": {
      "command": "/home/thomas/miniconda3/bin/python3",
      "args": ["/home/thomas/repos/stoside.data/mcp_arcgis/server.py"]
    }
  }
}
```

## Pre-configured Endpoints

### Servers
- **oceanside**: `gis.oceansideca.org` — City of Oceanside on-prem ArcGIS Server
- **sandag**: `geo.sandag.org` — SANDAG Regional Data Warehouse
- **arcgis_online_oceanside**: Oceanside's ArcGIS Online org (CIP, planning)

### Layer Shortcuts
Use these names directly in any tool's `layer_url` parameter:
- `water_mains`, `water_laterals`, `water_hydrants`, `water_meters`, `water_valves`
- `sewer_mains`, `sewer_laterals`, `sewer_manholes`
- `storm_drains`, `storm_inlets`, `storm_outlets`
- `parcels`, `roads`

## Tools

| Tool | Purpose |
|---|---|
| `list_known_servers` | Show all pre-configured servers and shortcuts |
| `list_services` | List services on an ArcGIS server |
| `list_folder` | List services inside a server folder |
| `list_layers` | List layers in a specific service |
| `get_layer_info` | Get field definitions, geometry type, count |
| `query_layer` | Query features with where clause, bbox, field selection |
| `query_count` | Count features matching a filter |
| `query_distinct` | Get distinct values for a field with counts |
| `search_arcgis_online` | Search ArcGIS Online catalog |

## Data Sources Found

### Oceanside GIS Server (`gis.oceansideca.org`)
- Water distribution system (mains, laterals, hydrants, meters, valves, wells, reservoirs)
- Sewer collection system (mains, laterals, manholes, fittings)
- Storm drain network (MS4 pipes, inlets, outlets)
- Recycled water system
- CCTV inspection data
- Planning layers (land use, zoning)
- Survey control monuments
- Right of way
- Historical orthophotos (2001-2023)

### SANDAG (`geo.sandag.org`)
- County-wide parcels (1.09M features)
- Street centerlines (Roads_All, 164K segments)
- Water/sewer pipes for City of SD and County only
- Transit, land use, environmental layers
