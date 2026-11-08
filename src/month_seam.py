"""Phase 3A item 6: Month seam check.

Creates per-pixel arrays in data/composites_months/ (never touches data/composites/):
  lst_march.tif      - median LST over March dates
  lst_aprmay.tif     - median LST over April+May dates
  vc_march.tif       - valid date count for March
  vc_april.tif       - valid date count for April
  vc_may.tif         - valid date count for May

Then, on flag-free cells only:
  a. Mean LST for March only and April+May; Spearman between them; top-20 Jaccard
     (top 20 cells by mean LST in each); count of cells where either is NaN.
  b. March share of valid dates = vc_march / (vc_march + vc_april + vc_may)
     per pixel, then cell median; min/median/max of share; Spearman between share
     and all-date mean LST.
  c. Spearman between all-date mean LST and cell median valid_count.
"""
import os
import sys
import numpy as np
import planetary_computer as pc
import rasterio
from pystac_client import Client
from rasterio.warp import transform as warp_transform
from rasterio.transform import from_origin
from rasterio.features import rasterize as rio_rasterize
from shapely.geometry import box as shp_box, mapping as shp_mapping
import geopandas as gpd
from collections import defaultdict
from scipy import stats

sys.path.insert(0, "src")
import config
from utils import write_log, silence_all_nan_warning, compute_validity

silence_all_nan_warning()

CACHE_DIR = "data/landsat/cache"
OUT_DIR = os.path.join(config.DIR_DATA, "composites_months")
os.makedirs(OUT_DIR, exist_ok=True)

SEARCH_BOX = shp_box(config.BOX["lon_min"], config.BOX["lat_min"],
                     config.BOX["lon_max"], config.BOX["lat_max"])

