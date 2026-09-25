# Layer and imagery sources — μField

Status: research draft, 2026-09-24. Put at `docs/layer-sources.md`. Machine-readable version: `config/layers.yaml`.

## 1. Goal for the MVP: the Farm Pack

The first integrated service is a **Farm Pack**: one consumer-friendly bundle of imagery and base data that covers one target area, typically a single large farm (50–1,000 ha). The user builds the target area from field parcels (peltolohkotunnus), properties (kiinteistötunnus) or map taps, or draws a boundary; the server returns a ready-to-open package for the phone and QGIS. Target areas can be fields, forest, other green land, brownfields or urban green areas; see `docs/adr/0001-target-areas.md`.

Farm Pack is the first real `ProductJob` (`product_type: farm_pack`). Orthomosaics, 3DGS and super-resolution stay unimplemented.

### Farm Pack contents (all free sources)

| Item | Source | Resolution | How it's fetched |
|---|---|---|---|
| Colour orthophoto | MML WCS | 0.5 m | Tiled requests, max 2 × 2 km each, mosaicked to one COG |
| False-colour (CIR) orthophoto | MML WCS | 0.5 m | Same as above |
| Elevation model, hillshade, slope | MML WCS (DEM 2 m) | 2 m | One request up to 10 × 10 km; derivatives computed on server |
| Sentinel-2 season series: true colour + NDVI per cloud-free date | CDSE openEO (SENTINEL2_L2A, SCL cloud mask) | 10 m | One openEO batch job per farm |
| Field parcels and plant parcels for the chosen year | Ruokavirasto INSPIRE WFS | vector | Clipped to farm AOI |
| Soil types, acid sulphate soils, peat | GTK WMS/WFS | vector/raster | Clipped |
| Catchments, groundwater areas, flood zones, Natura 2000 | SYKE GeoServer | vector | Clipped |
| Forest stands (if the farm has forest) | Metsäkeskus WFS | vector | Clipped |
| Weather summary: temperature sum, precipitation | FMI open data WFS | point/grid | Nearest station or grid cell |

### Package format

- `farm.gpkg`: all vectors + raster tiles for offline phone use.
- `rasters/*.tif`: Cloud-Optimised GeoTIFFs for QGIS and later processing.
- `catalog.json`: STAC catalog; every item carries source, licence, attribution and acquisition date.
- `overview.png` / `overview.pdf`: a one-page farm summary for the farmer.

Rough size for a 500 ha farm in a 4 × 3 km bounding box (estimate, to be measured): the 0.5 m orthophoto is about 48 million pixels, so roughly 15–40 MB as a JPEG-compressed COG per orthophoto type. The whole pack should stay under about 150 MB, which is acceptable over mobile data.

### Why it runs on the server, not on the phone

- MML's WCS limits each orthophoto request to 2 × 2 km, so a farm needs tiling and mosaicking.
- API keys (MML, CDSE) stay on the server, and the proxy endpoints require a signed-in user so the keys can't be used anonymously. MML's open service is meant for small-scale use; server-side caching keeps us within that.
- openEO jobs are asynchronous; the phone gets a notification when the pack is ready.

## 2. Finnish national sources

### Maanmittauslaitos (National Land Survey, NLS)

- **Access:** free open-data API key from the My Account service, MML accepts it as `api-key=<key>` in the URL or as the HTTP Basic user name with an empty password. **μField uses HTTP Basic only**: keys in URLs leak into logs, caches and STAC hrefs (`docs/adr/0002-credentials.md`).
- **WMTS (open):** `https://avoin-karttakuva.maanmittauslaitos.fi/avoin/wmts/1.0.0/WMTSCapabilities.xml`. Layers include maastokartta, taustakartta, selkokartta, ortokuva, ortokuva_vaaravari, korkeusmalli_vinovalo. Tile matrix sets: ETRS-TM35FIN (zoom 0–15) and WGS84 Pseudo-Mercator (zoom 0–18). The open service is intended for testing and small-scale use; contract access removes that limit.
- **Vector tiles:** `https://avoin-karttakuva.maanmittauslaitos.fi/vectortiles/wmts`.
- **Orthophoto and elevation query service (WCS):** `https://avoin-karttakuva.maanmittauslaitos.fi/ortokuvat-ja-korkeusmallit/wcs/v2`. Colour, black-and-white and false-colour orthophotos at 0.5 m; DEM 2 m. Limits per request: orthophotos 2,000 × 2,000 m and 4,000 px; DEM 10,000 × 10,000 m and 5,000 px. GeoTIFF output; EPSG:3067, GK zones or 3857.
- **File service (OGC API Processes):** clip by bbox or polygon; orthophotos (JPEG2000), DEM 2 m / 10 m, laser scanning point clouds (LAZ), Maastotietokanta, property maps, 3D buildings. EPSG:3067 only. No area limit documented. Good for LiDAR in later 3D products.
- **OGC API Features:** topographic database (`https://avoin-paikkatieto.maanmittauslaitos.fi/maastotiedot/features/v1/`) and property data.
- **Property boundaries (kiinteistöjaotus):** palstat with their kiinteistötunnus, used to resolve target areas selected by property id (`mml_kiinteistot` in the registry; endpoint path and collection id still to be confirmed). Owner data is not open and is not used.
- **Licence:** open data, CC BY 4.0 (attribution: Maanmittauslaitos).

