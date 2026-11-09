"""Build the heat hazard and exposure index table (Phase 4 round).

Primary index: W3_raw = 0.4 H + 0.4 S + 0.2 E_raw.
Matched without exposure: W4_noexp = 0.5 H + 0.5 S.
Output: data/processed/cells_index.csv, one row per core cell.
"""
import hashlib
import os
import sys

import numpy as np
import pandas as pd
import scipy

sys.path.insert(0, "src")

import index_candidates
import index_final
import stats_utils

CSV = os.path.join("data", "processed", "cells_500m.csv")
KMEANS_CSV = os.path.join("data", "processed", "cells_kmeans.csv")
OUT_CSV = os.path.join("data", "processed", "cells_index.csv")
LOG_PATH = os.path.join("logs", "phase4_index.txt")
FEATURES = ["lst_mean", "ndvi_mean", "ndbi_mean"]
N_TOP = 180


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
    pop = sub["pop"].to_numpy(dtype=np.float64)
    zero_pop = pop == 0.0
    n_zero_pop = int(zero_pop.sum())
    lines.append("zero-pop cells: " + str(n_zero_pop))
    if n_zero_pop != 199:
        lines.append("EXPECTED 199 zero-pop cells, got " + str(n_zero_pop))
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)

    thin_obs = sub["thin_obs"].to_numpy(dtype=bool)
    n_thin = int(thin_obs.sum())
    lines.append("thin_obs cells: " + str(n_thin))
    if n_thin != 83:
        lines.append("EXPECTED 83 thin_obs cells, got " + str(n_thin))
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)

    lst = sub["lst_mean"].to_numpy(dtype=np.float64)
    ndvi = sub["ndvi_mean"].to_numpy(dtype=np.float64)
    ndbi = sub["ndbi_mean"].to_numpy(dtype=np.float64)

    H, S, E_by_kind = index_candidates.component_sets(lst, ndvi, ndbi, density)
    scores = index_candidates.candidate_scores(lst, ndvi, ndbi, density)
    primary = scores["W3_raw"]
    noexp = scores["W4_noexp"]

    primary_expected = 0.4 * H + 0.4 * S + 0.2 * E_by_kind["raw"]
    noexp_expected = 0.5 * H + 0.5 * S
    if not np.allclose(primary, primary_expected, atol=1e-12):
        lines.append("primary index does not equal 0.4H+0.4S+0.2E_raw")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    if not np.allclose(noexp, noexp_expected, atol=1e-12):
        lines.append("noexp index does not equal 0.5H+0.5S")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)

    rank_primary = index_final.rank_desc(primary)
    rank_noexp = index_final.rank_desc(noexp)
    pct_primary = index_candidates.exposure(primary, "pct")
    zone_primary = index_final.zone_flag(primary, N_TOP)
    zone_noexp = index_final.zone_flag(noexp, N_TOP)
    zone_changed = index_final.changed_membership(zone_primary, zone_noexp)
    low_confidence = thin_obs | zero_pop

    out = pd.DataFrame({
        "cell_id": sub["cell_id"].values,
        "cell_row": sub["cell_row"].values,
        "cell_col": sub["cell_col"].values,
        "lst_mean": lst,
        "ndvi_mean": ndvi,
        "ndbi_mean": ndbi,
        "pop": pop,
        "pop_density_land": density,
        "H": H,
        "S": S,
        "E_raw": E_by_kind["raw"],
        "index_primary": primary,
        "index_noexp": noexp,
        "rank_primary": rank_primary,
        "rank_noexp": rank_noexp,
        "pct_primary": pct_primary,
        "zone_primary": zone_primary,
        "zone_noexp": zone_noexp,
        "zone_changed": zone_changed,
        "thin_obs": thin_obs,
        "zero_pop": zero_pop,
        "low_confidence": low_confidence,
    })

    out.to_csv(OUT_CSV, index=False)

    # Read back and verify.
    back = pd.read_csv(OUT_CSV)
    if len(back) != 1794:
        lines.append("read-back row count " + str(len(back)) + " != 1794")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    if back["index_primary"].isna().any() or back["index_noexp"].isna().any():
        lines.append("NaN in index_primary or index_noexp after read-back")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    if back["cell_id"].nunique() != 1794:
        lines.append("cell_id not unique after read-back")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    if not np.allclose(back["index_primary"].to_numpy(), primary, atol=1e-12):
        lines.append("read-back index_primary differs from in-memory")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    if not np.allclose(back["index_noexp"].to_numpy(), noexp, atol=1e-12):
        lines.append("read-back index_noexp differs from in-memory")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    if int(back["zone_primary"].sum()) != 180:
        lines.append("zone_primary count " + str(int(back["zone_primary"].sum())) + " != 180")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)

    lines.append("Wrote " + OUT_CSV + " with " + str(len(back)) + " rows")

    # h. Reconciliation checks against round 3c candidate report.
    rho_primary_noexp, _ = stats_utils.spearman_rho(primary, noexp)
    rho_primary_lst, _ = stats_utils.spearman_rho(primary, lst)
    jac_zone = index_candidates.jaccard(
        set(np.where(zone_primary)[0]), set(np.where(zone_noexp)[0])
    )
    lst_top = set(np.where(index_final.zone_flag(lst, N_TOP))[0])
    inter = len(set(np.where(zone_primary)[0]) & lst_top)
    zero_inside_zone = int(zero_pop[zone_primary].sum())

    checks = [
        ("Spearman index_primary vs index_noexp", rho_primary_noexp, 0.974),
        ("Jaccard top-180 primary vs noexp", jac_zone, 0.791),
        ("Spearman index_primary vs lst_mean", rho_primary_lst, 0.928),
    ]
    mismatch_found = False
    for name, computed, expected in checks:
        diff = abs(computed - expected)
        status = "MATCH" if diff <= 5e-4 else "MISMATCH"
        if status == "MISMATCH":
            mismatch_found = True
        lines.append("%s: computed=%.6f expected=%.6f abs_diff=%.6e %s" %
                     (name, computed, expected, diff, status))

    lines.append("intersection primary top-180 with LST-alone top-180: computed=%d expected=143 abs_diff=%s %s" %
                 (inter, str(abs(inter - 143)),
                  "MATCH" if inter == 143 else "MISMATCH"))
    if inter != 143:
        mismatch_found = True
    lines.append("zero-pop cells inside primary zone: computed=%d expected=0 abs_diff=%s %s" %
                 (zero_inside_zone, str(zero_inside_zone),
                  "MATCH" if zero_inside_zone == 0 else "MISMATCH"))
    if zero_inside_zone != 0:
        mismatch_found = True

    # i. Report numbers only.
    n_zone_thin = int(thin_obs[zone_primary].sum())
    n_zone_zero = int(zero_pop[zone_primary].sum())
    n_changed = int(zone_changed.sum())
    zone_primary_only = int((zone_changed & zone_primary).sum())
    zone_noexp_only = int((zone_changed & zone_noexp).sum())
    n_low_conf = int(low_confidence.sum())
    n_low_conf_zone = int(low_confidence[zone_primary].sum())

    km = pd.read_csv(KMEANS_CSV)[["cell_id", "k_2", "k_4"]]
    merged = out.merge(km, on="cell_id", how="left")
    if merged["k_2"].isna().any() or merged["k_4"].isna().any():
        lines.append("NaN in k_2 or k_4 after merge")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    zone = merged["zone_primary"].to_numpy(dtype=bool)
    k2_counts = [int((merged["k_2"][zone] == c).sum()) for c in range(2)]
    k4_counts = [int((merged["k_4"][zone] == c).sum()) for c in range(4)]

    med_in = [float(np.median(sub[f][zone])) for f in FEATURES]
    med_out = [float(np.median(sub[f][~zone])) for f in FEATURES]
    pop_med_in = float(np.median(density[zone]))
    pop_med_out = float(np.median(density[~zone]))

    lines.append("")
    lines.append("zone_primary cells that are thin_obs: " + str(n_zone_thin))
    lines.append("zone_primary cells that are zero_pop: " + str(n_zone_zero))
    lines.append("zone_changed True count: " + str(n_changed))
    lines.append("  in zone_primary only: " + str(zone_primary_only))
    lines.append("  in zone_noexp only: " + str(zone_noexp_only))
    lines.append("low_confidence cells overall: " + str(n_low_conf))
    lines.append("low_confidence cells in primary zone: " + str(n_low_conf_zone))
    lines.append("primary zone counts per k_2 cluster: " + str(k2_counts))
    lines.append("primary zone counts per k_4 cluster: " + str(k4_counts))
    lines.append("primary zone medians: lst_mean=%.6f ndvi_mean=%.6f ndbi_mean=%.6f pop_density_land=%.6f" %
                 (med_in[0], med_in[1], med_in[2], pop_med_in))
    lines.append("outside primary zone medians: lst_mean=%.6f ndvi_mean=%.6f ndbi_mean=%.6f pop_density_land=%.6f" %
                 (med_out[0], med_out[1], med_out[2], pop_med_out))

    # j. sha256 of output.
    with open(OUT_CSV, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    lines.append("sha256 " + OUT_CSV + ": " + digest)

    if mismatch_found:
        lines.append("")
        lines.append("RECONCILIATION HAS MISMATCHES; see above.")

    text = "\n".join(lines) + "\n"
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    if mismatch_found:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
