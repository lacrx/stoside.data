# Fiscal Analysis

Parcel-level fiscal productivity analysis for Oceanside, CA. Answers: "does each parcel pay for the infrastructure it consumes?"

## Methodology

Hybrid approach combining Strong Towns value-per-acre with physical infrastructure measurement:

- **Revenue:** Property tax (assessed value × 1% × city share), sales tax (commercial parcels), other (TOT, franchise fees)
- **Road costs:** Frontage-based attribution for local streets (81% of network), ITE trip generation for collectors/arterials (19%)
- **Water/sewer costs:** Pipe-foot × diameter proximity, or EDU-based if pipe GIS unavailable
- **Stormwater:** Impervious surface area per parcel
- **Other services:** Zone-based allocation (fire, police, parks)

Academic basis: Goodman 2019 (spatial extent as cost driver), Carruthers & Ulfarsson 2003 (density-cost relationship), Burchell & Mukherji 2003 (compact development 20-50% cheaper).

## Data Sources

- **Parcel boundaries + assessed values:** SanGIS (www.sangis.org) — SD County authoritative parcel shapefile
- **PCI road segments:** 4,311 segments from Oceanside PCI survey (have)
- **Treatment costs:** SCS 2022 verified costs by PCI bracket × functional class (have)
- **CIP spending:** FY25-26 adopted CIP, $7.17M/yr pavement (have)
- **Street centerlines:** SanGIS or Oceanside GIS
- **Water/sewer pipes:** Oceanside Water Utilities GIS (PRA or portal)

## Status

Phase 1 (Revenue Per Acre) in progress. Downloading parcel data from SanGIS.

## Phases

1. Revenue per acre — property tax per parcel normalized by acreage
2. Road cost per parcel — spatial join PCI segments to parcels
3. Water/sewer cost per parcel — pipe network attribution
4. Net fiscal impact — revenue - cost aggregated by land use, neighborhood, density
5. Refinement — stormwater, fire, police, parks, sales tax, Mello-Roos
