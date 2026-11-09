"""Null-model test of K-Means silhouettes (Phase 3B round 2).

Tests whether the real silhouettes exceed what a structureless continuum with
the same marginals and correlations produces. Spatial autocorrelation is NOT
modelled; this is stated in the log.

For each null type, 200 replicates (rng seeded with 2026 and the replicate
index), n_rows = 1794. Copula null uses the raw (unstandardised) real features
X, then each replicate is z-scored with ddof=0 exactly as the real data was.
For each replicate and each k = 2 to 10: KMeans(init="k-means++", n_init=10,
max_iter=1000, random_state=42), sklearn silhouette (Euclidean, all points).
The REAL data silhouettes use the identical settings (n_init=10, random_state=42)
so the comparison is like with like; they are printed next to the n_init=50
values from round 1 (k=2: 0.493867, k=4: 0.370169, k=3: 0.357874).

Logs to logs/phase3b2_null.txt.
"""
import os
import sys
import time

sys.path.insert(0, "src")

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score as sklearn_silhouette

from null_models import copula_null, gaussian_null

CSV = os.path.join("data", "processed", "cells_500m.csv")
LOG_PATH = os.path.join("logs", "phase3b2_null.txt")
FEATURES = ["lst_mean", "ndvi_mean", "ndbi_mean"]
N_REPLICATES = 200
N_DRAWS = 1794
KS = list(range(2, 11))
RNG_SEED_BASE = 2026
TIME_LIMIT_SEC = 8 * 60


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


def null_replicate_silhouettes(draws, rng_seed_base):
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
    os.makedirs("logs", exist_ok=True)
    start = time.time()
    lines = []
    lines.append("Null-model test of K-Means silhouettes (Phase 3B round 2).")
    lines.append("Spatial autocorrelation is NOT modelled; this is a structureless")
    lines.append("continuum with the same marginals and correlations.")
    lines.append("")

    analysis_df, X, Z, means, stds = load_real()
    lines.append("Analysis cells: " + str(X.shape[0]))
    lines.append("Features: " + ", ".join(FEATURES))
    lines.append("Null replicates per type: " + str(N_REPLICATES))
    lines.append("Draws per replicate: " + str(N_DRAWS))

    real_sil = real_silhouettes(Z)
    lines.append("")
    lines.append("REAL data silhouettes (n_init=10, random_state=42), printed next to")
    lines.append("the n_init=50 values from round 1 (k=2: 0.493867, k=4: 0.370169,")
    lines.append("k=3: 0.357874):")
    for k in (2, 3, 4):
        lines.append("  k=%d: n_init=10 value=%.6f  round-1 n_init=50 value=%.6f  differ=%s" % (
            k, real_sil[k],
            {2: 0.493867, 3: 0.357874, 4: 0.370169}[k],
            abs(real_sil[k] - {2: 0.493867, 3: 0.357874, 4: 0.370169}[k]) > 1e-6))

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

    results = {}
    for null_name, generator in (("gaussian", lambda rng: gaussian_null(Z, N_DRAWS, rng)),
                                 ("copula", lambda rng: copula_null(X, N_DRAWS, rng))):
        lines.append("")
        lines.append("Null type: " + null_name)
        null_sils = {k: [] for k in KS}
        argmax_counts = {k: 0 for k in KS}
        best_sils = []
        deadline = start + TIME_LIMIT_SEC

        def time_left():
            return deadline - time.time()

        null_start = time.time()

        # First 5 replicates to time the per-replicate cost for this null type.
        timed_reps = min(5, N_REPLICATES)
        for rep in range(timed_reps):
            rng = np.random.default_rng([RNG_SEED_BASE, rep])
            draws = generator(rng)
            rep_sils = null_replicate_silhouettes(draws, rng)
            for k in KS:
                null_sils[k].append(rep_sils[k])
            best_k = max(rep_sils, key=rep_sils.get)
            argmax_counts[best_k] += 1
            best_sils.append(rep_sils[best_k])
        lines.append("Timing after %d replicates (this null type): %.1f seconds" %
                     (timed_reps, time.time() - null_start))
        per_rep = (time.time() - null_start) / timed_reps

        # Plan replicate count: 200 unless projection exceeds the time limit,
        # in which case reduce to 100 (stated explicitly).
        planned = N_REPLICATES
        if per_rep * N_REPLICATES * 2 > time_left():
            planned = 100
            lines.append("Projected runtime exceeds the time limit; reducing to "
                         "100 replicates per null type, as stated.")
        # Enforce the remaining per-replicate budget for this null type.
        n_planned = min(planned, int(time_left() / per_rep) if per_rep > 0 else 0)
        n_planned = max(n_planned, timed_reps)
        n_used = n_planned

        for rep in range(timed_reps, n_used):
            if time_left() < per_rep:
                lines.append("Stopping " + null_name + " at " + str(rep) +
                             " replicates due to the time limit.")
                n_used = rep
                break
            rng = np.random.default_rng([RNG_SEED_BASE, rep])
            draws = generator(rng)
            rep_sils = null_replicate_silhouettes(draws, rng)
            for k in KS:
                null_sils[k].append(rep_sils[k])
            best_k = max(rep_sils, key=rep_sils.get)
            argmax_counts[best_k] += 1
            best_sils.append(rep_sils[best_k])
        lines.append("Replicates used: " + str(n_used))

        lines.append("Per-k null silhouette distribution vs real silhouette:")
        lines.append("k   real    null_mean  null_std  null_p5  null_p50  null_p95  null_max  p_value")
        for k in KS:
            vals = np.array(null_sils[k])
            n_ge = int((vals >= real_sil[k]).sum())
            p = (1.0 + n_ge) / (1.0 + n_used)
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
        results[null_name] = {
            "null_sils": null_sils, "argmax_counts": argmax_counts,
            "best_sils": best_sils, "n_used": n_used}

    text = "\n".join(lines) + "\n"
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    return {"results": results, "real_sil": real_sil}


if __name__ == "__main__":
    main()
