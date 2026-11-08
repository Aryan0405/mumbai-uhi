"""K-Means k sweep on core cells (Phase 3B round 1).

Features: z-scored lst_mean, ndvi_mean, ndbi_mean (ddof=0) on core cells with
n_land_px > 0. For k = 2 to 10: sklearn KMeans(init="k-means++", n_init=50,
max_iter=1000, random_state=42). Records inertia, silhouette_score, Davies-
Bouldin, Calinski-Harabasz, cluster sizes, smallest cluster, per-cluster mean
silhouette. Seed stability over random_state 0..9 (n_init=10). Subsample
stability over 30 random 80% subsamples (seed 123). Independent silhouette
check against src/silhouette_numpy.py for k = 2, 3 and the argmax k. Logs to
logs/phase3b_kmeans_sweep.txt.
"""
import os
import sys

sys.path.insert(0, "src")

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import (
    adjusted_rand_score,
    calinski_harabasz_score,
    davies_bouldin_score,
    silhouette_score as sklearn_silhouette,
)

from silhouette_numpy import silhouette_score as numpy_silhouette, silhouette_samples

CSV = os.path.join("data", "processed", "cells_500m.csv")
FEATURES = ["lst_mean", "ndvi_mean", "ndbi_mean"]
LOG_PATH = os.path.join("logs", "phase3b_kmeans_sweep.txt")
SEEDS = list(range(10))
SUBSAMPLE_FRAC = 0.8
SUBSAMPLES = 30
SUBSAMPLE_SEED = 123


def load_analysis_matrix():
    df = pd.read_csv(CSV)
    core = (df["in_bmc"] == True) & (df["core"] == True) & (df["n_land_px"] > 0)  # noqa: E712
    core_df = df.loc[core].copy()
    analysis_df = core_df.loc[core_df[FEATURES].notna().all(axis=1)].copy()
    cell_ids = analysis_df["cell_id"].to_numpy(dtype=np.int64)
    X = analysis_df[FEATURES].to_numpy(dtype=np.float64)
    means = np.mean(X, axis=0)
    stds = np.std(X, axis=0, ddof=0)
    Z = (X - means) / stds
    return cell_ids, Z, means, stds


def cluster_sizes(labels):
    sizes = np.bincount(labels)
    return sorted([int(s) for s in sizes if s > 0], reverse=True)


def per_cluster_silhouette(X, labels, sil_values):
    out = {}
    for lab in np.unique(labels):
        members = labels == lab
        out[int(lab)] = float(np.mean(sil_values[members]))
    return out


