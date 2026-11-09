"""Null-model test of K-Means silhouettes (Phase 3C round).

Tests whether the real silhouettes exceed what a structureless continuum with
the same marginals and correlations produces. Spatial autocorrelation is NOT
modelled; this is stated in the log.

Usage: python src/kmeans_null.py <null_type> <n_replicates> <log_path>
  null_type: gaussian or copula (runs ONLY that null).
  n_replicates: number of null replicates (positive integer).
  log_path: must start with logs/ and must not already exist (never overwrite).

For each replicate (rng seeded with 2026 and the replicate index),
n_rows = 1794. Copula null uses the raw (unstandardised) real features X,
then each replicate is z-scored with ddof=0 exactly as the real data was.
For each replicate and each k = 2 to 10: KMeans(init="k-means++",
n_init=10, max_iter=1000, random_state=42), sklearn silhouette (Euclidean,
all points). The REAL data silhouettes use the identical settings so the
comparison is like with like.
"""
import os
import sys
import time

sys.path.insert(0, "src")

import numpy as np
import pandas as pd
import scipy
import sklearn
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score as sklearn_silhouette

from null_models import copula_null, gaussian_null

CSV = os.path.join("data", "processed", "cells_500m.csv")
FEATURES = ["lst_mean", "ndvi_mean", "ndbi_mean"]
N_DRAWS = 1794
KS = list(range(2, 11))
RNG_SEED_BASE = 2026

REAL_SILHOUETTE_TARGETS = {2: 0.494168, 3: 0.359270, 4: 0.370169}
REAL_TOL = 1e-6


def usage():
    return ("usage: python src/kmeans_null.py <null_type> <n_replicates> <log_path>\n"
            "  null_type: gaussian or copula\n"
            "  n_replicates: positive integer\n"
            "  log_path: must start with logs/ and must not already exist")


def load_real():
    df = pd.read_csv(CSV)
    core = (df["in_bmc"] == True) & (df["core"] == True) & (df["n_land_px"] > 0)  # noqa: E712
    core_df = df.loc[core].copy()
    analysis_df = core_df.loc[core_df[FEATURES].notna().all(axis=1)].copy()
    X = analysis_df[FEATURES].to_numpy(dtype=np.float64)
    means = np.mean(X, axis=0)
    stds = np.std(X, axis=0, ddof=0)
    Z = (X - means) / stds
    return analysis_df, X, Z, means, stds


def real_silhouettes(Z):
    out = {}
    for k in KS:
        km = KMeans(n_clusters=k, init="k-means++", n_init=10, max_iter=1000,
                    random_state=42)
        labels = km.fit_predict(Z)
        out[k] = float(sklearn_silhouette(Z, labels))
    return out


def null_replicate_silhouettes(draws):
    """One null replicate: z-score ddof=0, then silhouette per k."""
    means = np.mean(draws, axis=0)
    stds = np.std(draws, axis=0, ddof=0)
    stds = np.where(stds == 0.0, 1.0, stds)
    Z = (draws - means) / stds
    out = {}
    for k in KS:
        km = KMeans(n_clusters=k, init="k-means++", n_init=10, max_iter=1000,
                    random_state=42)
        labels = km.fit_predict(Z)
        out[k] = float(sklearn_silhouette(Z, labels))
    return out


def percentile(vals, q):
    return float(np.percentile(vals, q))


