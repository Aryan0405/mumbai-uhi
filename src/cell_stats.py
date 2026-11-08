"""Phase 3A round R2: cell statistics on the 500 m grid (vectorised).

Reads data/composites/ (read only). Per 500 m cell, by pixel centre:
    bmc_px      = BMC mask
    land_px     = BMC mask AND NDWI <= 0 AND finite LST
    n_grid_px   = count of all 30 m pixel centres assigned to the cell (in_range only)
    n_bmc_px    = count of bmc_px per cell
    n_land_px   = count of land_px per cell (differs from n_bmc_px where water exists)
    bmc_fraction = n_bmc_px / n_grid_px (NaN if n_grid_px == 0)
    land_share   = n_land_px / n_bmc_px (NaN if n_bmc_px == 0)
    bmc_area_km2 = 0.25 * n_bmc_px / n_grid_px (NaN if n_grid_px == 0)
    land_area_km2 = 0.25 * n_land_px / n_grid_px (NaN if n_grid_px == 0)
On land_px only: LST mean, median, std (C, ddof=1); NDVI mean; NDBI mean;
valid_count min and median; share of land pixels with valid_count <= 20.
Empty cells get NaN, never 0.
Population: the R2 cell value taken ONCE per cell (never summed per pixel).
Density columns: pop_density_bmc = pop / bmc_area_km2, pop_density_land =
pop / land_area_km2, pop_density_full = pop / 0.25 (people per km2; NaN where
the denominator is 0).
Flags (report only, drop nothing; all False outside BMC):
    partial_bmc (bmc_fraction < 0.5), water_dominated (land_share < 0.5),
    low_obs (cell median valid_count < 3), no_pop (population == 0),
    thin_obs (cell median valid_count <= 20).
core = in_bmc AND NOT partial_bmc AND NOT water_dominated.
core = in_bmc AND NOT partial_bmc AND NOT water_dominated.
Cells with n_bmc_px == 0 are outside BMC: reported separately and excluded
from every flag count.
Writes data/processed/cells_500m.csv and cells_500m.geojson (gitignored).
Thermal native resolution is 100 m; 500 m cells are the unit of analysis.
"""
import os
import sys

import numpy as np
import pandas as pd
import rasterio
import geopandas as gpd
from rasterio.features import rasterize as rio_rasterize
from shapely.geometry import mapping as shp_mapping
from shapely import box

sys.path.insert(0, "src")
import config
from utils import write_log
from aggregate import assign_cells, sum_per_cell
from stats_utils import spearman_rho

DIR_COMP = config.DIR_COMPOSITES
CELL_SIZE = 500.0
PIXEL_AREA_M2 = 900.0
FULL_CELL_AREA_KM2 = 0.25  # 500 m x 500 m


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


