"""Candidate comparison report (Phase 3C round).

Numbers only: no weights are chosen, no exposure transform is selected, no
index is selected, no interpretation text beyond labels. Independent of
kmeans_null.py; imports only index_candidates, stats_utils, numpy, pandas,
scipy. sklearn-free.
"""
import os
import sys

import numpy as np
import pandas as pd
import scipy
from scipy.stats import spearmanr

sys.path.insert(0, "src")

import index_candidates
import stats_utils

LOG_PATH = os.path.join("logs", "phase3c_candidates.txt")
CSV = os.path.join("data", "processed", "cells_500m.csv")
KMEANS_CSV = os.path.join("data", "processed", "cells_kmeans.csv")
FEATURES = ["lst_mean", "ndvi_mean", "ndbi_mean"]
N_TOP = 180


def main():
    if os.path.exists(LOG_PATH):
        print("error: log path already exists, will not overwrite: " + LOG_PATH)
        raise SystemExit(2)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    lines = []
    lines.append("python " + sys.version.split()[0])
    lines.append("numpy " + np.__version__)
    lines.append("scipy " + scipy.__version__)
    lines.append("pandas " + pd.__version__)
    lines.append("")

    df = pd.read_csv(CSV)
    mask = (df["in_bmc"] == True) & (df["core"] == True) & (df["n_land_px"] > 0)  # noqa: E712
    sub = df.loc[mask].copy()
    sub = sub.dropna(subset=FEATURES).reset_index(drop=True)
    n_rows = len(sub)
    lines.append("rows after mask and dropna: " + str(n_rows))
    if n_rows != 1794:
        lines.append("EXPECTED 1794 rows, got " + str(n_rows))
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)

    km = pd.read_csv(KMEANS_CSV)[["cell_id", "k_2", "k_4"]]
    sub = sub.merge(km, on="cell_id", how="left")
    if sub["k_2"].isna().any() or sub["k_4"].isna().any():
        lines.append("NaN in k_2 or k_4 after merge on cell_id")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)

    density = sub["pop_density_land"].to_numpy(dtype=np.float64)
    zero_pop = density == 0.0
    n_zero_pop = int(zero_pop.sum())
    lines.append("zero-pop cells: " + str(n_zero_pop) + " of " + str(n_rows))

    lst = sub["lst_mean"].to_numpy(dtype=np.float64)
    ndvi = sub["ndvi_mean"].to_numpy(dtype=np.float64)
    ndbi = sub["ndbi_mean"].to_numpy(dtype=np.float64)
    k2 = sub["k_2"].to_numpy()
    k4 = sub["k_4"].to_numpy()

    H, S, E_by_kind = index_candidates.component_sets(lst, ndvi, ndbi, density)

    # c. Standardisation check
    lines.append("")
    lines.append("Standardisation check (mean and ddof=0 std):")
    all_std_ok = True
    std_items = [("H", H), ("S", S)] + [
        ("E_" + k, v) for k, v in E_by_kind.items()]
    for label, arr in std_items:
        m = float(np.mean(arr))
        s = float(np.std(arr, ddof=0))
        ok = abs(m) < 1e-9 and abs(s - 1.0) < 1e-9
        all_std_ok = all_std_ok and ok
        lines.append("  %s mean=%.12e std=%.12e ok=%s" % (label, m, s, ok))
    if not all_std_ok:
        lines.append("STANDARDISATION CHECK FAILED")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)

    # d. Pearson 3x3 among H, S, E for each exposure kind
    lines.append("")
    for kind in ("raw", "sqrt", "pct"):
        E = E_by_kind[kind]
        lines.append("Pearson 3x3 among H, S, E_%s:" % kind)
        for row_label, row_arr in [("H", H), ("S", S), ("E", E)]:
            vals = []
            for col_label, col_arr in [("H", H), ("S", S), ("E", E)]:
                r = float(np.corrcoef(row_arr, col_arr)[0, 1])
                vals.append("%.3f" % r)
            lines.append("  %s: %s" % (row_label, " ".join(vals)))

    # e. Print the 10 candidates with weights and exposure kind
    lines.append("")
    lines.append("Candidates (weights wH, wS, wE; exposure kind):")
    for name, (wH, wS, wE, kind) in index_candidates.CANDIDATES.items():
        lines.append("  %s: wH=%s wS=%s wE=%s kind=%s" %
                     (name, wH, wS, wE, kind))

    # Candidate scores
    scores = index_candidates.candidate_scores(lst, ndvi, ndbi, density)
    names = list(scores.keys())
    n_cand = len(names)

    # f. 10x10 Spearman matrix among candidate scores
    lines.append("")
    lines.append("Spearman matrix among candidate scores (rows/cols in candidate order):")
    header = "     " + " ".join("%8s" % n for n in names)
    lines.append(header)
    spearman_mat = np.zeros((n_cand, n_cand))
    for i, ni in enumerate(names):
        row_vals = []
        for j, nj in enumerate(names):
            rho, _ = stats_utils.spearman_rho(scores[ni], scores[nj])
            spearman_mat[i, j] = rho
            row_vals.append("%.3f" % rho)
        lines.append("  %8s %s" % (ni, " ".join(row_vals)))

    max_asym = 0.0
    max_diag = 0.0
    for i in range(n_cand):
        for j in range(n_cand):
            max_asym = max(max_asym, abs(spearman_mat[i, j] - spearman_mat[j, i]))
            max_diag = max(max_diag, abs(spearman_mat[i, i] - 1.0))
    lines.append("max asymmetry: %.3e" % max_asym)
    lines.append("max |diagonal - 1|: %.3e" % max_diag)
    assert max_asym < 1e-12
    assert max_diag < 1e-12

    max_scipy_diff = 0.0
    for i in range(n_cand):
        for j in range(i + 1, n_cand):
            rho_scipy, _ = spearmanr(scores[names[i]], scores[names[j]])
            max_scipy_diff = max(max_scipy_diff,
                                 abs(spearman_mat[i, j] - rho_scipy))
    lines.append("max abs difference vs scipy.stats.spearmanr (45 pairs): %.3e" %
                 max_scipy_diff)
    assert max_scipy_diff < 1e-9

    # g. N_TOP = 180, top-180 sets, Jaccard matrix
    lines.append("")
    lines.append("N_TOP = " + str(N_TOP))
    top_sets = {name: index_candidates.top_set(scores[name], N_TOP)
                for name in names}
    lines.append("Jaccard matrix of top-%d sets:" % N_TOP)
    lines.append(header)
    jaccard_mat = np.zeros((n_cand, n_cand))
    for i, ni in enumerate(names):
        row_vals = []
        for j, nj in enumerate(names):
            jj = index_candidates.jaccard(top_sets[ni], top_sets[nj])
            jaccard_mat[i, j] = jj
            row_vals.append("%.3f" % jj)
        lines.append("  %8s %s" % (ni, " ".join(row_vals)))

    max_j_asym = 0.0
    max_j_diag = 0.0
    for i in range(n_cand):
        for j in range(n_cand):
            max_j_asym = max(max_j_asym, abs(jaccard_mat[i, j] - jaccard_mat[j, i]))
            max_j_diag = max(max_j_diag, abs(jaccard_mat[i, i] - 1.0))
    lines.append("Jaccard max asymmetry: %.3e" % max_j_asym)
    lines.append("Jaccard max |diagonal - 1|: %.3e" % max_j_diag)
    assert max_j_asym < 1e-12
    assert max_j_diag < 1e-12

    # h. Per candidate
    lst_top = index_candidates.top_set(lst, N_TOP)
    lines.append("")
    lines.append("Per candidate (N_TOP=%d):" % N_TOP)
    for name in names:
        rho_with_lst, _ = stats_utils.spearman_rho(scores[name], lst)
        inter = len(top_sets[name] & lst_top)
        jj = index_candidates.jaccard(top_sets[name], lst_top)
        n_zero_inside = int(zero_pop[list(top_sets[name])].sum())
        k2_counts = [int((k2[list(top_sets[name])] == c).sum()) for c in (0, 1)]
        k4_counts = [int((k4[list(top_sets[name])] == c).sum()) for c in range(4)]
        lines.append(
            "  %s: rho_lst=%.3f inter=%d jaccard=%.3f zero_inside=%d/%d "
            "k2_c0=%d k2_c1=%d k4_c0=%d k4_c1=%d k4_c2=%d k4_c3=%d" %
            (name, rho_with_lst, inter, jj, n_zero_inside, n_zero_pop,
             k2_counts[0], k2_counts[1],
             k4_counts[0], k4_counts[1], k4_counts[2], k4_counts[3]))

    text = "\n".join(lines) + "\n"
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
