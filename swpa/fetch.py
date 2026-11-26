"""Download raw inputs. Every function is idempotent: it skips work when its output exists."""
import math

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.merge import merge
from rasterio.warp import Resampling, reproject

from . import config as C

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "swpa-landslide-model/0.1"


def _get(url, **params):
    for attempt in range(4):
        try:
            r = SESSION.get(url, params=params, timeout=300)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == 3:
                raise


def arcgis_query(layer_url, where="1=1", geometry=None, page=1000, simplify_deg=None):
    """Page through an ArcGIS REST layer and return a GeoDataFrame in EPSG:4326."""
    frames, offset = [], 0
    while True:
        params = dict(where=where, outFields="*", outSR=4326, f="geojson",
                      resultOffset=offset, resultRecordCount=page)
        if simplify_deg:
            params["maxAllowableOffset"] = simplify_deg
        if geometry is not None:
            xmin, ymin, xmax, ymax = geometry
            params.update(geometry=f"{xmin},{ymin},{xmax},{ymax}", geometryType="esriGeometryEnvelope",
                          inSR=4326, spatialRel="esriSpatialRelIntersects")
        gj = _get(f"{layer_url}/query", **params).json()
        if "error" in gj:
            raise RuntimeError(f"{layer_url}: {gj['error']}")
        feats = gj.get("features", [])
        if feats:
            frames.append(gpd.GeoDataFrame.from_features(feats, crs=4326))
        if len(feats) < page and not gj.get("exceededTransferLimit"):
            break
        offset += len(feats)
    return pd.concat(frames, ignore_index=True)


def _vector(name, fn):
    path = C.RAW / f"{name}.gpkg"
    if not path.exists():
        print(f"  downloading {name} ...")
        fn().to_file(path)
    return gpd.read_file(path)


def counties():
    codes = ",".join(f"'{c}'" for c in C.COUNTIES.values())
    g = _vector("counties", lambda: arcgis_query(C.TIGER_COUNTY, f"STATE='{C.STATE_FIPS}' AND COUNTY IN ({codes})"))
    g["county"] = g.NAME.str.replace(" County", "", regex=False)
    return g


def county(name):
    c = counties()
    return c[c.county == name]


def geology():
    """DCNR 1:250k bedrock geology units intersecting the study area (generalized to ~20 m)."""
    g = _vector("geology", lambda: arcgis_query(C.GEOLOGY, geometry=tuple(counties().total_bounds),
                                                page=100, simplify_deg=0.0002))
    g["geometry"] = g.geometry.make_valid()  # generalization can create self-intersections
    return g


def irise():
    """IRISE Regional Landslide Inventory (WPRDC), one point per record, with a label-group column."""
    path = C.RAW / "irise.csv"
    if not path.exists():
        print("  downloading IRISE inventory ...")
        path.write_bytes(_get(C.IRISE_CSV).content)
    df = pd.read_csv(path, low_memory=False, encoding_errors="replace").dropna(subset=["Latitude", "Longitude"])
    src = df["Data Source"]
    # USGS = 1970s air-photo mapping (training label). Modern agency records = independent test.
    # NASA's Global Landslide Catalog is kept apart: many of its locations are only accurate to kilometers.
    df["group"] = np.select(
        [src.eq("USGS"), src.isin(["311", "County", "City", "Pitt", "ForestHill"]), src.eq("Nasa")],
        ["usgs_1970s", "modern", "nasa"], default="historical_other")
    return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.Longitude, df.Latitude), crs=4326)


def county_grid(name):
    """Snapped UTM bounds of a county plus buffer."""
    xmin, ymin, xmax, ymax = county(name).to_crs(C.CRS).total_bounds
    b, r = C.BUFFER_M, C.RES
    return (math.floor((xmin - b) / r) * r, math.floor((ymin - b) / r) * r,
            math.ceil((xmax + b) / r) * r, math.ceil((ymax + b) / r) * r)


def _county_dir(name):
    d = C.RAW / name.lower()
    d.mkdir(exist_ok=True)
    return d


def dem(name, tile_px=2000):
    """USGS 3DEP bare-earth DEM at 10 m for one county (+ buffer). Tiles are shared across counties."""
    path = _county_dir(name) / "dem10.tif"
    if path.exists():
        return path
    xmin, ymin, xmax, ymax = county_grid(name)
    step = tile_px * C.RES
    tdir = C.RAW / "dem_tiles"
    tdir.mkdir(exist_ok=True)
    # Tiles sit on a fixed 20 km lattice so neighboring counties reuse them.
    x_start, y_start = math.floor(xmin / step) * step, math.floor(ymin / step) * step
    tiles = []
    for x0 in np.arange(x_start, xmax, step):
        for y0 in np.arange(y_start, ymax, step):
            t = tdir / f"dem_{int(x0)}_{int(y0)}.tif"
            if not t.exists():
                r = _get(C.DEM_SERVICE, bbox=f"{x0},{y0},{x0 + step},{y0 + step}", bboxSR=26917, imageSR=26917,
                         size=f"{tile_px},{tile_px}", format="tiff", pixelType="F32",
                         interpolation="RSP_BilinearInterpolation", f="image")
                if not r.content.startswith((b"II*", b"MM\x00*")):
                    raise RuntimeError(f"DEM tile failed: {r.content[:200]}")
                t.write_bytes(r.content)
            tiles.append(t)
    print(f"  {name}: merging {len(tiles)} DEM tiles")
    srcs = [rasterio.open(t) for t in tiles]
    arr, transform = merge(srcs, bounds=(xmin, ymin, xmax, ymax), res=C.RES, nodata=-9999)
    for s in srcs:
        s.close()
    arr = arr[0]
    arr[(arr < -100) | (arr > 2000)] = -9999
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1,
                       dtype="float32", crs=C.CRS, transform=transform, nodata=-9999,
                       compress="deflate", tiled=True) as dst:
        dst.write(arr.astype("float32"), 1)
    return path


def nlcd(name):
    """NLCD 2021 land cover (30 m), nearest-resampled onto the county DEM grid."""
    path = _county_dir(name) / "nlcd2021_10m.tif"
    if path.exists():
        return path
    native = _county_dir(name) / "nlcd2021_native.tif"
    if not native.exists():
        xmin, ymin, xmax, ymax = county(name).to_crs(5070).buffer(C.BUFFER_M * 1.5).total_bounds
        url = (f"{C.NLCD_WCS}?service=WCS&version=2.0.1&request=GetCoverage&coverageId={C.NLCD_COVERAGE}"
               f"&subset=X({xmin:.0f},{xmax:.0f})&subset=Y({ymin:.0f},{ymax:.0f})&format=image/geotiff")
        native.write_bytes(_get(url).content)
    with rasterio.open(dem(name)) as ref, rasterio.open(native) as src:
        out = np.zeros((ref.height, ref.width), dtype="uint8")
        reproject(rasterio.band(src, 1), out, dst_transform=ref.transform, dst_crs=ref.crs,
                  resampling=Resampling.nearest)
        prof = ref.profile | dict(dtype="uint8", nodata=0)
    with rasterio.open(path, "w", **prof) as dst:
        dst.write(out, 1)
    return path


def all_inputs():
    print("Fetching inputs")
    counties(); geology(); irise()
    for name in C.COUNTIES:
        dem(name); nlcd(name)
