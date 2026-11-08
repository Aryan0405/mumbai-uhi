"""Independent Spearman check (Phase 3A round R3).

Run in process under 'conda run -n uhi python' (no subprocess).
Compares src/stats_utils.spearman_rho against BOTH scipy.stats.spearmanr and
pandas Series.corr(method='spearman') on BMC cells with n_land_px > 0 from
data/processed/cells_500m.csv, for pairs:
lst_mean vs lst_median, lst_mean vs ndvi_mean, lst_mean vs ndbi_mean,
lst_mean vs pop.
Plus one synthetic tie-heavy case: integer arrays length 200, fixed seed.
Prints our value, scipy value, pandas value, absolute differences. Stops if
any difference exceeds 1e-9. Logs to logs/phase3a_spearman_check.txt.
"""
import os
import sys

sys.path.insert(0, "src")

import numpy as np
import pandas as pd
from scipy import stats

from stats_utils import spearman_rho

CSV = os.path.join("data", "processed", "cells_500m.csv")
PAIRS = [
    ("lst_mean", "lst_median"),
    ("lst_mean", "ndvi_mean"),
    ("lst_mean", "ndbi_mean"),
    ("lst_mean", "pop"),
]
THRESHOLD = 1e-9


def load_real():
    df = pd.read_csv(CSV)
    m = (df["in_bmc"] == True) & (df["n_land_px"] > 0)  # noqa: E712
    return df.loc[m]


def compare(label, a, b):
    ours, n = spearman_rho(a, b)
    scipy_val = float(stats.spearmanr(a, b).statistic)
    p_val = float(pd.Series(a).corr(pd.Series(b), method="spearman"))
    d1 = abs(ours - scipy_val)
    d2 = abs(ours - p_val)
    stop = d1 > THRESHOLD or d2 > THRESHOLD
    return {
        "label": label,
        "n": n,
        "ours": ours,
        "scipy": scipy_val,
        "pandas": p_val,
        "diff_scipy": d1,
        "diff_pandas": d2,
        "stop": stop,
    }


def main():
    os.makedirs("logs", exist_ok=True)
    log_path = os.path.join("logs", "phase3a_spearman_check.txt")
    lines = []
    df = load_real()
    lines.append("real data: BMC cells with n_land_px > 0: " + str(int(len(df))))
    results = []
    for c1, c2 in PAIRS:
        a = df[c1].to_numpy(dtype=np.float64)
        b = df[c2].to_numpy(dtype=np.float64)
        results.append(compare(c1 + " vs " + c2, a, b))

    rng = np.random.default_rng(7)
    syn_a = rng.integers(0, 5, size=200).astype(np.float64)
    syn_b = rng.integers(0, 5, size=200).astype(np.float64)
    results.append(compare("synthetic tie-heavy length 200", syn_a, syn_b))

    worst = 0.0
    stop = False
    for r in results:
        lines.append("")
        lines.append("=== " + r["label"] + " ===")
        lines.append("  n_pairs = " + str(r["n"]))
        lines.append("  our spearman_rho   = " + repr(r["ours"]))
        lines.append("  scipy spearmanr    = " + repr(r["scipy"]))
        lines.append("  pandas spearman    = " + repr(r["pandas"]))
        lines.append("  abs diff vs scipy  = " + repr(r["diff_scipy"]))
        lines.append("  abs diff vs pandas = " + repr(r["diff_pandas"]))
        worst = max(worst, r["diff_scipy"], r["diff_pandas"])
        if r["stop"]:
            stop = True
            lines.append("  STOP: difference exceeds 1e-9")
    lines.append("")
    lines.append("worst absolute difference across all comparisons: " + repr(worst))
    if stop:
        lines.append("RESULT: STOP (difference exceeds 1e-9).")
    else:
        lines.append("RESULT: all comparisons within 1e-9.")
    text = "\n".join(lines) + "\n"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    if stop:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
