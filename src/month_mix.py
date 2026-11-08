"""Item 4: month mix redo (corrected).

For each date: mosaic scenes (nanmedian of raw lwir DN), apply the shared
validity (src/utils.compute_validity) as UNION across scenes, then mask.
Per-date BMC land median LST printed for all 26 dates.
For each (year, month): per-pixel median over that month's dates, then median
over BMC land pixels. Pooled month medians computed from ALL dates of that
month across years (not a median of yearly medians).
Also: May 2025 STAC search at any cloud cover (search only, no downloads).
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
from collections import defaultdict

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
# Water mask from median composite NDWI (read-only): NDWI > 0 = water.
with rasterio.open(os.path.join(config.DIR_COMPOSITES, "ndwi.tif")) as src:
    NDWI = src.read(1).astype("float64")
WATER_MASK = NDWI > 0
BMC_LAND_MASK = BMC_MASK & (~WATER_MASK)

LWIR_SCALE = 0.00341802
LWIR_OFFSET = 149.0


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


def load_lwir_qa(it):
    lpath = os.path.join(CACHE_DIR, f"{it.id}_lwir11.npy")
    qpath = os.path.join(CACHE_DIR, f"{it.id}_qa_pixel.npy")
    if os.path.exists(lpath) and os.path.exists(qpath):
        return np.load(lpath), np.load(qpath)
    href_l = pc.sign(it.assets["lwir11"].href)
    href_q = pc.sign(it.assets["qa_pixel"].href)
    with rasterio.open(href_l) as src:
        dst = np.empty((TARGET_HEIGHT, TARGET_WIDTH), dtype="float32")
        reproject(
            source=rasterio.band(src, 1), destination=dst,
            src_transform=src.transform, src_crs=src.crs,
            dst_transform=TARGET_TRANSFORM, dst_crs=config.CRS_METRIC,
            resampling=Resampling.nearest,
            src_nodata=src.nodata, dst_nodata=np.nan,
        )
        np.save(lpath, dst)
    with rasterio.open(href_q) as src:
        dst = np.empty((TARGET_HEIGHT, TARGET_WIDTH), dtype="float32")
        reproject(
            source=rasterio.band(src, 1), destination=dst,
            src_transform=src.transform, src_crs=src.crs,
            dst_transform=TARGET_TRANSFORM, dst_crs=config.CRS_METRIC,
            resampling=Resampling.nearest,
            src_nodata=src.nodata, dst_nodata=np.nan,
        )
        np.save(qpath, dst)
    return np.load(lpath), np.load(qpath)


def dn_to_lst(dn):
    return dn * LWIR_SCALE + LWIR_OFFSET - 273.15


def main():
    by_date = search_window_b()
    dates = sorted(by_date)
    dates_by_ym = defaultdict(list)
    for d in dates:
        dates_by_ym[(int(d[:4]), int(d[5:7]))].append(d)

    print("Per-date BMC land median LST (all 26 dates):")
    per_date = {}
    for d in dates:
        scenes = []
        for it in by_date[d]:
            lwir, qa = load_lwir_qa(it)
            scenes.append({"lwir11": lwir, "qa_pixel": qa})
        mosaic, date_validity = build_date_mosaic(scenes)
        date_lst = dn_to_lst(mosaic["lwir11"])
        bmc_land = date_lst[BMC_LAND_MASK & ~np.isnan(date_lst)]
        med = float(np.median(bmc_land)) if bmc_land.size else None
        n_land = int(bmc_land.size)
        per_date[d] = (med, n_land)
        med_s = f"{med:.2f}" if med is not None else "N/A"
        print(f"  {d}: median LST={med_s} C n_land={n_land}")

    print("\nMonth mix (n dates, BMC land median LST, BMC land pixels with >=1 valid date):")
    monthly_all = {"Mar": [], "Apr": [], "May": []}
    for y in sorted(config.WINDOW_B):
        for m in (3, 4, 5):
            ds = sorted(dates_by_ym.get((y, m), []))
            if not ds:
                print(f"  {y}-{m:02d}: 0 dates [] median LST=N/A n_land_with_valid=0")
                continue
            date_lst_list = []
            any_valid = np.zeros((TARGET_HEIGHT, TARGET_WIDTH), dtype=bool)
            for d in ds:
                scenes = []
                for it in by_date[d]:
                    lwir, qa = load_lwir_qa(it)
                    scenes.append({"lwir11": lwir, "qa_pixel": qa})
                mosaic, date_validity = build_date_mosaic(scenes)
                date_lst_list.append(dn_to_lst(mosaic["lwir11"]))
                any_valid |= (date_validity & BMC_MASK)
            month_stack = np.stack(date_lst_list, axis=0)
            month_comp = np.nanmedian(month_stack, axis=0)
            lst = dn_to_lst(month_comp)
            bmc_land = lst[BMC_LAND_MASK & ~np.isnan(lst)]
            med = float(np.median(bmc_land)) if bmc_land.size else None
            n_any_valid = int((any_valid & BMC_LAND_MASK & ~np.isnan(month_comp)).sum())
            month_name = {3: "Mar", 4: "Apr", 5: "May"}[m]
            med_s = f"{med:.2f}" if med is not None else "N/A"
            print(f"  {y}-{m:02d}: {len(ds)} dates median LST={med_s} C "
                  f"n_land_with_valid={n_any_valid}")
            if med is not None:
                monthly_all[month_name].append(med)

    print("\nPooled monthly medians across years (all dates of that month):")
    for mname in ("Mar", "Apr", "May"):
        vals = [v for v in monthly_all[mname] if v is not None]
        if vals:
            print(f"  {mname}: {len(vals)} months, pooled median="
                  f"{float(np.median(vals)):.2f} C")
        else:
            print(f"  {mname}: 0 months, pooled median=N/A")

    # May 2025 STAC search only (no downloads)
    print("\nMay 2025 STAC search (any cloud cover):")
    catalog = Client.open(config.CATALOG_URL)
    search_any = catalog.search(
        collections=[config.COLLECTION], intersects=SEARCH_BOX,
        datetime="2025-05-01/2025-05-31", limit=None,
    )
    items_any = list(search_any.item_collection())
    print(f"  Without cloud filter: {len(items_any)} scenes")
    for it in items_any:
        print(f"    {it.id} platform={it.properties.get('platform')} "
              f"cloud={it.properties.get('eo:cloud_cover')}")
    search_10 = catalog.search(
        collections=[config.COLLECTION], intersects=SEARCH_BOX,
        datetime="2025-05-01/2025-05-31",
        query={"eo:cloud_cover": {"lt": 10}}, limit=None,
    )
    items_10 = list(search_10.item_collection())
    print(f"  With cloud < 10 percent filter: {len(items_10)} scenes")


if __name__ == "__main__":
    main()
