"""Index-input diagnostics (Phase 3B round 3, report only).

Reads data/processed/cells_500m.csv and data/processed/cells_kmeans.csv
(both read only). On the 1794 core analysis cells, z features from
cells_kmeans.csv are recomputed from cells_500m.csv raw columns (ddof=0)
and checked equal (max abs diff must be below 1e-9, else STOP).

Reports, numbers only:
    a. Spearman (src/stats_utils.spearman_rho) and Pearson (numpy) of
       pop_density_land with lst_mean, ndvi_mean, ndbi_mean, on all 1794
       cells and again on the pop > 0 cells only (1595).
    b. R squared of OLS regressions with intercept (numpy lstsq):
       z lst_mean ~ z ndvi_mean + z ndbi_mean; z ndbi_mean ~ z lst_mean +
       z ndvi_mean; z ndvi_mean ~ z lst_mean + z ndbi_mean. Prints
       coefficients and R squared.
    c. The 199 zero-pop core cells: count, mean raw lst_mean, ndvi_mean,
       ndbi_mean, and their k=2 / k=4 cluster distributions (columns k_2,
       k_4 in cells_kmeans.csv). Same for the thin_obs cells (actual count
       printed).
    d. Distribution of pop_density_land on the populated cells: percentiles
       1, 5, 25, 50, 75, 95, 99, max; skewness (numpy standardized third
       moment) of raw density, log10(density), sqrt(density).
    e. For the three raw features and pop_density_land (all 1794 cells,
       zeros included): number of cells exactly tied at the minimum and at
       the maximum value.

Numbers only. No interpretation. Logs to logs/phase3b3_index_inputs.txt.
"""
import os
import sys

sys.path.insert(0, "src")

import numpy as np
import pandas as pd

from stats_utils import spearman_rho

CSV = os.path.join("data", "processed", "cells_500m.csv")
KMEANS_CSV = os.path.join("data", "processed", "cells_kmeans.csv")
LOG_PATH = os.path.join("logs", "phase3b3_index_inputs.txt")
FEATURES = ["lst_mean", "ndvi_mean", "ndbi_mean"]


def skewness(x):
    x = np.asarray(x, dtype=np.float64)
    m = float(np.mean(x))
    s = float(np.std(x, ddof=0))
    if s == 0.0:
        return 0.0
    return float(np.mean((x - m) ** 3) / s ** 3)


