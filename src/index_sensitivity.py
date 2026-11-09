"""Exposure weight sensitivity for the heat hazard and exposure index (Phase 5 round).

Imports only: index_candidates, index_final, index_checks, stats_utils, numpy,
pandas, scipy, hashlib, os, sys.
"""
import hashlib
import os
import sys

import numpy as np
import pandas as pd
import scipy

sys.path.insert(0, "src")

import index_candidates
import index_checks
import index_final
import stats_utils

CSV = os.path.join("data", "processed", "cells_500m.csv")
INDEX_CSV = os.path.join("data", "processed", "cells_index.csv")
OUT_CSV = os.path.join("data", "processed", "cells_index_sens.csv")
LOG_PATH = os.path.join("logs", "phase5_sensitivity.txt")
FEATURES = ["lst_mean", "ndvi_mean", "ndbi_mean"]
N_TOP = 180
SCHEMES = [("E0", 0.0), ("E10", 0.1), ("E20", 0.2), ("E33", 1 / 3), ("E50", 0.5)]
TOL = 1e-12
RECON_TOL = 5e-4


def main():
    if os.path.exists(OUT_CSV):
        print("error: output already exists, will not overwrite: " + OUT_CSV)
        raise SystemExit(2)
    if os.path.exists(LOG_PATH):
        print("error: log path already exists, will not overwrite: " + LOG_PATH)
        raise SystemExit(2)
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    lines = []
    lines.append("python " + sys.version.split()[0])
    lines.append("numpy " + np.__version__)
    lines.append("scipy " + scipy.__version__)
    lines.append("pandas " + pd.__version__)
    lines.append("N_TOP = " + str(N_TOP))

    # b. Read base cells and cells_index.csv.
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

    density = sub["pop_density_land"].to_numpy(dtype=np.float64)
    thin_obs = sub["thin_obs"].to_numpy(dtype=bool)
    cell_ids = sub["cell_id"].values

    idx = pd.read_csv(INDEX_CSV)
    if list(idx["cell_id"].values) != list(cell_ids):
        lines.append("cell_id order mismatch between cells_500m.csv core and cells_index.csv")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)

    # c. Components and schemes.
    H, S, E_by_kind = index_candidates.component_sets(
        sub["lst_mean"].to_numpy(dtype=np.float64),
        sub["ndvi_mean"].to_numpy(dtype=np.float64),
        sub["ndbi_mean"].to_numpy(dtype=np.float64),
        density,
    )
    E_raw = E_by_kind["raw"]

    all_scores = {}
    for name, wE in SCHEMES:
        wH, wS, _ = index_checks.scheme_weights(wE)
        all_scores[name] = float(wH) * H + float(wS) * S + float(wE) * E_raw

    # d. Reconciliation against cells_index.csv.
    index_primary = idx["index_primary"].to_numpy(dtype=np.float64)
    index_noexp = idx["index_noexp"].to_numpy(dtype=np.float64)
    cand = index_candidates.candidate_scores(
        sub["lst_mean"].to_numpy(dtype=np.float64),
        sub["ndvi_mean"].to_numpy(dtype=np.float64),
        sub["ndbi_mean"].to_numpy(dtype=np.float64),
        density,
    )

    def close(a, b):
        return bool(np.allclose(a, b, atol=TOL))

    recon_checks = [
        ("E20 vs index_primary", all_scores["E20"], index_primary),
        ("E0 vs index_noexp", all_scores["E0"], index_noexp),
        ("E33 vs W1_raw", all_scores["E33"], cand["W1_raw"]),
    ]
    recon_mismatch = False
    for name, a, b in recon_checks:
        ok = close(a, b)
        if not ok:
            recon_mismatch = True
        lines.append("reconcile %s: %s" % (name, ok))

    # e. Spearman matrix and Jaccard matrix over the 5 schemes.
    names = [n for n, _ in SCHEMES]
    n_sch = len(names)
    scores_mat = np.column_stack([all_scores[n] for n in names])
    spearman_mat = np.zeros((n_sch, n_sch))
    for i in range(n_sch):
        for j in range(n_sch):
            rho, _ = stats_utils.spearman_rho(scores_mat[:, i], scores_mat[:, j])
            spearman_mat[i, j] = rho

    zone_sets = {}
    for n in names:
        zone_sets[n] = {i for i, v in enumerate(index_final.zone_flag(all_scores[n], N_TOP)) if v}

    jaccard_mat = np.zeros((n_sch, n_sch))
    for i in range(n_sch):
        for j in range(n_sch):
            jaccard_mat[i, j] = index_candidates.jaccard(zone_sets[names[i]], zone_sets[names[j]])

    max_asym_sp = max(abs(spearman_mat[i, j] - spearman_mat[j, i]) for i in range(n_sch) for j in range(n_sch))
    max_diag_sp = max(abs(spearman_mat[i, i] - 1.0) for i in range(n_sch))
    max_asym_ja = max(abs(jaccard_mat[i, j] - jaccard_mat[j, i]) for i in range(n_sch) for j in range(n_sch))
    max_diag_ja = max(abs(jaccard_mat[i, i] - 1.0) for i in range(n_sch))

    lines.append("Spearman matrix among schemes (rows/cols in scheme order):")
    lines.append("     " + " ".join("%8s" % n for n in names))
    for i in range(n_sch):
        lines.append("  %8s %s" % (names[i], " ".join("%.3f" % spearman_mat[i, j] for j in range(n_sch))))
    lines.append("Spearman max asymmetry: %.3e" % max_asym_sp)
    lines.append("Spearman max |diagonal - 1|: %.3e" % max_diag_sp)
    assert max_asym_sp < 1e-12
    assert max_diag_sp < 1e-12

    lines.append("Jaccard matrix of top-%d sets among schemes:" % N_TOP)
    lines.append("     " + " ".join("%8s" % n for n in names))
    for i in range(n_sch):
        lines.append("  %8s %s" % (names[i], " ".join("%.3f" % jaccard_mat[i, j] for j in range(n_sch))))
    lines.append("Jaccard max asymmetry: %.3e" % max_asym_ja)
    lines.append("Jaccard max |diagonal - 1|: %.3e" % max_diag_ja)
    assert max_asym_ja < 1e-12
    assert max_diag_ja < 1e-12

    # f. Zone size sensitivity for E20.
    lines.append("Zone size sensitivity for E20 (Jaccard with E0 and E33 top-N sets):")
    for N in (90, 180, 360):
        s_e20 = set(index_final.zone_flag(all_scores["E20"], N).astype(bool).tolist())
        s_e20 = {i for i, v in enumerate(index_final.zone_flag(all_scores["E20"], N)) if v}
        s_e0 = {i for i, v in enumerate(index_final.zone_flag(all_scores["E0"], N)) if v}
        s_e33 = {i for i, v in enumerate(index_final.zone_flag(all_scores["E33"], N)) if v}
        lines.append("  N=%d: Jaccard(E20,E0)=%.3f Jaccard(E20,E33)=%.3f" %
                     (N, index_candidates.jaccard(s_e20, s_e0),
                      index_candidates.jaccard(s_e20, s_e33)))

    # g. Transform sensitivity at weights 0.4/0.4/0.2.
    lines.append("Transform sensitivity at weights 0.4/0.4/0.2 (top-180 Jaccard vs E20):")
    s_e20_180 = {i for i, v in enumerate(index_final.zone_flag(all_scores["E20"], N_TOP)) if v}
    w3_sqrt = cand["W3_sqrt"]
    w3_pct = cand["W3_pct"]
    w1_raw = cand["W1_raw"]
    j_sqrt = index_candidates.jaccard(s_e20_180, {i for i, v in enumerate(index_final.zone_flag(w3_sqrt, N_TOP)) if v})
    j_pct = index_candidates.jaccard(s_e20_180, {i for i, v in enumerate(index_final.zone_flag(w3_pct, N_TOP)) if v})
    j_w1raw = index_candidates.jaccard(s_e20_180, {i for i, v in enumerate(index_final.zone_flag(w1_raw, N_TOP)) if v})

    transform_checks = [
        ("W3_raw vs W3_sqrt", j_sqrt, 0.925),
        ("W3_raw vs W3_pct", j_pct, 0.925),
        ("W3_raw vs W1_raw", j_w1raw, 0.827),
    ]
    transform_mismatch = False
    for name, computed, expected in transform_checks:
        diff = abs(computed - expected)
        status = "MATCH" if diff <= RECON_TOL else "MISMATCH"
        if status == "MISMATCH":
            transform_mismatch = True
        lines.append("%s: computed=%.6f expected=%.6f abs_diff=%.6e %s" %
                     (name, computed, expected, diff, status))

    # h. Stability.
    zone_flags = {}
    for n in names:
        zone_flags[n] = index_final.zone_flag(all_scores[n], N_TOP)
    flag_list = [zone_flags[n] for n in names]
    zone_count = index_checks.stability_count(flag_list)
    lines.append("Stability: number of cells per zone_count value (0..5):")
    for c in range(0, 6):
        lines.append("  zone_count=%d: %d cells" % (c, int((zone_count == c).sum())))
    e20_zone = zone_flags["E20"]
    n_robust = int((e20_zone & (zone_count == 5)).sum())
    n_fragile = int((e20_zone & (zone_count < 5)).sum())
    n_fragile_thin = int(((e20_zone & (zone_count < 5)) & thin_obs).sum())
    n_union = int(np.any(np.column_stack(flag_list), axis=1).sum())
    lines.append("cells in E20 zone with zone_count 5 (robust): " + str(n_robust))
    lines.append("cells in E20 zone with zone_count below 5 (fragile): " + str(n_fragile))
    lines.append("fragile E20-zone cells that are thin_obs: " + str(n_fragile_thin))
    lines.append("cells in union of the 5 zones: " + str(n_union))

    # i. Write cells_index_sens.csv.
    sens = pd.DataFrame({
        "cell_id": cell_ids,
        "rank_E0": index_final.rank_desc(all_scores["E0"]),
        "rank_E10": index_final.rank_desc(all_scores["E10"]),
        "rank_E20": index_final.rank_desc(all_scores["E20"]),
        "rank_E33": index_final.rank_desc(all_scores["E33"]),
        "rank_E50": index_final.rank_desc(all_scores["E50"]),
        "zone_count": zone_count,
        "zone_robust": (e20_zone & (zone_count == 5)),
        "zone_fragile": (e20_zone & (zone_count < 5)),
    })
    sens.to_csv(OUT_CSV, index=False)
    back = pd.read_csv(OUT_CSV)
    if len(back) != 1794:
        lines.append("read-back row count " + str(len(back)) + " != 1794")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    if back["cell_id"].nunique() != 1794:
        lines.append("cell_id not unique in cells_index_sens.csv")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    if back[["rank_E0", "rank_E10", "rank_E20", "rank_E33", "rank_E50", "zone_count", "zone_robust", "zone_fragile"]].isna().any().any():
        lines.append("NaN in cells_index_sens.csv read-back")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)

    with open(OUT_CSV, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    lines.append("sha256 " + OUT_CSV + ": " + digest)

    text = "\n".join(lines) + "\n"
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    if recon_mismatch or transform_mismatch:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
