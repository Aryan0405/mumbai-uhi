"""Phase 2 build composites: load (rasterio, signed per batch), mosaic, mask,
indices, median composite, write GeoTIFFs (EPSG:32643, 30 m), checks.
Loading uses rasterio directly because stackstac 0.5.0 is incompatible with
numpy 2.x (np.can_cast).
Validity uses src/utils.build_date_mosaic: each scene's bands are masked with
that scene's own validity (finite lwir AND QA bits 0-4 clear) BEFORE
nanmedian; date validity = valid in at least one scene.
Output directory is configurable (default config.DIR_COMPOSITES).
"""
import argparse
import os
import time
import tracemalloc
from collections import defaultdict
from datetime import datetime

import numpy as np
import planetary_computer as pc
import rasterio
import requests
from pystac_client import Client
from rasterio.warp import reproject, Resampling, transform
from rasterio.transform import from_origin
import rasterio.features

from utils import build_date_mosaic

import config

LOGS = config.DIR_LOGS
os.makedirs(LOGS, exist_ok=True)

SEARCH_BOX = __import__("shapely.geometry", fromlist=["box"]).box(
    config.BOX["lon_min"], config.BOX["lat_min"],
    config.BOX["lon_max"], config.BOX["lat_max"])

# Target grid in EPSG:32643 from the lon/lat box.
_CORNERS_X, _CORNERS_Y = transform(
    config.CRS_LONLAT, config.CRS_METRIC,
    [config.BOX["lon_min"], config.BOX["lon_max"]],
    [config.BOX["lat_min"], config.BOX["lat_max"]])
MINX, MAXX = min(_CORNERS_X), max(_CORNERS_X)
MINY, MAXY = min(_CORNERS_Y), max(_CORNERS_Y)
RES = 30.0
TARGET_TRANSFORM = from_origin(MINX, MAXY, RES, RES)
TARGET_WIDTH = int(round((MAXX - MINX) / RES))
TARGET_HEIGHT = int(round((MAXY - MINY) / RES))
print(f"Target grid: {TARGET_WIDTH}x{TARGET_HEIGHT} @30m EPSG:32643")

# Dissolved BMC mask rasterized to the target grid (centre-point assignment).
import geopandas as gpd
from rasterio.features import rasterize as rio_rasterize
from shapely.geometry import mapping as shp_mapping
_bmc = gpd.read_file(config.BMC_GEOJSON).dissolve().to_crs(config.CRS_METRIC)
BMC_MASK = rio_rasterize(
    [shp_mapping(g) for g in _bmc.geometry],
    out_shape=(TARGET_HEIGHT, TARGET_WIDTH),
    transform=TARGET_TRANSFORM, fill=0, default_value=1, dtype="uint8",
).astype(bool)
print(f"BMC mask pixels: {int(BMC_MASK.sum())} of {BMC_MASK.size}")


def search_window_b():
    catalog = Client.open(config.CATALOG_URL)
    by_date = defaultdict(list)
    for year, (start, end) in config.WINDOW_B.items():
        search = catalog.search(
            collections=[config.COLLECTION],
            intersects=SEARCH_BOX,
            datetime=f"{start}/{end}",
            query={
                "eo:cloud_cover": {"lt": config.CLOUD_MAX},
                "platform": {"in": list(config.PLATFORMS)},
            },
            limit=None,
        )
        for it in search.item_collection():
            d = it.properties["datetime"][:10]
            by_date[d].append(it)
    return dict(by_date)


def read_scale_offset(items):
    so = {}
    it0 = items[0]
    for asset_name in config.ASSETS:
        bands = it0.assets[asset_name].extra_fields.get("raster:bands")
        if bands:
            so[asset_name] = {"scale": bands[0].get("scale", 1.0),
                              "offset": bands[0].get("offset", 0.0)}
        else:
            so[asset_name] = {"scale": 1.0, "offset": 0.0}
    return so


def load_asset(it, asset_name):
    """Open signed asset, reproject to target grid, return float32 array.
    Reuses a cached reprojected array from data/landsat/cache/ when present,
    otherwise downloads from the signed URL and caches it.
    Returns (array, bytes_est). bytes_est is the signed asset's Content-Length
    when downloaded, 0 when served from cache.
    """
    cache_path = os.path.join("data", "landsat", "cache", f"{it.id}_{asset_name}.npy")
    if os.path.exists(cache_path):
        return np.load(cache_path), 0
    href = pc.sign(it.assets[asset_name].href)
    try:
        r = requests.head(href, timeout=20)
        bytes_est = int(r.headers.get("Content-Length", 0) or 0)
    except Exception:
        bytes_est = 0
    with rasterio.open(href) as src:
        dst = np.empty((TARGET_HEIGHT, TARGET_WIDTH), dtype="float32")
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=TARGET_TRANSFORM,
            dst_crs=config.CRS_METRIC,
            resampling=Resampling.nearest,
            src_nodata=src.nodata,
            dst_nodata=np.nan,
        )
    np.save(cache_path, dst)
    return dst, bytes_est


