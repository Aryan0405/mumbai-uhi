"""Make three maps from data/processed/cells_500m.csv (Phase 3A round R4).

Writes logs/phase3a_map_lst_mean.png, phase3a_map_population.png,
phase3a_map_vc_median.png.

Source: cells_500m.csv placed on the 84 x 48 grid by cell_row and cell_col,
row 0 at the top.
- BMC outline from config.BMC_GEOJSON projected to EPSG:32643, in the same
  coordinates as the cell grid.
- Axes equal aspect, figure size proportional to grid aspect, tight layout,
  colorbar with label and units.
- Colour scale limits computed from core cells only.
- Cells outside BMC are white. In_bmc cells that are not core are grey.
  Caption text explains white and grey.
- Title states what is shown and that LST is a composite of clear days
  March to May 2024 to 2026.
- thin_obs cells outlined with a thin dark edge on the vc_median map only.
Logs PNG file names, pixel sizes and colour limits to logs/phase3a_maps.txt.
"""
import os
import sys

sys.path.insert(0, "src")

import matplotlib
matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import geopandas as gpd

import config

CSV = os.path.join(config.DIR_DATA, "processed", "cells_500m.csv")
LOG_DIR = config.DIR_LOGS
N_COLS = 48
N_ROWS = 84
CELL_SIZE = 500.0


def grid_arrays(df):
    n_cells = N_ROWS * N_COLS
    cell_id = df["cell_id"].to_numpy(dtype=np.int64)
    row = (cell_id // N_COLS).astype(int)
    col = (cell_id % N_COLS).astype(int)
    return row, col


def make_value_grid(df, colname, mask):
    grid = np.full((N_ROWS, N_COLS), np.nan, dtype=np.float64)
    row, col = grid_arrays(df)
    grid[row[mask], col[mask]] = df.loc[mask, colname].to_numpy(dtype=np.float64)
    return grid


def make_bool_grid(df, mask):
    grid = np.full((N_ROWS, N_COLS), np.nan, dtype=np.float64)
    row, col = grid_arrays(df)
    grid[row[mask], col[mask]] = 1.0
    return grid


def extent_from_df(df):
    minx = float(df["cell_minx"].min())
    maxy = float(df["cell_maxy"].max())
    xmax = minx + N_COLS * CELL_SIZE
    ymin = maxy - N_ROWS * CELL_SIZE
    return (minx, xmax, ymin, maxy)


def draw_bmc_outline(ax):
    bmc = gpd.read_file(config.BMC_GEOJSON).dissolve().to_crs(config.CRS_METRIC)
    bmc.boundary.plot(ax=ax, color="black", linewidth=1.2)


def add_white_grey_caption(ax, fig):
    white_patch = mpatches.Patch(color="white", label="Outside BMC (white)")
    grey_patch = mpatches.Patch(color="grey", label="In BMC, not core (grey)")
    fig.legend(handles=[white_patch, grey_patch], loc="lower center",
               ncol=2, frameon=False, fontsize=9)


def draw_thin_obs_edges(ax, df, thin_mask):
    row, col = grid_arrays(df)
    for r, c in zip(row[thin_mask], col[thin_mask]):
        x0 = float(df.loc[df["cell_id"] == (r * N_COLS + c), "cell_minx"].iloc[0])
        y1 = float(df.loc[df["cell_id"] == (r * N_COLS + c), "cell_maxy"].iloc[0])
        rect = mpatches.Rectangle((x0, y1 - CELL_SIZE), CELL_SIZE, CELL_SIZE,
                                  fill=False, edgecolor="black", linewidth=0.6)
        ax.add_patch(rect)


def make_map(colname, title, vmin, vmax, cmap, thin_mask=None, fname_suffix=""):
    df = pd.read_csv(CSV)
    in_bmc = df["in_bmc"] == True  # noqa: E712
    core = in_bmc & (df["core"] == True)  # noqa: E712
    not_core_in_bmc = in_bmc & (~core)
    row, col = grid_arrays(df)

    value_grid = make_value_grid(df, colname, core)
    grey_grid = make_bool_grid(df, not_core_in_bmc)

    extent = extent_from_df(df)
    aspect = (extent[1] - extent[0]) / (extent[3] - extent[2])
    fig_w = 8.0
    fig_h = fig_w / aspect

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    cmap_val = plt.get_cmap(cmap).copy()
    cmap_val.set_bad(color="white")
    cmap_grey = matplotlib.colors.ListedColormap(["grey"])
    cmap_grey.set_bad(color=(0.0, 0.0, 0.0, 0.0))
    im1 = ax.imshow(value_grid, origin="upper", extent=extent,
                    vmin=vmin, vmax=vmax, cmap=cmap_val)
    im2 = ax.imshow(grey_grid, origin="upper", extent=extent,
                    vmin=0, vmax=1, cmap=cmap_grey)
    draw_bmc_outline(ax)
    if thin_mask is not None:
        draw_thin_obs_edges(ax, df, thin_mask)
    ax.set_aspect("equal")
    ax.set_xlabel("Easting (m)")
    ax.set_ylabel("Northing (m)")
    ax.set_title(title)
    cbar = fig.colorbar(im1, ax=ax, fraction=0.046, pad=0.04)
    add_white_grey_caption(ax, fig)
    fig.tight_layout(rect=[0, 0.04, 1, 0.96])
    out_path = os.path.join(LOG_DIR, f"phase3a_map{fname_suffix}.png")
    fig.savefig(out_path, dpi=150)
    plt.close(fig)

    arr = mpimg.imread(out_path)
    h, w = arr.shape[:2]
    return out_path, w, h, vmin, vmax


def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    df = pd.read_csv(CSV)
    in_bmc = df["in_bmc"] == True  # noqa: E712
    core = in_bmc & (df["core"] == True)  # noqa: E712
    core_pop = core & (df["pop"] > 0.0)

    lst_vals = df.loc[core, "lst_mean"].to_numpy(dtype=np.float64)
    pop_vals = df.loc[core, "pop"].to_numpy(dtype=np.float64)
    vc_vals = df.loc[core, "vc_median"].to_numpy(dtype=np.float64)

    lst_vmin, lst_vmax = float(np.nanmin(lst_vals)), float(np.nanmax(lst_vals))
    pop_vmin, pop_vmax = float(np.nanmin(pop_vals)), float(np.nanmax(pop_vals))
    vc_vmin, vc_vmax = float(np.nanmin(vc_vals)), float(np.nanmax(vc_vals))

    thin_mask = in_bmc & (df["thin_obs"] == True)  # noqa: E712

    results = []
    results.append(make_map(
        "lst_mean",
        "LST mean (C): core cells. LST is a composite of clear days March to May 2024 to 2026.",
        lst_vmin, lst_vmax, "YlOrRd", fname_suffix="_lst_mean"))
    results.append(make_map(
        "pop",
        "Population: core cells (people per cell).",
        pop_vmin, pop_vmax, "YlGn", fname_suffix="_population"))
    results.append(make_map(
        "vc_median",
        "Valid count median: core cells (dates).",
        vc_vmin, vc_vmax, "Blues", thin_mask=thin_mask,
        fname_suffix="_vc_median"))

    lines = []
    for out_path, w, h, vmin, vmax in results:
        lines.append(f"Wrote {out_path} ({w}x{h} pixels), colour limits "
                     f"vmin={vmin:.4f} vmax={vmax:.4f} (core cells only).")
    text = "\n".join(lines) + "\n"
    log_path = os.path.join(LOG_DIR, "phase3a_maps.txt")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
