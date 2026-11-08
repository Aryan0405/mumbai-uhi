"""Cluster profiles and labels (Phase 3B round 1).

For argmax k from the sweep (k=2) and k = 3, 4, 5 (no duplication if argmax
is one of them), takes n_init=50, random_state=42 labels on z-scored
lst_mean, ndvi_mean, ndbi_mean of the analysis cells. Per cluster prints:
cell count, share of analysis cells, mean and median of RAW lst_mean,
ndvi_mean, ndbi_mean, median pop_density_land, share of thin_obs, share of
pop == 0, mean silhouette of members. Clusters listed sorted by ascending mean
raw lst_mean (ordering rule stated in the log; CSV keeps sklearn ids).
Spatial coherence: connected components per cluster on the 84 x 48 grid
(row = cell_id // 48, col = cell_id % 48, 8-neighbour, scipy.ndimage.label).
Writes data/processed/cells_kmeans.csv: cell_id, one label column per k from
2 to 10 for the analysis cells, and the z-scored features. Does not modify
cells_500m.csv. Logs to logs/phase3b_kmeans_profiles.txt.
"""
import os
import sys

sys.path.insert(0, "src")

import numpy as np
import pandas as pd
from scipy import ndimage
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_samples

from silhouette_numpy import silhouette_samples as numpy_silhouette_samples

CSV = os.path.join("data", "processed", "cells_500m.csv")
OUT_CSV = os.path.join("data", "processed", "cells_kmeans.csv")
FEATURES = ["lst_mean", "ndvi_mean", "ndbi_mean"]
LOG_PATH = os.path.join("logs", "phase3b_kmeans_profiles.txt")
KS = [2, 3, 4, 5]


def load_analysis():
    df = pd.read_csv(CSV)
    core = (df["in_bmc"] == True) & (df["core"] == True) & (df["n_land_px"] > 0)  # noqa: E712
    core_df = df.loc[core].copy()
    analysis_df = core_df.loc[core_df[FEATURES].notna().all(axis=1)].copy()
    X = analysis_df[FEATURES].to_numpy(dtype=np.float64)
    means = np.mean(X, axis=0)
    stds = np.std(X, axis=0, ddof=0)
    Z = (X - means) / stds
    return analysis_df, Z, means, stds


def cluster_stats(analysis_df, labels, sil_values):
    n = len(analysis_df)
    rows = []
    for lab in np.unique(labels):
        members = labels == lab
        cnt = int(members.sum())
        sub = analysis_df.loc[members]
        rows.append({
            "cluster": int(lab),
            "count": cnt,
            "share": cnt / n,
            "lst_mean": float(sub["lst_mean"].mean()),
            "lst_median": float(sub["lst_mean"].median()),
            "ndvi_mean": float(sub["ndvi_mean"].mean()),
            "ndvi_median": float(sub["ndvi_mean"].median()),
            "ndbi_mean": float(sub["ndbi_mean"].mean()),
            "ndbi_median": float(sub["ndbi_mean"].median()),
            "pop_density_land_median": float(sub["pop_density_land"].median()),
            "share_thin_obs": float((sub["thin_obs"] == True).mean()),  # noqa: E712
            "share_pop_zero": float((sub["pop"] == 0.0).mean()),
            "mean_silhouette": float(np.mean(sil_values[members])),
        })
    rows.sort(key=lambda r: r["lst_mean"])
    return rows


