"""Month seam check on the 500 m cell grid (Phase 3A round R3).

Builds per-date mosaics exactly as the composite pipeline
(src/build_composites.py + src/utils.build_date_mosaic), loading from the
cache (data/landsat/cache/) only -- no downloads. If any needed cache file is
missing, the script STOPs.

Gate: recomputes the all-date per-pixel median of the per-date mosaics and
compares it to data/composites/lwir11.tif on BMC land pixels. If any pixel
differs by more than 1e-3, STOPs.

Writes data/composites_months/lst_march.tif, lst_aprmay.tif, vc_march.tif,
vc_april.tif, vc_may.tif (same grid/CRS/units as the composites: Kelvin).

Then runs cell-level diagnostics on core cells with n_land_px > 0 from
data/processed/cells_500m.csv: March vs AprMay cell LST means, spearmans,
top-20 Jaccards, March valid-date share, and spearman of all-date lst_mean
with cell vc_median. Coefficients only, no significance claims.
Logs to logs/phase3a_month_seam.txt.
"""
import os
import sys

sys.path.insert(0, "src")

import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize as rio_rasterize
import geopandas as gpd
from shapely.geometry import mapping as shp_mapping
from scipy import ndimage

import config
from utils import build_date_mosaic, write_log
import build_composites as bc
from stats_utils import spearman_rho

MONTH_DIR = os.path.join(config.DIR_DATA, "composites_months")
CACHE_DIR = os.path.join("data", "landsat", "cache")
GRID_TIF = os.path.join(config.DIR_COMPOSITES, "lwir11.tif")
CELL_CSV = os.path.join(config.DIR_DATA, "processed", "cells_500m.csv")
CELL_SIZE = 500.0
K_TO_C = 273.15


def _safe_divide(num, denom):
    out = np.full(num.shape, np.nan, dtype=np.float64)
    np.divide(num, denom, out=out, where=denom != 0.0)
    return out


def load_scene_from_cache(it, asset_name):
    """Load one asset band from cache only. Returns None if not cached."""
    cache_path = os.path.join(CACHE_DIR, f"{it.id}_{asset_name}.npy")
    if not os.path.exists(cache_path):
        return None
    return np.load(cache_path).astype(np.float32)


def read_grid():
    with rasterio.open(GRID_TIF) as src:
        tf = src.transform
        height, width = src.shape
    return tf, height, width


def bmc_mask_on_grid(transform, height, width):
    bmc = gpd.read_file(config.BMC_GEOJSON).dissolve().to_crs(config.CRS_METRIC)
    return rio_rasterize(
        [shp_mapping(g) for g in bmc.geometry],
        out_shape=(height, width), transform=transform,
        fill=0, default_value=1, dtype="uint8",
    ).astype(bool)


def month_of(date_str):
    return date_str[5:7]


def write_month_tif(path, array, transform):
    profile = {
        "driver": "GTiff", "dtype": "float32", "width": array.shape[1],
        "height": array.shape[0], "count": 1,
        "crs": config.CRS_METRIC, "transform": transform, "nodata": np.nan,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array.astype("float32"), 1)


def top20(cell_ids, values):
    """Top-20 cell ids by value desc, ties broken by cell_id ascending."""
    m = ~np.isnan(values)
    ids = cell_ids[m]
    vals = values[m]
    order = np.lexsort((ids, -vals))
    return set(ids[order[:20]].tolist())


def jaccard(a, b):
    if len(a) == 0 and len(b) == 0:
        return float("nan")
    inter = len(a & b)
    uni = len(a | b)
    return inter / uni if uni > 0 else float("nan")


def top_n(cell_ids, values, n):
    """Top-n cell ids by value desc, ties broken by cell_id ascending."""
    m = ~np.isnan(values)
    ids = cell_ids[m]
    vals = values[m]
    order = np.lexsort((ids, -vals))
    return set(ids[order[:n]].tolist())


