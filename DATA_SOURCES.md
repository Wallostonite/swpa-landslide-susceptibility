# Data Sources and Credits

This project builds a landslide susceptibility model for the 12-county IRISE study area of southwestern
Pennsylvania entirely from public data. **No third-party data files are redistributed in this repository.**
The pipeline downloads every input directly from its provider at run time (see `swpa/config.py` and
`swpa/pasda.py`), and the `data/` directory is excluded from version control.

The derived outputs that *are* committed (figures, metric tables, the interactive map) are covered by
[`DATA_LICENSE.md`](DATA_LICENSE.md). This file credits each source, states its license or terms of use,
records how the project used and modified it, and gives a recommended citation.

Data were accessed between 26 September 2026 and 27 September 2026 unless noted otherwise.

## Summary

| # | Dataset | Provider | Role in this project | License / terms |
|---|---|---|---|---|
| 1 | IRISE Regional Landslide Inventory for Southwestern Pennsylvania | University of Pittsburgh IRISE, via WPRDC | Training labels (USGS group) and independent test records | CC BY-SA |
| 2 | 3D Elevation Program (3DEP) bare-earth DEM | U.S. Geological Survey | All terrain predictors | Public domain (U.S. Government work) |
| 3 | National Land Cover Database 2021 | U.S. Geological Survey / MRLC | Land-cover predictors | Public domain (U.S. Government work) |
| 4 | Bedrock Geology of Pennsylvania, geologic units | PA DCNR, Bureau of Geological Survey, via PASDA | Geology predictors | PaGS use constraints (credit and modification notice required) |
| 5 | PA DEP Mined Out Area (MOA), Coal Underground | PA Department of Environmental Protection, via PASDA | Undermining predictors (primary model) | PA DEP use constraints; **not for commercial use or resale** |
| 6 | PA DEP Mining Permits, Coal Underground (Historic) | PA Department of Environmental Protection, via PASDA | Undermining predictor (primary model) | PA DEP use constraints; **not for commercial use or resale** |
| 7 | PA DEP Longwall Mining Panels | PA Department of Environmental Protection, via PASDA | Undermining predictor, pre-1976 panels (primary model) | PA DEP use constraints; **not for commercial use or resale** |
| 8 | Oil and Gas Locations, Conventional and Unconventional | PA Department of Environmental Protection, via PASDA | Tested predictor (not in primary model) | Commonwealth disclaimer; as-is, user indemnifies |
| 9 | Pennsylvania State Roads; Pennsylvania Local Roads | PennDOT, via PASDA | Tested predictor; near-road test subset | Commonwealth disclaimer; as-is, user indemnifies |
| 10 | Bedrock Surface Topography Digital Elevation Raster of Pennsylvania | PA DCNR, Bureau of Geological Survey, via PASDA | Tested predictor (regolith thickness) | PaGS use constraints (credit and modification notice required) |
| 11 | Soil Survey Geographic Database (SSURGO), 11 survey areas | USDA NRCS, via PASDA | Tested predictors (not in primary model) | Public domain; NRCS acknowledgment requested |
| 12 | Allegheny County Landslides (County Public Works) 2025; Landslide Individual Assistance; Landslide Public Assistance | Allegheny County GIS, via PASDA | Independent test records | Allegheny County use constraints (informational, as-is) |
| 13 | AlphaEarth Foundations Satellite Embedding V1 (annual, 2017) | Google and Google DeepMind, via Source Cooperative | Foundation-model experiment only (not in primary model) | CC BY 4.0 |
| 14 | TIGER/Line boundaries (TIGERweb) | U.S. Census Bureau | County boundaries and study-area extent | Public domain (U.S. Government work) |

## 1. IRISE Regional Landslide Inventory for Southwestern Pennsylvania

