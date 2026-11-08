"""Feature table for K-Means (Phase 3B round 1).

Reads data/processed/cells_500m.csv (read only). Core cells (core == True)
with n_land_px > 0. Features: lst_mean, ndvi_mean, ndbi_mean. Logs to
logs/phase3b_features.txt.
"""
import os
import sys

sys.path.insert(0, "src")

import numpy as np
import pandas as pd

from stats_utils import spearman_rho

CSV = os.path.join("data", "processed", "cells_500m.csv")
FEATURES = ["lst_mean", "ndvi_mean", "ndbi_mean"]


def main():
    os.makedirs("logs", exist_ok=True)
    log_path = os.path.join("logs", "phase3b_features.txt")
    lines = []

    df = pd.read_csv(CSV)
    core = (df["in_bmc"] == True) & (df["core"] == True) & (df["n_land_px"] > 0)  # noqa: E712
    core_df = df.loc[core].copy()
    n_core = int(core_df.shape[0])
    lines.append("Core cells with n_land_px > 0: " + str(n_core) + " (expected 1794)")

    # NaN per feature among core cells.
    nan_counts = {}
    nan_ids = {}
    for col in FEATURES:
        mask = core_df[col].isna()
        nan_counts[col] = int(mask.sum())
        if mask.any():
            nan_ids[col] = core_df.loc[mask, "cell_id"].tolist()
    lines.append("NaN count per feature among core cells:")
    for col in FEATURES:
        lines.append("  " + col + ": " + str(nan_counts[col]))
        if nan_counts[col] > 0:
            lines.append("    cell_ids: " + str(nan_ids[col]))

    # Drop cells with any NaN feature (no imputation).
    analysis_mask = core_df[FEATURES].notna().all(axis=1)
    dropped = core_df.loc[~analysis_mask].copy()
    analysis_df = core_df.loc[analysis_mask].copy()
    n_analysis = int(analysis_df.shape[0])
    lines.append("Cells dropped due to NaN feature: " + str(int(dropped.shape[0])))
    if dropped.shape[0] > 0:
        for _, row in dropped.iterrows():
            reasons = [c for c in FEATURES if pd.isna(row[c])]
            lines.append("  cell_id=" + str(int(row["cell_id"])) + " reasons=" + str(reasons))
    lines.append("Analysis cells after dropping NaN: " + str(n_analysis))

    # b. pop_density_land recomputed: pop / land_area_km2,
    # land_area_km2 = 0.25 * n_land_px / n_grid_px.
    analysis_df["land_area_km2_recomp"] = (
        0.25 * analysis_df["n_land_px"].to_numpy(dtype=np.float64)
        / analysis_df["n_grid_px"].to_numpy(dtype=np.float64)
    )
    analysis_df["pop_density_land_recomp"] = analysis_df["pop"].to_numpy(dtype=np.float64) / analysis_df["land_area_km2_recomp"].to_numpy(dtype=np.float64)
    stored = analysis_df["pop_density_land"].to_numpy(dtype=np.float64)
    recomputed = analysis_df["pop_density_land_recomp"].to_numpy(dtype=np.float64)
    max_abs_diff = float(np.max(np.abs(stored - recomputed)))
    lines.append("pop_density_land methodology: pop / land_area_km2, where "
                 "land_area_km2 = 0.25 * n_land_px / n_grid_px (0.25 km2 nominal "
                 "500 m cell; n_grid_px is 256, 272 or 289 pixels depending on grid "
                 "position; footprint based, so pixel count bias removed).")
    lines.append("Recomputed against stored column; maximum absolute difference: " + repr(max_abs_diff))

    n_pop_zero = int((analysis_df["pop"] == 0.0).sum())
    lines.append("Core cells with pop equal to 0 (density 0, not NaN; zero kept in "
                 "profiles and noted for index round): " + str(n_pop_zero))

    # c. Raw feature summary.
    lines.append("")
    lines.append("Raw feature summary on analysis cells:")
    for col in FEATURES:
        vals = analysis_df[col].to_numpy(dtype=np.float64)
        qs = np.percentile(vals, [1, 25, 50, 75, 99])
        lines.append("  " + col + ":")
        lines.append("    min=" + repr(float(np.min(vals))))
        lines.append("    p1=" + repr(float(qs[0])))
        lines.append("    p25=" + repr(float(qs[1])))
        lines.append("    p50=" + repr(float(qs[2])))
        lines.append("    p75=" + repr(float(qs[3])))
        lines.append("    p99=" + repr(float(qs[4])))
        lines.append("    max=" + repr(float(np.max(vals))))
        lines.append("    mean=" + repr(float(np.mean(vals))))
        lines.append("    std=" + repr(float(np.std(vals, ddof=0))))

    # Correlation matrices.
    X = analysis_df[FEATURES].to_numpy(dtype=np.float64)
    n = X.shape[0]
    pearson = np.corrcoef(X, rowvar=False)
    spearman = np.zeros((3, 3), dtype=np.float64)
    for i in range(3):
        for j in range(3):
            if i == j:
                spearman[i, j] = 1.0
            else:
                rho, _ = spearman_rho(X[:, i], X[:, j])
                spearman[i, j] = rho
    lines.append("")
    lines.append("Pearson correlation matrix (numpy):")
    lines.append(np.array2string(pearson, precision=6))
    lines.append("Spearman correlation matrix (src/stats_utils.spearman_rho):")
    lines.append(np.array2string(spearman, precision=6))

    # d. Standardisation ddof=0.
    means = np.mean(X, axis=0)
    stds = np.std(X, axis=0, ddof=0)
    Z = (X - means) / stds
    lines.append("")
    lines.append("Standardisation z = (x - mean) / std, ddof=0:")
    for i, col in enumerate(FEATURES):
        lines.append("  " + col + ": mean=" + repr(float(means[i])) + " std=" + repr(float(stds[i])))
    z_means = np.mean(Z, axis=0)
    z_stds = np.std(Z, axis=0, ddof=0)
    for i, col in enumerate(FEATURES):
        lines.append("  z " + col + ": mean=" + repr(float(z_means[i])) + " std=" + repr(float(z_stds[i])))
    for i, col in enumerate(FEATURES):
        assert abs(z_means[i]) <= 1e-9, "z mean not zero"
        assert abs(z_stds[i] - 1.0) <= 1e-9, "z std not one"
    lines.append("Assertion: each z column mean within 1e-9 of 0 and std within 1e-9 of 1: OK")

    # e. Cells with any |z| above 3.
    abs_z = np.abs(Z)
    per_feature = {}
    for i, col in enumerate(FEATURES):
        per_feature[col] = int((abs_z[:, i] > 3.0).sum())
    overall = int((abs_z > 3.0).any(axis=1).sum())
    lines.append("Cells with any |z| above 3 (not removed or winsorised):")
    for col in FEATURES:
        lines.append("  " + col + ": " + str(per_feature[col]))
    lines.append("  overall: " + str(overall))

    text = "\n".join(lines) + "\n"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    return {"n_core": n_core, "n_analysis": n_analysis, "n_dropped": int(dropped.shape[0]),
            "max_abs_diff": max_abs_diff, "n_pop_zero": n_pop_zero, "n_overall_abs_z_gt3": overall}


if __name__ == "__main__":
    main()
