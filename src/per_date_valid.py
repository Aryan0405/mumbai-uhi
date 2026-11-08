"""Regenerate logs/per_date_valid_fraction.txt using the shared validity
function (src/utils.compute_validity) with UNION of per-scene validity per
date. Columns: date, valid_fraction_box, valid_fraction_bmc,
bmc_pixel_count, footprint_fraction_bmc.

valid_fraction_box   = fraction of box pixels valid for the date (union of
                       per-scene validity).
valid_fraction_bmc   = fraction of BMC pixels valid for the date (denominator
                       = bmc_pixel_count).
footprint_fraction_bmc = fraction of BMC pixels with finite lwir11 on that
                       date, BEFORE QA masking (union of finite lwir across
                       scenes).
Reuses disk cache; no re-download of cached scenes.
"""
import os
import sys
import numpy as np
import planetary_computer as pc
import rasterio
from pystac_client import Client
from rasterio.warp import reproject, Resampling, transform
from rasterio.transform import from_origin
from rasterio.features import rasterize as rio_rasterize
from shapely.geometry import box as shp_box, mapping as shp_mapping
import geopandas as gpd

sys.path.insert(0, "src")
import config
from utils import build_date_mosaic

CACHE_DIR = "data/landsat/cache"
SEARCH_BOX = shp_box(config.BOX["lon_min"], config.BOX["lat_min"],
                     config.BOX["lon_max"], config.BOX["lat_max"])

_CORNERS_X, _CORNERS_Y = transform(
    config.CRS_LONLAT, config.CRS_METRIC,
    [config.BOX["lon_min"], config.BOX["lon_max"]],
    [config.BOX["lat_min"], config.BOX["lat_max"]])
MINX, MAXX = min(_CORNERS_X), max(_CORNERS_X)
MINY, MAXY = min(_CORNERS_Y), max(_CORNERS_Y)
TARGET_TRANSFORM = from_origin(MINX, MAXY, 30.0, 30.0)
TARGET_WIDTH = int(round((MAXX - MINX) / 30.0))
TARGET_HEIGHT = int(round((MAXY - MINY) / 30.0))

_bmc = gpd.read_file(config.BMC_GEOJSON).dissolve().to_crs(config.CRS_METRIC)
BMC_MASK = rio_rasterize(
    [shp_mapping(g) for g in _bmc.geometry],
    out_shape=(TARGET_HEIGHT, TARGET_WIDTH),
    transform=TARGET_TRANSFORM, fill=0, default_value=1, dtype="uint8",
).astype(bool)
BMC_PIXEL_COUNT = int(BMC_MASK.sum())
print(f"BMC pixel count (denominator): {BMC_PIXEL_COUNT}")


def search_window_b():
    catalog = Client.open(config.CATALOG_URL)
    by_date = {}
    for year, (start, end) in config.WINDOW_B.items():
        search = catalog.search(
            collections=[config.COLLECTION], intersects=SEARCH_BOX,
            datetime=f"{start}/{end}",
            query={"eo:cloud_cover": {"lt": config.CLOUD_MAX},
                   "platform": {"in": list(config.PLATFORMS)}},
            limit=None,
        )
        for it in search.item_collection():
            by_date.setdefault(it.properties["datetime"][:10], []).append(it)
    return by_date


def load_asset_cached(it, asset_name):
    key = f"{it.id}_{asset_name}"
    path = os.path.join(CACHE_DIR, key + ".npy")
    if os.path.exists(path):
        return np.load(path)
    href = pc.sign(it.assets[asset_name].href)
    with rasterio.open(href) as src:
        dst = np.empty((TARGET_HEIGHT, TARGET_WIDTH), dtype="float32")
        reproject(
            source=rasterio.band(src, 1), destination=dst,
            src_transform=src.transform, src_crs=src.crs,
            dst_transform=TARGET_TRANSFORM, dst_crs=config.CRS_METRIC,
            resampling=Resampling.nearest,
            src_nodata=src.nodata, dst_nodata=np.nan,
        )
    np.save(path, dst)
    return dst


def main():
    by_date = search_window_b()
    dates = sorted(by_date)
    rows = []
    for d in dates:
        scenes = []
        date_finite_union = np.zeros((TARGET_HEIGHT, TARGET_WIDTH), dtype=bool)
        for it in by_date[d]:
            lwir = load_asset_cached(it, "lwir11")
            qa = load_asset_cached(it, "qa_pixel")
            scenes.append({"lwir11": lwir, "qa_pixel": qa})
            date_finite_union |= np.isfinite(lwir)
        mosaic, date_validity = build_date_mosaic(scenes)
        vf_box = float(np.mean(date_validity))
        vf_bmc = float(np.sum(date_validity & BMC_MASK) / BMC_PIXEL_COUNT)
        fp_bmc = float(np.sum(date_finite_union & BMC_MASK) / BMC_PIXEL_COUNT)
        rows.append((d, vf_box, vf_bmc, BMC_PIXEL_COUNT, fp_bmc))
        print(f"{d}: vf_box={vf_box:.4f} vf_bmc={vf_bmc:.4f} "
              f"fp_bmc={fp_bmc:.4f}")
    table_path = os.path.join(config.DIR_LOGS, "per_date_valid_fraction.txt")
    with open(table_path, "w") as f:
        f.write("date valid_fraction_box valid_fraction_bmc "
                "bmc_pixel_count footprint_fraction_bmc\n")
        for d, vb, vbmc, bpc, fpb in rows:
            f.write(f"{d} {vb:.6f} {vbmc:.6f} {bpc} {fpb:.6f}\n")
    print(f"Per-date table written to {table_path}")


if __name__ == "__main__":
    main()
