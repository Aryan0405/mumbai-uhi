"""Phase 3A round R3: cell statistics on the 500 m grid (vectorised).

Reads data/composites/ (read only). Per 500 m cell, by pixel centre:
    bmc_px      = BMC mask
    land_px     = BMC mask AND NDWI <= 0 AND finite LST
    n_bmc_px    = count of bmc_px per cell
    n_land_px   = count of land_px per cell (differs from n_bmc_px where water exists)
    bmc_fraction = n_bmc_px / (500 * 500 / 900)
    land_share   = n_land_px / n_bmc_px (NaN if n_bmc_px == 0)
On land_px only: LST mean, median, std (C); NDVI mean; NDBI mean;
valid_count min and median; share of land pixels with valid_count <= 20.
Empty cells get NaN, never 0.
Population: the R2 cell value taken ONCE per cell (never summed per pixel).
Flags (report only, drop nothing): partial_bmc (bmc_fraction < 0.5),
water_dominated (land_share < 0.5), low_obs (cell median valid_count < 3),
no_pop (population == 0).
Cells with n_bmc_px == 0 are outside BMC: reported separately and excluded
from every flag count.
Writes data/processed/cells_500m.csv and cells_500m.geojson (gitignored).
Thermal native resolution is 100 m and 500 m cells are the unit of analysis.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import rasterio
import geopandas as gpd
from rasterio.features import rasterize as rio_rasterize
from shapely.geometry import mapping as shp_mapping
from shapely.geometry import Polygon

sys.path.insert(0, "src")
import config
from utils import write_log
from aggregate import assign_cells

DIR_COMP = config.DIR_COMPOSITES
CELL_SIZE = 500.0
CELL_AREA_PX = CELL_SIZE * CELL_SIZE / 900.0  # 30 m pixels per 500 m cell


def read_band(name):
    with rasterio.open(os.path.join(DIR_COMP, f"{name}.tif")) as src:
        return src.read(1).astype(np.float64), src.transform, src.height, src.width


def bmc_mask_30m(transform, height, width):
    bmc = gpd.read_file(config.BMC_GEOJSON).dissolve().to_crs(config.CRS_METRIC)
    return rio_rasterize(
        [shp_mapping(g) for g in bmc.geometry],
        out_shape=(height, width), transform=transform,
        fill=0, default_value=1, dtype="uint8",
    ).astype(bool)


def main():
    lwir, tf, H, W = read_band("lwir11")
    ndvi, _, _, _ = read_band("ndvi")
    ndbi, _, _, _ = read_band("ndbi")
    ndwi, _, _, _ = read_band("ndwi")
    vcount, _, _, _ = read_band("valid_count")

    bmc_mask = bmc_mask_30m(tf, H, W)
    lst = lwir - 273.15
    land_mask = bmc_mask & (ndwi <= 0.0) & np.isfinite(lst)

    minx = tf.c
    maxy = tf.f
    maxx = tf.c + W * tf.a
    miny = tf.f + H * tf.e
    n_cols = int(np.ceil((maxx - minx) / CELL_SIZE))
    n_rows = int(np.ceil((maxy - miny) / CELL_SIZE))
    n_cells = n_rows * n_cols

    xs = minx + (np.arange(W) + 0.5) * tf.a
    ys = maxy + (np.arange(H) + 0.5) * tf.e
    xx, yy = np.meshgrid(xs, ys)
    cell_rows, cell_cols, in_range = assign_cells(xx.ravel(), yy.ravel(),
                                                  minx, maxy, CELL_SIZE,
                                                  n_rows, n_cols)
    flat_cell_id = cell_rows * n_cols + cell_cols  # valid only where in_range

    flat_bmc = bmc_mask.ravel()
    flat_land = land_mask.ravel()
    use = in_range

    n_bmc_px = np.bincount(flat_cell_id[flat_bmc & use], minlength=n_cells)
    n_land_px = np.bincount(flat_cell_id[flat_land & use], minlength=n_cells)

    bmc_fraction = n_bmc_px / CELL_AREA_PX
    land_share = np.full(n_cells, np.nan)
    np.divide(n_land_px, n_bmc_px, out=land_share, where=n_bmc_px > 0)

    # Stats on land pixels only, via pandas groupby (no per-cell Python loop).
    land_ids = flat_cell_id[flat_land & use]
    df_land = pd.DataFrame({
        "cid": land_ids,
        "lst": lst.ravel()[flat_land & use],
        "ndvi": ndvi.ravel()[flat_land & use],
        "ndbi": ndbi.ravel()[flat_land & use],
        "vc": vcount.ravel()[flat_land & use],
    })
    g = df_land.groupby("cid")
    agg = g.agg(lst_mean=("lst", "mean"),
                lst_median=("lst", "median"),
                lst_std=("lst", "std"),
                ndvi_mean=("ndvi", "mean"),
                ndbi_mean=("ndbi", "mean"),
                vc_min=("vc", "min"),
                vc_median=("vc", "median"),
                vc_le20_count=("vc", lambda s: int((s <= 20).sum())))
    agg = agg.sort_index()
    cids = agg.index.to_numpy(dtype=np.int64)

    lst_mean = np.full(n_cells, np.nan)
    lst_med = np.full(n_cells, np.nan)
    lst_std = np.full(n_cells, np.nan)
    ndvi_mean = np.full(n_cells, np.nan)
    ndbi_mean = np.full(n_cells, np.nan)
    vc_min = np.full(n_cells, np.nan)
    vc_med = np.full(n_cells, np.nan)
    vc_le20_share = np.full(n_cells, np.nan)

    lst_mean[cids] = agg["lst_mean"].to_numpy(dtype=np.float64)
    lst_med[cids] = agg["lst_median"].to_numpy(dtype=np.float64)
    lst_std[cids] = agg["lst_std"].to_numpy(dtype=np.float64)
    ndvi_mean[cids] = agg["ndvi_mean"].to_numpy(dtype=np.float64)
    ndbi_mean[cids] = agg["ndbi_mean"].to_numpy(dtype=np.float64)
    vc_min[cids] = agg["vc_min"].to_numpy(dtype=np.float64)
    vc_med[cids] = agg["vc_median"].to_numpy(dtype=np.float64)
    vc_ok = n_land_px[cids] > 0
    vc_counts = agg["vc_le20_count"].to_numpy(dtype=np.float64)
    vc_le20_share[cids[vc_ok]] = vc_counts[vc_ok] / n_land_px[cids[vc_ok]]

    # Population: R2 cell value taken ONCE per cell, never summed per pixel.
    pop_path = os.path.join(config.DIR_DATA, "population", "cells_population.npy")
    cell_pop = np.load(pop_path).astype(np.float64).ravel()
    if cell_pop.size != n_cells:
        msg = (f"STOP: population array size {cell_pop.size} != n_cells {n_cells}")
        print(msg)
        raise SystemExit(msg)
    pop = cell_pop
    pop_grid_sum = float(pop.sum())
    print(f"  R2 grid sum of population = {pop_grid_sum:.2f}")
    print(f"  Sum of population column (once per cell) = {float(pop.sum()):.2f}")
    assert abs(float(pop.sum()) - pop_grid_sum) < 1e-9

    # Flags only among BMC cells (n_bmc_px > 0). Cells with n_bmc_px == 0 are
    # outside BMC: reported separately, excluded from every flag count.
    bmc_cells = n_bmc_px > 0
    n_outside_bmc = int((~bmc_cells).sum())
    print(f"  Cells with n_bmc_px == 0 (outside BMC): {n_outside_bmc}")

    partial_bmc = bmc_fraction < 0.5
    water_dominated = land_share < 0.5
    low_obs = vc_med < 3.0
    no_pop = pop == 0.0
    any_flag = partial_bmc | water_dominated | low_obs | no_pop

    def count_bmc(mask):
        return int((mask & bmc_cells).sum())

    n_partial_bmc = count_bmc(partial_bmc)
    n_water_dominated = count_bmc(water_dominated)
    n_low_obs = count_bmc(low_obs)
    n_no_pop = count_bmc(no_pop)
    n_any_flag = count_bmc(any_flag)
    n_no_flags = int((bmc_cells & (~any_flag)).sum())

    # Spearman between LST mean and LST median across BMC cells with n_land_px > 0.
    # Computed with vectorised numpy (average ranks + Pearson of ranks) because
    # scipy.stats.spearmanr crashes in this environment.
    spear_mask = bmc_cells & (n_land_px > 0)
    valid_pair = spear_mask & ~np.isnan(lst_mean) & ~np.isnan(lst_med)
    rho = None
    if int(valid_pair.sum()) > 1:
        a = lst_mean[valid_pair]
        b = lst_med[valid_pair]

        def rankdata_average(v):
            order = np.argsort(v, kind="mergesort")
            sorted_v = v[order]
            n = v.size
            is_start = np.concatenate(([True], sorted_v[1:] != sorted_v[:-1]))
            run_id = np.cumsum(is_start) - 1
            run_sum = np.bincount(run_id, weights=np.arange(1, n + 1, dtype=np.float64))
            run_count = np.bincount(run_id)
            ranks_sorted = run_sum / run_count
            ranks = np.empty(n, dtype=np.float64)
            ranks[order] = ranks_sorted[run_id]
            return ranks

        ra = rankdata_average(a)
        rb = rankdata_average(b)
        ca = ra - ra.mean()
        cb = rb - rb.mean()
        denom = np.sqrt(np.sum(ca * ca) * np.sum(cb * cb))
        rho = float(np.sum(ca * cb) / denom) if denom > 0.0 else np.nan

    print(f"  Flags (report only, drop nothing; BMC cells only):")
    print(f"    partial_bmc (bmc_fraction < 0.5): {n_partial_bmc}")
    print(f"    water_dominated (land_share < 0.5): {n_water_dominated}")
    print(f"    low_obs (cell median valid_count < 3): {n_low_obs}")
    print(f"    no_pop (population == 0): {n_no_pop}")
    print(f"    Cells with any flag: {n_any_flag}")
    print(f"    Cells with no flags: {n_no_flags}")
    if rho is not None:
        print(f"  Spearman(LST mean, LST median) across BMC cells with n_land_px > 0 = {rho:.4f}")

    # Sanity assertions that print their results.
    n_bmc_cells = int(bmc_cells.sum())
    ok_a = n_bmc_cells == 2005
    print(f"  ASSERT number of BMC cells == 2005: {n_bmc_cells} {'OK' if ok_a else 'FAIL'}")
    if not ok_a:
        raise SystemExit(f"STOP: BMC cells {n_bmc_cells} != 2005")

    sum_nbmc = int(n_bmc_px.sum())
    ok_b = sum_nbmc == 509028
    print(f"  ASSERT sum of n_bmc_px == 509028: {sum_nbmc} {'OK' if ok_b else 'FAIL'}")
    if not ok_b:
        raise SystemExit(f"STOP: sum n_bmc_px {sum_nbmc} != 509028")

    nonfinite_lst = int((bmc_mask & (ndwi <= 0.0) & (~np.isfinite(lst))).sum())
    expected_land = 494795 - nonfinite_lst
    sum_nland = int(n_land_px.sum())
    diff_land = sum_nland - expected_land
    ok_c = diff_land == 0
    print(f"  ASSERT sum of n_land_px == 494795 - non-finite LST pixels ({expected_land}): "
          f"{sum_nland} (diff={diff_land}) {'OK' if ok_c else 'FAIL'}")
    if not ok_c:
        raise SystemExit(f"STOP: sum n_land_px {sum_nland} != expected {expected_land}")

    # Build output table (all cells).
    df = pd.DataFrame({
        "cell_id": np.arange(n_cells),
        "cell_row": np.arange(n_cells) // n_cols,
        "cell_col": np.arange(n_cells) % n_cols,
        "n_bmc_px": n_bmc_px,
        "n_land_px": n_land_px,
        "bmc_fraction": bmc_fraction,
        "land_share": land_share,
        "lst_mean": lst_mean,
        "lst_median": lst_med,
        "lst_std": lst_std,
        "ndvi_mean": ndvi_mean,
        "ndbi_mean": ndbi_mean,
        "vc_min": vc_min,
        "vc_median": vc_med,
        "vc_le20_share": vc_le20_share,
        "pop": pop,
        "partial_bmc": partial_bmc,
        "water_dominated": water_dominated,
        "low_obs": low_obs,
        "no_pop": no_pop,
    })

    os.makedirs(os.path.join(config.DIR_DATA, "processed"), exist_ok=True)
    out_csv = os.path.join(config.DIR_DATA, "processed", "cells_500m.csv")
    df.to_csv(out_csv, index=False)
    print(f"  CSV written to {out_csv}")

    out_geojson = os.path.join(config.DIR_DATA, "processed", "cells_500m.geojson")
    features = []
    for cid in range(n_cells):
        r = int(cid // n_cols)
        c = int(cid % n_cols)
        x0 = minx + c * CELL_SIZE
        x1 = x0 + CELL_SIZE
        y1 = maxy - r * CELL_SIZE
        y0 = y1 - CELL_SIZE

        def clean(v):
            return None if (isinstance(v, float) and np.isnan(v)) else v

        feat = {
            "type": "Feature",
            "properties": {
                "cell_id": int(cid),
                "row": r,
                "col": c,
                "n_bmc_px": int(n_bmc_px[cid]),
                "n_land_px": int(n_land_px[cid]),
                "lst_mean": clean(float(lst_mean[cid])),
                "lst_median": clean(float(lst_med[cid])),
                "ndvi_mean": clean(float(ndvi_mean[cid])),
                "ndbi_mean": clean(float(ndbi_mean[cid])),
                "pop": float(pop[cid]),
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[x0, y1], [x1, y1], [x1, y0], [x0, y0], [x0, y1]]],
            },
        }
        features.append(feat)
    geojson = {"type": "FeatureCollection", "features": features}
    with open(out_geojson, "w", encoding="utf-8") as f:
        json.dump(geojson, f)
    print(f"  GeoJSON written to {out_geojson}")

    # Print first 10 rows of BMC cells and describe() of numeric columns.
    df_bmc = df[bmc_cells]
    print("")
    print("First 10 rows of BMC cells:")
    print(df_bmc.head(10).to_string())
    print("")
    print("Describe() of numeric columns:")
    print(df.select_dtypes(include="number").describe().to_string())

    lines = [
        f"Cell stats (500 m grid, EPSG:32643, BMC land pixels):",
        f"  n_rows={n_rows}, n_cols={n_cols}, total_cells={n_cells}",
        f"  Cells with n_bmc_px > 0 (BMC cells): {n_bmc_cells}",
        f"  Cells with n_bmc_px == 0 (outside BMC): {n_outside_bmc}",
        f"  Sum of n_bmc_px: {sum_nbmc}",
        f"  Sum of n_land_px: {sum_nland}",
        f"  Thermal native resolution is 100 m; 500 m cells are the unit of analysis.",
        f"",
        f"  Flags (report only, drop nothing; BMC cells only):",
        f"    partial_bmc (bmc_fraction < 0.5): {n_partial_bmc}",
        f"    water_dominated (land_share < 0.5): {n_water_dominated}",
        f"    low_obs (cell median valid_count < 3): {n_low_obs}",
        f"    no_pop (population == 0): {n_no_pop}",
        f"    Cells with any flag: {n_any_flag}",
        f"    Cells with no flags: {n_no_flags}",
    ]
    if rho is not None:
        lines.append(f"  Spearman(LST mean, LST median) across BMC cells with n_land_px > 0 = {rho:.4f}")
    log_path = os.path.join(config.DIR_LOGS, "phase3a_cell_stats.txt")
    write_log(log_path, "\n".join(lines))
    print(f"  Log written to {log_path}")
    return {"n_bmc_cells": n_bmc_cells, "sum_nbmc": sum_nbmc,
            "sum_nland": sum_nland, "n_outside_bmc": n_outside_bmc,
            "n_partial_bmc": n_partial_bmc, "n_water_dominated": n_water_dominated,
            "n_low_obs": n_low_obs, "n_no_pop": n_no_pop,
            "n_no_flags": n_no_flags, "spearman": rho}


if __name__ == "__main__":
    main()
