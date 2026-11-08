"""K-Means robustness variants (Phase 3B round 1).

Repeats the silhouette sweep (n_init=50, random_state=42) on variants, with
standardisation recomputed on each variant's own cells:
(i) core cells excluding thin_obs cells;
(ii) robust scaling (median and IQR, numpy) on the main analysis cells;
(iii) features lst_mean and ndvi_mean only (drop NDBI).
Prints per variant: cell count, silhouette for k = 2 to 10, argmax k, margin.
Compares to the main sweep in one table. Logs to
logs/phase3b_kmeans_robustness.txt.
"""
import os
import sys

sys.path.insert(0, "src")

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score as sklearn_silhouette

CSV = os.path.join("data", "processed", "cells_500m.csv")
LOG_PATH = os.path.join("logs", "phase3b_kmeans_robustness.txt")


def load_core():
    df = pd.read_csv(CSV)
    core = (df["in_bmc"] == True) & (df["core"] == True) & (df["n_land_px"] > 0)  # noqa: E712
    return df.loc[core].copy()


def standardise_ddof0(X):
    means = np.mean(X, axis=0)
    stds = np.std(X, axis=0, ddof=0)
    return (X - means) / stds, means, stds


def standardise_robust(X):
    medians = np.median(X, axis=0)
    q25 = np.percentile(X, 25, axis=0)
    q75 = np.percentile(X, 75, axis=0)
    iqr = q75 - q25
    safe_iqr = np.where(iqr == 0.0, 1.0, iqr)
    return (X - medians) / safe_iqr, medians, safe_iqr


def sweep(Z, label):
    lines = []
    lines.append("Variant: " + label + "  cells: " + str(Z.shape[0]))
    results = {}
    for k in range(2, 11):
        km = KMeans(
            n_clusters=k, init="k-means++", n_init=50, max_iter=1000,
            random_state=42,
        )
        labels = km.fit_predict(Z)
        sil = float(sklearn_silhouette(Z, labels))
        results[k] = sil
        lines.append("  k=%d silhouette=%.6f" % (k, sil))
    best_k = max(results, key=results.get)
    sorted_sils = sorted(results.values(), reverse=True)
    margin = sorted_sils[0] - sorted_sils[1]
    lines.append("  argmax k=%d silhouette=%.6f second=%.6f margin=%.6f" % (
        best_k, sorted_sils[0], sorted_sils[1], margin))
    lines.append("")
    return results, best_k, margin, sorted_sils[0]


def main():
    os.makedirs("logs", exist_ok=True)
    core_df = load_core()
    main_df = core_df.loc[core_df[["lst_mean", "ndvi_mean", "ndbi_mean"]].notna().all(axis=1)].copy()
    main_Z, _, _ = standardise_ddof0(main_df[["lst_mean", "ndvi_mean", "ndbi_mean"]].to_numpy(dtype=np.float64))

    lines = []
    lines.append("Main analysis cells: " + str(main_df.shape[0]))
    lines.append("")

    main_res, main_best, main_margin, _ = sweep(main_Z, "main")

    # Variant (i): core excluding thin_obs.
    var_i = core_df.loc[(core_df["thin_obs"] == False) &  # noqa: E712
                        core_df[["lst_mean", "ndvi_mean", "ndbi_mean"]].notna().all(axis=1)].copy()
    var_i_Z, _, _ = standardise_ddof0(var_i[["lst_mean", "ndvi_mean", "ndbi_mean"]].to_numpy(dtype=np.float64))
    res_i, best_i, margin_i, _ = sweep(var_i_Z, "core excluding thin_obs")

    # Variant (ii): robust scaling on main cells.
    var_ii_Z, _, _ = standardise_robust(main_df[["lst_mean", "ndvi_mean", "ndbi_mean"]].to_numpy(dtype=np.float64))
    res_ii, best_ii, margin_ii, _ = sweep(var_ii_Z, "main cells, robust scaling (median/IQR)")

    # Variant (iii): lst_mean and ndvi_mean only.
    var_iii = main_df[["lst_mean", "ndvi_mean"]].to_numpy(dtype=np.float64)
    var_iii_Z, _, _ = standardise_ddof0(var_iii)
    res_iii, best_iii, margin_iii, _ = sweep(var_iii_Z, "features lst_mean and ndvi_mean only")

    # Comparison table.
    lines.append("Comparison table (silhouette by k):")
    lines.append("k   main   no_thin_obs   robust   lst_ndvi_only")
    for k in range(2, 11):
        lines.append("  %d  %.6f   %.6f   %.6f   %.6f" % (
            k, main_res[k], res_i[k], res_ii[k], res_iii[k]))
    lines.append("")
    lines.append("Argmax k: main=%d  no_thin_obs=%d  robust=%d  lst_ndvi_only=%d" % (
        main_best, best_i, best_ii, best_iii))
    lines.append("Margin: main=%.6f  no_thin_obs=%.6f  robust=%.6f  lst_ndvi_only=%.6f" % (
        main_margin, margin_i, margin_ii, margin_iii))

    text = "\n".join(lines) + "\n"
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    return {"main_best": main_best, "best_i": best_i, "best_ii": best_ii, "best_iii": best_iii}


if __name__ == "__main__":
    main()