- **Provider:** University of Pittsburgh, Impactful Resilient Infrastructure Science and Engineering (IRISE) consortium; published by the Western Pennsylvania Regional Data Center (WPRDC).
- **Access:** <https://data.wprdc.org/dataset/irise-regional-landslide-inventory-for-southwestern-pennsylvania> (CSV resource `IRISELandslideDatabaseForWPRDC.csv`). Accompanying report: *A Regional Landslide Inventory for Southwestern Pennsylvania* (July 2024).
- **License:** Creative Commons Attribution-ShareAlike (as listed on WPRDC). Because of the ShareAlike condition, derived outputs in this repository are released under CC BY-SA 4.0 (see `DATA_LICENSE.md`).
- **Use:** Records with `Data Source = USGS` (4,844 points; 1970s air-photo landslide mapping by the U.S. Geological Survey, digitized by the Southwestern Pennsylvania Commission and the University of Pittsburgh) are the training labels. Records from `311`, `County`, `City`, `Pitt` and `ForestHill` (1,172 points) are used only as independent test data. `Nasa` records (NASA Global Landslide Catalog) are excluded because many locations are accurate only to kilometers; `Adams` and `Ackenheil` historical records are not used.
- **Modifications:** points assigned to H3 resolution-10 hexagons; per-hexagon record counts computed by source group.
- **Suggested citation:** University of Pittsburgh IRISE (2024). *IRISE Regional Landslide Inventory for Southwestern Pennsylvania* [dataset]. Western Pennsylvania Regional Data Center. CC BY-SA.
- **Note:** the inventory itself compiles records from several upstream agencies (USGS, the City of Pittsburgh, Allegheny County, NASA and others); credit for those records rests with their original producers as documented in the IRISE report.

## 2. USGS 3D Elevation Program (3DEP)

- **Provider:** U.S. Geological Survey, National Geospatial Program.
- **Access:** 3DEPElevation ImageServer, `exportImage`, <https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer>.
- **License:** public domain (works of the U.S. Government are not subject to copyright in the United States).
- **Use and modifications:** bare-earth elevation requested at 10 m in NAD83 / UTM zone 17N (EPSG:26917) with bilinear resampling, in 20 km tiles merged per county. The service draws on the best available 3DEP source, including 1 m lidar. Slope, aspect, curvature, topographic position, local relief, roughness, wetness index, height above nearest drainage and distance to channel were derived from it.
- **Suggested credit:** Elevation data courtesy of the U.S. Geological Survey, 3D Elevation Program.

## 3. National Land Cover Database (NLCD) 2021

- **Provider:** U.S. Geological Survey and the Multi-Resolution Land Characteristics (MRLC) Consortium.
- **Access:** MRLC WCS, coverage `NLCD_2021_Land_Cover_L48`, <https://www.mrlc.gov/>.
- **License:** public domain (U.S. Government work).
- **Use and modifications:** 30 m land cover resampled to the 10 m grid (nearest neighbor), grouped into nine classes, and summarized as per-hexagon fractions.
- **Suggested citation:** Dewitz, J. (2023). *National Land Cover Database (NLCD) 2021 Products*. U.S. Geological Survey data release. <https://doi.org/10.5066/P9JZ7AO3>

## 4. Bedrock Geology of Pennsylvania (geologic units)

