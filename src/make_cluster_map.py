"""Cluster map for the argmax k (Phase 3B round 1).

Writes logs/phase3b_map_clusters.png for k = 2: core analysis cells coloured
by cluster with qualitative tab10 colormap (no white/grey in clusters);
outside BMC white; in_bmc cells that are not core in light grey; BMC outline
from config.BMC_GEOJSON in EPSG:32643; equal aspect; figure sized to the grid
aspect; axis tick labels in metres; legend with one entry per cluster showing
cluster id, cell count and mean raw LST, plus entries for white and grey;
title states K-Means, k, the three features, and that LST is a composite of
clear days March to May 2024 to 2026.
Logs file name, pixel size and colours to logs/phase3b_map.txt.
"""
import os
import sys

sys.path.insert(0, "src")

import matplotlib
matplotlib.use("Agg")
import matplotlib.colors
import matplotlib.image as mpimg
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import geopandas as gpd

import config

CSV = os.path.join("data", "processed", "cells_500m.csv")
LABELS_CSV = os.path.join("data", "processed", "cells_kmeans.csv")
LOG_DIR = config.DIR_LOGS
OUT_PNG = os.path.join(LOG_DIR, "phase3b_map_clusters.png")
N_COLS = 48
N_ROWS = 84
CELL_SIZE = 500.0


def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    df = pd.read_csv(CSV)
    lab = pd.read_csv(LABELS_CSV)
    df = df.merge(lab[["cell_id", "k_2"]], on="cell_id", how="left")
    in_bmc = df["in_bmc"] == True  # noqa: E712
    core = in_bmc & (df["core"] == True)  # noqa: E712
    analysis = core & (df["n_land_px"] > 0)

    # Grid placement by cell_row / cell_col, row 0 at the top.
    grid = np.full((N_ROWS, N_COLS), np.nan, dtype=np.float64)
    not_core_grid = np.zeros((N_ROWS, N_COLS), dtype=bool)
    rows = df.loc[analysis, "cell_row"].to_numpy(dtype=int)
    cols = df.loc[analysis, "cell_col"].to_numpy(dtype=int)
    labels = df.loc[analysis, "k_2"].to_numpy(dtype=int)
    grid[rows, cols] = labels
    not_core_rows = df.loc[in_bmc & (~core), "cell_row"].to_numpy(dtype=int)
    not_core_cols = df.loc[in_bmc & (~core), "cell_col"].to_numpy(dtype=int)
    not_core_grid[not_core_rows, not_core_cols] = True

    minx = float(df["cell_minx"].min())
    maxy = float(df["cell_maxy"].max())
    xmax = minx + N_COLS * CELL_SIZE
    ymin = maxy - N_ROWS * CELL_SIZE
    extent = (minx, xmax, ymin, maxy)
    aspect = (xmax - minx) / (maxy - ymin)
    fig_w = 8.0
    fig_h = fig_w / aspect

    cmap = plt.get_cmap("tab10").copy()
    cmap.set_bad(color="white")

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    im = ax.imshow(grid, origin="upper", extent=extent, vmin=0, vmax=9, cmap=cmap)
    if not_core_grid.any():
        nc = np.where(not_core_grid, 10.0, np.nan)
        ax.imshow(nc, origin="upper", extent=extent, vmin=0, vmax=10,
                  cmap=matplotlib.colors.ListedColormap(["grey"]))
    bmc = gpd.read_file(config.BMC_GEOJSON).dissolve().to_crs(config.CRS_METRIC)
    bmc.boundary.plot(ax=ax, color="black", linewidth=1.2)
    ax.set_aspect("equal")
    ax.set_xlabel("Easting (m)")
    ax.set_ylabel("Northing (m)")
    ax.set_title("K-Means k=2 clusters: features lst_mean, ndvi_mean, ndbi_mean. "
                 "LST composite of clear days March to May 2024 to 2026.")

    # Legend: one entry per cluster with id, cell count, mean raw LST.
    handles = []
    for k_id in range(2):
        members = labels == k_id
        cnt = int(members.sum())
        mean_lst = float(df.loc[analysis, "lst_mean"].to_numpy(dtype=np.float64)[members].mean())
        handles.append(mpatches.Patch(color=cmap(k_id),
                                      label="cluster %d: %d cells, mean LST %.2f C" % (k_id, cnt, mean_lst)))
    handles.append(mpatches.Patch(color="white", label="Outside BMC (white)"))
    handles.append(mpatches.Patch(color="grey", label="In BMC, not core (grey)"))
    ax.legend(handles=handles, loc="lower center", ncol=2, frameon=False, fontsize=8)
    fig.tight_layout(rect=[0, 0.06, 1, 0.96])
    fig.savefig(OUT_PNG, dpi=150)
    plt.close(fig)

    arr = mpimg.imread(OUT_PNG)
    h, w = arr.shape[:2]
    lines = []
    lines.append("Wrote " + OUT_PNG + " (" + str(w) + "x" + str(h) + " pixels)")
    lines.append("Colours: tab10 cluster 0 and 1; outside BMC white; in BMC not core grey")
    text = "\n".join(lines) + "\n"
    with open(os.path.join(LOG_DIR, "phase3b_map.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
