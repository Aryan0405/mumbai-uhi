"""Null-model test of K-Means silhouettes (Phase 3B round 3).

Tests whether the real silhouettes exceed what a structureless continuum with
the same marginals and correlations produces. Spatial autocorrelation is NOT
modelled; this is stated in the log.

Pure numpy + stdlib only (scipy/sklearn/pandas DLLs are blocked by the
environment's application-control policy).

Usage: python src/kmeans_null.py <null_type> <n_replicates> <log_path>
  null_type: gaussian or copula
  n_replicates: number of null replicates to run
  log_path: path to write the log

For each null type, n_replicates replicates (rng seeded with 2026 and the
replicate index), n_rows = 1794. Copula null uses the raw (unstandardised)
real features X, then each replicate is z-scored with ddof=0 exactly as the
real data was. For each replicate and each k = 2 to 10: KMeans(init="k-means++",
max_iter=1000, random_state=42), silhouette (Euclidean, all points). The REAL
data silhouettes use the identical settings so the comparison is like with
like; they are printed next to the n_init=50 values from round 1
(k=2: 0.493867, k=4: 0.370169, k=3: 0.357874).

Each run times itself from its own start. Replicates run until n_replicates is
reached; the count actually used is printed in the header line "Null replicates
per type: N" and next to the per-k table.

Logs to the path given on the command line.
"""
import csv
import os
import sys
import time

sys.path.insert(0, "src")

import numpy as np

from silhouette_numpy import silhouette_score
from null_models import copula_null, gaussian_null

CSV = os.path.join("data", "processed", "cells_500m.csv")
FEATURES = ["lst_mean", "ndvi_mean", "ndbi_mean"]
N_DRAWS = 1794
KS = list(range(2, 11))
RNG_SEED_BASE = 2026
TIME_LIMIT_SEC = 8 * 60
MAX_ITER = 1000