def _safe_divide(num, denom):
    out = np.full(num.shape, np.nan, dtype=np.float64)
    np.divide(num, denom, out=out, where=denom != 0.0)
    return out


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
    full_cell_px = CELL_SIZE * CELL_SIZE / PIXEL_AREA_M2  # theoretical 30 m px per cell

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

    # n_grid_px: all pixel centres assigned to the cell (in_range only).
    n_grid_px = np.bincount(flat_cell_id[use], minlength=n_cells)
    n_bmc_px = np.bincount(flat_cell_id[flat_bmc & use], minlength=n_cells)
    n_land_px = np.bincount(flat_cell_id[flat_land & use], minlength=n_cells)

    bmc_fraction = _safe_divide(n_bmc_px, n_grid_px)
    land_share = _safe_divide(n_land_px, n_bmc_px)
    # Footprint-based areas (cells hold 256, 272 or 289 pixels, so pixel-count
    # areas are biased by grid position).
    bmc_area_km2 = _safe_divide(0.25 * n_bmc_px, n_grid_px)
    land_area_km2 = _safe_divide(0.25 * n_land_px, n_grid_px)

    # Stats on land pixels only, via pandas groupby (no per-cell Python loop).
    land_ids = flat_cell_id[flat_land & use]
    df_land = pd.DataFrame({
        "cid": land_ids,
        "lst": lst.ravel()[flat_land & use],
        "ndvi": ndvi.ravel()[flat_land & use],
        "ndbi": ndbi.ravel()[flat_land & use],
        "vc": vcount.ravel()[flat_land & use],
    })
    # Vectorised boolean column summed in the groupby (no lambda).
    df_land["vc_le20"] = df_land["vc"] <= 20.0
    g = df_land.groupby("cid")
    agg = g.agg(lst_mean=("lst", "mean"),
                lst_median=("lst", "median"),
                lst_std=("lst", "std"),
                ndvi_mean=("ndvi", "mean"),
                ndbi_mean=("ndbi", "mean"),
                vc_min=("vc", "min"),
                vc_median=("vc", "median"),
                vc_le20_count=("vc_le20", "sum"))
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
    n_land_c = n_land_px[cids].astype(np.float64)
    vc_counts = agg["vc_le20_count"].to_numpy(dtype=np.float64)
    vc_ok = n_land_c > 0
    vc_le20_share[cids[vc_ok]] = vc_counts[vc_ok] / n_land_c[vc_ok]

    # Population: R2 cell value taken ONCE per cell, never summed per pixel.
    pop_path = os.path.join(config.DIR_DATA, "population", "cells_population.npy")
    pop = np.load(pop_path).astype(np.float64).ravel()
    if pop.size != n_cells:
        msg = f"STOP: population array size {pop.size} != n_cells {n_cells}"
        print(msg)
        raise SystemExit(msg)

    # Density columns (people per km2); NaN where denominator is 0.
    pop_density_bmc = _safe_divide(pop, bmc_area_km2)
    pop_density_land = _safe_divide(pop, land_area_km2)
    pop_density_full = _safe_divide(pop, np.full(n_cells, FULL_CELL_AREA_KM2))

    # Flags, all False outside BMC.
    bmc_cells = n_bmc_px > 0
    in_bmc = bmc_cells
    n_outside_bmc = int((~in_bmc).sum())

    partial_bmc = (bmc_fraction < 0.5) & in_bmc
    water_dominated = (land_share < 0.5) & in_bmc
    low_obs = (vc_med < 3.0) & in_bmc
    no_pop = (pop == 0.0) & in_bmc
    thin_obs = in_bmc & (vc_med <= 20.0)
    any_flag = partial_bmc | water_dominated | low_obs | no_pop | thin_obs

    def count_bmc(mask):
        return int((mask & in_bmc).sum())

    n_partial_bmc = count_bmc(partial_bmc)
    n_water_dominated = count_bmc(water_dominated)
    n_low_obs = count_bmc(low_obs)
    n_no_pop = count_bmc(no_pop)
    n_thin_obs = count_bmc(thin_obs)
    n_any_flag = count_bmc(any_flag)
    n_no_flags = int((in_bmc & (~any_flag)).sum())
    land_with_data = in_bmc & (n_land_px > 0)
    min_vc_med_land = float(np.min(vc_med[land_with_data])) if int(land_with_data.sum()) else np.nan

    core = in_bmc & (~partial_bmc) & (~water_dominated)
    n_core = int(core.sum())
    n_in_bmc_no_pop_not_core = int(((in_bmc & no_pop) & (~core)).sum())

    # Max bmc_fraction must be at most 1.0.
    max_bmc_fraction = float(np.nanmax(bmc_fraction[in_bmc])) if int(in_bmc.sum()) else np.nan
    max_bmc_area = float(np.nanmax(bmc_area_km2[in_bmc])) if int(in_bmc.sum()) else np.nan
    max_grid_px = int(n_grid_px[in_bmc].max()) if int(in_bmc.sum()) else 0
    n_bmc_below_full = int(((in_bmc) & (n_grid_px < max_grid_px)).sum()) if int(in_bmc.sum()) else 0

    # Density report for BMC cells with pop > 0.
    pop_pos_bmc = in_bmc & (pop > 0.0)
    n_pop_pos_bmc = int(pop_pos_bmc.sum())
    if n_pop_pos_bmc > 0:
        pdb = pop_density_bmc[pop_pos_bmc]
        pdl = pop_density_land[pop_pos_bmc]
        pdf = pop_density_full[pop_pos_bmc]
        max_density_bmc = float(np.max(pdb))
        med_density_bmc = float(np.median(pdb))
        max_density_land = float(np.max(pdl))
        med_density_land = float(np.median(pdl))
        max_density_full = float(np.max(pdf))
        med_density_full = float(np.median(pdf))
        with np.errstate(invalid="ignore", divide="ignore"):
            rel_diff = np.abs((pdl - pdf) / pdf)
        n_density_diff_gt20 = int((rel_diff > 0.20).sum())
    else:
        max_density_bmc = med_density_bmc = np.nan
        max_density_land = med_density_land = np.nan
        max_density_full = med_density_full = np.nan
        n_density_diff_gt20 = 0

    # Spearman between LST mean and LST median across BMC cells with n_land_px > 0.
    spear_mask = in_bmc & (n_land_px > 0)
    valid_pair = spear_mask & (~np.isnan(lst_mean)) & (~np.isnan(lst_med))
    rho, n_spear = spearman_rho(lst_mean[valid_pair], lst_med[valid_pair])

    # Number of BMC cells with n_land_px == 1 (lst_std is NaN there, ddof=1).
    n_land_eq1 = int(((in_bmc) & (n_land_px == 1)).sum())

    # Build output table (all cells).
    df = pd.DataFrame({
        "cell_id": np.arange(n_cells),
        "cell_row": np.arange(n_cells) // n_cols,
        "cell_col": np.arange(n_cells) % n_cols,
        "n_grid_px": n_grid_px,
        "n_bmc_px": n_bmc_px,
        "n_land_px": n_land_px,
        "bmc_fraction": bmc_fraction,
        "land_share": land_share,
        "bmc_area_km2": bmc_area_km2,
        "land_area_km2": land_area_km2,
        "lst_mean": lst_mean,
        "lst_median": lst_med,
        "lst_std": lst_std,
        "ndvi_mean": ndvi_mean,
        "ndbi_mean": ndbi_mean,
        "vc_min": vc_min,
        "vc_median": vc_med,
        "vc_le20_share": vc_le20_share,
        "pop": pop,
        "pop_density_bmc": pop_density_bmc,
        "pop_density_land": pop_density_land,
        "pop_density_full": pop_density_full,
        "in_bmc": in_bmc,
        "partial_bmc": partial_bmc,
        "water_dominated": water_dominated,
        "low_obs": low_obs,
        "no_pop": no_pop,
        "thin_obs": thin_obs,
        "core": core,
        "cell_minx": minx + (np.arange(n_cells) % n_cols) * CELL_SIZE,
        "cell_maxy": maxy - (np.arange(n_cells) // n_cols) * CELL_SIZE,
    })

    os.makedirs(os.path.join(config.DIR_DATA, "processed"), exist_ok=True)
    out_csv = os.path.join(config.DIR_DATA, "processed", "cells_500m.csv")
    df.to_csv(out_csv, index=False)
    print(f"CSV written to {out_csv}")

    out_geojson = os.path.join(config.DIR_DATA, "processed", "cells_500m.geojson")
    # Geometry built without a Python for loop over cells (shapely.box with arrays).
    rows_arr = (np.arange(n_cells) // n_cols).astype(np.float64)
    cols_arr = (np.arange(n_cells) % n_cols).astype(np.float64)
    x0 = minx + cols_arr * CELL_SIZE
    x1 = x0 + CELL_SIZE
    y1 = maxy - rows_arr * CELL_SIZE
    y0 = y1 - CELL_SIZE
    geometries = box(x0, y0, x1, y1)  # vectorised; no per-cell Python loop

    df_in_bmc_only = df[in_bmc].copy()
    geoms_in_bmc = geometries[in_bmc]
    gdf = gpd.GeoDataFrame(df_in_bmc_only,
                           geometry=geoms_in_bmc, crs=config.CRS_METRIC)
    gdf = gdf.to_crs(config.CRS_LONLAT)
    gdf.to_file(out_geojson, driver="GeoJSON")
    n_features = len(gdf)
    print(f"GeoJSON written to {out_geojson} ({n_features} features)")

    # Round trip check: read CSV back from disk and assert.
    df_back = pd.read_csv(out_csv)
    checks = []
    checks.append(("sum of pop within 1 of 13661494",
                   abs(float(df_back["pop"].sum()) - 13661494.0) <= 1.0,
                   f"sum pop = {df_back['pop'].sum():.2f}"))
    checks.append(("sum of n_bmc_px equals 509028",
                   int(df_back["n_bmc_px"].sum()) == 509028,
                   f"sum n_bmc_px = {int(df_back['n_bmc_px'].sum())}"))
    checks.append(("sum of n_land_px equals 494795",
                   int(df_back["n_land_px"].sum()) == 494795,
                   f"sum n_land_px = {int(df_back['n_land_px'].sum())}"))
    checks.append(("number of rows equals 4032",
                   len(df_back) == 4032,
                   f"rows = {len(df_back)}"))
    checks.append(("number of in_bmc cells equals 2005",
                   int(df_back["in_bmc"].sum()) == 2005,
                   f"in_bmc cells = {int(df_back['in_bmc'].sum())}"))
    roundtrip_ok = True
    for name, ok, detail in checks:
        status = "OK" if ok else "FAIL"
        print(f"ASSERT {name}: {detail} -> {status}")
        lines_local = []
        lines_local.append(f"ASSERT {name}: {detail} -> {status}")
        if not ok:
            roundtrip_ok = False
    if not roundtrip_ok:
        raise SystemExit("STOP: round trip check failed.")

    # Cross-checks (print only).
    n_pop_pos_bf_lt01 = int(((in_bmc) & (pop > 0.0) & (bmc_fraction < 0.1)).sum())
    n_pop0_bf_gt09 = int(((in_bmc) & (pop == 0.0) & (bmc_fraction > 0.9)).sum())
    print(f"BMC cells with pop > 0 and bmc_fraction < 0.1: {n_pop_pos_bf_lt01}")
    print(f"BMC cells with pop == 0 and bmc_fraction > 0.9: {n_pop0_bf_gt09}")

    # GeoJSON read-back check.
    gdf = gpd.read_file(out_geojson)
    gdf = gdf.to_crs(config.CRS_LONLAT)
    bounds = gdf.total_bounds  # minx, miny, maxx, maxy in degrees
    lon_ok = (bounds[0] >= 72.77) and (bounds[2] <= 72.99)
    lat_ok = (bounds[1] >= 18.89) and (bounds[3] <= 19.27)
    geojson_pop_sum = float(gdf["pop"].sum()) if "pop" in gdf.columns else np.nan
    csv_pop_sum = float(df.loc[in_bmc, "pop"].sum())
    geojson_ok = (len(gdf) == 2005) and lon_ok and lat_ok
    print(f"GeoJSON read-back: features={len(gdf)}, CRS={gdf.crs}")
    print(f"  bounds (lon_min, lat_min, lon_max, lat_max) = "
          f"({bounds[0]:.6f}, {bounds[1]:.6f}, {bounds[2]:.6f}, {bounds[3]:.6f})")
    print(f"  bounds inside box (lon 72.77-72.99, lat 18.89-19.27): {bool(lon_ok and lat_ok)}")
    print(f"  GeoJSON pop sum = {geojson_pop_sum:.2f}, CSV pop sum (in_bmc) = {csv_pop_sum:.2f}")
    if not geojson_ok:
        raise SystemExit("STOP: GeoJSON read-back check failed.")

    # Logging output.
    df_in_bmc = df[in_bmc]
    numeric_cols = df_in_bmc.select_dtypes(include="number").columns
    nan_counts = df_in_bmc[numeric_cols].isna().sum()

    lines = [
        f"Cell stats (500 m grid, EPSG:32643, BMC land pixels):",
        f"  n_rows={n_rows}, n_cols={n_cols}, total_cells={n_cells}",
        f"  Cells with n_bmc_px > 0 (BMC cells / in_bmc): {int(in_bmc.sum())}",
        f"  Cells with n_bmc_px == 0 (outside BMC): {n_outside_bmc}",
        f"  Sum of n_bmc_px: {int(n_bmc_px.sum())}",
        f"  Sum of n_land_px: {int(n_land_px.sum())}",
        f"  Thermal native resolution is 100 m; 500 m cells are the unit of analysis.",
        f"",
        f"  n_grid_px distribution among BMC cells (value counts):",
        f"    {df_in_bmc['n_grid_px'].value_counts().sort_index().to_string()}",
        f"  Max bmc_fraction among BMC cells = {max_bmc_fraction:.6f} (must be <= 1.0)",
        f"  Max bmc_area_km2 among BMC cells = {max_bmc_area:.6f} (must be <= 0.25)",
        f"  Max n_grid_px (full-cell count) among BMC cells = {max_grid_px}",
        f"  BMC cells with n_grid_px below full-cell count = {n_bmc_below_full}",
        f"",
        f"  Areas: bmc_area_km2 = 0.25 * n_bmc_px / n_grid_px; land_area_km2 = 0.25 * n_land_px / n_grid_px",
        f"  Densities (people per km2): pop_density_bmc, pop_density_land, pop_density_full (= pop / 0.25)",
        f"  BMC cells with pop > 0: {n_pop_pos_bmc}",
        f"    pop_density_bmc: max={max_density_bmc:.4f}, median={med_density_bmc:.4f}",
        f"    pop_density_land: max={max_density_land:.4f}, median={med_density_land:.4f}",
        f"    pop_density_full: max={max_density_full:.4f}, median={med_density_full:.4f}",
        f"    cells where pop_density_land differs from pop_density_full by > 20%: {n_density_diff_gt20}",
        f"",
        f"  Flags (report only, drop nothing; BMC cells only):",
        f"    partial_bmc (bmc_fraction < 0.5): {n_partial_bmc}",
        f"    water_dominated (land_share < 0.5): {n_water_dominated}",
        f"    low_obs (cell median valid_count < 3): {n_low_obs}",
        f"    no_pop (population == 0): {n_no_pop}",
        f"    Cells with any flag: {n_any_flag}",
        f"    Cells with no flags: {n_no_flags}",
        f"    core (in_bmc AND NOT partial_bmc AND NOT water_dominated): {n_core}",
        f"    in_bmc cells that are no_pop and not in core: {n_in_bmc_no_pop_not_core}",
        f"    low_obs fired {n_low_obs} time(s).",
        f"    thin_obs (cell median valid_count <= 20): {n_thin_obs}",
        f"    min vc_median among in_bmc cells with land: {min_vc_med_land}",
        f"",
        f"  lst_std uses pandas groupby std with ddof=1 (sample std).",
        f"  BMC cells with n_land_px == 1 (lst_std NaN there): {n_land_eq1}",
        f"",
        f"  Spearman(LST mean, LST median) across BMC cells with n_land_px > 0 = {rho:.4f} (n_pairs={n_spear})",
        f"",
        f"  Cross-checks (print only):",
        f"    BMC cells with pop > 0 and bmc_fraction < 0.1: {n_pop_pos_bf_lt01}",
        f"    BMC cells with pop == 0 and bmc_fraction > 0.9: {n_pop0_bf_gt09}",
        f"",
        f"  Round trip check (read back {out_csv}): all assertions OK.",
        f"  GeoJSON written to {out_geojson} ({n_features} in_bmc features, reprojected to EPSG:4326).",
        f"  Exact file names written: data/processed/cells_500m.csv, data/processed/cells_500m.geojson",
        f"",
        f"  First 10 rows of in_bmc cells (all columns):",
        f"{df_in_bmc.head(10).to_string()}",
        f"",
        f"  describe() of numeric columns on in_bmc cells only:",
        f"{df_in_bmc[numeric_cols].describe().to_string()}",
        f"",
        f"  Count of NaN per column among in_bmc cells:",
        f"{nan_counts.to_string()}",
    ]
    log_path = os.path.join(config.DIR_LOGS, "phase3a_cell_stats.txt")
    write_log(log_path, "\n".join(lines))
    print(f"Log written to {log_path}")
    return {"n_bmc_cells": int(in_bmc.sum()), "n_outside_bmc": n_outside_bmc,
            "n_core": n_core, "spearman": rho, "n_land_eq1": n_land_eq1}


if __name__ == "__main__":
    main()
