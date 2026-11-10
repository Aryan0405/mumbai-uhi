"""Month seam sensitivity of the hotspot zone (Phase 7B round, rewrite).

Imports only: index_candidates, index_final, stats_utils, numpy, pandas, scipy,
os, sys, hashlib, rasterio, geopandas, config, aggregate.

Read-only reuse:
- config for DIR_DATA, DIR_COMPOSITES, CRS_METRIC, BMC_GEOGRAM constants.
- rasterio + geopandas to read the grid transform and rasterize the BMC mask
  (same method as month_seam_cells.read_grid / bmc_mask_on_grid; that module is
  NOT importable here because its import chain pulls in planetary_computer which
  is not installed, so the existing logic is reused verbatim, not re-derived).
- aggregate.assign_cells for pixel-centre to cell assignment.
- The per-cell mean aggregation reuses the exact np.bincount algorithm from
  month_seam_cells.main()'s mean_over_land (nested there, hence not directly
  importable; its body is reused verbatim here over the same land mask
  bmc_mask & (ndwi <= 0.0)). No re-derivation of a different method.

Reads S, E, zone_primary, zone_robust, zone_fragile, thin_obs from existing CSVs;
never recomputes them. Writes logs\phase7b_month_index.txt in exclusive-create
mode ("x") and data\processed\cells_index_month.csv (refuse to overwrite an
existing file; if it already exists, its sha256 is reported and it is left
untouched).
"""
import hashlib
import os
import sys

import numpy as np
import pandas as pd
import rasterio
import scipy
from rasterio.features import rasterize as rio_rasterize
import geopandas as gpd
from shapely.geometry import mapping as shp_mapping

sys.path.insert(0, "src")

import index_candidates
import index_final
import stats_utils
import aggregate
import config

CSV = os.path.join("data", "processed", "cells_500m.csv")
INDEX_CSV = os.path.join("data", "processed", "cells_index.csv")
SENS_CSV = os.path.join("data", "processed", "cells_index_sens.csv")
OUT_CSV = os.path.join("data", "processed", "cells_index_month.csv")
LOG_PATH = os.path.join("logs", "phase7b_month_index.txt")
MONTH_DIR = os.path.join(config.DIR_DATA, "composites_months")
MARCH_TIF = os.path.join(MONTH_DIR, "lst_march.tif")
APRMAY_TIF = os.path.join(MONTH_DIR, "lst_aprmay.tif")
NDWI_TIF = os.path.join(config.DIR_COMPOSITES, "ndwi.tif")
GRID_TIF = os.path.join(config.DIR_COMPOSITES, "lwir11.tif")
FEATURES = ["lst_mean", "ndvi_mean", "ndbi_mean"]
N_TOP = 180
N_TOP20 = 20
CELL_SIZE = 500.0
K_TO_C = 273.15
TOL_MEAN = 5e-3
TOL_RHO = 5e-4
TOL_J = 5e-3

TARGETS = [
    ("March mean cell LST (C)", 39.04, TOL_MEAN),
    ("AprMay mean cell LST (C)", 41.18, TOL_MEAN),
    ("AprMay - March mean cell LST (C)", 2.14, TOL_MEAN),
    ("Spearman(March, AprMay)", 0.958, TOL_RHO),
    ("top-180 Jaccard of LST alone", 0.64, TOL_J),
    ("top-20 Jaccard of LST alone", 0.29, TOL_J),
]


def _safe_divide(num, denom):
    out = np.full(num.shape, np.nan, dtype=np.float64)
    np.divide(num, denom, out=out, where=denom != 0.0)
    return out


def cell_mean_over_land(r, land_flat, flat_cell_id, n_cells):
    """Per-cell mean of a raster over land pixels (np.bincount).

    Reuses the exact algorithm from month_seam_cells.main()'s mean_over_land
    (nested there): weights = r over valid = land & isfinite, bincount by
    flat_cell_id, then safe_divide(sum, count). Cells with no valid pixel are
    NaN.
    """
    rflat = r.ravel()
    valid = land_flat & np.isfinite(rflat)
    fcid = flat_cell_id[valid]
    s = np.bincount(fcid, weights=rflat[valid], minlength=n_cells)
    c = np.bincount(fcid, minlength=n_cells)
    return _safe_divide(s, c)