def spatial_coherence(analysis_df, labels):
    n_cols = 48
    n_rows = 84
    out = {}
    for lab in np.unique(labels):
        ids = analysis_df.loc[labels == lab, "cell_id"].to_numpy(dtype=np.int64)
        grid = np.zeros((n_rows, n_cols), dtype=bool)
        grid[ids // n_cols, ids % n_cols] = True
        structure = np.ones((3, 3), dtype=int)
        labeled, num_components = ndimage.label(grid, structure=structure)
        if num_components == 0:
            sizes = []
        else:
            sizes = np.bincount(labeled.ravel())[1:]
        out[int(lab)] = {
            "num_components": int(num_components),
            "largest_component_size": int(sizes.max()) if sizes.size else 0,
        }
    return out


def main():
    os.makedirs("logs", exist_ok=True)
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    analysis_df, Z, means, stds = load_analysis()
    n_cells = len(analysis_df)
    cell_ids = analysis_df["cell_id"].to_numpy(dtype=np.int64)

    lines = []
    lines.append("Analysis cells: " + str(n_cells))
    lines.append("Cluster ordering rule: profile tables list clusters sorted by "
                 "ascending mean raw lst_mean. sklearn cluster ids are not "
                 "renamed in the CSV.")
    lines.append("")

    # Labels for k = 2 to 10 (deterministic).
    all_labels = {}
    all_sils = {}
    for k in range(2, 11):
        km = KMeans(
            n_clusters=k, init="k-means++", n_init=50, max_iter=1000,
            random_state=42,
        )
        labels = km.fit_predict(Z)
        all_labels[k] = labels
        sil_samples = numpy_silhouette_samples(Z, labels)
        all_sils[k] = sil_samples

    argmax_k = max(all_sils, key=lambda kk: float(np.mean(all_sils[kk])))
    profile_ks = [k for k in KS if k != argmax_k]
    profile_ks = [argmax_k] + profile_ks
    lines.append("Argmax k from this run: " + str(argmax_k))
    lines.append("")

    for k in profile_ks:
        labels = all_labels[k]
        sil_values = all_sils[k]
        stats_rows = cluster_stats(analysis_df, labels, sil_values)
        coh = spatial_coherence(analysis_df, labels)
        lines.append("k = " + str(k))
        for r in stats_rows:
            c = coh[r["cluster"]]
            lines.append(
                "  cluster %d: count=%d share=%.6f raw_lst_mean=%.6f "
                "raw_lst_median=%.6f raw_ndvi_mean=%.6f raw_ndvi_median=%.6f "
                "raw_ndbi_mean=%.6f raw_ndbi_median=%.6f "
                "pop_density_land_median=%.6f share_thin_obs=%.6f "
                "share_pop_zero=%.6f mean_silhouette=%.6f "
                "components=%d largest_component=%d" % (
                    r["cluster"], r["count"], r["share"], r["lst_mean"],
                    r["lst_median"], r["ndvi_mean"], r["ndvi_median"],
                    r["ndbi_mean"], r["ndbi_median"],
                    r["pop_density_land_median"], r["share_thin_obs"],
                    r["share_pop_zero"], r["mean_silhouette"],
                    c["num_components"], c["largest_component_size"]))
        lines.append("")

    # Write cells_kmeans.csv.
    out_df = pd.DataFrame({"cell_id": cell_ids})
    for k in range(2, 11):
        out_df["k_" + str(k)] = all_labels[k]
    out_df["z_lst_mean"] = (analysis_df["lst_mean"].to_numpy(dtype=np.float64) - means[0]) / stds[0]
    out_df["z_ndvi_mean"] = (analysis_df["ndvi_mean"].to_numpy(dtype=np.float64) - means[1]) / stds[1]
    out_df["z_ndbi_mean"] = (analysis_df["ndbi_mean"].to_numpy(dtype=np.float64) - means[2]) / stds[2]
    out_df.to_csv(OUT_CSV, index=False)
    lines.append("Wrote " + OUT_CSV + " rows=" + str(len(out_df)))
    lines.append("Columns: " + ", ".join(out_df.columns.tolist()))

    text = "\n".join(lines) + "\n"
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    return {"argmax_k": argmax_k, "profile_ks": profile_ks, "out_csv": OUT_CSV,
            "n_rows": len(out_df)}


if __name__ == "__main__":
    main()