def main():
    args = sys.argv[1:]
    if len(args) != 3:
        print(usage())
        raise SystemExit(2)
    null_type, n_replicates_text, log_path = args
    if null_type not in ("gaussian", "copula"):
        print(usage())
        raise SystemExit(2)
    try:
        n_replicates = int(n_replicates_text)
    except ValueError:
        print(usage())
        raise SystemExit(2)
    if n_replicates <= 0:
        print(usage())
        raise SystemExit(2)
    if not log_path.startswith("logs/"):
        print(usage())
        raise SystemExit(2)
    if os.path.exists(log_path):
        print("error: log path already exists, will not overwrite: " + log_path)
        raise SystemExit(2)

    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    start = time.time()
    lines = []
    lines.append("Null-model test of K-Means silhouettes (Phase 3C round).")
    lines.append("Spatial autocorrelation is NOT modelled; this is a structureless")
    lines.append("continuum with the same marginals and correlations.")
    lines.append("")
    lines.append("python " + sys.version.split()[0])
    lines.append("numpy " + np.__version__)
    lines.append("scipy " + scipy.__version__)
    lines.append("pandas " + pd.__version__)
    lines.append("scikit-learn " + sklearn.__version__)
    lines.append("")
    lines.append("Null type: " + null_type)
    lines.append("Replicates requested: " + str(n_replicates))

    analysis_df, X, Z, means, stds = load_real()
    lines.append("Analysis cells: " + str(X.shape[0]))
    lines.append("Features: " + ", ".join(FEATURES))
    lines.append("Draws per replicate: " + str(N_DRAWS))

    real_sil = real_silhouettes(Z)
    lines.append("")
    lines.append("REAL data silhouettes (n_init=10, random_state=42):")
    real_ok = True
    for k in (2, 3, 4):
        target = REAL_SILHOUETTE_TARGETS[k]
        ok = abs(real_sil[k] - target) <= REAL_TOL
        real_ok = real_ok and ok
        lines.append("  k=%d: value=%.6f target=%.6f ok=%s" % (k, real_sil[k],
                                                               target, ok))
    if not real_ok:
        lines.append("")
        lines.append("REAL silhouette mismatch against accepted targets;")
        lines.append("no replicates run.")
        text = "\n".join(lines) + "\n"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)

    # Eigenvalues of correlation matrix of real z features; share of variance
    # of first principal component.
    corr = np.corrcoef(Z, rowvar=False)
    eigenvalues = np.linalg.eigh(corr)[0]
    eigenvalues = eigenvalues[::-1]
    lines.append("")
    lines.append("Eigenvalues of the correlation matrix of the real z features: " +
                 repr(eigenvalues.tolist()))
    lines.append("Share of variance of the first principal component: " +
                 repr(float(eigenvalues[0] / eigenvalues.sum())))

    generator = gaussian_null if null_type == "gaussian" else copula_null
    base = Z if null_type == "gaussian" else X

    null_sils = {k: [] for k in KS}
    argmax_counts = {k: 0 for k in KS}
    best_sils = []

    for rep in range(n_replicates):
        rng = np.random.default_rng([RNG_SEED_BASE, rep])
        draws = generator(base, N_DRAWS, rng)
        rep_sils = null_replicate_silhouettes(draws)
        for k in KS:
            null_sils[k].append(rep_sils[k])
        best_k = max(rep_sils, key=rep_sils.get)
        argmax_counts[best_k] += 1
        best_sils.append(rep_sils[best_k])

    n_run = len(null_sils[KS[0]])
    assert n_run == n_replicates, (
        "replicate count mismatch: requested %d, stored %d" %
        (n_replicates, n_run))
    for k in KS:
        assert len(null_sils[k]) == n_run

    lines.append("")
    lines.append("Replicates actually run: " + str(n_run))
    lines.append("Total elapsed seconds: %.3f" % (time.time() - start))

    lines.append("")
    lines.append("Per-k null silhouette distribution vs real silhouette:")
    lines.append("k   real    null_mean  null_std  null_p5  null_p50  null_p95  null_max  p_value")
    for k in KS:
        vals = np.array(null_sils[k])
        n_ge = int((vals >= real_sil[k]).sum())
        p = (1.0 + n_ge) / (1.0 + n_run)
        lines.append("  %d  %.6f  %.6f  %.6f  %.6f  %.6f  %.6f  %.6f  %.6f" % (
            k, real_sil[k], float(vals.mean()), float(vals.std(ddof=0)),
            percentile(vals, 5), percentile(vals, 50), percentile(vals, 95),
            float(vals.max()), p))
    lines.append("")
    lines.append("Distribution of argmax k across replicates (counts per k): " +
                 str({k: argmax_counts[k] for k in KS}))
    best_arr = np.array(best_sils)
    lines.append("Null distribution of best silhouette over k: mean=%.6f "
                 "std=%.6f p5=%.6f p50=%.6f p95=%.6f max=%.6f" % (
                     float(best_arr.mean()), float(best_arr.std(ddof=0)),
                     percentile(best_arr, 5), percentile(best_arr, 50),
                     percentile(best_arr, 95), float(best_arr.max())))

    text = "\n".join(lines) + "\n"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    return {"null_sils": null_sils, "argmax_counts": argmax_counts,
            "best_sils": best_sils, "n_run": n_run, "real_sil": real_sil}


if __name__ == "__main__":
    main()