def cluster_stats(cell_ids, n_cols=48):
    """Connected components with 8-neighbour adjacency on the row/col grid.

    row = cell_id // n_cols, col = cell_id % n_cols. Returns
    (num_components, size_of_largest_component).
    """
    n_rows = int(np.ceil((cell_ids.max() + 1) / n_cols)) if cell_ids.size else 0
    grid = np.zeros((n_rows, n_cols), dtype=bool)
    rows = cell_ids // n_cols
    cols = cell_ids % n_cols
    grid[rows, cols] = True
    structure = np.ones((3, 3), dtype=int)
    labeled, num_components = ndimage.label(grid, structure=structure)
    if num_components == 0:
        return (0, 0)
    sizes = np.bincount(labeled.ravel())[1:]
    return (int(num_components), int(sizes.max()))


def main():
    os.makedirs(MONTH_DIR, exist_ok=True)
    os.makedirs(config.DIR_LOGS, exist_ok=True)
    log_path = os.path.join(config.DIR_LOGS, "phase3a_month_seam.txt")
    lines = []

    def log(*parts):
        lines.append(" ".join(str(p) for p in parts))

    # --- Grid from the composites tif (same grid as cell_stats.py).
    tf, H, W = read_grid()
    log("Grid:", tf, H, W)

    # --- Grid equality with build_composites target grid (pixelwise gate).
    if (abs(bc.TARGET_TRANSFORM.a - tf.a) > 1e-9
            or abs(bc.TARGET_TRANSFORM.e - tf.e) > 1e-9
            or abs(bc.TARGET_TRANSFORM.c - tf.c) > 1e-9
            or abs(bc.TARGET_TRANSFORM.f - tf.f) > 1e-9
            or bc.TARGET_HEIGHT != H or bc.TARGET_WIDTH != W):
        log("STOP: build_composites target grid differs from composites tif grid; cannot compare pixelwise.")
        write_log(log_path, "\n".join(lines) + "\n")
        print("\n".join(lines))
        raise SystemExit(1)
    log("build_composites target grid matches composites tif grid.")

    bmc_mask = bmc_mask_on_grid(tf, H, W)
    log("BMC mask pixels:", int(bmc_mask.sum()))

    # --- STAC search for scene lists (read only, no downloads).
    try:
        by_date = bc.search_window_b()
    except Exception as exc:  # network or search failure
        log("STOP: STAC search failed:", repr(exc))
        write_log(log_path, "\n".join(lines) + "\n")
        print("\n".join(lines))
        raise SystemExit(1)
    dates = sorted(by_date)
    log("Unique dates from STAC search:", len(dates))
    for d in dates:
        log("  date:", d, "scenes:", len(by_date[d]))

    # --- Verify every needed asset is cached; STOP if any missing.
    missing = []
    for d in dates:
        for it in by_date[d]:
            for asset_name in config.ASSETS:
                cache_path = os.path.join(CACHE_DIR, f"{it.id}_{asset_name}.npy")
                if not os.path.exists(cache_path):
                    missing.append(cache_path)
    if missing:
        log("STOP: missing cache files (" + str(len(missing)) + "):")
        for p in missing[:20]:
            log("   ", p)
        write_log(log_path, "\n".join(lines) + "\n")
        print("\n".join(lines))
        raise SystemExit(1)
    log("All assets cached for all scenes.")

    # --- Per-date mosaics (build_date_mosaic, scale/offset from items).
    so = None
    per_date = {}
    for d in dates:
        items = by_date[d]
        if so is None:
            so = bc.read_scale_offset(items)
        scenes = []
        for it in items:
            scene = {}
            for asset_name in config.ASSETS:
                scene[asset_name] = load_scene_from_cache(it, asset_name)
            scenes.append(scene)
        mosaic, date_validity = build_date_mosaic(scenes)
        s = so["lwir11"]
        lwir_k = mosaic["lwir11"] * s["scale"] + s["offset"]
        per_date[d] = (lwir_k, np.isfinite(lwir_k))
    log("Per-date mosaics built:", len(per_date))

    # --- GATE: all-date median vs data/composites/lwir11.tif on BMC land.
    stack = np.stack([per_date[d][0] for d in dates], axis=0)  # (date, y, x)
    all_median_k = np.nanmedian(stack, axis=0)
    with rasterio.open(GRID_TIF) as src:
        existing_k = src.read(1).astype(np.float64)
        ndwi = rasterio.open(os.path.join(config.DIR_COMPOSITES, "ndwi.tif")).read(1).astype(np.float64)
    land = bmc_mask & (ndwi <= 0.0) & np.isfinite(existing_k) & np.isfinite(all_median_k)
    diff = np.abs(all_median_k[land] - existing_k[land])
    max_diff = float(diff.max()) if diff.size else 0.0
    n_bad = int((diff > 1e-3).sum())
    log("GATE: BMC land pixels compared:", int(land.sum()))
    log("GATE: max abs difference (K):", max_diff)
    log("GATE: pixels differing by more than 1e-3 K:", n_bad)
    if n_bad > 0:
        log("STOP: gate failed (pixel differs by more than 1e-3 K).")
        write_log(log_path, "\n".join(lines) + "\n")
        print("\n".join(lines))
        raise SystemExit(1)
    log("GATE: OK.")

    # --- Monthly mosaics (Kelvin), all years pooled.
    march_dates = [d for d in dates if month_of(d) == "03"]
    april_dates = [d for d in dates if month_of(d) == "04"]
    may_dates = [d for d in dates if month_of(d) == "05"]
    aprmay_dates = april_dates + may_dates

    def month_median(dlist):
        return np.nanmedian(np.stack([per_date[d][0] for d in dlist], axis=0), axis=0)

    def month_vc(dlist):
        return np.nansum(np.stack([per_date[d][1] for d in dlist], axis=0), axis=0).astype(np.float32)

    lst_march = month_median(march_dates)
    lst_aprmay = month_median(aprmay_dates)
    vc_march = month_vc(march_dates)
    vc_april = month_vc(april_dates)
    vc_may = month_vc(may_dates)
    log("March dates:", len(march_dates), march_dates)
    log("April dates:", len(april_dates), april_dates)
    log("May dates:", len(may_dates), may_dates)

    write_month_tif(os.path.join(MONTH_DIR, "lst_march.tif"), lst_march, tf)
    write_month_tif(os.path.join(MONTH_DIR, "lst_aprmay.tif"), lst_aprmay, tf)
    write_month_tif(os.path.join(MONTH_DIR, "vc_march.tif"), vc_march, tf)
    write_month_tif(os.path.join(MONTH_DIR, "vc_april.tif"), vc_april, tf)
    write_month_tif(os.path.join(MONTH_DIR, "vc_may.tif"), vc_may, tf)
    log("Wrote monthly rasters to", MONTH_DIR)

    # --- Cell level on core cells with n_land_px > 0.
    df = pd.read_csv(CELL_CSV)
    core = (df["in_bmc"] == True) & (df["core"] == True) & (df["n_land_px"] > 0)  # noqa: E712
    cell_ids = df.loc[core, "cell_id"].to_numpy(dtype=np.int64)
    n_cells_used = int(cell_ids.size)
    log("Core cells with n_land_px > 0:", n_cells_used)

    # Pixel centres -> cells on the composites grid (same grid as cell_stats).
    minx = tf.c
    maxy = tf.f
    xs = minx + (np.arange(W) + 0.5) * tf.a
    ys = maxy + (np.arange(H) + 0.5) * tf.e
    xx, yy = np.meshgrid(xs, ys)
    from aggregate import assign_cells
    n_cols = int(np.ceil(((tf.c + W * tf.a) - minx) / CELL_SIZE))
    n_rows = int(np.ceil((maxy - (tf.f + H * tf.e)) / CELL_SIZE))
    n_cells = n_rows * n_cols
    cell_rows, cell_cols, in_range = assign_cells(xx.ravel(), yy.ravel(),
                                                  minx, maxy, CELL_SIZE,
                                                  n_rows, n_cols)
    flat_cell_id = cell_rows * n_cols + cell_cols

    land = bmc_mask & (ndwi <= 0.0)

    # Vectorised per-cell mean for a raster over land pixels (np.bincount).
    def mean_over_land(r):
        rflat = r.ravel()
        valid = land.ravel() & np.isfinite(rflat)
        fcid = flat_cell_id[valid]
        s = np.bincount(fcid, weights=rflat[valid], minlength=n_cells)
        c = np.bincount(fcid, minlength=n_cells)
        return _safe_divide(s, c)

    march_mean = mean_over_land(lst_march) - K_TO_C
    aprmay_mean = mean_over_land(lst_aprmay) - K_TO_C

    core_df = df.loc[core]
    vals = df.set_index("cell_id")
    march_cell = march_mean[cell_ids]
    aprmay_cell = aprmay_mean[cell_ids]
    dropped = int((np.isnan(march_cell) | np.isnan(aprmay_cell)).sum())
    used = n_cells_used - dropped
    log("Cells with both months valid:", used)
    log("Cells dropped because either month is NaN:", dropped)

    m_ok = ~np.isnan(march_cell) & ~np.isnan(aprmay_cell)
    ids_ok = cell_ids[m_ok]
    march_ok = march_cell[m_ok]
    aprmay_ok = aprmay_cell[m_ok]
    log("Mean over cells of March LST (C):", float(np.mean(march_ok)))
    log("Mean over cells of AprMay LST (C):", float(np.mean(aprmay_ok)))
    diff_cell = aprmay_ok - march_ok
    log("Mean over cells of (AprMay - March) LST (C):", float(np.mean(diff_cell)))
    rho_ma, n_ma = spearman_rho(march_ok, aprmay_ok)
    log("Spearman(March, AprMay) cell values:", rho_ma, "n_pairs:", n_ma)

    t20_march = top20(ids_ok, march_ok)
    t20_aprmay = top20(ids_ok, aprmay_ok)
    log("Top-20 March cells:", sorted(t20_march))
    log("Top-20 AprMay cells:", sorted(t20_aprmay))
    log("Jaccard(top20 March, top20 AprMay):", jaccard(t20_march, t20_aprmay))

    lst_mean_cell = vals.loc[cell_ids, "lst_mean"].to_numpy(dtype=np.float64)
    m2 = ~np.isnan(lst_mean_cell)
    ids2 = cell_ids[m2]
    lst2 = lst_mean_cell[m2]
    t20_lst = top20(ids2, lst2)
    log("Top-20 by all-date lst_mean (CSV):", sorted(t20_lst))
    log("Jaccard(top20 March, top20 lst_mean):", jaccard(t20_march, t20_lst))
    log("Jaccard(top20 AprMay, top20 lst_mean):", jaccard(t20_aprmay, t20_lst))

    # --- Top-decile sets: top 180 cells, ties broken by cell_id ascending.
    n_decile = 180
    t180_march = top_n(ids_ok, march_ok, n_decile)
    t180_aprmay = top_n(ids_ok, aprmay_ok, n_decile)
    t180_lst = top_n(ids2, lst2, n_decile)
    log(f"Top-{n_decile} March cells:", sorted(t180_march))
    log(f"Top-{n_decile} AprMay cells:", sorted(t180_aprmay))
    log(f"Top-{n_decile} by all-date lst_mean (CSV):", sorted(t180_lst))
    log(f"Jaccard(top{n_decile} March, top{n_decile} AprMay):",
        jaccard(t180_march, t180_aprmay))
    log(f"Jaccard(top{n_decile} March, top{n_decile} lst_mean):",
        jaccard(t180_march, t180_lst))
    log(f"Jaccard(top{n_decile} AprMay, top{n_decile} lst_mean):",
        jaccard(t180_aprmay, t180_lst))

    # --- Spatial clustering: 8-neighbour components on the 84 x 48 grid.
    for label, cell_set in [
        ("top20 March", t20_march),
        ("top20 AprMay", t20_aprmay),
        ("top20 lst_mean", t20_lst),
        (f"top{n_decile} March", t180_march),
        (f"top{n_decile} AprMay", t180_aprmay),
        (f"top{n_decile} lst_mean", t180_lst),
    ]:
        cell_set_ids = np.array(sorted(cell_set), dtype=np.int64)
        n_comp, largest = cluster_stats(cell_set_ids, n_cols=48)
        log(f"Clustering {label}: num_components={n_comp} "
            f"largest_component_size={largest}")

    # --- Check previously logged values are unchanged; STOP on any difference.
    rho_ma_expected = 0.9579299465605265
    j_ma_expected = 0.2903225806451613
    j_ml_expected = 0.42857142857142855
    j_al_expected = 0.7391304347826086
    log("Previously logged value checks (old vs new):")
    log(f"  Spearman(March, AprMay): old={rho_ma_expected} new={rho_ma}")
    log(f"  Jaccard(top20 March, top20 AprMay): old={j_ma_expected} new="
        f"{jaccard(t20_march, t20_aprmay)}")
    log(f"  Jaccard(top20 March, top20 lst_mean): old={j_ml_expected} new="
        f"{jaccard(t20_march, t20_lst)}")
    log(f"  Jaccard(top20 AprMay, top20 lst_mean): old={j_al_expected} new="
        f"{jaccard(t20_aprmay, t20_lst)}")
    if abs(rho_ma - rho_ma_expected) > 1e-12:
        log("STOP: Spearman(March, AprMay) changed.")
        write_log(log_path, "\n".join(lines) + "\n")
        print("\n".join(lines))
        raise SystemExit(1)
    if abs(jaccard(t20_march, t20_aprmay) - j_ma_expected) > 1e-12:
        log("STOP: Jaccard(top20 March, top20 AprMay) changed.")
        write_log(log_path, "\n".join(lines) + "\n")
        print("\n".join(lines))
        raise SystemExit(1)
    if abs(jaccard(t20_march, t20_lst) - j_ml_expected) > 1e-12:
        log("STOP: Jaccard(top20 March, top20 lst_mean) changed.")
        write_log(log_path, "\n".join(lines) + "\n")
        print("\n".join(lines))
        raise SystemExit(1)
    if abs(jaccard(t20_aprmay, t20_lst) - j_al_expected) > 1e-12:
        log("STOP: Jaccard(top20 AprMay, top20 lst_mean) changed.")
        write_log(log_path, "\n".join(lines) + "\n")
        print("\n".join(lines))
        raise SystemExit(1)

    # --- March share of valid dates per pixel, then cell median.
    denom = vc_march + vc_april + vc_may
    share = _safe_divide(vc_march, denom)
    valid_share = land.ravel() & np.isfinite(share.ravel())
    fcid = flat_cell_id[valid_share]
    share_df = pd.DataFrame({"cid": fcid, "share": share.ravel()[valid_share]})
    share_med = share_df.groupby("cid")["share"].median()
    share_cell = np.full(n_cells, np.nan)
    share_cell[share_med.index.to_numpy(dtype=np.int64)] = share_med.to_numpy(dtype=np.float64)
    share_core = share_cell[cell_ids]
    s_ok = ~np.isnan(share_core)
    log("March share of valid dates: cell median min/median/max:",
        float(np.min(share_core[s_ok])), float(np.median(share_core[s_ok])),
        float(np.max(share_core[s_ok])))
    rho_share, n_share = spearman_rho(share_core[s_ok], lst_mean_cell[s_ok])
    log("Spearman(cell median March share, all-date lst_mean):", rho_share, "n_pairs:", int(s_ok.sum()))

    # --- Spearman between all-date lst_mean (CSV) and cell vc_median (CSV).
    vc_med_cell = vals.loc[cell_ids, "vc_median"].to_numpy(dtype=np.float64)
    v_ok = ~np.isnan(vc_med_cell) & ~np.isnan(lst_mean_cell)
    rho_vc, n_vc = spearman_rho(lst_mean_cell[v_ok], vc_med_cell[v_ok])
    log("Spearman(all-date lst_mean, cell vc_median):", rho_vc, "n_pairs:", int(v_ok.sum()))

    text = "\n".join(lines) + "\n"
    write_log(log_path, text)
    print(text)
    return {"gate_max_diff": max_diff, "gate_n_bad": n_bad,
            "n_cells_used": n_cells_used, "dropped": dropped,
            "spearman_march_aprmay": rho_ma, "jaccard": jaccard(t20_march, t20_aprmay),
            "jaccard_march_lst": jaccard(t20_march, t20_lst),
            "jaccard_aprmay_lst": jaccard(t20_aprmay, t20_lst),
            "spearman_share": rho_share, "spearman_vc": rho_vc}


if __name__ == "__main__":
    main()
