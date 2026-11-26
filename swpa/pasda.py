"""Extra predictors and test records from PASDA (Pennsylvania Spatial Data Access).

Features, aggregated per H3 cell on each county's 10 m grid:
  mining  - DEP digitized underground-mined areas, longwall panels, historic underground permits
  wells   - DEP oil & gas well density (all wells, unconventional wells)
  roads   - PennDOT state + local roads: distance and road share (road cuts and fills)
  regolith- DCNR bedrock-surface model -> depth to bedrock
  soils   - NRCS SSURGO county surveys: clay, shrink-swell, Ksat, hydrologic group, soil-slip potential
Test records (Allegheny): County Public Works landslides (2025) and FEMA 2018 individual/public assistance sites.
"""
import io
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import rasterio
from pyproj import CRS
from rasterio.features import rasterize
from rasterio.warp import Resampling, reproject
from scipy import ndimage, signal

from . import config as C
from . import fetch, grid, terrain

SRC = C.RAW / "pasda"
CACHE = C.DERIVED / "pasda"
CACHE.mkdir(exist_ok=True)
CELLS = C.DERIVED / f"cells_pasda_h3r{C.H3_RES}.parquet"
FT = 0.3048006

MINING = {"mined": "DigitizedMinedAreas2026_09", "longwall": "LongwallMiningPanels2026_09",
          "ug_permit": "PA_Historic_Underground_Mine_Permits202609"}
WELLS = "OilGasLocations_ConventionalUnconventional2026_09"
ROADS = {"state": "PaStateRoads2026_07", "local": "PaLocalRoads2026_07"}
SOIL_ZIPS = ["wss_SSA_PA003_soildb_Allegheny_PA_2003", "wss_SSA_PA005_soildb_Armstrong_PA_2003",
             "wss_SSA_PA007_soildb_Beaver_PA_2003", "wss_SSA_PA019_soildb_Butler_PA_2003",
             "wss_SSA_PA031_soildb_Clarion_PA_2003", "wss_SSA_PA051_soildb_Fayette_PA_2003",
             "wss_SSA_PA063_soildb_Indiana_PA_2003", "wss_SSA_PA065_soildb_Jefferson_PA_2003",
             "wss_SSA_PA073_soildb_Lawrence_PA_2003", "wss_SSA_PA129_soildb_Westmoreland_PA_2003",
             "Greene-Washington_PA_2003"]
WELL_RADIUS_M = 500
LABEL_YEAR = 1975  # the USGS training landslides were mapped from ~1973 air photos
DIST_CAP_M = 2000


DOWNLOAD = "https://www.pasda.psu.edu/download/"
FILES = {  # local zip stem -> PASDA path
    **{v: f"dep/{v}.zip" for v in MINING.values()}, WELLS: f"dep/{WELLS}.zip",
    ROADS["state"]: f"padot/state/{ROADS['state']}.zip", ROADS["local"]: f"padot/local/{ROADS['local']}.zip",
    "DCNR_BedrockElevation2023": "dcnr/DCNR_BedrockElevation2023.zip",
    "AlleghenyLandSlide_IndividualAssistance": "alleghenycounty/AlleghenyLandSlide_IndividualAssistance.zip",
    "AlleghenyLandSlide_PublicAssistance": "alleghenycounty/AlleghenyLandSlide_PublicAssistance.zip",
    **{z: f"soils/{z}_[2024-09-04].zip" for z in SOIL_ZIPS if z.startswith("wss_")},
    "Greene-Washington_PA_2003": "soils/Greene-Washington_PA_2003_[2024-09-05].zip",
}
COUNTY_PW_LANDSLIDES = ("https://mapservices.pasda.psu.edu/server/rest/services/pasda/AlleghenyCounty/MapServer/38")


