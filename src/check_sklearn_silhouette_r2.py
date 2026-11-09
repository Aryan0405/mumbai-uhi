"""Independent sklearn KMeans silhouette reproduction check (after rasterio install).

Does not import kmeans_null.py or any other project script.
Writes its own log to logs/phase7a_sklearn_check.txt.
"""
import os
import sys

import numpy as np
import pandas as pd
import scipy
import sklearn
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score as sklearn_silhouette
from sklearn.metrics import silhouette_score as sklearn_silhouette


TARGETS = {
    2: 0.494168,
    3: 0.359270,
    4: 0.370169,
    5: 0.306941,
    6: 0.305566,
    7: 0.303950,
    8: 0.297139,
    9: 0.297564,
    10: 0.298447,
}

FEATURES = ["lst_mean", "ndvi_mean", "ndbi_mean"]
TOL = 1e-6


def run_loop(Z):
    results = []
    for k in range(2, 11):
        km = KMeans(
            n_clusters=k,
            init="k-means++",
            n_init=10,
            max_iter=1000,
            random_state=42,
        )
        labels = km.fit_predict(Z)
        score = sklearn_silhouette(Z, labels)
        results.append(score)
    return results


def main():
    log_path = "logs/phase7a_sklearn_check.txt"
    if os.path.exists(log_path):
        print("error: log path already exists, will not overwrite: " + log_path)
        raise SystemExit(2)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    lines = []
    lines.append("after rasterio install")
    lines.append("python " + sys.version.split()[0])
    lines.append("numpy " + np.__version__)
    lines.append("scipy " + scipy.__version__)
    lines.append("pandas " + pd.__version__)
    lines.append("scikit-learn " + sklearn.__version__)
    lines.append("")

    df = pd.read_csv("data/processed/cells_500m.csv")
    mask = (df["in_bmc"] == True) & (df["core"] == True) & (df["n_land_px"] > 0)  # noqa: E712
    sub = df[mask].copy()
    sub = sub.dropna(subset=FEATURES)
    n_rows = len(sub)
    lines.append("rows after mask and dropna: " + str(n_rows))
    if n_rows != 1794:
        lines.append("EXPECTED 1794 rows, got " + str(n_rows))
        text = "\n".join(lines) + "\n"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)

    X = sub[FEATURES].to_numpy(dtype=np.float64)
    mean = X.mean(axis=0)
    std = X.std(axis=0, ddof=0)
    Z = (X - mean) / std

    results1 = run_loop(Z)
    results2 = run_loop(Z)

    if results1 != results2:
        lines.append("DETERMINISM CHECK FAILED: two runs differ")
        text = "\n".join(lines) + "\n"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    lines.append("determinism check: OK")

    mismatch_found = False
    for i, k in enumerate(range(2, 11)):
        value = results1[i]
        target = TARGETS[k]
        diff = abs(value - target)
        status = "MATCH" if diff <= TOL else "MISMATCH"
        if status == "MISMATCH":
            mismatch_found = True
        lines.append(
            "k={} value={:.6f} target={:.6f} diff={:.6e} {}".format(
                k, value, target, diff, status
            )
        )

    argmax_k = int(np.argmax(results1)) + 2
    lines.append("argmax k: " + str(argmax_k))

    text = "\n".join(lines) + "\n"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)

    if mismatch_found:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
