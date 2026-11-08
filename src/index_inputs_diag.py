"""Index-input diagnostics (Phase 3B round 2, report only).

No index, no weights, no vulnerability score. Reads data/processed/cells_500m.csv
and data/processed/cells_kmeans.csv (both read only).
On the 1794 analysis cells: z features from cells_kmeans.csv z-columns,
recomputed from cells_500m.csv raw columns and checked equal.
Logs to logs/phase3b2_index_inputs.txt.
"""
import os
import sys

sys.path.insert(0, "src")

import numpy as np
import pandas as pd

from stats_utils import spearman_rho

CSV = os.path.join("data", "processed", "cells_500m.csv")
KMEANS_CSV = os.path.join("data", "processed", "cells_kmeans.csv")
LOG_PATH = os.path.join("logs", "phase3b2_index_inputs.txt")
FEATURES = ["lst_mean", "ndvi_mean", "ndbi_mean"]


def skewness(x):
    x = np.asarray(x, dtype=np.float64)
    m = np.mean(x)
    s = np.std(x, ddof=0)
    if s == 0.0:
        return 0.0
    return float(np.mean((x - m) ** 3) / s ** 3)


def main():
    os.makedirs("logs", exist_ok=True)
    df = pd.read_csv(CSV)
    km = pd.read_csv(KMEANS_CSV)
    df = df.merge(km[["cell_id", "k_2", "k_4", "z_lst_mean", "z_ndvi_mean",
                      "z_ndbi_mean"]], on="cell_id", how="left")

    core = (df["in_bmc"] == True) & (df["core"] == True) & (df["n_land_px"] > 0)  # noqa: E712
    analysis = df.loc[core].copy()
    analysis = analysis.loc[analysis[FEATURES].notna().all(axis=1)].copy()
    n = len(analysis)
    lines = []
    lines.append("Index-input diagnostics (report only, no index, no weights).")
    lines.append("Analysis cells: " + str(n))

    # z features from cells_kmeans.csv vs recomputed from raw cells_500m.csv.
    z_from_csv = analysis[["z_lst_mean", "z_ndvi_mean", "z_ndbi_mean"]].to_numpy(dtype=np.float64)
    raw = analysis[FEATURES].to_numpy(dtype=np.float64)
    rmeans = np.mean(raw, axis=0)
    rstds = np.std(raw, axis=0, ddof=0)
    z_recomputed = (raw - rmeans) / rstds
    z_diff = float(np.max(np.abs(z_from_csv - z_recomputed)))
    lines.append("z columns from cells_kmeans.csv vs recomputed from raw: "
                 "max abs difference = %.6g" % z_diff)
    if z_diff > 1e-9:
        lines.append("STOP: z columns do not match recomputed values.")
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print("\n".join(lines))
        raise SystemExit(1)
    Z = z_from_csv

    pop = analysis["pop"].to_numpy(dtype=np.float64)
    pop_density_land = analysis["pop_density_land"].to_numpy(dtype=np.float64)
    pop_pos = pop > 0.0
    n_pop_pos = int(pop_pos.sum())
    lines.append("Populated cells (pop > 0): " + str(n_pop_pos))

    # a. Spearman and Pearson of pop_density_land with each feature.
    lines.append("")
    lines.append("a. pop_density_land vs features: Spearman (stats_utils) and "
                 "Pearson (numpy), all 1794 cells and pop>0 cells only.")
    for subset_name, mask in (("all cells", np.ones(n, dtype=bool)),
                              ("pop > 0 cells", pop_pos)):
        lines.append("  Subset: " + subset_name + " (n=%d)" % int(mask.sum()))
        for col in FEATURES:
            fv = analysis[col].to_numpy(dtype=np.float64)
            rho, _ = spearman_rho(pop_density_land[mask], fv[mask])
            rp = float(np.corrcoef(pop_density_land[mask], fv[mask])[0, 1])
            lines.append("    %s vs %s: rho=%.6f  r=%.6f" %
                         ("pop_density_land", col, rho, rp))

    # b. R squared of regressions with intercept (numpy lstsq).
    lines.append("")
    lines.append("b. R squared of OLS regressions with intercept (numpy lstsq):")
    idx = {c: i for i, c in enumerate(FEATURES)}
    for tname, yi in (("z lst_mean", 0), ("z ndbi_mean", 2), ("z ndvi_mean", 1)):
        pred_cols = [j for j in range(3) if j != yi]
        Xp = np.column_stack([np.ones(n), Z[:, pred_cols]])
        coef, residuals, rank, sv = np.linalg.lstsq(Xp, Z[:, yi], rcond=None)
        y = Z[:, yi]
        y_mean = np.mean(y)
        ss_res = float(np.sum((y - Xp @ coef) ** 2))
        ss_tot = float(np.sum((y - y_mean) ** 2))
        r2 = 1.0 - ss_res / ss_tot
        lines.append("  %s ~ z %s + z %s: coef=(intercept=%.6f, %.6f, %.6f) "
                     "R^2=%.6f" % (
                         tname, FEATURES[pred_cols[0]], FEATURES[pred_cols[1]],
                         float(coef[0]), float(coef[1]), float(coef[2]), r2))

    # c. zero-pop core cells.
    lines.append("")
    zero_pop = analysis.loc[~pop_pos]
    n_zero_pop = len(zero_pop)
    lines.append("c. Zero-pop core cells: count = " + str(n_zero_pop))
    lines.append("  mean raw lst_mean=%.6f ndvi_mean=%.6f ndbi_mean=%.6f" % (
        float(zero_pop["lst_mean"].mean()), float(zero_pop["ndvi_mean"].mean()),
        float(zero_pop["ndbi_mean"].mean())))
    for kname, kcol in (("k=2", "k_2"), ("k=4", "k_4")):
        vc = zero_pop[kcol].value_counts().sort_index()
        lines.append("  " + kname + " cluster distribution: " +
                     str({int(k): int(c) for k, c in vc.items()}))

    thin = analysis.loc[analysis["thin_obs"] == True]  # noqa: E712
    n_thin = len(thin)
    lines.append("  thin_obs cells: actual count = " + str(n_thin))
    lines.append("  mean raw lst_mean=%.6f ndvi_mean=%.6f ndbi_mean=%.6f" % (
        float(thin["lst_mean"].mean()), float(thin["ndvi_mean"].mean()),
        float(thin["ndbi_mean"].mean())))
    for kname, kcol in (("k=2", "k_2"), ("k=4", "k_4")):
        vc = thin[kcol].value_counts().sort_index()
        lines.append("  thin_obs " + kname + " cluster distribution: " +
                     str({int(k): int(c) for k, c in vc.items()}))

    # d. Distribution of pop_density_land on populated cells.
    lines.append("")
    lines.append("d. pop_density_land on the %d populated cells:" % n_pop_pos)
    pd_pos = pop_density_land[pop_pos]
    for q in (1, 5, 25, 50, 75, 95, 99):
        lines.append("  p%d=%.6f" % (q, float(np.percentile(pd_pos, q))))
    lines.append("  max=%.6f" % float(pd_pos.max()))
    lines.append("  skewness (numpy, standardized third moment):")
    lines.append("    raw density: %.6f" % skewness(pd_pos))
    lines.append("    log10(density): %.6f" % skewness(np.log10(pd_pos)))
    lines.append("    sqrt(density): %.6f" % skewness(np.sqrt(pd_pos)))

    # e. Ties at min and max.
    lines.append("")
    lines.append("e. Cells exactly tied at the minimum and maximum value:")
    for col in FEATURES + ["pop_density_land"]:
        v = analysis[col].to_numpy(dtype=np.float64)
        lines.append("  %s: min=% .6f tied_at_min=%d  max=% .6f tied_at_max=%d" % (
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
