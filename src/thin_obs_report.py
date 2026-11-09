"""thin_obs spatial and zone checks (Phase 6 round).

Imports only: thin_checks, index_candidates, numpy, pandas, scipy, os, sys,
hashlib.
"""
import hashlib
import os
import sys

import numpy as np
import pandas as pd
import scipy
from scipy.stats import fisher_exact, mannwhitneyu

sys.path.insert(0, "src")

import index_candidates
import thin_checks

CSV = os.path.join("data", "processed", "cells_500m.csv")
INDEX_CSV = os.path.join("data", "processed", "cells_index.csv")
SENS_CSV = os.path.join("data", "processed", "cells_index_sens.csv")
LOG_PATH = os.path.join("logs", "phase6_thin.txt")
ROWS = 84
COLS = 48
N_TOP = 180
N_PERM = 5000
SEED = 2026
FEATURES = ["lst_mean", "ndvi_mean", "ndbi_mean"]


def main():
    if os.path.exists(LOG_PATH):
        print("error: log path already exists, will not overwrite: " + LOG_PATH)
        raise SystemExit(2)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    lines = []
    lines.append("python " + sys.version.split()[0])
    lines.append("numpy " + np.__version__)
    lines.append("scipy " + scipy.__version__)
    lines.append("pandas " + pd.__version__)
    lines.append("N_PERM=%d SEED=%d N_TOP=%d" % (N_PERM, SEED, N_TOP))

    grid = pd.read_csv(CSV)
    idx = pd.read_csv(INDEX_CSV)
    sens = pd.read_csv(SENS_CSV)

    core_mask = (grid["in_bmc"] == True) & (grid["core"] == True) & (grid["n_land_px"] > 0)  # noqa: E712
    core_mask = core_mask & grid[FEATURES].notna().all(axis=1)
    core_grid = grid.loc[core_mask].reset_index(drop=True)
    n_core = len(core_grid)
    lines.append("core cells after mask: " + str(n_core))
    if n_core != 1794:
        lines.append("EXPECTED 1794 core cells, got " + str(n_core))
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    if list(idx["cell_id"].values) != list(core_grid["cell_id"].values):
        lines.append("cells_index.csv cell_id order mismatch")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    if list(sens["cell_id"].values) != list(core_grid["cell_id"].values):
        lines.append("cells_index_sens.csv cell_id order mismatch")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)

    thin_obs = idx["thin_obs"].to_numpy(dtype=bool)
    zone_primary = idx["zone_primary"].to_numpy(dtype=bool)
    zone_robust = sens["zone_robust"].to_numpy(dtype=bool)
    zone_fragile = sens["zone_fragile"].to_numpy(dtype=bool)
    n_thin = int(thin_obs.sum())
    n_zone_primary = int(zone_primary.sum())
    n_zone_robust = int(zone_robust.sum())
    n_zone_fragile = int(zone_fragile.sum())
    lines.append("thin_obs count=%d zone_primary=%d zone_robust=%d zone_fragile=%d" %
                 (n_thin, n_zone_primary, n_zone_robust, n_zone_fragile))
    if n_thin != 83 or n_zone_primary != 180 or n_zone_robust != 107 or n_zone_fragile != 73:
        lines.append("count assertion failed")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)

    # c. Spatial clustering of thin_obs.
    thin_grid = np.full((ROWS, COLS), False, dtype=bool)
    thin_grid[core_grid["cell_row"].to_numpy(dtype=int)[thin_obs],
              core_grid["cell_col"].to_numpy(dtype=int)[thin_obs]] = True

    T_obs = float(thin_checks.mean_neighbour_count(thin_grid, thin_grid))
    rng = np.random.default_rng(SEED)
    thin_vec = thin_obs.copy()
    t_perm = []
    core_rows = core_grid["cell_row"].to_numpy(dtype=int)
    core_cols = core_grid["cell_col"].to_numpy(dtype=int)
    for _ in range(N_PERM):
        shuffled = thin_vec[rng.permutation(len(thin_vec))]
        perm_grid = np.full((ROWS, COLS), False, dtype=bool)
        perm_grid[core_rows[shuffled], core_cols[shuffled]] = True
        t_perm.append(float(thin_checks.mean_neighbour_count(perm_grid, perm_grid)))
    t_perm = np.array(t_perm)
    p = (1.0 + int((t_perm >= T_obs).sum())) / (1.0 + N_PERM)
    lines.append("thin T_obs=%.6f perm_mean=%.6f perm_std=%.6f perm_max=%.6f p=%.6f" %
                 (T_obs, float(t_perm.mean()), float(t_perm.std(ddof=0)), float(t_perm.max()), p))
    thin_rows = core_grid["cell_row"].to_numpy(dtype=int)[thin_obs]
    thin_cols = core_grid["cell_col"].to_numpy(dtype=int)[thin_obs]
    lines.append("thin rows min=%d max=%d median=%.1f cols min=%d max=%d median=%.1f" %
                 (int(thin_rows.min()), int(thin_rows.max()), float(np.median(thin_rows)),
                  int(thin_cols.min()), int(thin_cols.max()), float(np.median(thin_cols))))

    # d. Overlap with zones.
    thin_robust = int((thin_obs & zone_robust).sum())
    thin_fragile = int((thin_obs & zone_fragile).sum())
    thin_in_zone = int((thin_obs & zone_primary).sum())
    thin_out_zone = n_thin - thin_in_zone
    lines.append("thin in robust=%d thin in fragile=%d thin in zone_primary=%d thin outside zone_primary=%d" %
                 (thin_robust, thin_fragile, thin_in_zone, thin_out_zone))
    assert thin_robust + thin_fragile == thin_in_zone, (
        "robust thin + fragile thin != thin in zone_primary")
    table = [[thin_in_zone, thin_out_zone],
             [int(zone_primary.sum()) - thin_in_zone, int((~zone_primary).sum()) - thin_out_zone]]
    odds, fp = fisher_exact(table, alternative="two-sided")
    lines.append("fisher table=[[%d,%d],[%d,%d]] odds_ratio=%.6f p=%.6f" %
                 (table[0][0], table[0][1], table[1][0], table[1][1], odds, fp))

    # e. Thin vs non-thin comparison.
    vc_cols = ["vc_min", "vc_median", "vc_le20_share"]
    align = grid.set_index("cell_id").loc[core_grid["cell_id"].values].reset_index(drop=True)
    vars_map = {
        "lst_mean": core_grid["lst_mean"].to_numpy(dtype=float),
        "ndvi_mean": core_grid["ndvi_mean"].to_numpy(dtype=float),
        "ndbi_mean": core_grid["ndbi_mean"].to_numpy(dtype=float),
        "pop_density_land": core_grid["pop_density_land"].to_numpy(dtype=float),
        "index_primary": idx["index_primary"].to_numpy(dtype=float),
    }
    for vc in vc_cols:
        vars_map[vc] = align[vc].to_numpy(dtype=float)
    lines.append("thin vs non-thin medians and Mann-Whitney U p (two-sided):")
    for name, vals in vars_map.items():
        thin_vals = vals[thin_obs]
        nonthin_vals = vals[~thin_obs]
        u, mp = mannwhitneyu(thin_vals, nonthin_vals, alternative="two-sided", method="auto")
        lines.append("  %s thin_median=%.6f nonthin_median=%.6f U=%.0f p=%.6f" %
                     (name, float(np.median(thin_vals)), float(np.median(nonthin_vals)),
                      u, mp))

    # f. Re-standardised zone without thin cells.
    nonthin = ~thin_obs
    sub_lst = core_grid["lst_mean"].to_numpy(dtype=float)[nonthin]
    sub_ndvi = core_grid["ndvi_mean"].to_numpy(dtype=float)[nonthin]
    sub_ndbi = core_grid["ndbi_mean"].to_numpy(dtype=float)[nonthin]
    sub_density = core_grid["pop_density_land"].to_numpy(dtype=float)[nonthin]
    H, S, E_by_kind = index_candidates.component_sets(sub_lst, sub_ndvi, sub_ndbi, sub_density)
    E_raw = E_by_kind["raw"]
    score = 0.4 * H + 0.4 * S + 0.2 * E_raw
    nonthin_idx = np.where(nonthin)[0]
    top_local = index_candidates.top_set(score, N_TOP)
    zone_without_thin = set(nonthin_idx[sorted(top_local)])
    zone_primary_not_thin = set(np.where(zone_primary & nonthin)[0])
    inter = len(zone_without_thin & zone_primary_not_thin)
    union = len(zone_without_thin | zone_primary_not_thin)
    jac = inter / float(union)
    lines.append("zone_without_thin count=%d zone_primary_not_thin count=%d intersection=%d union=%d Jaccard=%.6f" %
                 (len(zone_without_thin), len(zone_primary_not_thin), inter, union, jac))
    lines.append("zone_primary_not_thin not in zone_without_thin=%d zone_without_thin not in zone_primary_not_thin=%d" %
                 (len(zone_primary_not_thin - zone_without_thin),
                  len(zone_without_thin - zone_primary_not_thin)))

    # g. Band counts.
    lines.append("thin count by column band (width 8):")
    for start in range(0, COLS, 8):
        band = (thin_cols >= start) & (thin_cols < start + 8)
        lines.append("  cols %d-%d: %d" % (start, start + 7, int(band.sum())))
    lines.append("thin count by row band (width 14):")
    for start in range(0, ROWS, 14):
        band = (thin_rows >= start) & (thin_rows < start + 14)
        lines.append("  rows %d-%d: %d" % (start, start + 13, int(band.sum())))

    text = "\n".join(lines) + "\n"
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