def main():
    os.makedirs("logs", exist_ok=True)
    df = pd.read_csv(CSV)
    km = pd.read_csv(KMEANS_CSV)
    df = df.merge(km[["cell_id", "k_2", "k_4", "z_lst_mean",
                      "z_ndvi_mean", "z_ndbi_mean"]], on="cell_id",
                  how="left")

    core = (df["in_bmc"] == 1.0) & (df["core"] == 1.0) & (df["n_land_px"] > 0)
    analysis = df.loc[core].copy()
    analysis = analysis.loc[analysis[FEATURES].notna().all(axis=1)].copy()
    n = len(analysis)
    lines = []
    lines.append("Index-input diagnostics (report only, no index, no weights).")
    lines.append("Analysis cells: " + str(n))

    # z features from cells_kmeans.csv vs recomputed from raw cells_500m.csv.
    z_csv = analysis[["z_lst_mean", "z_ndvi_mean", "z_ndbi_mean"]].to_numpy(dtype=np.float64)
    raw = analysis[FEATURES].to_numpy(dtype=np.float64)
    rmeans = np.mean(raw, axis=0)
    rstds = np.std(raw, axis=0, ddof=0)
    rstds = np.where(rstds == 0.0, 1.0, rstds)
    z_recomputed = (raw - rmeans) / rstds
    z_diff = float(np.max(np.abs(z_csv - z_recomputed)))
    lines.append("z columns from cells_kmeans.csv vs recomputed from raw: "
                 "max abs difference = %.6g" % z_diff)
    if z_diff > 1e-9:
        lines.append("")
        lines.append("STOP: z columns from cells_kmeans.csv do not match the "
                     "values recomputed from cells_500m.csv raw columns.")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)

    pop = analysis["pop"].to_numpy(dtype=np.float64)
    pop_density_land = analysis["pop_density_land"].to_numpy(dtype=np.float64)
    pop_pos = pop > 0.0
    n_pop_pos = int(pop_pos.sum())
    lines.append("")
    lines.append("a. pop_density_land vs features: Spearman "
                 "(src/stats_utils.spearman_rho) and Pearson (numpy), on all "
                 "1794 cells and on the pop > 0 cells only (1595).")
    for subset_name, mask in (("all cells", np.ones(n, dtype=bool)),
                              ("pop > 0 cells", pop_pos)):
        lines.append("  Subset: %s (n=%d)" % (subset_name, int(mask.sum())))
        for col in FEATURES:
            fv = analysis[col].to_numpy(dtype=np.float64)
            rho, _ = spearman_rho(pop_density_land[mask], fv[mask])
            rp = float(np.corrcoef(pop_density_land[mask], fv[mask])[0, 1])
            lines.append("    pop_density_land vs %s: rho=%.6f  r=%.6f"
                         % (col, rho, rp))

    lines.append("")
    lines.append("b. R squared of OLS regressions with intercept "
                 "(numpy lstsq):")
    idx = {c: i for i, c in enumerate(FEATURES)}
    for tname, yi in (("z lst_mean", 0), ("z ndbi_mean", 2),
                      ("z ndvi_mean", 1)):
        pred_cols = [j for j in range(3) if j != yi]
        Xp = np.column_stack([np.ones(n), analysis[FEATURES[pred_cols[0]]].to_numpy(dtype=np.float64),
                              analysis[FEATURES[pred_cols[1]]].to_numpy(dtype=np.float64)])
        y = analysis[FEATURES[yi]].to_numpy(dtype=np.float64)
        coef, residuals, rank, sv = np.linalg.lstsq(Xp, y, rcond=None)
        y_mean = float(np.mean(y))
        ss_res = float(np.sum((y - Xp @ coef) ** 2))
        ss_tot = float(np.sum((y - y_mean) ** 2))
        r2 = 1.0 - ss_res / ss_tot
        lines.append("  z %s ~ z %s + z %s: coef=(intercept=%.6f, %.6f, %.6f) "
                     "R^2=%.6f" % (
                         tname, FEATURES[pred_cols[0]], FEATURES[pred_cols[1]],
                         float(coef[0]), float(coef[1]), float(coef[2]), r2))

    lines.append("")
    zero_pop = analysis.loc[~pop_pos]
    n_zero_pop = int(len(zero_pop))
    lines.append("c. Zero-pop core cells: count = %d" % n_zero_pop)
    lines.append("  mean raw lst_mean=%.6f ndvi_mean=%.6f ndbi_mean=%.6f" % (
        float(zero_pop["lst_mean"].mean()), float(zero_pop["ndvi_mean"].mean()),
        float(zero_pop["ndbi_mean"].mean())))
    for kname, kcol in (("k=2", "k_2"), ("k=4", "k_4")):
        vc = zero_pop[kcol].value_counts().sort_index()
        lines.append("  %s cluster distribution: %s" % (
            kname, {int(k): int(c) for k, c in vc.items()}))

    thin = analysis.loc[analysis["thin_obs"] == 1.0]
    n_thin = int(len(thin))
    lines.append("  thin_obs cells: actual count = %d" % n_thin)
    lines.append("  mean raw lst_mean=%.6f ndvi_mean=%.6f ndbi_mean=%.6f" % (
        float(thin["lst_mean"].mean()), float(thin["ndvi_mean"].mean()),
        float(thin["ndbi_mean"].mean())))
    for kname, kcol in (("k=2", "k_2"), ("k=4", "k_4")):
        vc = thin[kcol].value_counts().sort_index()
        lines.append("  thin_obs %s cluster distribution: %s" % (
            kname, {int(k): int(c) for k, c in vc.items()}))

    lines.append("")
    lines.append("d. pop_density_land on the %d populated cells:" % n_pop_pos)
    pd_pos = pop_density_land[pop_pos]
    for q in (1, 5, 25, 50, 75, 95, 99):
        lines.append("  p%d=%.6f" % (q, float(np.percentile(pd_pos, q))))
    lines.append("  max=%.6f" % float(pd_pos.max()))
    lines.append("  skewness (numpy standardized third moment):")
    lines.append("    raw density: %.6f" % skewness(pd_pos))
    lines.append("    log10(density): %.6f" % skewness(np.log10(pd_pos)))
    lines.append("    sqrt(density): %.6f" % skewness(np.sqrt(pd_pos)))

    lines.append("")
    lines.append("e. Cells exactly tied at the minimum and maximum value:")
    for col in FEATURES + ["pop_density_land"]:
        v = analysis[col].to_numpy(dtype=np.float64)
        lines.append("  %s: min=%.6f tied_at_min=%d  max=%.6f tied_at_max=%d" % (
            col, float(v.min()), int((v == v.min()).sum()),
            float(v.max()), int((v == v.max()).sum())))

    text = "\n".join(lines) + "\n"
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    return {"n": n, "n_pop_pos": n_pop_pos, "n_zero_pop": n_zero_pop,
            "n_thin": n_thin, "z_diff": z_diff}


if __name__ == "__main__":
    main()
