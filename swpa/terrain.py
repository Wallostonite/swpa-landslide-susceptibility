"""Terrain derivatives from a county's 10 m DEM, written as float32 GeoTIFFs in data/derived/<county>/."""
import numpy as np
import rasterio
from scipy import ndimage, signal

from . import config as C
from .fetch import dem

LAYERS = ["slope", "northness", "eastness", "profile_curv", "plan_curv", "tpi_50m", "tpi_300m",
          "relief_250m", "roughness", "twi", "hand", "dist_channel"]
CHANNEL_AREA_M2 = 250_000  # contributing area that defines a channel (0.25 km2)


def out_dir(name):
    d = C.DERIVED / name.lower()
    d.mkdir(exist_ok=True)
    return d


def _write(path, arr, prof):
    with rasterio.open(path, "w", **(prof | dict(dtype="float32", nodata=np.nan))) as dst:
        dst.write(arr.astype("float32"), 1)


def _circle(radius_px):
    y, x = np.ogrid[-radius_px:radius_px + 1, -radius_px:radius_px + 1]
    return (x * x + y * y) <= radius_px * radius_px


def _tpi(z, radius_px):
    """Topographic position index: elevation minus the mean elevation of a surrounding disk."""
    k = _circle(radius_px).astype("float64")
    k /= k.sum()
    zp = np.pad(z, radius_px, mode="edge")
    return z - signal.fftconvolve(zp, k, mode="valid")


def local_derivatives(z, r):
    """Slope, aspect components and Zevenbergen-Thorne curvatures (1/100 m, positive = convex)."""
    zp = np.pad(z, 1, mode="edge")
    z1, z2, z3 = zp[:-2, :-2], zp[:-2, 1:-1], zp[:-2, 2:]
    z4, z5, z6 = zp[1:-1, :-2], zp[1:-1, 1:-1], zp[1:-1, 2:]
    z7, z8, z9 = zp[2:, :-2], zp[2:, 1:-1], zp[2:, 2:]
    D = ((z4 + z6) / 2 - z5) / r**2
    E = ((z2 + z8) / 2 - z5) / r**2
    F = (-z1 + z3 + z7 - z9) / (4 * r**2)
    G = (z6 - z4) / (2 * r)   # dz/dx, east positive
    H = (z2 - z8) / (2 * r)   # dz/dy, north positive (row 0 is north)
    p = G**2 + H**2
    slope = np.degrees(np.arctan(np.sqrt(p)))
    aspect = np.arctan2(-G, -H)  # downslope direction, radians clockwise from north
    with np.errstate(invalid="ignore", divide="ignore"):
        prof = np.where(p > 1e-8, -2 * (D * G**2 + E * H**2 + F * G * H) / p, 0.0) * 100
        plan = np.where(p > 1e-8, 2 * (D * H**2 + E * G**2 - F * G * H) / p, 0.0) * 100
    return slope, np.cos(aspect), np.sin(aspect), prof, plan


def hydrology(name):
    """Contributing area, height above nearest drainage and distance to channel via pysheds D8.

    Flow is routed within the county buffer only, so drainage area is truncated for large rivers
    entering from outside. That matters little for hillslope-scale TWI and HAND.
    """
    from pysheds.grid import Grid
    from pysheds.sview import Raster

    grid = Grid.from_raster(str(dem(name)))
    raw = grid.read_raster(str(dem(name)))
    filled = grid.resolve_flats(grid.fill_depressions(grid.fill_pits(raw)))
    fdir = grid.flowdir(filled)
    acc = grid.accumulation(fdir)
    area = np.asarray(acc, dtype="float64") * C.RES**2
    channels = area >= CHANNEL_AREA_M2
    hand = np.asarray(grid.compute_hand(fdir, raw, Raster(channels, viewfinder=acc.viewfinder)),
                      dtype="float64")
    dist = ndimage.distance_transform_edt(~channels) * C.RES
    return area, hand, dist


def build(name, force=False):
    d = out_dir(name)
    if not force and all((d / f"{n}.tif").exists() for n in LAYERS):
        return
    print(f"  {name}: terrain derivatives")
    with rasterio.open(dem(name)) as src:
        z = src.read(1).astype("float64")
        prof = src.profile
    z[z == -9999] = np.nan
    if np.isnan(z).any():  # fill rare voids so window operations stay finite
        idx = ndimage.distance_transform_edt(np.isnan(z), return_distances=False, return_indices=True)
        z = z[tuple(idx)]
    slope, north, east, pc, plc = local_derivatives(z, C.RES)
    for n, arr in [("slope", slope), ("northness", north), ("eastness", east),
                   ("profile_curv", pc), ("plan_curv", plc)]:
        _write(d / f"{n}.tif", arr, prof)
    _write(d / "tpi_50m.tif", _tpi(z, 5), prof)
    _write(d / "tpi_300m.tif", _tpi(z, 30), prof)
    fp = _circle(12)
    _write(d / "relief_250m.tif", ndimage.maximum_filter(z, footprint=fp) - ndimage.minimum_filter(z, footprint=fp), prof)
    # roughness = std. dev. of slope in a 50 m window
    m, m2 = ndimage.uniform_filter(slope, 5), ndimage.uniform_filter(slope**2, 5)
    _write(d / "roughness.tif", np.sqrt(np.maximum(m2 - m**2, 0)), prof)
    del m, m2, pc, plc, north, east
    area, hand, dist = hydrology(name)
    tan_b = np.maximum(np.tan(np.radians(slope)), 0.001)
    _write(d / "twi.tif", np.log(area / C.RES / tan_b), prof)
    _write(d / "hand.tif", hand, prof)
    _write(d / "dist_channel.tif", dist, prof)