def jaccard_set(a, b):
    if len(a) == 0 and len(b) == 0:
        return float("nan")
    inter = len(a & b)
    uni = len(a | b)
    return inter / uni if uni > 0 else float("nan")


def main():
    lines = []
    lines.append("python " + sys.version.split()[0])
    lines.append("numpy " + np.__version__)
    lines.append("scipy " + scipy.__version__)
    lines.append("pandas " + pd.__version__)

    # Reuse existing grid / land-mask approach (read only):
    # read_grid (open composites lwir11.tif for transform) and
    # bmc_mask_on_grid (rasterize BMC geojson) from month_seam_cells, replicated
    # here because month_seam_cells is not importable (its import chain pulls in
    # planetary_computer which is not installed). Same method, not a new one.
    with rasterio.open(GRID_TIF) as src:
        tf = src.transform
        H, W = src.shape
    bmc = gpd.read_file(config.BMC_GEOJSON).dissolve().to_crs(config.CRS_METRIC)
    bmc_mask = rio_rasterize(
        [shp_mapping(g) for g in bmc.geometry],
        out_shape=(H, W), transform=tf,
        fill=0, default_value=1, dtype="uint8",
    ).astype(bool)
    with rasterio.open(NDWI_TIF) as src:
        ndwi = src.read(1).astype(np.float64)
    land = bmc_mask & (ndwi <= 0.0)
    land_flat = land.ravel()

    minx = tf.c
    maxy = tf.f
    xs = minx + (np.arange(W) + 0.5) * tf.a
    ys = maxy + (np.arange(H) + 0.5) * tf.e
    xx, yy = np.meshgrid(xs, ys)
    n_cols = int(np.ceil(((tf.c + W * tf.a) - minx) / CELL_SIZE))
    n_rows = int(np.ceil((maxy - (tf.f + H * tf.e)) / CELL_SIZE))
    n_cells = n_rows * n_cols
    cell_rows, cell_cols, in_range = aggregate.assign_cells(
        xx.ravel(), yy.ravel(), minx, maxy, CELL_SIZE, n_rows, n_cols)
    flat_cell_id = cell_rows * n_cols + cell_cols

    # S1. Load and baseline asserts.
    grid = pd.read_csv(CSV)
    if len(grid) != 4032:
        lines.append("S1 EXPECTED 4032 grid rows, got " + str(len(grid)))
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "x", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    core_mask = (grid["in_bmc"] == True) & (grid["core"] == True) & (grid["n_land_px"] > 0)  # noqa: E712
    core_mask = core_mask & grid[FEATURES].notna().all(axis=1)
    core_grid = grid.loc[core_mask].reset_index(drop=True)
    n_core = len(core_grid)
    lines.append("S1 core cells after mask: " + str(n_core))
    if n_core != 1794:
        lines.append("S1 EXPECTED 1794 core cells, got " + str(n_core))
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "x", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)

    idx = pd.read_csv(INDEX_CSV)
    sens = pd.read_csv(SENS_CSV)
    if list(idx["cell_id"].values) != list(core_grid["cell_id"].values):
        lines.append("S1 cells_index.csv cell_id order mismatch")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "x", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    if list(sens["cell_id"].values) != list(core_grid["cell_id"].values):
        lines.append("S1 cells_index_sens.csv cell_id order mismatch")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "x", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)

    cell_ids = core_grid["cell_id"].values
    rows = core_grid["cell_row"].values
    cols = core_grid["cell_col"].values
    thin_obs = idx["thin_obs"].to_numpy(dtype=bool)
    zone_primary = idx["zone_primary"].to_numpy(dtype=bool)
    zone_noexp_stored = idx["zone_noexp"].to_numpy(dtype=bool)
    index_primary_stored = idx["index_primary"].to_numpy(dtype=float)
    index_noexp_stored = idx["index_noexp"].to_numpy(dtype=float)
    H_stored = idx["H"].to_numpy(dtype=float)
    S_stored = idx["S"].to_numpy(dtype=float)
    E_raw_stored = idx["E_raw"].to_numpy(dtype=float)
    zero_pop = core_grid["pop"].to_numpy(dtype=float) == 0.0

    zone_robust = sens["zone_robust"].to_numpy(dtype=bool)
    zone_fragile = sens["zone_fragile"].to_numpy(dtype=bool)
    n_thin = int(thin_obs.sum())
    n_zone_primary = int(zone_primary.sum())
    n_zone_robust = int(zone_robust.sum())
    n_zone_fragile = int(zone_fragile.sum())
    n_zero_pop = int(zero_pop.sum())
    lines.append("S1 zero-pop cells: " + str(n_zero_pop))
    lines.append("S1 thin_obs cells: " + str(n_thin))
    lines.append("S1 zone_primary cells: " + str(n_zone_primary))
    lines.append("S1 zone_robust cells: " + str(n_zone_robust))
    lines.append("S1 zone_fragile cells: " + str(n_zone_fragile))
    if n_zero_pop != 199 or n_thin != 83 or n_zone_primary != 180 or n_zone_robust != 107 or n_zone_fragile != 73:
        lines.append("S1 baseline count assertion failed")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "x", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)

    # S2. Monthly aggregation.
    lst_march_full = cell_mean_over_land(
        rasterio.open(MARCH_TIF).read(1).astype(np.float64), land_flat, flat_cell_id, n_cells)
    lst_aprmay_full = cell_mean_over_land(
        rasterio.open(APRMAY_TIF).read(1).astype(np.float64), land_flat, flat_cell_id, n_cells)
    march_cell = lst_march_full[cell_ids] - K_TO_C
    aprmay_cell = lst_aprmay_full[cell_ids] - K_TO_C
    n_march_nan = int(np.isnan(march_cell).sum())
    n_aprmay_nan = int(np.isnan(aprmay_cell).sum())
    lines.append("S2 monthly LST source: " + MARCH_TIF + " and " + APRMAY_TIF)
    lines.append("S2 lst_march.tif finite pixels: " + str(int(np.isfinite(rasterio.open(MARCH_TIF).read(1)).sum())))
    lines.append("S2 lst_aprmay.tif finite pixels: " + str(int(np.isfinite(rasterio.open(APRMAY_TIF).read(1)).sum())))
    lines.append("S2 core cells with NaN lst_march: " + str(n_march_nan))
    lines.append("S2 core cells with NaN lst_aprmay: " + str(n_aprmay_nan))
    if n_march_nan > 0 or n_aprmay_nan > 0:
        lines.append("S2 STOP: core cell has NaN monthly LST; not imputing, not dropping.")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "x", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)

    m_ok = ~np.isnan(march_cell) & ~np.isnan(aprmay_cell)
    march_ok = march_cell[m_ok]
    aprmay_ok = aprmay_cell[m_ok]

    # S3. GATE: reproduce Phase 3A seam numbers.
    march_mean = float(np.mean(march_ok))
    aprmay_mean = float(np.mean(aprmay_ok))
    diff_mean = float(np.mean(aprmay_ok - march_ok))
    rho_ma, n_ma = stats_utils.spearman_rho(march_ok, aprmay_ok)

    top180_march = index_candidates.top_set(march_ok, N_TOP)
    top180_aprmay = index_candidates.top_set(aprmay_ok, N_TOP)
    top20_march = index_candidates.top_set(march_ok, N_TOP20)
    top20_aprmay = index_candidates.top_set(aprmay_ok, N_TOP20)
    j180 = index_candidates.jaccard(top180_march, top180_aprmay)
    j20 = index_candidates.jaccard(top20_march, top20_aprmay)

    gate_rows = [
        ("March mean cell LST (C)", march_mean, 39.04, TOL_MEAN),
        ("AprMay mean cell LST (C)", aprmay_mean, 41.18, TOL_MEAN),
        ("AprMay - March mean cell LST (C)", diff_mean, 2.14, TOL_MEAN),
        ("Spearman(March, AprMay)", rho_ma, 0.958, TOL_RHO),
        ("top-180 Jaccard of LST alone", j180, 0.64, TOL_J),
        ("top-20 Jaccard of LST alone", j20, 0.29, TOL_J),
    ]
    mismatch_found = False
    lines.append("")
    lines.append("S3 seam reproduction gate (tolerances fixed):")
    for name, computed, expected, tol in gate_rows:
        diff = abs(computed - expected)
        status = "PASS" if diff <= tol else "FAIL"
        if status == "FAIL":
            mismatch_found = True
        lines.append("  %s: expected=%.6f observed=%.6f diff=%.6e %s" %
                     (name, expected, computed, diff, status))
    if mismatch_found:
        lines.append("S3 STOP: seam reproduction gate has FAIL; doing nothing else.")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "x", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)

    # Spearman of each monthly LST with all-date lst_mean (S5 part).
    lst_all = core_grid["lst_mean"].to_numpy(dtype=float)
    rho_m_lst, _ = stats_utils.spearman_rho(march_ok, lst_all[m_ok])
    rho_a_lst, _ = stats_utils.spearman_rho(aprmay_ok, lst_all[m_ok])
    lines.append("S5 Spearman(lst_march, lst_mean_all): %.6f n_pairs=%d" % (rho_m_lst, int(n_ma)))
    lines.append("S5 Spearman(lst_aprmay, lst_mean_all): %.6f n_pairs=%d" % (rho_a_lst, int(n_ma)))

    # S4. GATE: self-consistency of stored primary and noexp indices.
    primary_recomputed = 0.4 * H_stored + 0.4 * S_stored + 0.2 * E_raw_stored
    noexp_recomputed = 0.5 * H_stored + 0.5 * S_stored
    if not np.allclose(primary_recomputed, index_primary_stored, atol=1e-9):
        lines.append("S4 STOP: recomputed primary index differs from stored index_primary at atol 1e-9")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "x", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    recomputed_zone_primary = set(index_candidates.top_set(primary_recomputed, N_TOP))
    stored_zone_primary = set(np.where(zone_primary)[0])
    if recomputed_zone_primary != stored_zone_primary:
        lines.append("S4 STOP: recomputed top-180 set differs from stored zone_primary")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "x", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    if not np.allclose(noexp_recomputed, index_noexp_stored, atol=1e-9):
        lines.append("S4 STOP: recomputed noexp index differs from stored index_noexp at atol 1e-9")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "x", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    recomputed_zone_noexp = set(index_candidates.top_set(noexp_recomputed, N_TOP))
    stored_zone_noexp = set(np.where(zone_noexp_stored)[0])
    if recomputed_zone_noexp != stored_zone_noexp:
        lines.append("S4 STOP: recomputed noexp top-180 set differs from stored zone_noexp")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "x", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    lines.append("S4 self-consistency: primary index matches stored index_primary (atol 1e-9); top-180 set equals zone_primary")
    lines.append("S4 self-consistency: noexp index matches stored index_noexp (atol 1e-9); top-180 set equals zone_noexp")

    # S6. Monthly H: standardise each month's LST separately over the core cells (ddof=0).
    H_march = index_candidates.standardise(march_ok)
    H_aprmay = index_candidates.standardise(aprmay_ok)
    lines.append("S6 monthly H over core cells (ddof=0):")
    lines.append("  H_march mean=%.12e std=%.12e" % (float(np.mean(H_march)), float(np.std(H_march, ddof=0))))
    lines.append("  H_aprmay mean=%.12e std=%.12e" % (float(np.mean(H_aprmay)), float(np.std(H_aprmay, ddof=0))))

    # S7. Monthly indices and zones.
    S_core = S_stored[m_ok]
    E_core = E_raw_stored[m_ok]
    score_march = 0.4 * H_march + 0.4 * S_core + 0.2 * E_core
    score_aprmay = 0.4 * H_aprmay + 0.4 * S_core + 0.2 * E_core
    noexp_march = 0.5 * H_march + 0.5 * S_core
    noexp_aprmay = 0.5 * H_aprmay + 0.5 * S_core
    zone_march = index_final.zone_flag(score_march, N_TOP)
    zone_aprmay = index_final.zone_flag(score_aprmay, N_TOP)
    zone_noexp_march = index_final.zone_flag(noexp_march, N_TOP)
    zone_noexp_aprmay = index_final.zone_flag(noexp_aprmay, N_TOP)
    n_zone_march = int(zone_march.sum())
    n_zone_aprmay = int(zone_aprmay.sum())
    lines.append("S7 zone_march cells: " + str(n_zone_march))
    lines.append("S7 zone_aprmay cells: " + str(n_zone_aprmay))
    if n_zone_march != N_TOP or n_zone_aprmay != N_TOP:
        lines.append("S7 STOP: monthly zone does not have exactly " + str(N_TOP) + " cells")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "x", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)

    # S8. Report tables.
    zone_primary_m = zone_primary[m_ok]
    zone_robust_m = zone_robust[m_ok]
    zone_fragile_m = zone_fragile[m_ok]
    thin_m = thin_obs[m_ok]

    set_march = set(np.where(zone_march)[0])
    set_aprmay = set(np.where(zone_aprmay)[0])
    set_noexp_march = set(np.where(zone_noexp_march)[0])
    set_noexp_aprmay = set(np.where(zone_noexp_aprmay)[0])
    set_primary = set(np.where(zone_primary_m)[0])
    set_noexp_stored_m = set(np.where(zone_noexp_stored[m_ok])[0])

    j_march_aprmay = index_candidates.jaccard(set_march, set_aprmay)
    j_noexp_march_aprmay = index_candidates.jaccard(set_noexp_march, set_noexp_aprmay)
    j_march_primary = index_candidates.jaccard(set_march, set_primary)
    j_aprmay_primary = index_candidates.jaccard(set_aprmay, set_primary)
    j_march_noexp = index_candidates.jaccard(set_march, set_noexp_stored_m)
    j_aprmay_noexp = index_candidates.jaccard(set_aprmay, set_noexp_stored_m)

    lines.append("")
    lines.append("S8 Jaccard / intersection / union sizes:")
    lines.append("  primary: zone_march vs zone_aprmay -> Jaccard=%.6f intersection=%d union=%d" %
                 (j_march_aprmay, len(set_march & set_aprmay), len(set_march | set_aprmay)))
    lines.append("  noexp: zone_march vs zone_aprmay -> Jaccard=%.6f intersection=%d union=%d" %
                 (j_noexp_march_aprmay, len(set_noexp_march & set_noexp_aprmay), len(set_noexp_march | set_noexp_aprmay)))
    lines.append("  Jaccard(zone_march, zone_primary)=%.6f" % j_march_primary)
    lines.append("  Jaccard(zone_aprmay, zone_primary)=%.6f" % j_aprmay_primary)
    lines.append("  Jaccard(zone_march, zone_noexp_stored)=%.6f" % j_march_noexp)
    lines.append("  Jaccard(zone_aprmay, zone_noexp_stored)=%.6f" % j_aprmay_noexp)

    # Group membership tables (primary version).
    lines.append("")
    lines.append("S8 zone_primary (180) by monthly primary zone membership:")
    both_p = int((zone_primary_m & zone_march & zone_aprmay).sum())
    only_march_p = int((zone_primary_m & zone_march & ~zone_aprmay).sum())
    only_aprmay_p = int((zone_primary_m & ~zone_march & zone_aprmay).sum())
    neither_p = int((zone_primary_m & ~zone_march & ~zone_aprmay).sum())
    lines.append("  both=%d only_march=%d only_aprmay=%d neither=%d sum=%d" %
                 (both_p, only_march_p, only_aprmay_p, neither_p, both_p + only_march_p + only_aprmay_p + neither_p))
    assert both_p + only_march_p + only_aprmay_p + neither_p == 180

    lines.append("S8 zone_robust (107) by monthly primary zone membership:")
    both_r = int((zone_robust_m & zone_march & zone_aprmay).sum())
    only_march_r = int((zone_robust_m & zone_march & ~zone_aprmay).sum())
    only_aprmay_r = int((zone_robust_m & ~zone_march & zone_aprmay).sum())
    neither_r = int((zone_robust_m & ~zone_march & ~zone_aprmay).sum())
    lines.append("  both=%d only_march=%d only_aprmay=%d neither=%d sum=%d" %
                 (both_r, only_march_r, only_aprmay_r, neither_r, both_r + only_march_r + only_aprmay_r + neither_r))
    assert both_r + only_march_r + only_aprmay_r + neither_r == 107

    lines.append("S8 zone_fragile (73) by monthly primary zone membership:")
    both_f = int((zone_fragile_m & zone_march & zone_aprmay).sum())
    only_march_f = int((zone_fragile_m & zone_march & ~zone_aprmay).sum())
    only_aprmay_f = int((zone_fragile_m & ~zone_march & zone_aprmay).sum())
    neither_f = int((zone_fragile_m & ~zone_march & ~zone_aprmay).sum())
    lines.append("  both=%d only_march=%d only_aprmay=%d neither=%d sum=%d" %
                 (both_f, only_march_f, only_aprmay_f, neither_f, both_f + only_march_f + only_aprmay_f + neither_f))
    assert both_f + only_march_f + only_aprmay_f + neither_f == 73

    assert both_r + both_f == both_p
    assert only_march_r + only_march_f == only_march_p
    assert only_aprmay_r + only_aprmay_f == only_aprmay_p
    assert neither_r + neither_f == neither_p
    lines.append("S8 robust row + fragile row equals zone_primary row column by column: asserted OK")

    # Same table for noexp monthly zones.
    both_p_n = int((zone_primary_m & zone_noexp_march & zone_noexp_aprmay).sum())
    only_march_p_n = int((zone_primary_m & zone_noexp_march & ~zone_noexp_aprmay).sum())
    only_aprmay_p_n = int((zone_primary_m & ~zone_noexp_march & zone_noexp_aprmay).sum())
    neither_p_n = int((zone_primary_m & ~zone_noexp_march & ~zone_noexp_aprmay).sum())
    lines.append("S8 zone_primary (180) by monthly noexp zone membership:")
    lines.append("  both=%d only_march=%d only_aprmay=%d neither=%d sum=%d" %
                 (both_p_n, only_march_p_n, only_aprmay_p_n, neither_p_n,
                  both_p_n + only_march_p_n + only_aprmay_p_n + neither_p_n))
    assert both_p_n + only_march_p_n + only_aprmay_p_n + neither_p_n == 180

    # thin_obs: count in each monthly primary zone and each noexp zone; fisher exact.
    thin_in_march = int((thin_m & zone_march).sum())
    thin_in_aprmay = int((thin_m & zone_aprmay).sum())
    thin_in_noexp_march = int((thin_m & zone_noexp_march).sum())
    thin_in_noexp_aprmay = int((thin_m & zone_noexp_aprmay).sum())
    lines.append("S8 thin_obs in zone_march: " + str(thin_in_march))
    lines.append("S8 thin_obs in zone_aprmay: " + str(thin_in_aprmay))
    lines.append("S8 thin_obs in zone_noexp_march: " + str(thin_in_noexp_march))
    lines.append("S8 thin_obs in zone_noexp_aprmay: " + str(thin_in_noexp_aprmay))

    # 2x2 table: thin vs not thin by in zone_primary vs outside (1794 core cells).
    thin_in_zone = int((thin_obs & zone_primary).sum())
    thin_out_zone = int((thin_obs & ~zone_primary).sum())
    not_thin_in_zone = int((~thin_obs & zone_primary).sum())
    not_thin_out_zone = int((~thin_obs & ~zone_primary).sum())
    table = [[thin_in_zone, thin_out_zone], [not_thin_in_zone, not_thin_out_zone]]
    from scipy.stats import fisher_exact
    odds, fp = fisher_exact(table, alternative="two-sided")
    lines.append("S8 fisher_exact table (thin vs not thin x in zone_primary vs outside): [[%d,%d],[%d,%d]]" %
                 (table[0][0], table[0][1], table[1][0], table[1][1]))
    lines.append("S8 fisher_exact odds_ratio=%.6f p=%.6f" % (odds, fp))

    # Spearman between the two monthly primary indices.
    rho_scores, _ = stats_utils.spearman_rho(score_march, score_aprmay)
    lines.append("S8 Spearman(score_march, score_aprmay) over core cells: %.6f" % rho_scores)

    # Count of core cells in zone_primary and in neither monthly primary zone; list cell_id, row, col.
    neither_primary = zone_primary_m & ~zone_march & ~zone_aprmay
    n_neither_primary = int(neither_primary.sum())
    lines.append("S8 core cells in zone_primary and in neither monthly primary zone: " + str(n_neither_primary))
    neither_ids = cell_ids[neither_primary]
    neither_rows = rows[neither_primary]
    neither_cols = cols[neither_primary]
    for cid, r, c in zip(neither_ids, neither_rows, neither_cols):
        lines.append("  cell_id=%d row=%d col=%d" % (int(cid), int(r), int(c)))

    # S9. Park box (replicate index_sanity.py logic: cell centres to lat/lon, box test).
    import pyproj
    core_all = grid[(grid["in_bmc"] == True) & (grid["core"] == True)].copy()  # noqa: E712
    core_all = core_all.reset_index(drop=True)
    to_4326 = pyproj.Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True)
    x_centre = core_all["cell_minx"].to_numpy(dtype=float) + 250.0
    y_centre = core_all["cell_maxy"].to_numpy(dtype=float) - 250.0
    lon_centre, lat_centre = to_4326.transform(x_centre, y_centre)
    lon_centre = np.asarray(lon_centre, dtype=float)
    lat_centre = np.asarray(lat_centre, dtype=float)
    in_box = (lat_centre >= 19.17) & (lat_centre <= 19.25) & \
             (lon_centre >= 72.89) & (lon_centre <= 72.93)
    n_box = int(in_box.sum())
    lines.append("S9 park box core cell count: " + str(n_box) + " (expected 107)")
    lines.append("S9 pyproj version: " + pyproj.__version__)
    if n_box != 107:
        lines.append("S9 FLAG: park box core cell count differs from 107; not adjusted.")

    # S10. Write cells_index_month.csv (refuse to overwrite an existing file).
    out_rows = []
    n_all = len(grid)
    all_cell_ids = grid["cell_id"].values
    all_rows = grid["cell_row"].values
    all_cols = grid["cell_col"].values
    all_core = grid["core"].to_numpy(dtype=bool)
    core_pos = {int(cid): p for p, cid in enumerate(cell_ids)}
    cols_out = ["cell_id", "row", "col", "core", "lst_march_c", "lst_aprmay_c",
                "h_march", "h_aprmay", "index_primary_march", "index_primary_aprmay",
                "index_noexp_march", "index_noexp_aprmay", "zone_primary_march",
                "zone_primary_aprmay", "zone_noexp_march", "zone_noexp_aprmay",
                "zone_primary", "zone_robust", "zone_fragile", "thin_obs", "month_class"]
    for i in range(n_all):
        cid = int(all_cell_ids[i])
        is_core = bool(all_core[i])
        row = {"cell_id": cid, "row": int(all_rows[i]), "col": int(all_cols[i]), "core": is_core}
        if is_core:
            p = core_pos[cid]
            row["lst_march_c"] = float(march_cell[p])
            row["lst_aprmay_c"] = float(aprmay_cell[p])
            row["h_march"] = float(H_march[p])
            row["h_aprmay"] = float(H_aprmay[p])
            row["index_primary_march"] = float(score_march[p])
            row["index_primary_aprmay"] = float(score_aprmay[p])
            row["index_noexp_march"] = float(noexp_march[p])
            row["index_noexp_aprmay"] = float(noexp_aprmay[p])
            row["zone_primary_march"] = bool(zone_march[p])
            row["zone_primary_aprmay"] = bool(zone_aprmay[p])
            row["zone_noexp_march"] = bool(zone_noexp_march[p])
            row["zone_noexp_aprmay"] = bool(zone_noexp_aprmay[p])
            row["zone_primary"] = bool(zone_primary[p])
            row["zone_robust"] = bool(zone_robust[p])
            row["zone_fragile"] = bool(zone_fragile[p])
            row["thin_obs"] = bool(thin_obs[p])
            if zone_primary[p]:
                if zone_march[p] and zone_aprmay[p]:
                    row["month_class"] = "BOTH"
                elif zone_march[p]:
                    row["month_class"] = "ONLY_MARCH"
                elif zone_aprmay[p]:
                    row["month_class"] = "ONLY_APRMAY"
                else:
                    row["month_class"] = "NEITHER"
            else:
                row["month_class"] = ""
        else:
            row["lst_march_c"] = np.nan
            row["lst_aprmay_c"] = np.nan
            row["h_march"] = np.nan
            row["h_aprmay"] = np.nan
            row["index_primary_march"] = np.nan
            row["index_primary_aprmay"] = np.nan
            row["index_noexp_march"] = np.nan
            row["index_noexp_aprmay"] = np.nan
            row["zone_primary_march"] = False
            row["zone_primary_aprmay"] = False
            row["zone_noexp_march"] = False
            row["zone_noexp_aprmay"] = False
            row["zone_primary"] = False
            row["zone_robust"] = False
            row["zone_fragile"] = False
            row["thin_obs"] = False
            row["month_class"] = ""
        out_rows.append(row)

    out = pd.DataFrame(out_rows)
    out = out[cols_out]

    if os.path.exists(OUT_CSV):
        lines.append("S10 output already exists, not overwriting: " + OUT_CSV)
        with open(OUT_CSV, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        lines.append("S10 sha256 " + OUT_CSV + ": " + digest + " (existing file, not overwritten)")
    else:
        out.to_csv(OUT_CSV, index=False)
        back = pd.read_csv(OUT_CSV)
        if len(back) != n_all:
            lines.append("S10 read-back row count " + str(len(back)) + " != " + str(n_all))
            text = "\n".join(lines) + "\n"
            with open(LOG_PATH, "x", encoding="utf-8") as f:
                f.write(text)
            print(text)
            raise SystemExit(1)
        if back["cell_id"].nunique() != n_all:
            lines.append("S10 cell_id not unique in cells_index_month.csv")
            text = "\n".join(lines) + "\n"
            with open(LOG_PATH, "x", encoding="utf-8") as f:
                f.write(text)
            print(text)
            raise SystemExit(1)
        core_mask_back = back["core"].values.astype(bool)
        num_cols = ["lst_march_c", "lst_aprmay_c", "h_march", "h_aprmay",
                    "index_primary_march", "index_primary_aprmay",
                    "index_noexp_march", "index_noexp_aprmay"]
        if back.loc[core_mask_back, num_cols].isna().any().any():
            lines.append("S10 NaN in numeric monthly columns for core cells in read-back")
            text = "\n".join(lines) + "\n"
            with open(LOG_PATH, "x", encoding="utf-8") as f:
                f.write(text)
            print(text)
            raise SystemExit(1)
        with open(OUT_CSV, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        lines.append("S10 wrote " + OUT_CSV + " with " + str(len(back)) + " rows")
        lines.append("S10 columns: " + ", ".join(cols_out))
        lines.append("S10 sha256 " + OUT_CSV + ": " + digest)

    text = "\n".join(lines) + "\n"
    with open(LOG_PATH, "x", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