### Ruokavirasto (Finnish Food Authority)

- **Datasets:** Peltolohkorekisteri (field parcels), landscape features on agricultural land, spatial plant parcels (kasvulohkot), agricultural land. Yearly, 2020–2025 available now.
- **WMS:** `https://inspire.ruokavirasto-awsa.com/geoserver/wms`
- **WFS:** `https://inspire.ruokavirasto-awsa.com/geoserver/wfs`. Feature types per year, for example `inspire:LC.LandCoverSurfaces.LPIS.2025` (field parcels) and `inspire:LandUse.ExistingLandUse.GSAAAgriculturalParcel.2025` (plant parcels). Native CRS EPSG:3067; JSON output supported.
- **Downloads:** `https://download.inspire.ruokavirasto-awsa.com/data/<YEAR>/<DATASET>.gpkg` and an Atom feed.
- **Licence:** CC BY 4.0.
- **Target areas:** field parcels are selected by peltolohkotunnus (10 digits) from the field parcel layer of the chosen year.
- **Note:** layer names contain the year. The registry should resolve "latest year" at runtime instead of hard-coding it.

### GTK (Geological Survey of Finland)

- **Soil WMS:** `https://gtkdata.gtk.fi/arcgis/rest/services/Rajapinnat/GTK_Maapera_WMS/MapServer/WMSServer`
- **Layers under open licence:** soil maps 1:20,000/1:50,000, 1:100,000, 1:200,000 (soil types), 1:1,000,000, acid sulphate soils 1:250,000. The same service also has peatland layers: peatland types, peatland nutrient level, regional peat carbon stock.
- **Basic-licence layers** (for example studied peatland areas, shaded relief, seabed materials) have different terms; keep them out of the default registry until checked.
- A WFS version of the soil layers exists too.

### SYKE (Finnish Environment Institute)

All services are on `https://paikkatiedot.ymparisto.fi/geoserver/<workspace>/wms|wfs|wcs`. Useful workspaces:

- `inspire_hy`: catchment areas and river network
- `syke_vhspohjavesi`: groundwater areas (WFD)
- `inspire_nz`, `tulva_perus_peittama`, `tulva_havaitut`: flood hazard and observed floods
- `inspire_lc`: CORINE land cover
- `inspire_ps`: protected sites and Natura 2000
- `vemalaAvoin`: VEMALA nutrient loading results
- `syke_hiilikartta`: Carbon Map datasets
- `vetisetsuopinnat_*`: wet mire surfaces over time

Licence: check per dataset in SYKE's metadata service; most open SYKE data is CC BY 4.0.

### Luke (Natural Resources Institute Finland)

- **MS-NFI (multi-source forest inventory) WMS:** `http://kartta.luke.fi/geoserver/MVMI/wms`. Forest rasters, relevant for farms with forest.
- Most other Luke resources in the Agrihubi list are statistics databases, not map services.

### Metsäkeskus (Finnish Forest Centre)

Not in the Agrihubi list, but useful for Finnish farms, which usually include forest.

- **Forest stands:** `https://avoin.metsakeskus.fi/rajapinnat/v2/stand/ows` (WMS/WFS)
- **Special habitats:** `https://avoin.metsakeskus.fi/rajapinnat/v2/habitat/ows`
- **Grid data (WCS):** `https://avoin.metsakeskus.fi/rajapinnat/v2/gridcell/ows`. Includes surface flow models, wetness index and canopy height model.
- Licence: confirm in the product descriptions before release.

### FMI (Finnish Meteorological Institute)

- **Open data WFS:** `https://opendata.fmi.fi/wfs` with stored queries for observations, forecasts and gridded data. WMS view services also exist.
- **Licence:** CC BY 4.0 (attribution: Ilmatieteen laitos). No API key.
- **Farm pack use:** growing-season temperature sum and precipitation for the farm.

### Paituli (CSC)

- GeoServer at `https://paituli.csc.fi/geoserver/` with WMS, WFS and OGC API Features. Mostly a research mirror of national datasets; use it as a fallback source, not a primary one.

## 3. Satellite imagery services

### Copernicus Data Space Ecosystem (CDSE): Sentinel Hub and openEO

