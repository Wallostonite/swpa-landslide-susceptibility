"""Map and chart outputs for the regional model."""
import json

import folium
import h3
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.colors import BoundaryNorm, LightSource, ListedColormap
from rasterio.transform import from_origin

from . import config as C
from . import fetch
from .grid import pixel_index
from .model import PRIMARY

# Sequential blue ramp (light = low risk, dark = high), one step per risk-percentile band.
RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
BANDS = [0, 0.5, 0.7, 0.8, 0.9, 0.95, 0.98, 1.0]
BAND_LABELS = ["< 50th", "50-70th", "70-80th", "80-90th", "90-95th", "95-98th", "top 2%"]
SERIES = {"Spatial block CV": "#2a78d6", "Leave-one-county-out": "#eb6834", "Trained on Allegheny only": "#1baf7a"}
INK, MUTED, SURFACE, GRID = "#1f1f1e", "#6b6a66", "#ffffff", "#e6e5e1"
MOSAIC_RES = 50  # m, for the regional PNG and GeoTIFF


def rasters(risk):
    """Per-county 10 m GeoTIFFs (uint8 percentile, 0 = nodata) plus a 50 m regional mosaic for plotting."""
    lut = pd.Series(np.clip(np.round(risk.risk_pct.values * 100), 1, 100).astype("uint8"),
                    index=risk.index.astype("uint64"))
    xmin, ymin, xmax, ymax = fetch.counties().to_crs(C.CRS).total_bounds
    xmin, ymax = np.floor(xmin / MOSAIC_RES) * MOSAIC_RES, np.ceil(ymax / MOSAIC_RES) * MOSAIC_RES
    W, H = int(np.ceil((xmax - xmin) / MOSAIC_RES)), int(np.ceil((ymax - ymin) / MOSAIC_RES))
    mosaic, relief = np.zeros((H, W), "uint8"), np.full((H, W), np.nan, "float32")
    k = int(MOSAIC_RES / C.RES)
    for name in C.COUNTIES:
        with rasterio.open(fetch.dem(name)) as src:
            prof, z = src.profile, src.read(1)
        cell = pixel_index(name, prof)
        arr = np.zeros(cell.shape, "uint8")
        m = cell > 0
        arr[m] = lut.reindex(cell[m]).fillna(0).values.astype("uint8")
        with rasterio.open(C.OUT / f"risk_pct_10m_{name.lower()}.tif", "w",
                           **(prof | dict(dtype="uint8", nodata=0, compress="deflate"))) as dst:
            dst.write(arr, 1)
        # Paste a k-strided sample of this county into the mosaic.
        t = prof["transform"]
        c0, r0 = int(round((t.c - xmin) / MOSAIC_RES)), int(round((ymax - t.f) / MOSAIC_RES))
        sub, zs = arr[::k, ::k], z[::k, ::k]
        rr, cc = np.nonzero(sub)
        rr2, cc2 = rr + r0, cc + c0
        ok = (rr2 >= 0) & (rr2 < H) & (cc2 >= 0) & (cc2 < W)
        mosaic[rr2[ok], cc2[ok]] = sub[rr[ok], cc[ok]]
        relief[rr2[ok], cc2[ok]] = zs[rr[ok], cc[ok]]
    transform = from_origin(xmin, ymax, MOSAIC_RES, MOSAIC_RES)
    with rasterio.open(C.OUT / "risk_pct_50m_region.tif", "w", driver="GTiff", height=H, width=W, count=1,
                       dtype="uint8", crs=C.CRS, transform=transform, nodata=0, compress="deflate") as dst:
        dst.write(mosaic, 1)
    return mosaic, relief, (xmin, xmin + W * MOSAIC_RES, ymax - H * MOSAIC_RES, ymax)


