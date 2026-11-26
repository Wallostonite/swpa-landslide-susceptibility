"""Google/DeepMind AlphaEarth Foundations (AEF) satellite embeddings as per-cell features.

AEF is a foundation model: it compresses a year of multi-sensor satellite data into a 64-dimensional
embedding for every 10 m pixel. The annual embeddings are public COGs on Source Cooperative (CC-BY 4.0,
Google and Google DeepMind); no Earth Engine account is needed.

We read the 2017 layer, the earliest available. Later years could show scars from the 2018 landslides that the
modern test uses. Tiles are read at their 40 m overview (about 9 embedding pixels per H3 res-10 cell) and
averaged per cell after dequantization.
"""
import os

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer

from . import config as C
from . import fetch, grid

YEAR = 2017
OVERVIEW_LEVEL = 1  # 0 = 20 m, 1 = 40 m
N_DIM = 64
COLS = [f"aef_{i:02d}" for i in range(N_DIM)]
RAW = C.RAW / "aef"
CELLS = C.DERIVED / f"cells_aef{YEAR}_h3r{C.H3_RES}.parquet"
INDEX_URL = "https://data.source.coop/tge-labs/aef/v1/annual/aef_index.parquet"
S3_PREFIX = "s3://us-west-2.opendata.source.coop/"
HTTP_PREFIX = "https://data.source.coop/"
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")


def tiles():
    idx = RAW / "aef_index.parquet"
    RAW.mkdir(parents=True, exist_ok=True)
    if not idx.exists():
        idx.write_bytes(fetch._get(INDEX_URL).content)
    i = gpd.read_parquet(idx)
    region = fetch.counties().to_crs(4326).union_all()
    return i[(i.year == YEAR) & i.intersects(region)]


def local_tile(path):
    """Cache the 40 m overview of one tile (int8, 64 bands) as a local GeoTIFF."""
    out = RAW / f"{YEAR}_ovr{OVERVIEW_LEVEL}_{os.path.basename(path)}"
    if out.exists():
        return out
    url = path.replace(S3_PREFIX, HTTP_PREFIX)
    print(f"  reading {os.path.basename(path)} (40 m overview) ...")
    with rasterio.open(url, overview_level=OVERVIEW_LEVEL) as src:
        arr = src.read()
        prof = src.profile | dict(driver="GTiff", height=arr.shape[1], width=arr.shape[2],
                                  transform=src.transform, compress="deflate", tiled=True,
                                  blockxsize=256, blockysize=256)
    with rasterio.open(out, "w", **prof) as dst:
        dst.write(arr)
    return out


def dequantize(q):
    """int8 -> [-1, 1]: (q / 127.5)^2 * sign(q); -128 is nodata."""
    x = q.astype("float32") / 127.5
    return x * np.abs(x)


def build(force=False):
    if CELLS.exists() and not force:
        return pd.read_parquet(CELLS)
    print(f"Building AEF {YEAR} embedding features")
    cells = grid.build()
    wanted = set(cells.index.astype("uint64"))
    sums, counts = {}, {}
    for path in tiles().path:
        with rasterio.open(local_tile(path)) as src:
            q, t, crs = src.read(), src.transform, src.crs
        valid = (q != -128).all(axis=0)
        rows, cols = np.nonzero(valid)
        # Pixel centers from the transform: the files are stored bottom-up (positive y pixel size).
        xs, ys = rasterio.transform.xy(t, rows, cols)
        lon, lat = Transformer.from_crs(crs, 4326, always_xy=True).transform(np.asarray(xs), np.asarray(ys))
        ids = np.fromiter((h3.str_to_int(h3.latlng_to_cell(a, b, C.H3_RES)) for a, b in zip(lat, lon)),
                          dtype="uint64", count=len(lat))
        keep = np.fromiter((i in wanted for i in ids), dtype=bool, count=len(ids))
        if not keep.any():
            continue
        emb = dequantize(q[:, rows[keep], cols[keep]]).T
        df = pd.DataFrame(emb, columns=COLS)
        df["h3"] = ids[keep]
        g = df.groupby("h3")
        s, n = g[COLS].sum(), g.size()
        for k, v in (("s", s), ("n", n)):
            store = sums if k == "s" else counts
            store[len(store)] = v
    s = pd.concat(sums.values()).groupby(level=0).sum()
    n = pd.concat(counts.values()).groupby(level=0).sum()
    out = s.div(n, axis=0).astype("float32")
    out["aef_npx"] = n.astype("int16")
    out.index = out.index.astype("uint64")
    out = out.reindex(cells.index)
    out.to_parquet(CELLS)
    print(f"  {out[COLS[0]].notna().mean():.1%} of cells have embeddings")
    return out
