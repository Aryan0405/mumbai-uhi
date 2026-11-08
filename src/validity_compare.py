"""Item 2: compare NEW shared-validity valid_count vs EXISTING
data/composites/valid_count.tif, WITHOUT regenerating composites.

Reads per-scene arrays from data/landsat/cache/ (no re-download), computes
per-date union validity via src/utils.compute_validity, builds new valid_count,
and compares to the existing valid_count.tif (min, median, max, count differ).
"""
import os
import numpy as np
import rasterio
import sys

sys.path.insert(0, "src")
import config
from utils import compute_validity

CACHE_DIR = "data/landsat/cache"
OLD_COUNT_PATH = os.path.join(config.DIR_COMPOSITES, "valid_count.tif")


def scene_files_for_date(date, items):
    """Return list of (lwir_path, qa_path) from cache for scenes of a date."""
    out = []
    for it in items:
        out.append((os.path.join(CACHE_DIR, f"{it.id}_lwir11.npy"),
                    os.path.join(CACHE_DIR, f"{it.id}_qa_pixel.npy")))
    return out


def main():
    # Existing valid_count
    with rasterio.open(OLD_COUNT_PATH) as src:
        old_count = src.read(1).astype("float64")
        old_transform = src.transform
        old_crs = src.crs
        old_shape = src.shape

    # Search to get per-date scene membership
    from pystac_client import Client
    from shapely.geometry import box as shp_box
    catalog = Client.open(config.CATALOG_URL)
    search_box = shp_box(config.BOX["lon_min"], config.BOX["lat_min"],
                         config.BOX["lon_max"], config.BOX["lat_max"])
    by_date = {}
    for year, (start, end) in config.WINDOW_B.items():
        search = catalog.search(
            collections=[config.COLLECTION], intersects=search_box,
            datetime=f"{start}/{end}",
            query={"eo:cloud_cover": {"lt": config.CLOUD_MAX},
                   "platform": {"in": list(config.PLATFORMS)}},
            limit=None,
        )
        for it in search.item_collection():
            by_date.setdefault(it.properties["datetime"][:10], []).append(it)

    new_count = np.zeros(old_shape, dtype="float64")
    n_valid_dates = np.zeros(old_shape, dtype="int32")
    for d in sorted(by_date):
        date_valid_union = np.zeros(old_shape, dtype=bool)
        for it in by_date[d]:
            lpath = os.path.join(CACHE_DIR, f"{it.id}_lwir11.npy")
            qpath = os.path.join(CACHE_DIR, f"{it.id}_qa_pixel.npy")
            if not (os.path.exists(lpath) and os.path.exists(qpath)):
                continue
            lwir = np.load(lpath)
            qa = np.load(qpath)
            date_valid_union |= compute_validity(lwir, qa)
        new_count += date_valid_union.astype("float64")
        n_valid_dates += date_valid_union.astype("int32")

    # Compare
    old_finite = old_count[~np.isnan(old_count)]
    new_finite = new_count[~np.isnan(new_count)]
    diff = new_count - old_count
    diff_finite = diff[~np.isnan(diff)]
    n_diff = int((diff_finite != 0).sum())
    print(f"OLD valid_count: min={float(np.nanmin(old_count))} "
          f"median={float(np.median(old_finite)):.1f} max={float(np.nanmax(old_count))}")
    print(f"NEW valid_count: min={float(np.nanmin(new_count))} "
          f"median={float(np.median(new_finite)):.1f} max={float(np.nanmax(new_count))}")
    print(f"Pixels that differ: {n_diff}")
    if n_diff > 0:
        print(f"  diff min={float(diff_finite.min())} max={float(diff_finite.max())}")
        print(f"  diff median={float(np.median(diff_finite)):.1f}")
    print(f"Dates processed: {len(by_date)}")


if __name__ == "__main__":
    main()