def load_date(date, items, outdir=None):
    """Load one date using src/utils.build_date_mosaic.

    For each scene: load all bands, mask EVERY band with that scene's own
    validity (finite lwir AND QA bits 0-4 clear) setting masked pixels to NaN.
    Mosaic scenes with nanmedian over the masked arrays. Date validity =
    valid in at least one scene. Scale/offset applied by caller after masking.
    `outdir` is accepted for interface compatibility but writing is handled
    by main().
    """
    so = read_scale_offset(items)
    scenes = []
    bytes_est = 0
    for it in items:
        scene = {}
        for asset_name in config.ASSETS:
            scene[asset_name], b = load_asset(it, asset_name)
            bytes_est += b
        scenes.append(scene)
    mosaic, date_validity = build_date_mosaic(scenes)
    band_names = [b for b in config.ASSETS if b != "qa_pixel"]
    out = {}
    for bname in band_names:
        s = so[bname]["scale"]; o = so[bname]["offset"]
        out[bname] = mosaic[bname] * s + o
    valid_frac = float(np.mean(date_validity))
    valid_frac_bmc = (float(np.mean(date_validity & BMC_MASK))
                      if BMC_MASK.any() else float("nan"))
    arr = np.stack([out[b] for b in band_names], axis=0)  # (band, y, x)
    return arr, band_names, valid_frac, valid_frac_bmc, bytes_est


def main(outdir=None):
    if outdir is None:
        outdir = config.DIR_COMPOSITES
    os.makedirs(outdir, exist_ok=True)
    by_date = search_window_b()
    dates = sorted(by_date)
    print(f"Unique dates: {len(dates)}")
    # ---- Pilot: 2 dates ----
    tracemalloc.start()
    t0 = time.time()
    pilot_arrays = []
    for d in dates[:2]:
        arr, bands, vf, vf_bmc, bts = load_date(d, by_date[d], outdir)
        pilot_arrays.append(arr)
        print(f"Pilot {d}: valid_frac_box={vf:.4f}, valid_frac_bmc={vf_bmc:.4f}, bytes_est={bts}")
    t1 = time.time()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"PILOT 2 dates: wall_time={t1-t0:.1f}s, peak_memory={peak/1e6:.1f} MB")
    # ---- All dates ----
    arrays = []
    vf_table = []
    for d in dates:
        arr, bands, vf, vf_bmc, bts = load_date(d, by_date[d], outdir)
        arrays.append(arr)
        vf_table.append((d, vf, vf_bmc))
    stack_all = np.stack(arrays, axis=0)  # (date, band, y, x)
    composite = np.nanmedian(stack_all, axis=0)  # (band, y, x)
    vcount = np.nansum(~np.isnan(stack_all), axis=0)[0]  # (y, x)
    print(f"Composite shape: {composite.shape}, bands: {bands}")
    # ---- LST checks ----
    li = bands.index("lwir11")
    lst = composite[li] - 273.15
    finite = lst[~np.isnan(lst)]
    p01, p999 = np.percentile(finite, [config.LST_PERCENTILES[0],
                                       config.LST_PERCENTILES[1]])
    mx = float(finite.max())
    n_hot = int((finite > config.LST_HOT_THRESHOLD_C).sum())
    print(f"LST composite: 0.1th={p01:.2f} C, 99.9th={p999:.2f} C, max={mx:.2f} C, "
          f"count_above_50C={n_hot}, valid={finite.size}")
    # ---- Write GeoTIFFs ----
    profile = {
        "driver": "GTiff", "dtype": "float32", "width": TARGET_WIDTH,
        "height": TARGET_HEIGHT, "count": len(bands),
        "crs": config.CRS_METRIC, "transform": TARGET_TRANSFORM, "nodata": np.nan,
    }
    for i, bname in enumerate(bands):
        path = os.path.join(outdir, f"{bname}.tif")
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(composite[i].astype("float32"), 1)
            dst.set_band_description(1, bname)
    vprofile = dict(profile); vprofile["count"] = 1
    with rasterio.open(os.path.join(outdir, "valid_count.tif"),
                       "w", **vprofile) as dst:
        dst.write(vcount.astype("float32"), 1)
    print(f"Wrote {len(bands)} composite GeoTIFFs + valid_count to {outdir}")
    # NDVI band range check (nir band values are reflectance)
    ni = bands.index("nir08")
    print(f"NIR band min={float(np.nanmin(composite[ni])):.3f} "
          f"max={float(np.nanmax(composite[ni])):.3f}")
    return composite, bands, vcount


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default=config.DIR_COMPOSITES,
                        help="output directory for GeoTIFFs")
    args = parser.parse_args()
    main(args.outdir)