def region_map(mosaic, relief, extent):
    cmap, norm = ListedColormap(RAMP), BoundaryNorm(BANDS, len(RAMP))
    pct = np.where(mosaic > 0, mosaic / 100.0, np.nan)
    z = np.nan_to_num(relief, nan=np.nanmean(relief))
    hs = LightSource(azdeg=315, altdeg=45).hillshade(z, vert_exag=3, dx=MOSAIC_RES, dy=MOSAIC_RES)
    fig, ax = plt.subplots(figsize=(11, 12), facecolor=SURFACE)
    ax.imshow(np.where(np.isnan(pct), np.nan, hs), cmap="gray", extent=extent, vmin=0, vmax=1.2)
    ax.imshow(pct, cmap=cmap, norm=norm, extent=extent, alpha=0.8, interpolation="nearest")
    cty = fetch.counties().to_crs(C.CRS)
    cty.boundary.plot(ax=ax, color=INK, linewidth=0.6)
    for _, r in cty.iterrows():
        p = r.geometry.representative_point()
        ax.annotate(r.county, (p.x, p.y), ha="center", fontsize=9, color=INK,
                    bbox=dict(boxstyle="round,pad=0.2", fc=SURFACE, ec="none", alpha=0.75))
    ax.set_axis_off()
    ax.set_title("Landslide susceptibility, IRISE study area (12 counties, SW Pennsylvania)",
                 loc="left", fontsize=14, color=INK)
    handles = [plt.Rectangle((0, 0), 1, 1, fc=c, ec="none") for c in RAMP]
    ax.legend(handles[::-1], BAND_LABELS[::-1], title="Risk percentile", loc="lower right",
              frameon=True, facecolor=SURFACE, edgecolor="none", fontsize=9, title_fontsize=10)
    ax.text(0.0, -0.01, "Out-of-fold scores from spatial block CV. Labels: IRISE inventory, USGS 1970s landslides.\n"
            "Terrain: USGS 3DEP 10 m. Geology: DCNR 1:250k. Land cover: NLCD 2021. Mining, wells, roads,\n"
            "regolith and soils: PASDA (DEP, PennDOT, DCNR, NRCS). Rendered at 50 m.",
            transform=ax.transAxes, ha="left", va="top", fontsize=8, color=MUTED)
    fig.savefig(C.OUT / "risk_map_region.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def county_chart(table):
    cols = {"Spatial block CV": f"auc_usgs__cv_{PRIMARY}", "Leave-one-county-out": f"auc_usgs__loco_{PRIMARY}",
            "Trained on Allegheny only": f"auc_usgs__allegheny_only_{PRIMARY}"}
    t = table.sort_values(f"auc_usgs__cv_{PRIMARY}", na_position="first")
    t = t[t[cols["Spatial block CV"]].notna()]
    fig, ax = plt.subplots(figsize=(9, 0.5 * len(t) + 1.5), facecolor=SURFACE)
    y = np.arange(len(t))
    for i, (label, col) in enumerate(cols.items()):
        vals = t[col].values
        if label == "Trained on Allegheny only":
            vals = np.where(t.county.values == "Allegheny", np.nan, vals)  # in-sample there
        ax.scatter(vals, y + (i - 1) * 0.18, s=64, color=SERIES[label], edgecolor=SURFACE, linewidth=2,
                   label=label, zorder=3)
    ax.set_yticks(y, [f"{c}  (n={n:,})" for c, n in zip(t.county, t.usgs_cells)])
    ax.axvline(0.5, color=MUTED, linewidth=1, linestyle=":")
    ax.set_xlabel("ROC-AUC against USGS 1970s landslides in that county", color=MUTED)
    ax.set_title("How well the model transfers between counties", loc="left", color=INK)
    for s in ["top", "right", "left"]:
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=MUTED, length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(loc="lower right", frameon=True, facecolor=SURFACE, edgecolor="none", fontsize=9)
    fig.savefig(C.OUT / "per_county_auc.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def importance_chart(importance, top=15):
    imp = importance.head(top).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 6), facecolor=SURFACE)
    ax.barh(imp.feature, imp.mean_abs_shap, color="#2a78d6", height=0.6)
    ax.set_xlabel("Mean |SHAP| (log-odds)", color=MUTED)
    ax.set_title("What drives the regional model", loc="left", color=INK)
    for s in ["top", "right", "left"]:
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=MUTED, length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    fig.savefig(C.OUT / "feature_importance.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def interactive_map(risk):
    """Folium map at H3 res 8 (90th percentile of child cells), upper 30% only, plus modern IRISE records."""
    parent = [h3.cell_to_parent(h3.int_to_str(int(c)), C.H3_MAP_RES) for c in risk.index]
    agg = risk.assign(parent=parent).groupby("parent").agg(
        risk=("risk_pct", lambda s: s.quantile(0.9)), county=("county", "first"),
        usgs=("n_usgs_1970s", "sum"), modern=("n_modern", "sum"))
    agg = agg[agg.risk >= 0.7]
    feats = []
    for cid, r in agg.iterrows():
        ring = [[lng, lat] for lat, lng in h3.cell_to_boundary(cid)]
        band = int(np.searchsorted(BANDS, r.risk, side="right") - 1)
        feats.append(dict(type="Feature", geometry=dict(type="Polygon", coordinates=[ring + ring[:1]]),
                          properties=dict(county=r.county, risk_pct=round(float(r.risk) * 100, 1),
                                          usgs=int(r.usgs), modern=int(r.modern),
                                          color=RAMP[min(band, len(RAMP) - 1)])))
    m = folium.Map(location=[40.35, -79.85], zoom_start=9, tiles="CartoDB positron")
    folium.GeoJson(dict(type="FeatureCollection", features=feats),
                   style_function=lambda f: dict(fillColor=f["properties"]["color"], color=SURFACE,
                                                 weight=0.2, fillOpacity=0.75),
                   tooltip=folium.GeoJsonTooltip(["county", "risk_pct", "usgs", "modern"],
                                                 aliases=["County", "Risk percentile (p90)", "USGS 1970s slides",
                                                          "Modern records"])).add_to(m)
    folium.GeoJson(json.loads(fetch.counties()[["county", "geometry"]].to_json()),
                   style_function=lambda f: dict(fill=False, color=INK, weight=1)).add_to(m)
    m.save(str(C.OUT / "risk_map_region.html"))


def build(risk, table, importance):
    print("Rendering maps")
    mosaic, relief, extent = rasters(risk)
    region_map(mosaic, relief, extent)
    county_chart(table)
    importance_chart(importance)
    interactive_map(risk)