def load_real():
    """Read cells_500m.csv with the stdlib csv module (no pandas DLL) and return
    the analysis cells' raw features X and their ddof=0 z-scores Z. Values are
    identical to a pandas read; only the I/O mechanism differs."""
    with open(CSV, newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames
        cols = {c: [] for c in header}
        for row in reader:
            for c in header:
                v = row[c]
                if v == "":
                    cols[c].append(np.nan)
                elif v in ("True", "False"):
                    cols[c].append(1.0 if v == "True" else 0.0)
                else:
                    cols[c].append(float(v))
    data = {c: np.array(cols[c], dtype=np.float64) for c in header}
    core_mask = (data["in_bmc"] == 1.0) & (data["core"] == 1.0) & (data["n_land_px"] > 0)
    X = np.column_stack([data[c][core_mask] for c in FEATURES])
    means = np.mean(X, axis=0)
    stds = np.std(X, axis=0, ddof=0)
    Z = (X - means) / stds
    return X, Z, means, stds


def kmeans_pp_init(X, k, rng):
    """k-means++ initialization, pure numpy."""
    n = X.shape[0]
    centers = np.empty((k, X.shape[1]))
    centers[0] = X[rng.integers(n)]
    dist2 = np.sum((X - centers[0]) ** 2, axis=1)
    for i in range(1, k):
        prob = dist2 / dist2.sum()
        cum = np.cumsum(prob)
        r = rng.random()
        idx = int(np.searchsorted(cum, r))
        centers[i] = X[idx]
        dist2 = np.minimum(dist2, np.sum((X - centers[i]) ** 2, axis=1))
    return centers


def kmeans_lloyd(X, centers, max_iter):
    """Lloyd iterations, pure numpy. Returns (centers, labels, inertia)."""
    for _ in range(max_iter):
        dist2 = np.sum((X[:, None, :] - centers[None, :, :]) ** 2, axis=2)
        labels = np.argmin(dist2, axis=1)
        new_centers = np.array([X[labels == j].mean(axis=0) for j in range(centers.shape[0])])
        if np.allclose(new_centers, centers):
            centers = new_centers
            break
        centers = new_centers
    dist2 = np.sum((X[:, None, :] - centers[None, :, :]) ** 2, axis=2)
    labels = np.argmin(dist2, axis=1)
    inertia = float(dist2[np.arange(X.shape[0]), labels].sum())
    return centers, labels, inertia


def percentile(vals, q):
    return float(np.percentile(vals, q))


def kmeans(X, k, rng, n_init, max_iter):
    """Run n_init k-means++ initializations, keep best inertia."""
    best = None
    for _ in range(n_init):
        centers0 = kmeans_pp_init(X, k, rng)
        centers, labels, inertia = kmeans_lloyd(X, centers0, max_iter)
        if best is None or inertia < best[2]:
            best = (centers, labels, inertia)
    return best


def null_replicate_silhouettes(draws, rng):
    """One null replicate: z-score ddof=0, then silhouette per k."""
    means = np.mean(draws, axis=0)
    stds = np.std(draws, axis=0, ddof=0)
    stds = np.where(stds == 0.0, 1.0, stds)
    Z = (draws - means) / stds
    out = {}
    for k in KS:
        _, labels, _ = kmeans(Z, k, rng, n_init=10, max_iter=MAX_ITER)
        out[k] = float(silhouette_score(Z, labels))
    return out


def main():
    if len(sys.argv) != 4:
        sys.stderr.write("usage: python src/kmeans_null.py <null_type> <n_replicates> <log_path>\n"
                       "  null_type: gaussian or copula\n"
                       "  n_replicates: number of null replicates to run\n"
                       "  log_path: path to write the log\n")
        raise SystemExit(2)
    null_name = sys.argv[1]
    if null_name not in ("gaussian", "copula"):
        sys.stderr.write("error: null_type must be gaussian or copula, got %s\n" % null_name)
        raise SystemExit(2)
    n_replicates = int(sys.argv[2])
    log_path = sys.argv[3]

    os.makedirs("logs", exist_ok=True)
    start = time.time()
    lines = []
    lines.append("Null-model test of K-Means silhouettes (Phase 3B round 3).")
    lines.append("Spatial autocorrelation is NOT modelled; this is a structureless")
    lines.append("continuum with the same marginals and correlations.")
    lines.append("Implemented in pure numpy + stdlib csv (scipy/sklearn/pandas DLLs")
    lines.append("are blocked by the environment's application-control policy).")
    lines.append("")

    X, Z, means, stds = load_real()
    lines.append("Analysis cells: " + str(X.shape[0]))
    lines.append("Features: " + ", ".join(FEATURES))
    lines.append("Null replicates per type: " + str(n_replicates))
    lines.append("Draws per replicate: " + str(N_DRAWS))

    real_sil = {}
    for k in KS:
        _, labels, _ = kmeans(Z, k, rng=np.random.default_rng(RNG_SEED_BASE),
                              n_init=10, max_iter=MAX_ITER)
        real_sil[k] = float(silhouette_score(Z, labels))
    lines.append("")
    lines.append("REAL data silhouettes (k-means++ n_init=10, random_state=42), printed next to")
    lines.append("the n_init=50 values from round 1 (k=2: 0.493867, k=4: 0.370169,")
    lines.append("k=3: 0.357874):")
    round1 = {2: 0.493867, 3: 0.357874, 4: 0.370169}
    max_diff = 0.0
    for k in (2, 3, 4):
        d = abs(real_sil[k] - round1[k])
        max_diff = max(max_diff, d)
    if max_diff > 1e-3:
        lines.append("")
        lines.append("STOP: real silhouette differs from round 2 by more than 1e-3:")
        for k in (2, 3, 4):
            lines.append("  k=%d: n_init=10 value=%.6f  round-1 n_init=50 value=%.6f" % (
                k, real_sil[k], round1[k]))
        text = "\n".join(lines) + "\n"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    lines.append("")
    lines.append("REAL data silhouettes (k-means++ n_init=10, random_state=42), printed next to")
    lines.append("the n_init=50 values from round 1 (k=2: 0.493867, k=4: 0.370169,")
    lines.append("k=3: 0.357874); max abs difference from round 2 = %.6f "
                 "(RNG noise in k-means++ initialization)." % max_diff)
    for k in (2, 3, 4):
        lines.append("  k=%d: n_init=10 value=%.6f  round-1 n_init=50 value=%.6f" % (
            k, real_sil[k], round1[k]))

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
        timed_reps = min(5, n_replicates)
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

        # Plan replicate count: n_replicates unless projection exceeds the time
        # limit, in which case reduce and state the actual count.
        planned = n_replicates
        if per_rep * n_replicates > time_left():
            planned = int(time_left() / per_rep) if per_rep > 0 else timed_reps
            planned = max(planned, timed_reps)
            lines.append("Projected runtime exceeds the time limit; reducing to %d "
                         "replicates for %s, as stated." % (planned, null_name))
        n_used = planned

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
        lines.append("Null replicates per type: %d" % n_used)
        lines.append("Null replicates actually run: %d" % len(best_sils))

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
        results = {
            "null_sils": null_sils, "argmax_counts": argmax_counts,
            "best_sils": best_sils, "n_used": n_used}

    text = "\n".join(lines) + "\n"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    return {"results": results, "real_sil": real_sil}


if __name__ == "__main__":
    main()
