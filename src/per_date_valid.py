"""Per-date valid fraction (box + inside BMC), computed from qa_pixel + lwir11
per scene per date, with disk caching so re-runs are fast. Writes
logs/per_date_valid_fraction.txt: date valid_fraction_box valid_fraction_bmc.
"""
import os
import numpy as np
import planetary_computer as pc
import rasterio
from pystac_client import Client
from rasterio.warp import reproject, Resampling, transform
from rasterio.transform import from_origin
from rasterio.features import rasterize as rio_rasterize
from shapely.geometry import box as shp_box, mapping as shp_mapping
import geopandas as gpd

import config

CACHE_DIR = "data/landsat/cache"
os.makedirs(CACHE_DIR, exist_ok=True)
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

# Dissolved BMC polygon, reprojected to EPSG:32643 before rasterizing.
_bmc = gpd.read_file(config.BMC_GEOJSON).dissolve().to_crs(config.CRS_METRIC)
BMC_MASK = rio_rasterize(
    [shp_mapping(g) for g in _bmc.geometry],
    out_shape=(TARGET_HEIGHT, TARGET_WIDTH),
    transform=TARGET_TRANSFORM, fill=0, default_value=1, dtype="uint8",
).astype(bool)
print(f"BMC mask pixels: {int(BMC_MASK.sum())} of {BMC_MASK.size}")


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
    np.save(path, dst)
    return dst


def main():
    by_date = search_window_b()
    dates = sorted(by_date)
    rows = []
    for d in dates:
        vf_box_list, vf_bmc_list = [], []
        for it in by_date[d]:
            qa = load_asset_cached(it, "qa_pixel")
            lwir = load_asset_cached(it, "lwir11")
            valid = (lwir != 0)
            qai = np.nan_to_num(qa, nan=0).astype(np.uint16)
            valid &= ((qai >> 0) & 1) == 0
            for b in (1, 2, 3, 4):
                valid &= ((qai >> b) & 1) == 0
            vf_box_list.append(float(np.mean(valid)))
            vf_bmc_list.append(float(np.mean(valid & BMC_MASK)))
        vf_box = float(np.max(vf_box_list)) if vf_box_list else 0.0
        vf_bmc = float(np.max(vf_bmc_list)) if vf_bmc_list else 0.0
        rows.append((d, vf_box, vf_bmc))
        print(f"{d}: vf_box={vf_box:.4f} vf_bmc={vf_bmc:.4f}")
    table_path = os.path.join(config.DIR_LOGS, "per_date_valid_fraction.txt")
    with open(table_path, "w") as f:
        f.write("date valid_fraction_box valid_fraction_bmc\n")
        for d, vb, vbmc in rows:
            f.write(f"{d} {vb:.6f} {vbmc:.6f}\n")
    print(f"Per-date table written to {table_path}")


if __name__ == "__main__":
    main()