- **Free tier, per user account.** Sentinel Hub: 10,000 processing units and 10,000 requests per month, 300 per minute. openEO: 10,000 credits per month, 2 concurrent batch jobs, 12 requests per minute.
- The March 2026 billing update made openEO about 25 % cheaper: credits now count only CPU and RAM reserved while a job runs, and queuing is free.
- **Licence:** Copernicus data can be redistributed with attribution; modified data must say "Contains modified Copernicus Sentinel data [year]".
- **Commercial scale:** larger quotas are available under commercial terms through the ecosystem's service providers.
- **Fit:** the best free engine for the Farm Pack's Sentinel-2 series. openEO is also the right abstraction for later products, because a recipe written once runs on any openEO back-end.

**Scaling note:** the free quota is per account. With Biomitta's single server account, 10,000 credits a month is enough for testing and a pilot group. For a public app, budget for a commercial CDSE plan, or let power users connect their own CDSE account.

### Planet Labs

- **Planet Agriculture (area-under-management):** PlanetScope, next-day, 3 m, sold in 500 ha (5 km²) packages. Price per hectare per year depends on the country tier: $0.35, $0.85 or $1.80. That is $175, $425 or $900 a year per 500 ha, plus monitoring credits for platform use. Includes a two-year archive; polygons can be as small as 1 ha.
- **How area is counted:** the union of your polygons. Re-ordering the same polygon costs nothing extra; 20 % overage fee above the purchased quota; 12-month subscription.
- **Planet Insights Platform (self-service):** Starter $1,100/yr (7,000 credits/month, about 100 km² of ordering), Professional $5,500/yr and Scale $12,000/yr. Starter and Professional only get imagery 30 days or older; next-day data requires Scale or Enterprise.
- **Fit:** the 500 ha package matches "one big farm" almost exactly. It's the natural paid upgrade for the Farm Pack: daily 3 m imagery instead of Sentinel-2's 10 m every few days.
- **To check before building:** Finland's price tier, and whether the licence lets Biomitta show raw PlanetScope imagery to farmers in a consumer app or only derived products. Planet's standard terms restrict redistribution; ask Planet about partner or reseller terms.

### UP42 (assumed to be what "U42" meant)

- A marketplace for many operators: Pléiades, Pléiades Neo, SPOT, Planet, SAR (ICEYE, Capella, Umbra), hyperspectral and drones. REST API, Python SDK, STAC-compatible delivery.
- **Pricing:** credits at 100 credits = €1, minimum purchase 10,000 credits (€100). Sentinel-2 and Landsat cost nothing.
- **Tasking minimums** are too large for one farm: 100 km² for Pléiades, Pléiades Neo and SPOT. Planet, Satellogic and SAR tasking is per scene, and Globhe drone tasking starts at 1 km².
- Acquired by Neo Space Group in July 2025.
- **Fit:** not for the everyday Farm Pack. Useful later for one-off very-high-resolution (30–50 cm) archive images or SAR through a single API. The Globhe drone option is interesting for farms without their own drone.

### FMI "CARBS"

I couldn't find an FMI service called CARBS. The closest FMI work is:

- **Pelto-observatorio (Field Observatory Network, FiON):** combines sensors, weather, satellites and models into near-real-time carbon balance and yield forecasts. Covers three research fields and about 20 Carbon Action pilot farms. It has a web portal but no documented public API.
- **A published method** that estimates daily photosynthesis per field parcel from openly available satellite data, calibrated with eddy covariance measurements.

Both fit the future product pipeline (carbon and MRV products) rather than the MVP. **Confirm the exact name or link.**

### Peltoraportti

Not found as a public service. The domain `peltoraportti.fi` doesn't resolve. **Confirm what this refers to**, for example a specific company's field report or a project output.

## 4. Decisions proposed

1. **The MVP Farm Pack uses free sources only:** MML ortho and DEM, CDSE openEO Sentinel-2, Ruokavirasto, GTK, SYKE, Metsäkeskus, FMI.
2. **Planet Agriculture (500 ha packages) is the first paid imagery option.** Design the Farm Pack so an extra imagery source slots in as another STAC collection.
3. **UP42 is for later one-off very-high-resolution or SAR orders.** No MVP integration.
4. **All server-side fetching goes through ufield-server:** keys stay off the phone, results are cached per farm AOI, and every output item records its source licence (see the CLAUDE.md provenance rule).
5. **The layer registry resolves year-stamped layer names** (Ruokavirasto) at runtime, and CI checks every endpoint weekly.

## 5. Open questions

- What are "FMI CARBS" and "Peltoraportti"? (Name or link.)
- Which Planet country tier applies to Finland, and does the licence allow showing raw imagery to farmers?
- Commercial CDSE quota needs once there are more than about 50 active farms.
- Metsäkeskus and SYKE per-dataset licences: confirm CC BY 4.0 before public release.
