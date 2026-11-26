"""Aggregate 10 m rasters onto an H3 grid, county by county, then merge into one regional cell table."""
import json
import re

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.features import rasterize

from . import config as C
from . import fetch, terrain

CELLS = C.DERIVED / f"cells_h3r{C.H3_RES}.parquet"
NLCD_GROUPS = {"water": [11], "dev_open": [21], "dev_low": [22], "dev_high": [23, 24], "barren": [31],
               "forest": [41, 42, 43], "shrub_grass": [52, 71], "agriculture": [81, 82], "wetland": [90, 95]}
MIN_UNIT_SHARE = 0.005  # geologic units covering less than 0.5% of the region fold into geo_other
LABEL_GROUPS = ["usgs_1970s", "modern", "nasa", "historical_other"]


def _slug(name):
    return "geo_" + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def geology_units():
    """Map of DCNR unit name -> feature column, fixed once for the whole region."""
    path = C.DERIVED / "geology_units.json"
    if path.exists():
        return json.loads(path.read_text())
    geo = fetch.geology().to_crs(C.CRS)
    region = fetch.counties().to_crs(C.CRS).dissolve()
    clip = gpd.clip(geo, region)
    share = (clip.area.groupby(clip.NAME).sum() / region.area.iloc[0]).sort_values(ascending=False)
    units = {n: (_slug(n) if s >= MIN_UNIT_SHARE else "geo_other") for n, s in share.items()}
    path.write_text(json.dumps(units, indent=1))
    return units


def _burn(gdf, prof):
    if gdf.empty:
        return np.zeros((prof["height"], prof["width"]), dtype="uint8")
    return rasterize(gdf.geometry, out_shape=(prof["height"], prof["width"]),
                     transform=prof["transform"], fill=0, default_value=1, dtype="uint8")


def pixel_index(name, prof):
    """H3 cell id (uint64) for every pixel inside the county; 0 outside."""
    path = terrain.out_dir(name) / f"pixel_h3r{C.H3_RES}.npz"
    if path.exists():
        return np.load(path)["cell"]
    inside = _burn(fetch.county(name).to_crs(C.CRS), prof).astype(bool)
    rows, cols = np.nonzero(inside)
    xs, ys = rasterio.transform.xy(prof["transform"], rows, cols)
    lon, lat = Transformer.from_crs(C.CRS, 4326, always_xy=True).transform(np.asarray(xs), np.asarray(ys))
    ids = np.fromiter((h3.str_to_int(h3.latlng_to_cell(a, b, C.H3_RES)) for a, b in zip(lat, lon)),
                      dtype="uint64", count=len(lat))
    cell = np.zeros(inside.shape, dtype="uint64")
    cell[rows, cols] = ids
    np.savez_compressed(path, cell=cell)
    return cell


def county_cells(name, force=False):
    path = terrain.out_dir(name) / f"cells_h3r{C.H3_RES}.parquet"
    if path.exists() and not force:
        return pd.read_parquet(path)
    terrain.build(name)
    print(f"  {name}: H3 aggregation")
    with rasterio.open(fetch.dem(name)) as src:
        prof, z = src.profile, src.read(1)
    cell = pixel_index(name, prof)
    m = cell > 0
    df = pd.DataFrame({"h3": cell[m], "elev": z[m]})
    for n in terrain.LAYERS:
        with rasterio.open(terrain.out_dir(name) / f"{n}.tif") as src:
            df[n] = src.read(1)[m]

    units = geology_units()
    geo = fetch.geology().to_crs(C.CRS)
    for col in sorted(set(units.values())):
        names = [n for n, c in units.items() if c == col]
        df[col] = _burn(geo[geo.NAME.isin(names)], prof)[m]
    with rasterio.open(fetch.nlcd(name)) as src:
        lc = src.read(1)[m]
    for k, codes in NLCD_GROUPS.items():
        df[f"lc_{k}"] = np.isin(lc, codes).astype("uint8")
    df["steep"] = (df.slope > 20).astype("uint8")

    frac_cols = [*sorted(set(units.values())), *[f"lc_{k}" for k in NLCD_GROUPS]]
    g = df.groupby("h3", sort=False)
    out = g.agg(
        n_px=("elev", "size"), elev=("elev", "mean"),
        slope_mean=("slope", "mean"), slope_max=("slope", "max"), slope_std=("slope", "std"),
        frac_steep=("steep", "mean"), northness=("northness", "mean"), eastness=("eastness", "mean"),
        profile_curv=("profile_curv", "mean"), plan_curv=("plan_curv", "mean"),
        profile_curv_min=("profile_curv", "min"), plan_curv_min=("plan_curv", "min"),
        tpi_50m=("tpi_50m", "mean"), tpi_300m=("tpi_300m", "mean"),
        relief_250m=("relief_250m", "mean"), roughness=("roughness", "mean"),
        twi_mean=("twi", "mean"), twi_max=("twi", "max"),
        hand=("hand", "mean"), dist_channel=("dist_channel", "min"),
        **{c: (c, "mean") for c in frac_cols},
    )
    out["slope_p90"] = g["slope"].quantile(0.9)
    out["county"] = name
    out.index = out.index.astype("uint64")
    out.astype({c: "float32" for c in out.columns if out[c].dtype == "float64"}).to_parquet(path)
    return out


def point_cells(gdf):
    return np.array([h3.str_to_int(h3.latlng_to_cell(p.y, p.x, C.H3_RES)) for p in gdf.geometry], dtype="uint64")


def build(force=False):
    if CELLS.exists() and not force:
        return pd.read_parquet(CELLS)
    print("Building regional H3 cell table")
    parts = [county_cells(n, force=force) for n in C.COUNTIES]
    cells = pd.concat(parts)
    # Hexagons on a county line appear once per county; keep the larger piece.
    cells = cells.sort_values("n_px", ascending=False)
    cells = cells[~cells.index.duplicated(keep="first")]
    cells = cells[cells.n_px >= 50].copy()
    geo_cols = [c for c in cells.columns if c.startswith("geo_")]
    cells[geo_cols] = cells[geo_cols].fillna(0)  # a unit absent from a county is simply 0 there

    inv = fetch.irise()
    inv["h3"] = point_cells(inv)
    for grp in LABEL_GROUPS:
        counts = inv.loc[inv.group == grp, "h3"].value_counts()
        cells[f"n_{grp}"] = counts.reindex(cells.index, fill_value=0).astype("int32")
    cells["block"] = [h3.str_to_int(h3.cell_to_parent(h3.int_to_str(int(c)), C.H3_BLOCK_RES)) for c in cells.index]
    cells.to_parquet(CELLS)
    summary = cells.groupby("county").agg(cells=("n_px", "size"), usgs=("n_usgs_1970s", lambda s: (s > 0).sum()),
                                          modern=("n_modern", lambda s: (s > 0).sum()))
    print(summary.to_string())
    return cells