def download():
    """Fetch PASDA zips (about 600 MB). File names change monthly; update the dates above if a link 404s."""
    SRC.mkdir(exist_ok=True)
    for stem, rel in FILES.items():
        path = SRC / f"{stem}.zip"
        if not path.exists():
            print(f"  downloading {rel} ...")
            with fetch.SESSION.get(DOWNLOAD + rel, stream=True, timeout=1800) as r:
                r.raise_for_status()
                with open(path, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
    pw = SRC / "allegheny_pw_landslides_2025.gpkg"
    if not pw.exists():  # the bulk zip is ~280 MB of attachments; the REST layer is 115 points
        fetch.arcgis_query(COUNTY_PW_LANDSLIDES).to_file(pw)


# ---------------------------------------------------------------- vector inputs, clipped to the study area

def _region_bbox(crs):
    return tuple(fetch.counties().to_crs(crs).buffer(C.BUFFER_M).total_bounds)


def _read_zip_shp(stem, columns=None, where=None):
    path = f"zip://{SRC / (stem + '.zip')}"
    info = pyogrio.read_info(path)
    crs = info["crs"]
    if crs is None:  # e.g. the historic-permits custom Albers: take the .prj directly
        with zipfile.ZipFile(SRC / f"{stem}.zip") as z:
            crs = CRS.from_wkt(z.read(f"{stem}.prj").decode())
    g = pyogrio.read_dataframe(path, columns=columns or [], where=where, bbox=_region_bbox(crs))
    g = g.set_crs(crs, allow_override=True)
    return g[g.geometry.notna()].to_crs(C.CRS)


def _cached(name, fn):
    path = CACHE / f"{name}.gpkg"
    if not path.exists():
        print(f"  preparing {name} ...")
        fn().to_file(path)
    return gpd.read_file(path)


def mining_layers():
    out = {}
    for key, stem in MINING.items():
        cols = ["YEAR_COMPL"] if key == "longwall" else []
        out[key] = _cached(key, lambda s=stem, c=cols: _read_zip_shp(s, columns=c)[c + ["geometry"]].assign(
            geometry=lambda d: d.geometry.make_valid()))
    return out


def wells():
    return _cached("wells", lambda: _read_zip_shp(WELLS, columns=["UNCONVENTI", "WELL_STATU", "SPUD_DATE"]).query(
        "WELL_STATU not in ['Proposed But Never Materialized', 'Operator Reported Not Drilled']"))


def roads():
    return {k: _cached(f"roads_{k}", lambda s=s: _read_zip_shp(s)[["geometry"]]) for k, s in ROADS.items()}


# ---------------------------------------------------------------- SSURGO

def _ssurgo_table(z, prefix, table, cols):
    names = pd.read_csv(io.BytesIO(z.read(f"{prefix}tabular/mstabcol.txt")), sep="|", header=None,
                        usecols=[0, 2], names=["table", "col"])
    header = names.loc[names.table == table, "col"].tolist()
    df = pd.read_csv(io.BytesIO(z.read(f"{prefix}tabular/{ {'component': 'comp'}.get(table, table)}.txt")),
                     sep="|", header=None, names=header, usecols=cols, low_memory=False)
    return df


def soils():
    """Map-unit polygons with numeric attributes (component-weighted where needed)."""
    path = CACHE / "soils.gpkg"
    if path.exists():
        return gpd.read_file(path)
    print("  preparing SSURGO soils ...")
    polys, attrs = [], []
    for stem in SOIL_ZIPS:
        with zipfile.ZipFile(SRC / f"{stem}.zip") as z:
            names = z.namelist()
            shp = next(n for n in names if "/spatial/soilmu_a_" in n and n.endswith(".shp"))
            prefix = shp.split("spatial/")[0]
            polys.append(gpd.read_file(f"zip://{SRC / (stem + '.zip')}!{shp}")[["MUKEY", "geometry"]].to_crs(C.CRS))
            mu = _ssurgo_table(z, prefix, "muaggatt", ["mukey", "brockdepmin", "wtdepannmin", "hydgrpdcd", "drclassdcd"])
            comp = _ssurgo_table(z, prefix, "component", ["mukey", "cokey", "comppct_r", "soilslippot"])
            hz = _ssurgo_table(z, prefix, "chorizon", ["cokey", "hzdept_r", "hzdepb_r", "claytotal_r", "ksat_r", "lep_r"])
        # Horizon properties averaged over 0-100 cm, then weighted by component percentage.
        hz = hz.dropna(subset=["hzdept_r", "hzdepb_r"])
        hz["w"] = (hz.hzdepb_r.clip(upper=100) - hz.hzdept_r.clip(upper=100)).clip(lower=0)
        hz = hz[hz.w > 0]
        prop = hz.groupby("cokey").apply(lambda d: pd.Series(
            {c: np.average(d[c], weights=d.w) if d[c].notna().any() else np.nan
             for c in ["claytotal_r", "ksat_r", "lep_r"]} if d[["claytotal_r"]].notna().any().any() else
            {c: np.nan for c in ["claytotal_r", "ksat_r", "lep_r"]}), include_groups=False)
        comp = comp.merge(prop, left_on="cokey", right_index=True, how="left")
        comp["slip_high"] = comp.soilslippot.eq("High").astype(float)
        comp["w"] = comp.comppct_r.fillna(0)

        def wavg(d, c):
            m = d[c].notna() & (d.w > 0)
            return np.average(d.loc[m, c], weights=d.loc[m, "w"]) if m.any() else np.nan
        agg = comp.groupby("mukey").apply(lambda d: pd.Series(
            {c: wavg(d, c) for c in ["claytotal_r", "ksat_r", "lep_r", "slip_high"]}), include_groups=False)
        mu = mu.merge(agg, left_on="mukey", right_index=True, how="left")
        mu["hydgrp"] = mu.hydgrpdcd.astype(str).str[0].map({"A": 1, "B": 2, "C": 3, "D": 4})
        mu["drainage"] = mu.drclassdcd.map({"Excessively drained": 1, "Somewhat excessively drained": 2,
                                            "Well drained": 3, "Moderately well drained": 4,
                                            "Somewhat poorly drained": 5, "Poorly drained": 6,
                                            "Very poorly drained": 7})
        attrs.append(mu[["mukey", "brockdepmin", "wtdepannmin", "hydgrp", "drainage",
                         "claytotal_r", "ksat_r", "lep_r", "slip_high"]])
    g = pd.concat(polys, ignore_index=True)
    a = pd.concat(attrs).drop_duplicates("mukey")
    g["MUKEY"] = g.MUKEY.astype("int64")
    g = g.merge(a, left_on="MUKEY", right_on="mukey", how="left").drop(columns="mukey")
    g.to_file(path)
    return g


SOIL_COLS = {"brockdepmin": "soil_bedrock_cm", "wtdepannmin": "soil_watertable_cm", "hydgrp": "soil_hydgrp",
             "drainage": "soil_drainage", "claytotal_r": "soil_clay", "ksat_r": "soil_ksat",
             "lep_r": "soil_shrinkswell", "slip_high": "soil_slip_high"}


# ---------------------------------------------------------------- per-county rasterization and aggregation

def _burn(geoms, prof, all_touched=False, values=None, dtype="uint8"):
    shape = (prof["height"], prof["width"])
    if len(geoms) == 0:
        return np.zeros(shape, dtype=dtype)
    shapes = geoms if values is None else zip(geoms, values)
    return rasterize(shapes, out_shape=shape, transform=prof["transform"], fill=0,
                     default_value=1, all_touched=all_touched, dtype=dtype)


def _clip(gdf, prof):
    t = prof["transform"]
    xmin, ymax = t.c, t.f
    xmax, ymin = xmin + t.a * prof["width"], ymax + t.e * prof["height"]
    return gdf.cx[xmin:xmax, ymin:ymax].geometry


def _dist(mask):
    if not mask.any():
        return np.full(mask.shape, DIST_CAP_M, dtype="float32")
    return np.minimum(ndimage.distance_transform_edt(~mask) * C.RES, DIST_CAP_M).astype("float32")


def _density(points, prof, radius_m=WELL_RADIUS_M):
    """Points per km2 within a radius, as a 10 m raster."""
    counts = np.zeros((prof["height"], prof["width"]), dtype="float32")
    if len(points):
        inv = ~prof["transform"]
        cols, rows = inv * (points.x.values, points.y.values)
        rows, cols = rows.astype(int), cols.astype(int)
        ok = (rows >= 0) & (rows < counts.shape[0]) & (cols >= 0) & (cols < counts.shape[1])
        np.add.at(counts, (rows[ok], cols[ok]), 1)
    r = int(radius_m / C.RES)
    y, x = np.ogrid[-r:r + 1, -r:r + 1]
    k = ((x * x + y * y) <= r * r).astype("float32")
    area_km2 = k.sum() * C.RES**2 / 1e6
    return np.maximum(signal.fftconvolve(counts, k, mode="same"), 0) / area_km2


def county_features(name, force=False):
    path = terrain.out_dir(name) / f"cells_pasda_h3r{C.H3_RES}.parquet"
    if path.exists() and not force:
        return pd.read_parquet(path)
    print(f"  {name}: PASDA features")
    with rasterio.open(fetch.dem(name)) as src:
        prof, z = src.profile, src.read(1).astype("float32")
    cell = grid.pixel_index(name, prof)
    m = cell > 0
    df = pd.DataFrame({"h3": cell[m]})

    mines = mining_layers()
    mined = _burn(_clip(mines["mined"], prof), prof).astype(bool)
    df["mined"] = mined[m]
    df["dist_mined"] = _dist(mined)[m]
    lw = mines["longwall"]
    df["longwall"] = _burn(_clip(lw, prof), prof)[m]
    # The labels are 1970s slides, so the model may only use mining that existed by then.
    old_lw = lw[pd.to_numeric(lw.YEAR_COMPL, errors="coerce").between(1800, LABEL_YEAR)]
    df["longwall_pre1976"] = _burn(_clip(old_lw, prof), prof)[m]
    df["ug_permit"] = _burn(_clip(mines["ug_permit"], prof), prof)[m]

    w = wells()
    pts = w.geometry
    df["well_density"] = _density(pts, prof)[m]
    spud = pd.to_datetime(w.SPUD_DATE, errors="coerce").dt.year
    df["well_density_pre1976"] = _density(pts[spud.isna() | (spud <= LABEL_YEAR)], prof)[m]
    df["unconv_density"] = _density(pts[w.UNCONVENTI == "Y"], prof, radius_m=1000)[m]

    rd = roads()
    state = _burn(_clip(rd["state"], prof), prof, all_touched=True).astype(bool)
    local = _burn(_clip(rd["local"], prof), prof, all_touched=True).astype(bool)
    df["road"] = (state | local)[m]
    df["dist_road"] = _dist(state | local)[m]
    df["dist_state_road"] = _dist(state)[m]

    with rasterio.open(f"zip://{SRC / 'DCNR_BedrockElevation2023.zip'}!DCNR_BedrockElevation2023.tif") as bsrc:
        bed = np.full(z.shape, np.nan, dtype="float32")
        reproject(rasterio.band(bsrc, 1), bed, dst_transform=prof["transform"], dst_crs=prof["crs"],
                  src_nodata=bsrc.nodata, dst_nodata=np.nan, resampling=Resampling.bilinear)
    df["regolith_m"] = np.clip(z - bed * FT, 0, None)[m]

    s = soils()
    sub = s.loc[_clip(s, prof).index]
    idx = _burn(sub.geometry.values, prof, values=np.arange(1, len(sub) + 1), dtype="int32")
    lut = sub[list(SOIL_COLS)].rename(columns=SOIL_COLS).reset_index(drop=True)
    # SSURGO leaves these blank when bedrock / the water table is deeper than 200 cm.
    lut[["soil_bedrock_cm", "soil_watertable_cm"]] = lut[["soil_bedrock_cm", "soil_watertable_cm"]].fillna(250)
    pix = idx[m]
    for col in lut.columns:
        vals = np.concatenate([[np.nan], lut[col].values.astype("float32")])
        df[col] = vals[pix]

    g = df.groupby("h3", sort=False)
    means = [c for c in df.columns if c not in ("h3", "dist_mined", "dist_road", "dist_state_road")]
    out = g[means].mean()
    for c in ("dist_mined", "dist_road", "dist_state_road"):
        out[c] = g[c].min()
    out.index = out.index.astype("uint64")
    out = out.astype("float32")
    out.to_parquet(path)
    return out


# ---------------------------------------------------------------- extra Allegheny test records

def allegheny_test_points():
    """County Public Works landslides (2025) and FEMA 2018 disaster-assistance landslide sites."""
    parts = [gpd.read_file(SRC / "allegheny_pw_landslides_2025.gpkg")[["geometry"]].assign(source="County PW 2025")]
    for stem, label in [("AlleghenyLandSlide_IndividualAssistance", "FEMA IA 2018"),
                        ("AlleghenyLandSlide_PublicAssistance", "FEMA PA 2018")]:
        with zipfile.ZipFile(SRC / f"{stem}.zip") as zf:
            gdb = next(n.split(".gdb/")[0] + ".gdb" for n in zf.namelist() if ".gdb/" in n)
        g = gpd.read_file(f"zip://{SRC / (stem + '.zip')}!{gdb}")
        g = g.set_geometry(g.geometry.representative_point() if g.geom_type.iloc[0] != "Point" else g.geometry)
        parts.append(g[["geometry"]].to_crs(4326).assign(source=label))
    return pd.concat([p.to_crs(4326) for p in parts], ignore_index=True)


def build(force=False):
    if CELLS.exists() and not force:
        return pd.read_parquet(CELLS)
    print("Building PASDA features")
    cells = grid.build()
    # Border hexagons: take features from the same county piece the terrain table kept.
    parts = [county_features(n, force=force).assign(county=n) for n in C.COUNTIES]
    feats = pd.concat(parts).rename_axis("h3").reset_index()
    keep = cells[["county"]].rename_axis("h3").reset_index()
    feats = keep.merge(feats, on=["h3", "county"], how="left").set_index("h3").drop(columns="county")
    tp = allegheny_test_points()
    tp["h3"] = grid.point_cells(tp)
    for src_name in tp.source.unique():
        col = "n_" + src_name.lower().replace(" ", "_")
        feats[col] = tp.loc[tp.source == src_name, "h3"].value_counts().reindex(cells.index, fill_value=0).astype("int32")
    feats.to_parquet(CELLS)
    print(tp.source.value_counts().to_string())
    return feats