_CORNERS_X, _CORNERS_Y = warp_transform(
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

LWIR_SCALE = 0.00341802
LWIR_OFFSET = 149.0


def dn_to_lst(dn):
    return dn * LWIR_SCALE + LWIR_OFFSET - 273.15


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


def date_mosaic_lwir(date_items):
    """For one date: mosaic lwir11 DN across scenes (nanmedian), with per-scene
    QA masking. Returns (lwir_dn_mosaic, valid_date_mask)."""
    scene_lwir = []
    scene_valid = []
    for it in date_items:
        lwir = load_asset_cached(it, "lwir11")
        qa = load_asset_cached(it, "qa_pixel")
        validity = compute_validity(lwir, qa)
        scene_lwir.append(lwir)
        scene_valid.append(validity)
    scene_lwir_stack = np.stack(scene_lwir, axis=0)
    scene_valid_stack = np.stack(scene_valid, axis=0)
    date_validity = np.any(scene_valid_stack, axis=0)
    date_mosaic = np.nanmedian(np.where(scene_valid_stack, scene_lwir_stack, np.nan), axis=0)
    date_mosaic = np.where(date_validity, date_mosaic, np.nan)
    return date_mosaic, date_validity


def main():
    by_date = search_window_b()
    dates = sorted(by_date.keys())
    dates_by_ym = defaultdict(list)
    for d in dates:
        dates_by_ym[(int(d[:4]), int(d[5:7]))].append(d)

    # Build per-date LST mosaics and valid masks
    date_lst = {}
    date_valid = {}
    for d in dates:
        mosaic, valid = date_mosaic_lwir(by_date[d])
        date_lst[d] = dn_to_lst(mosaic)
        date_valid[d] = valid

    # Month stacks
    month_lst = {}
    month_valid_count = {}
    for mname, months in (("march", [3]), ("april", [4]), ("may", [5])):
        ds = sorted([d for d in dates if int(d[5:7]) in months])
        lst_list = [date_lst[d] for d in ds]
        valid_list = [date_valid[d] for d in ds]
        month_stack = np.stack(lst_list, axis=0)
        month_comp = np.nanmedian(month_stack, axis=0)
        month_comp = np.where(np.any(valid_list, axis=0), month_comp, np.nan)
        month_lst[mname] = month_comp
        month_valid_count[mname] = np.sum(valid_list, axis=0)

    # Save to disk
    for mname, key in (("march", "march"), ("april", "apr_may"), ("may", "apr_may")):
        pass
    # Save individual files
    with rasterio.open(os.path.join(config.DIR_COMPOSITES, "lwir11.tif")) as src:
        profile = src.profile
    profile.update(dtype="float32", count=1, nodata=np.nan)

    def write_tif(name, arr):
        path = os.path.join(OUT_DIR, f"{name}.tif")
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(arr.astype(np.float32), 1)

    write_tif("lst_march", month_lst["march"])
    write_tif("lst_aprmay", np.nanmedian(np.stack([month_lst["april"], month_lst["may"]], axis=0), axis=0))
    write_tif("vc_march", month_valid_count["march"].astype(np.float32))
    write_tif("vc_april", month_valid_count["april"].astype(np.float32))
    write_tif("vc_may", month_valid_count["may"].astype(np.float32))

    # Flag-free cells: valid in all months
    vc_march = month_valid_count["march"]
    vc_april = month_valid_count["april"]
    vc_may = month_valid_count["may"]
    all_valid = (vc_march > 0) & (vc_april > 0) & (vc_may > 0)
    flag_free = all_valid & ~np.isnan(month_lst["march"]) & ~np.isnan(month_lst["april"]) & ~np.isnan(month_lst["may"])

    lines = []
    lines.append("Month seam analysis (flag-free cells only):")
    lines.append("")

    # a. March vs April+May mean LST
    mar_mean = month_lst["march"][flag_free]
    apr_may_stack = np.stack([month_lst["april"][flag_free], month_lst["may"][flag_free]], axis=0)
    apr_may_mean = np.nanmean(apr_may_stack, axis=0)
    valid_pair = ~np.isnan(mar_mean) & ~np.isnan(apr_may_mean)
    mar_mean_v = mar_mean[valid_pair]
    apr_may_mean_v = apr_may_mean[valid_pair]
    rho_seam, _ = stats.spearmanr(mar_mean_v, apr_may_mean_v)
    both_nan = int((np.isnan(month_lst["march"]) | np.isnan(month_lst["april"])).sum())
    mar_top20 = np.argsort(mar_mean_v)[::-1][:20]
    apr_may_top20 = np.argsort(apr_may_mean_v)[::-1][:20]
    mar_top20_set = set(np.where(valid_pair)[0][mar_top20])
    apr_may_top20_set = set(np.where(valid_pair)[0][apr_may_top20])
    jaccard = len(mar_top20_set & apr_may_top20_set) / len(mar_top20_set | apr_may_top20_set)
    lines.append("a. March vs April+May mean LST (flag-free cells):")
    lines.append(f"  March mean LST mean={float(mar_mean_v.mean()):.2f} C, n={mar_mean_v.size}")
    lines.append(f"  Apr+May mean LST mean={float(apr_may_mean_v.mean()):.2f} C, n={apr_may_mean_v.size}")
    lines.append(f"  Spearman(LST_mar, LST_apr+May) = {rho_seam:.4f}")
    lines.append(f"  Cells where either is NaN: {int(both_nan)}")
    lines.append(f"  Top-20 Jaccard (by mean LST): {jaccard:.4f}")

    # b. March share of valid dates
    vc_total = vc_march + vc_april + vc_may
    share = np.where(vc_total > 0, vc_march / vc_total, np.nan)
    share_flagfree = share[flag_free]
    share_valid = share_flagfree[~np.isnan(share_flagfree)]
    share_med = float(np.median(share_valid))
    share_min = float(np.nanmin(share_valid))
    share_max = float(np.nanmax(share_valid))
    rho_share, _ = stats.spearmanr(share_valid, month_lst["march"][flag_free][~np.isnan(share_valid)])
    lines.append("")
    lines.append("b. March share of valid dates (flag-free cells):")
    lines.append(f"  March share median={share_med:.4f}, min={share_min:.4f}, max={share_max:.4f}")
    lines.append(f"  Spearman(March share, March mean LST) = {rho_share:.4f}")

    # c. Spearman between all-date mean LST and cell median valid_count
    all_date_lst = np.nanmedian(np.stack([date_lst[d] for d in dates], axis=0), axis=0)
    all_date_lst = all_date_lst[flag_free]
    cell_vc_med = np.nanmedian(np.stack([vc_march[flag_free], vc_april[flag_free], vc_may[flag_free]], axis=0), axis=0)
    cell_vc_med_valid = cell_vc_med[~np.isnan(cell_vc_med)]
    all_date_lst_valid = all_date_lst[~np.isnan(cell_vc_med)]
    rho_lst_vc, _ = stats.spearmanr(all_date_lst_valid, cell_vc_med_valid)
    lines.append("")
    lines.append("c. Spearman between all-date mean LST and cell median valid_count (flag-free cells):")
    lines.append(f"  rho = {rho_lst_vc:.4f}")

    log_path = os.path.join(config.DIR_LOGS, "round4c_month_seam.txt")
    write_log(log_path, "\n".join(lines))
    print(log_path)


if __name__ == "__main__":
    main()
