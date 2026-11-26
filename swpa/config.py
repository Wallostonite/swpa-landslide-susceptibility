"""Paths, study area and data-source endpoints for the southwestern Pennsylvania (IRISE) landslide model."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DERIVED = ROOT / "data" / "derived"
OUT = ROOT / "outputs"
for _d in (RAW, DERIVED, OUT):
    _d.mkdir(parents=True, exist_ok=True)

# IRISE study area: the 12 counties of PennDOT Districts 10, 11 and 12.
COUNTIES = {
    "Allegheny": "003", "Armstrong": "005", "Beaver": "007", "Butler": "019", "Clarion": "031",
    "Fayette": "051", "Greene": "059", "Indiana": "063", "Jefferson": "065", "Lawrence": "073",
    "Washington": "125", "Westmoreland": "129",
}
STATE_FIPS = "42"

# Terrain is processed one county at a time (plus a buffer) on a 10 m UTM 17N grid.
CRS = "EPSG:26917"
RES = 10.0
BUFFER_M = 2000

H3_RES = 10        # ~15,000 m2 hexagons
H3_BLOCK_RES = 6   # ~36 km2 blocks for spatial cross-validation
H3_MAP_RES = 8     # ~0.74 km2 hexagons for the interactive map

TIGER_COUNTY = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1"
GEOLOGY = "https://mapservices.pasda.psu.edu/server/rest/services/pasda/DCNR2/MapServer/11"
DEM_SERVICE = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
NLCD_WCS = "https://www.mrlc.gov/geoserver/mrlc_download/wcs"
NLCD_COVERAGE = "mrlc_download__NLCD_2021_Land_Cover_L48"
IRISE_CSV = ("https://data.wprdc.org/dataset/42a2155f-edf2-4baf-bac9-6d3e77c4a463/resource/"
             "f6aea9d6-910c-4755-9bf6-e4c40d2f52e0/download/iriselandslidedatabaseforwprdc.csv")
