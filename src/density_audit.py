"""Density audit report (Phase 3A round R4).

Reads data/processed/cells_500m.csv. Reports population density numbers only.
No choice is made among pop_density_bmc, pop_density_land and pop_density_full.
Logs to logs/phase3a_density_audit.txt.
"""
import os

import numpy as np
import pandas as pd

CSV = os.path.join("data", "processed", "cells_500m.csv")
TOTAL_POP = 13661494.69


def p99(values):
    return float(np.percentile(values, 99))


def main():
    os.makedirs("logs", exist_ok=True)
    log_path = os.path.join("logs", "phase3a_density_audit.txt")
    lines = []

    df = pd.read_csv(CSV)
    in_bmc = df["in_bmc"] == True  # noqa: E712
    core = in_bmc & (df["core"] == True)  # noqa: E712
    partial = in_bmc & (df["partial_bmc"] == True)  # noqa: E712
    water = in_bmc & (df["water_dominated"] == True)  # noqa: E712

    lines.append(f"Source: {CSV}")
    lines.append(f"Total population reference: {TOTAL_POP}")
    lines.append("")

    # a. Core cells with pop > 0: count, max, 99th percentile, median of each density.
    core_pop_pos = core & (df["pop"] > 0.0)
    n_core_pop_pos = int(core_pop_pos.sum())
    lines.append("a. Core cells with pop > 0:")
    lines.append(f"  count = {n_core_pop_pos}")
    for col in ["pop_density_bmc", "pop_density_land", "pop_density_full"]:
        vals = df.loc[core_pop_pos, col].to_numpy(dtype=np.float64)
        lines.append(
            f"  {col}: count={int(np.sum(~np.isnan(vals)))} "
            f"max={np.nanmax(vals):.4f} "
            f"p99={p99(vals):.4f} "
            f"median={np.nanmedian(vals):.4f}"
        )
    lines.append("")

    # b. 10 core cells with highest pop_density_bmc.
    core_df = df.loc[core_pop_pos].copy()
    top10_core = core_df.sort_values(
        ["pop_density_bmc", "cell_id"], ascending=[False, True]
    ).head(10)
    lines.append("b. 10 core cells with highest pop_density_bmc:")
    for _, row in top10_core.iterrows():
        lines.append(
            f"  cell_id={int(row['cell_id'])} "
            f"n_bmc_px={int(row['n_bmc_px'])} "
            f"n_grid_px={int(row['n_grid_px'])} "
            f"bmc_fraction={float(row['bmc_fraction']):.6f} "
            f"pop={float(row['pop']):.4f} "
            f"pop_density_bmc={float(row['pop_density_bmc']):.4f} "
            f"pop_density_land={float(row['pop_density_land']):.4f} "
            f"pop_density_full={float(row['pop_density_full']):.4f}"
        )
    lines.append("")

    # c. Among ALL in_bmc cells, the 10 highest pop_density_bmc and whether each is core.
    in_bmc_df = df.loc[in_bmc].copy()
    top10_all = in_bmc_df.sort_values(
        ["pop_density_bmc", "cell_id"], ascending=[False, True]
    ).head(10)
    lines.append("c. 10 highest pop_density_bmc among all in_bmc cells:")
    for _, row in top10_all.iterrows():
        is_core = bool(row["core"])
        lines.append(
            f"  cell_id={int(row['cell_id'])} "
            f"pop_density_bmc={float(row['pop_density_bmc']):.4f} "
            f"core={is_core}"
        )
    lines.append("")

    # d. Population by group.
    pop_core = float(df.loc[core, "pop"].sum())
    pop_partial = float(df.loc[partial, "pop"].sum())
    pop_water = float(df.loc[water, "pop"].sum())
    both = partial & water
    pop_both = float(df.loc[both, "pop"].sum())
    lines.append("d. Population by group (share of total 13,661,494.69):")
    lines.append(f"  pop in core cells = {pop_core:.2f} "
                 f"({100 * pop_core / TOTAL_POP:.4f}%)")
    lines.append(f"  pop in partial_bmc cells = {pop_partial:.2f} "
                 f"({100 * pop_partial / TOTAL_POP:.4f}%)")
    lines.append(f"  pop in water_dominated cells = {pop_water:.2f} "
                 f"({100 * pop_water / TOTAL_POP:.4f}%)")
    lines.append(f"  pop in cells that are both partial_bmc and water_dominated = "
                 f"{pop_both:.2f} ({100 * pop_both / TOTAL_POP:.4f}%)")
    lines.append("")

    # e. Core cells where densities differ from pop_density_full by more than 20 percent.
    core_vals = df.loc[core]
    pdb = core_vals["pop_density_bmc"].to_numpy(dtype=np.float64)
    pdl = core_vals["pop_density_land"].to_numpy(dtype=np.float64)
    pdf = core_vals["pop_density_full"].to_numpy(dtype=np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        diff_bmc = np.abs((pdb - pdf) / pdf)
        diff_land = np.abs((pdl - pdf) / pdf)
    n_diff_bmc = int(np.sum(diff_bmc > 0.20))
    n_diff_land = int(np.sum(diff_land > 0.20))
    lines.append("e. Core cells where density differs from pop_density_full by > 20%:")
    lines.append(f"  pop_density_bmc vs pop_density_full: {n_diff_bmc}")
    lines.append(f"  pop_density_land vs pop_density_full: {n_diff_land}")
    lines.append("")

    # f. Cells with pop > 0 and n_land_px equal to 0.
    n_pop_pos_land0 = int(((df["pop"] > 0.0) & (df["n_land_px"] == 0)).sum())
    lines.append(f"f. Cells with pop > 0 and n_land_px == 0: {n_pop_pos_land0}")
    lines.append("")
    lines.append("Numbers only; no interpretation.")

    text = "\n".join(lines) + "\n"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