- **Provider:** Pennsylvania Department of Conservation and Natural Resources (DCNR), Bureau of Geological Survey (formerly Bureau of Topographic and Geologic Survey); distributed by PASDA.
- **Access:** PASDA map service `pasda/DCNR2/MapServer/11` ("DCNR Bedrock Geology of Pennsylvania Geologic Units", 2023 edition); see also PASDA dataset 480.
- **Terms (from the provider's metadata):** the data may be used provided that credit for the original (unaltered) data is given to the Pennsylvania Bureau of Geological Survey, DCNR; users must clearly indicate the source and describe any modifications; users must not misrepresent the data or imply that their changes were approved by the PaGS. The data are not designed for use as a primary regulatory tool in permitting and siting decisions.
- **Source credit:** Geologic data are from the Pennsylvania Bureau of Geological Survey, Department of Conservation and Natural Resources. The original data are unaltered at the source; the PaGS has not reviewed or approved the modifications below.
- **Modifications made in this project:** polygons were requested in WGS84 for the study-area extent with vertex generalization (`maxAllowableOffset` 0.0002°, about 20 m), repaired with a geometric validity correction, reprojected to EPSG:26917, rasterized to 10 m, and summarized as the fraction of each H3 hexagon underlain by each unit. Units covering less than 0.5% of the study area were pooled into a single `geo_other` class.

## 5 to 7. PA DEP coal-mining layers

| Dataset | PASDA ID | Layer used |
|---|---|---|
| PA DEP Mined Out Area (MOA), Coal Underground (distributed as "Digitized Mined Areas") | 257 | `DigitizedMinedAreas2026_09` |
| PA DEP Mining Permits, Coal Underground (Historic) | 366 | `PA_Historic_Underground_Mine_Permits202609` |
| PA DEP Longwall Mining Panels | 256 | `LongwallMiningPanels2026_09` |

- **Provider:** Pennsylvania Department of Environmental Protection; distributed by PASDA, <https://www.pasda.psu.edu/>.
- **Terms (from the provider's metadata):** compiled from various sources with no guarantee of accuracy, completeness or veracity; the Department disclaims responsibility for actions taken in reliance on the data; the user saves the Commonwealth harmless from claims arising from use of the data; data provided as is. **Not for commercial use or resale.**
- **Use and modifications:** polygons rasterized to 10 m and summarized per hexagon as the fraction inside a mined-out area, inside a historic underground-mine permit, and inside a longwall panel completed by 1975 (panels completed after 1975 are excluded from the model because they post-date the training labels), plus the distance to the nearest mined-out area (capped at 2 km).
- **Suggested credit:** Coal-mining data: Pennsylvania Department of Environmental Protection, via Pennsylvania Spatial Data Access (PASDA).

## 8. Oil and Gas Locations, Conventional and Unconventional

- **Provider:** Pennsylvania Department of Environmental Protection, via PASDA (dataset 1088, `OilGasLocations_ConventionalUnconventional2026_09`).
- **Terms:** Commonwealth disclaimer; data provided as is, with no warranty; the user saves the Commonwealth harmless from claims arising from use of the data.
- **Use:** density of wells spudded by 1975 (or undated) within 500 m, tested as a predictor; not part of the primary model.

## 9. PennDOT roads

- **Provider:** Pennsylvania Department of Transportation, Bureau of Planning and Research, Geographic Information Division, via PASDA (dataset 54, `PaStateRoads2026_07`; and `PaLocalRoads2026_07`).
- **Terms:** the user indemnifies and holds harmless the Commonwealth; the Commonwealth excludes all implied warranties; files are provided as is.
- **Use:** road presence and distance to roads were tested as predictors (not in the primary model); distance to the nearest road defines the near-road subset of the independent test.

## 10. Bedrock Surface Topography Digital Elevation Raster of Pennsylvania

- **Provider:** PA DCNR, Bureau of Geological Survey, via PASDA (dataset 316, `DCNR_BedrockElevation2023`).
- **Terms (from the provider's metadata):** may be used provided that credit for the original (unaltered) data is given to the Pennsylvania Bureau of Geological Survey, DCNR; users must indicate the source, describe modifications, and not imply PaGS approval of changes.
- **Source credit:** Bedrock surface data are from the Pennsylvania Bureau of Geological Survey, Department of Conservation and Natural Resources. The PaGS has not reviewed or approved the modifications below.
- **Modifications made in this project:** band 1 (predicted bedrock elevation, feet NAVD88) converted to meters, resampled bilinearly from 100 m to the 10 m grid, and subtracted from the 3DEP surface to estimate regolith thickness (clipped at zero). Tested as a predictor; not part of the primary model.

## 11. Soil Survey Geographic Database (SSURGO)

- **Provider:** U.S. Department of Agriculture, Natural Resources Conservation Service (NRCS); county survey downloads distributed by PASDA.
- **Survey areas:** PA003 Allegheny, PA005 Armstrong, PA007 Beaver, PA019 Butler, PA031 Clarion, PA051 Fayette, PA063 Indiana, PA065 Jefferson, PA073 Lawrence, PA129 Westmoreland, and the Greene-Washington survey area (2024 releases).
- **Terms:** public domain; the provider requests that NRCS be acknowledged as the data source in derived products.
- **Use and modifications:** horizon clay, saturated hydraulic conductivity and linear extensibility depth-weighted over 0 to 100 cm and component-weighted by representative component percentage; map-unit aggregates (depth to bedrock, depth to water table, hydrologic group, drainage class) and the share of components rated high for soil slippage potential. Tested as predictors; not part of the primary model.
- **Suggested citation:** Soil Survey Staff, Natural Resources Conservation Service, United States Department of Agriculture. *Soil Survey Geographic (SSURGO) Database* for the survey areas listed above. Accessed via PASDA, September 2026.

## 12. Allegheny County landslide layers

| Dataset | PASDA ID | Access |
|---|---|---|
| Allegheny County Landslides (County Public Works), 2025 | 3003 | map service `pasda/AlleghenyCounty/MapServer/38` |
| Allegheny County Landslide Individual Assistance (FEMA 2018) | 3004 | `AlleghenyLandSlide_IndividualAssistance.zip` |
| Allegheny County Landslide Public Assistance (FEMA 2018) | 3005 | `AlleghenyLandSlide_PublicAssistance.zip` |

- **Provider:** Allegheny County, Division of Computer Services, Geographic Information Systems Group; distributed by PASDA.
- **Terms:** the data are for informational purposes only, shipped as is, with no guarantee of completeness or accuracy; the County is not responsible for reliance on the data.
- **Use:** independent test records only; point locations assigned to hexagons and counted.

## 13. AlphaEarth Foundations Satellite Embedding V1

- **Provider:** Google and Google DeepMind; Cloud-Optimized GeoTIFF mirror hosted on Source Cooperative by Taylor Geospatial Engine (TGE Labs).
- **Access:** <https://source.coop/tge-labs/aef>, annual layer 2017, UTM zone 17N tiles.
- **License:** Creative Commons Attribution 4.0 International (CC BY 4.0).
- **Required attribution:** credit to Google and Google DeepMind as the producers of the dataset.
- **Use and modifications:** read at the 40 m overview level, dequantized, and averaged per hexagon. Used only in the foundation-model experiment (`aef_experiment.py`, `aef_pca.py`); the embeddings did not improve the model and are not part of the primary model or any committed output map.
- **Suggested citation:** Brown, C. F., et al. (2025). *AlphaEarth Foundations: An embedding field model for accurate and efficient global mapping from sparse label data*. arXiv:2507.22291. Dataset: Google and Google DeepMind, *Satellite Embedding V1*, CC BY 4.0.

## 14. U.S. Census Bureau TIGER boundaries

- **Provider:** U.S. Census Bureau, TIGERweb REST services (State_County, layer 1).
- **License:** public domain (U.S. Government work).
- **Use:** county boundaries that define the study area and the per-county processing extents.

## Background references

The training labels trace back to the U.S. Geological Survey's landslide mapping of southwestern Pennsylvania after
Hurricane Agnes (1972), including:

- Pomeroy, J. S. (1982). *Landslides in the Greater Pittsburgh Region, Pennsylvania*. U.S. Geological Survey Professional Paper 1229. <https://doi.org/10.3133/pp1229>
- Briggs, R. P., Pomeroy, J. S., and Davies, W. E. (1975). *Landsliding in Allegheny County, Pennsylvania*. U.S. Geological Survey Circular 728. <https://pubs.usgs.gov/publication/cir728>

## Software

The analysis uses open-source software, credited here with thanks: geopandas, rasterio, pyogrio, shapely and
pyproj (BSD-3-Clause / MIT); NumPy, SciPy, pandas and scikit-learn (BSD-3-Clause); pyarrow and requests
(Apache-2.0); h3-py (Apache-2.0); LightGBM (MIT); folium (MIT); matplotlib (PSF-based Matplotlib License); and
pysheds (GPL-3.0-or-later). Each package is used under its own license and is installed separately
(`requirements.txt`); none is redistributed here.
