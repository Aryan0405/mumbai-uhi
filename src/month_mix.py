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
        date_lst = dn_to_lst(mosaic["lwir11"])  # already in Celsius
        bmc_land = date_lst[BMC_LAND_MASK & ~np.isnan(date_lst)]
        med = float(np.median(bmc_land)) if bmc_land.size else None
        n_land = int(bmc_land.size)
        per_date[d] = {"med": med, "n_land": n_land, "lst": date_lst}
        med_s = f"{med:.2f}" if med is not None else "N/A"
        print(f"  {d}: median LST={med_s} C n_land={n_land}")

    print("\nMonth mix (n dates, BMC land median LST, effective dates, min/max/IQR):")
    monthly_meds = {"Mar": [], "Apr": [], "May": []}  # per-date medians
    monthly_lst = {"Mar": [], "Apr": [], "May": []}   # per-date arrays (pooled)
    for y in sorted(config.WINDOW_B):
        for m in (3, 4, 5):
            ds = sorted(dates_by_ym.get((y, m), []))
            month_name = {3: "Mar", 4: "Apr", 5: "May"}[m]
            if not ds:
                print(f"  {y}-{m:02d}: 0 dates [] median LST=N/A effective dates=0 "
                      f"min=N/A max=N/A IQR=N/A")
                continue
            date_lst_list = []
            date_medians = []
            effective_dates = 0
            for d in ds:
                entry = per_date[d]
                date_lst_list.append(entry["lst"])
                if entry["n_land"] > 0:
                    effective_dates += 1
                    date_medians.append(entry["med"])
            month_stack = np.stack(date_lst_list, axis=0)
            month_comp = np.nanmedian(month_stack, axis=0)  # already Celsius
            lst = month_comp
            bmc_land = lst[BMC_LAND_MASK & ~np.isnan(lst)]
            med = float(np.median(bmc_land)) if bmc_land.size else None
            if date_medians:
                mn = float(np.min(date_medians))
                mx = float(np.max(date_medians))
                q1 = float(np.percentile(date_medians, 25))
                q3 = float(np.percentile(date_medians, 75))
                iqr = q3 - q1
            else:
                mn = mx = q1 = q3 = iqr = None
            med_s = f"{med:.2f}" if med is not None else "N/A"
            mn_s = f"{mn:.2f}" if mn is not None else "N/A"
            mx_s = f"{mx:.2f}" if mx is not None else "N/A"
            iqr_s = f"{iqr:.2f}" if iqr is not None else "N/A"
            print(f"  {y}-{m:02d}: {len(ds)} dates median LST={med_s} C "
                  f"effective dates={effective_dates} min={mn_s} max={mx_s} IQR={iqr_s}")
            if med is not None:
                monthly_meds[month_name].append(med)
            monthly_lst[month_name].extend(date_lst_list)

    print("\nPer-date BMC land medians:")
    for d in dates:
        entry = per_date[d]
        med_s = f"{entry['med']:.2f}" if entry["med"] is not None else "N/A"
        print(f"  {d}: {med_s} C (n_land={entry['n_land']})")

    print("\nPooled monthly medians across years (all dates of that month):")
    for mname in ("Mar", "Apr", "May"):
        meds = [v for v in monthly_meds[mname] if v is not None]
        pooled_lst = np.nanmedian(np.stack(monthly_lst[mname], axis=0), axis=0)
        bmc_land = pooled_lst[BMC_LAND_MASK & ~np.isnan(pooled_lst)]
        pooled_med = (float(np.median(bmc_land))
                      if bmc_land.size else None)
        med_of_meds = (float(np.median(meds)) if meds else None)
        meds_s = f"{med_of_meds:.2f}" if med_of_meds is not None else "N/A"
        pooled_s = f"{pooled_med:.2f}" if pooled_med is not None else "N/A"
        print(f"  {mname}: pooled (per-pixel over all dates)={pooled_s} C "
              f"median-of-per-date-medians={meds_s} C "
              f"(n months with data={len(meds)})")

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
