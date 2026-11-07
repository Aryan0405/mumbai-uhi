"""Phase 2 build composites: load (rasterio, signed per batch), mosaic, mask,
indices, median composite, write GeoTIFFs (EPSG:32643, 30 m), per-date table,
checks. stackstac is listed in environment.yml but rasterio is used directly
because stackstac 0.5.0 is incompatible with numpy 2.x (np.can_cast).
"""
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

import config

LOGS = config.DIR_LOGS
os.makedirs(config.DIR_COMPOSITES, exist_ok=True)
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
    transform=TARGET_TRANSFORM,
    fill=0, default_value=1, dtype="uint8",
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


def sign_batch(items):
    signed = []
    bytes_est = 0
    for it in items:
        for asset_name in config.ASSETS:
            it.assets[asset_name].href = pc.sign(it.assets[asset_name].href)
            try:
                r = requests.head(it.assets[asset_name].href, timeout=20)
                bytes_est += int(r.headers.get("Content-Length", 0) or 0)
            except Exception:
                pass
        signed.append(it)
    return signed, bytes_est


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
    """Open signed asset, reproject to target grid, return float32 array."""
    with rasterio.open(it.assets[asset_name].href) as src:
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
    return dst


def load_date(date, items):
    signed, bytes_est = sign_batch(items)
    so = read_scale_offset(signed)
    # Mosaic scenes of this date: stack scene arrays, nanmedian over scenes.
    scene_arrays = []
    for it in signed:
        bands = {}
        for asset_name in config.ASSETS:
            bands[asset_name] = load_asset(it, asset_name)
        scene_arrays.append(bands)
    band_names = [b for b in config.ASSETS if b != "qa_pixel"]
    out = {}
    for bname in band_names:
        stack = np.stack([sa[bname] for sa in scene_arrays], axis=0)
        out[bname] = np.nanmedian(stack, axis=0)
    # QA mask from qa_pixel (mosaic scenes: any scene cloudy -> mask)
    qa_stack = np.stack([sa["qa_pixel"] for sa in scene_arrays], axis=0)
    qa_mosaic = np.nanmedian(qa_stack, axis=0)
    valid = np.ones((TARGET_HEIGHT, TARGET_WIDTH), dtype=bool)
    qa_i = np.nan_to_num(qa_mosaic, nan=0).astype(np.uint16)
    valid &= ((qa_i >> config.QA_BIT_FILL) & 1) == 0
    for bit in config.QA_MASK_BITS:
        valid &= ((qa_i >> bit) & 1) == 0
    # lwir11 fill DN==0 -> invalid
    valid &= out["lwir11"] != 0
    # Apply scale/offset
    for bname in band_names:
        s = so[bname]["scale"]; o = so[bname]["offset"]
        out[bname] = out[bname] * s + o
        out[bname] = np.where(valid, out[bname], np.nan)
    valid_frac = float(np.mean(valid))
    valid_frac_bmc = float(np.mean(valid & BMC_MASK)) if BMC_MASK.any() else float("nan")
    arr = np.stack([out[b] for b in band_names], axis=0)  # (band, y, x)
    return arr, band_names, valid_frac, valid_frac_bmc, bytes_est


def main():
    by_date = search_window_b()
    dates = sorted(by_date)
    print(f"Unique dates: {len(dates)}")
    # ---- Pilot: 2 dates ----
    tracemalloc.start()
    t0 = time.time()
    pilot_arrays = []
    for d in dates[:2]:
        arr, bands, vf, vf_bmc, bts = load_date(d, by_date[d])
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
        arr, bands, vf, vf_bmc, bts = load_date(d, by_date[d])
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
        path = os.path.join(config.DIR_COMPOSITES, f"{bname}.tif")
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(composite[i].astype("float32"), 1)
            dst.set_band_description(1, bname)
    vprofile = dict(profile); vprofile["count"] = 1
    with rasterio.open(os.path.join(config.DIR_COMPOSITES, "valid_count.tif"),
                       "w", **vprofile) as dst:
        dst.write(vcount.astype("float32"), 1)
    print(f"Wrote {len(bands)} composite GeoTIFFs + valid_count to {config.DIR_COMPOSITES}")
    # ---- Per-date table ----
    table_path = os.path.join(LOGS, "per_date_valid_fraction.txt")
    with open(table_path, "w") as f:
        f.write("date valid_fraction_box valid_fraction_bmc\n")
        for d, vf, vf_bmc in vf_table:
            f.write(f"{d} {vf:.6f} {vf_bmc:.6f}\n")
    print(f"Per-date table written to {table_path}")
    # NDVI band range check (nir band values are reflectance)
    ni = bands.index("nir08")
    print(f"NIR band min={float(np.nanmin(composite[ni])):.3f} "
          f"max={float(np.nanmax(composite[ni])):.3f}")
    return composite, bands, vcount


if __name__ == "__main__":
    main()
