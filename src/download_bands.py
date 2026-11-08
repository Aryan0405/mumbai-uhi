"""Step 4: download red/nir08/swir16/green for the 49 window-B scenes,
box window only, resuming from data/landsat/cache/. Prints count out of 196
(4 bands x 49 scenes) after each batch.
Usage: conda run -n uhi python src/download_bands.py [--batch-size N] [--batch-index I]
"""
import argparse
import os
import sys
import numpy as np
import planetary_computer as pc
import rasterio
from pystac_client import Client
from rasterio.warp import reproject, Resampling, transform
from rasterio.transform import from_origin
from shapely.geometry import box as shp_box

sys.path.insert(0, "src")
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

BANDS = ["red", "nir08", "swir16", "green"]
EXPECTED = len(BANDS) * 49  # 196


def search_window_b():
    catalog = Client.open(config.CATALOG_URL)
    scenes = []
    seen = set()
    for year, (start, end) in config.WINDOW_B.items():
        search = catalog.search(
            collections=[config.COLLECTION], intersects=SEARCH_BOX,
            datetime=f"{start}/{end}",
            query={"eo:cloud_cover": {"lt": config.CLOUD_MAX},
                   "platform": {"in": list(config.PLATFORMS)}},
            limit=None,
        )
        for it in search.item_collection():
            if it.id in seen:
                continue
            seen.add(it.id)
            scenes.append(it)
    return scenes


def download_band(it, band):
    key = f"{it.id}_{band}"
    path = os.path.join(CACHE_DIR, key + ".npy")
    if os.path.exists(path):
        return True
    href = pc.sign(it.assets[band].href)
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
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=49)
    parser.add_argument("--batch-index", type=int, default=0)
    args = parser.parse_args()

    scenes = search_window_b()
    print(f"Total unique scenes: {len(scenes)}")
    start = args.batch_index * args.batch_size
    end = min(start + args.batch_size, len(scenes))
    batch = scenes[start:end]
    print(f"Batch {args.batch_index}: scenes {start} to {end-1} ({len(batch)} scenes)")

    downloaded = 0
    skipped = 0
    for i, it in enumerate(batch):
        for band in BANDS:
            key = f"{it.id}_{band}"
            path = os.path.join(CACHE_DIR, key + ".npy")
            if os.path.exists(path):
                skipped += 1
                continue
            download_band(it, band)
            downloaded += 1
            if (downloaded + skipped) % 4 == 0:
                present = sum(1 for s in scenes for b in BANDS
                              if os.path.exists(os.path.join(CACHE_DIR, f"{s.id}_{b}.npy")))
                print(f"progress: {present}/{EXPECTED} 4-band files cached", flush=True)

    present = 0
    for it in scenes:
        for band in BANDS:
            if os.path.exists(os.path.join(CACHE_DIR, f"{it.id}_{band}.npy")):
                present += 1
    print(f"Batch downloaded={downloaded} skipped={skipped}")
    print(f"4-band files present: {present} / {EXPECTED}")


if __name__ == "__main__":
    main()