def main():
    os.makedirs("logs", exist_ok=True)
    cell_ids, Z, means, stds = load_analysis_matrix()
    n_cells = Z.shape[0]

    lines = []
    lines.append("Analysis cells: " + str(n_cells))
    lines.append("Features: " + ", ".join(FEATURES))
    lines.append("Standardisation ddof=0 means: " + repr(means.tolist()))
    lines.append("Standardisation ddof=0 stds: " + repr(stds.tolist()))

    results = {}
    for k in range(2, 11):
        km = KMeans(
            n_clusters=k, init="k-means++", n_init=50, max_iter=1000,
            random_state=42,
        )
        labels = km.fit_predict(Z)
        sil = sklearn_silhouette(Z, labels)
        sil = float(sklearn_silhouette(Z, labels))
        db = davies_bouldin_score(Z, labels)
        ch = calinski_harabasz_score(Z, labels)
        sizes = cluster_sizes(labels)
        # per-sample silhouette via sklearn internals (values match sklearn's
        # silhouette_samples definition).
        sil_samples = silhouette_samples(Z, labels)
        pcsil = per_cluster_silhouette(Z, labels, sil_samples)
        results[k] = {

            "inertia": float(km.inertia_),
            "silhouette": float(sil),
            "davies_bouldin": float(db),
            "calinski_harabasz": float(ch),
            "sizes": sizes,
            "smallest": int(sizes[-1]),
            "per_cluster_silhouette": pcsil,
            "labels": labels,
        }

    # Seed stability: random_state 0..9, n_init=10.
    seed_stability = {}
    for k in range(2, 11):
        sils = []
        label_sets = []
        for seed in SEEDS:
            km = KMeans(
                n_clusters=k, init="k-means++", n_init=10, max_iter=1000,
                random_state=seed,
            )
            labels = km.fit_predict(Z)
            sils.append(float(sklearn_silhouette(Z, labels)))
            label_sets.append(labels)
        min_pairwise_ari = 1.0
        for i in range(len(label_sets)):
            for j in range(i + 1, len(label_sets)):
                ari = float(adjusted_rand_score(label_sets[i], label_sets[j]))
                if ari < min_pairwise_ari:
                    min_pairwise_ari = ari
        seed_stability[k] = {
            "sil_min": float(np.min(sils)),
            "sil_max": float(np.max(sils)),
            "sil_std": float(np.std(sils, ddof=0)),
            "min_pairwise_ari": min_pairwise_ari,
        }

    # Subsample stability: 30 subsamples of 80%, seed 123.
    rng = np.random.default_rng(SUBSAMPLE_SEED)
    subsample_stability = {}
    for k in range(2, 11):
        full_labels = results[k]["labels"]
        aris = []
        for _ in range(SUBSAMPLES):
            perm = rng.permutation(n_cells)
            n_sub = int(round(SUBSAMPLE_FRAC * n_cells))
            sub_idx = perm[:n_sub]
            hold_idx = perm[n_sub:]
            km = KMeans(
                n_clusters=k, init="k-means++", n_init=10, max_iter=1000,
                random_state=42,
            )
            km.fit(Z[sub_idx])
            pred = km.predict(Z[hold_idx])
            aris.append(float(adjusted_rand_score(full_labels[hold_idx], pred)))
        subsample_stability[k] = {
            "mean_ari": float(np.mean(aris)),
            "min_ari": float(np.min(aris)),
        }

    # Argmax k by silhouette.
    best_k = max(range(2, 11), key=lambda k: results[k]["silhouette"])
    sil_values = [results[k]["silhouette"] for k in range(2, 11)]
    sorted_sils = sorted(sil_values, reverse=True)
    best_sil = sorted_sils[0]
    second_sil = sorted_sils[1]
    margin = best_sil - second_sil

    # Independent silhouette check: k = 2, 3, best_k.
    check_ks = [2, 3, best_k]
    if 3 in check_ks and best_k == 3:
        check_ks = [2, 3]
    silhouette_checks = {}
    for k in check_ks:
        labels = results[k]["labels"]
        sk = float(sklearn_silhouette(Z, labels))
        np_ = float(numpy_silhouette(Z, labels))
        silhouette_checks[k] = {"sklearn": sk, "numpy": np_, "diff": abs(sk - np_)}

    # Compose output.
    lines.append("")
    lines.append("k sweep results (n_init=50, random_state=42, z-scored features):")
    header = ("k  inertia silhouette davies_bouldin calinski_harabasz "
              "sizes smallest per_cluster_sil")
    lines.append(header)
    for k in range(2, 11):
        r = results[k]
        lines.append(
            f"{k:2d} {r['inertia']:.6f} {r['silhouette']:.6f} "
            f"{r['davies_bouldin']:.6f} {r['calinski_harabasz']:.6f} "
            f"{r['sizes']} {r['smallest']} "
            + str({kk: round(vv, 6) for kk, vv in sorted(r["per_cluster_silhouette"].items())})
        )
    lines.append("")
    lines.append("Highest silhouette: k = " + str(best_k) + " (" + repr(best_sil) + ")")
    lines.append("Second highest silhouette: " + repr(second_sil) + " (margin " + repr(margin) + ")")
    if best_sil < 0.25:
        lines.append("Best silhouette below 0.25: " + repr(best_sil))
    lines.append("")
    lines.append("Independent silhouette check (sklearn vs pure numpy):")
    for k in sorted(silhouette_checks):
        c = silhouette_checks[k]
        lines.append(
            f"  k={k}: sklearn={c['sklearn']:.12f} numpy={c['numpy']:.12f} "
            f"diff={c['diff']:.3e}"
        )
        if c["diff"] > 1e-9:
            lines.append("STOP: silhouette difference exceeds 1e-9 for k=" + str(k))
            raise SystemExit(1)
    lines.append("")
    lines.append("Seed stability (random_state 0..9, n_init=10):")
    for k in range(2, 11):
        s = seed_stability[k]
        lines.append(
            f"  k={k}: sil_min={s['sil_min']:.6f} sil_max={s['sil_max']:.6f} "
            f"sil_std={s['sil_std']:.6f} min_pairwise_ARI={s['min_pairwise_ari']:.6f}"
        )
    lines.append("")
    lines.append("Subsample stability (30 x 80% subsamples, seed 123):")
    for k in range(2, 11):
        s = subsample_stability[k]
        lines.append(f"  k={k}: mean_ARI={s['mean_ari']:.6f} min_ARI={s['min_ari']:.6f}")

    text = "\n".join(lines) + "\n"
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    return {"best_k": best_k, "best_silhouette": best_sil, "second_silhouette": second_sil,
            "margin": margin, "results": results}


if __name__ == "__main__":
    main()
