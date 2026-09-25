# San Clemente Fiscal Productivity

Parcel-level value-per-acre analysis for San Clemente, CA. Urban3-style 3D choropleth showing fiscal productivity by parcel.

## Data Source

Orange County Treasurer-Tax Collector ArcGIS FeatureServer:
`https://ocgis.com/arcpub/rest/services/Treasurer_Tax_Collector/Secured_Property_Tax_Information/FeatureServer/0`

985K parcels countywide. San Clemente parcels identified by APN book prefixes 688, 690, 691, 692 (approximately 9,600 parcels).

### Available Fields

- `AssessmentNo`: APN (e.g. 690-371-45)
- `SiteAddress`: street address
- `UseDqLanduse`: OC land use code
- `tav`: total assessed value
- `alv`: assessed land value
- `aiv`: assessed improvement value
- `ta`: tax amount
- `Shape__Area`: parcel area in sq ft (CA State Plane Zone 6)

No explicit acreage field. Convert Shape__Area / 43560 for acres.

## Methodology

Simple value-per-acre: `vpa = tav / acres`. This is the assessed-value version (Prop 13 constrained). Market value version would require Zillow/Redfin estimates or sales data.

Same color scale and height mapping as the Oceanside visualization on the stoside.frontend website.

## Status

Pipeline scripts ready. Run `download_parcels.py` then `build_vpa_tiles.py`.
