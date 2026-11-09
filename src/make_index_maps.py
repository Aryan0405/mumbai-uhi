"""Build index maps (Phase 5 round).

matplotlib Agg, numpy, pandas, pyproj, os, sys. Writes three PNGs to
docs/figures/. Existing files are not overwritten. Does not describe what
the maps look like.
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
from matplotlib.image import imread
import numpy as np
import pandas as pd
import pyproj

sys.path.insert(0, "src")

import index_checks

CSV = os.path.join("data", "processed", "cells_500m.csv")
INDEX_CSV = os.path.join("data", "processed", "cells_index.csv")
SENS_CSV = os.path.join("data", "processed", "cells_index_sens.csv")
FIG_DIR = os.path.join("docs", "figures")
LOG_PATH = os.path.join("logs", "phase5_maps.txt")
ROWS = 84
COLS = 48
N_TOP = 180
BOX_PARK_LAT_MIN = 19.17
BOX_PARK_LAT_MAX = 19.25
BOX_PARK_LON_MIN = 72.89
BOX_PARK_LON_MAX = 72.93
DPI = 100
WIDTH_PX = 1000


def grid_values(values, rows, cols, fill=np.nan):
    out = np.full((ROWS, COLS), fill, dtype=float)
    out[rows, cols] = values
    return out


def write_map(path, title, draw_fn, lines):
    if os.path.exists(path):
        lines.append("skipped (already exists): " + path)
        arr = imread(path)
        lines.append("image size %s: %d x %d pixels" % (path, arr.shape[1], arr.shape[0]))
        return
    fig_w_in = WIDTH_PX / DPI
    fig_h_in = fig_w_in * ROWS / COLS
    fig, ax = plt.subplots(figsize=(fig_w_in, fig_h_in), dpi=DPI)
    draw_fn(ax, fig)
    ax.set_title(title)
    ax.set_xlabel("cell_col")
    ax.set_ylabel("cell_row")
    fig.savefig(path)
    plt.close(fig)
    arr = imread(path)
    lines.append("wrote %s" % path)
    lines.append("image size %s: %d x %d pixels" % (path, arr.shape[1], arr.shape[0]))


def main():
    os.makedirs(FIG_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    lines = []
    lines.append("colormap primary: inferno")
    lines.append("colormap agreement: ListedColormap white lightgrey orange blue darkred")
    lines.append("colormap stability: ListedColormap 6 discrete colours zone_count 0..5")
    lines.append("grid shape: %d x %d" % (ROWS, COLS))

    grid = pd.read_csv(CSV)
    idx = pd.read_csv(INDEX_CSV)
    sens = pd.read_csv(SENS_CSV)

    core_mask = (grid["in_bmc"] == True) & (grid["core"] == True)  # noqa: E712
    core_grid = grid.loc[core_mask].reset_index(drop=True)
    rows_a = core_grid["cell_row"].to_numpy(dtype=int)
    cols_a = core_grid["cell_col"].to_numpy(dtype=int)

    # Box rectangle in fractional grid coordinates.
    to_32643 = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)
    to_4326 = pyproj.Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True)
    xmin_edge = float(grid["cell_minx"].min())
    ymax_edge = float(grid["cell_maxy"].max())
    cell_w = 500.0
    cell_h = 500.0

    x_centre = core_grid["cell_minx"].to_numpy(dtype=float) + cell_w / 2.0
    y_centre = core_grid["cell_maxy"].to_numpy(dtype=float) - cell_h / 2.0
    lon_centre, lat_centre = to_4326.transform(x_centre, y_centre)
    lon_centre = np.asarray(lon_centre, dtype=float)
    lat_centre = np.asarray(lat_centre, dtype=float)

    in_box = (lat_centre >= BOX_PARK_LAT_MIN) & (lat_centre <= BOX_PARK_LAT_MAX) & \
             (lon_centre >= BOX_PARK_LON_MIN) & (lon_centre <= BOX_PARK_LON_MAX)

    corners_lon = [BOX_PARK_LON_MIN, BOX_PARK_LON_MAX, BOX_PARK_LON_MAX, BOX_PARK_LON_MIN]
    corners_lat = [BOX_PARK_LAT_MIN, BOX_PARK_LAT_MIN, BOX_PARK_LAT_MAX, BOX_PARK_LAT_MAX]
    corners_x, corners_y = to_32643.transform(corners_lon, corners_lat)
    corners_x = np.asarray(corners_x, dtype=float)
    corners_y = np.asarray(corners_y, dtype=float)
    corner_cols = (corners_x - xmin_edge) / cell_w - 0.5
    corner_rows = (ymax_edge - corners_y) / cell_h - 0.5
    box_left = float(corner_cols.min()) / COLS
    box_right = float(corner_cols.max()) / COLS
    box_top = float(corner_rows.min()) / ROWS
    box_bottom = float(corner_rows.max()) / ROWS
    lines.append("box rectangle fractional grid coords: left=%.4f right=%.4f top=%.4f bottom=%.4f" %
                 (box_left, box_right, box_top, box_bottom))

    zone_p = idx["zone_primary"].to_numpy(dtype=bool)
    zone_n = idx["zone_noexp"].to_numpy(dtype=bool)
    agree = np.full(len(rows_a), 1, dtype=int)
    agree[zone_p & zone_n] = 4
    agree[zone_p & ~zone_n] = 2
    agree[~zone_p & zone_n] = 3
    agree_grid = grid_values(agree, rows_a, cols_a, fill=0)
    cmap_agree = mcolors.ListedColormap(["white", "lightgrey", "orange", "blue", "darkred"])
    bounds_agree = [-0.5, 0.5, 1.5, 2.5, 3.5, 4.5]
    norm_agree = mcolors.BoundaryNorm(bounds_agree, cmap_agree.N)

    zone_count = sens["zone_count"].to_numpy(dtype=int)
    stab_grid = grid_values(zone_count.astype(float), rows_a, cols_a, fill=-1.0)
    colors_stab = ["#8b0000", "#d73027", "#f46d43", "#fdae61", "#fee090", "#ffffbf"]
    cmap_stab = mcolors.ListedColormap(colors_stab)
    cmap_stab.set_under("lightgrey")
    bounds_stab = [-0.5, 0.5, 1.5, 2.5, 3.5, 4.5, 5.5]
    norm_stab = mcolors.BoundaryNorm(bounds_stab, cmap_stab.N)

    primary_values = idx["index_primary"].to_numpy(dtype=float)

    def draw_primary(ax, fig):
        values_grid = grid_values(primary_values, rows_a, cols_a, fill=np.nan)
        im = ax.imshow(values_grid, origin="upper", cmap="inferno",
                       extent=[0, COLS, 0, ROWS])
        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label("index_primary")
        thin = core_grid["thin_obs"].to_numpy(dtype=bool)
        ax.scatter(cols_a[thin] + 0.5, ROWS - (rows_a[thin] + 0.5), s=6, c="white", marker=".")
        left_px = box_left * COLS
        right_px = box_right * COLS
        top_px = box_top * ROWS
        bottom_px = box_bottom * ROWS
        rect = mpatches.Rectangle((left_px, top_px), right_px - left_px, bottom_px - top_px,
                                  fill=False, edgecolor="cyan", linewidth=1.5)
        ax.add_patch(rect)
        ax.text(left_px, top_px, "approximate park box", color="cyan", fontsize=8,
                verticalalignment="bottom")

    def draw_agree(ax, fig):
        ax.imshow(agree_grid, origin="upper", cmap=cmap_agree, norm=norm_agree,
                  extent=[0, COLS, 0, ROWS])
        patches = [
            mpatches.Patch(color="white", label="not core"),
            mpatches.Patch(color="lightgrey", label="neither"),
            mpatches.Patch(color="orange", label="primary only"),
            mpatches.Patch(color="blue", label="noexp only"),
            mpatches.Patch(color="darkred", label="both zones"),
        ]
        ax.legend(handles=patches, loc="lower right", fontsize=7, framealpha=0.8)

    def draw_stab(ax, fig):
        ax.imshow(stab_grid, origin="upper", cmap=cmap_stab, norm=norm_stab,
                  extent=[0, COLS, 0, ROWS])
        patches = [
            mpatches.Patch(color=colors_stab[i], label="zone_count=%d" % i) for i in range(6)
        ]
        ax.legend(handles=patches, loc="lower right", fontsize=7, framealpha=0.8)

    path_primary = os.path.join(FIG_DIR, "map_index_primary.png")
    path_agree = os.path.join(FIG_DIR, "map_zone_agreement.png")
    path_stab = os.path.join(FIG_DIR, "map_zone_stability.png")

    title_primary = "index_primary (primary = 0.4 H + 0.4 S + 0.2 E_raw), N_TOP=%d" % N_TOP
    title_agree = "zone agreement (primary vs noexp), N_TOP=%d" % N_TOP
    title_stab = "zone_count across 5 sensitivity schemes, N_TOP=%d" % N_TOP

    write_map(path_primary, title_primary, draw_primary, lines)
    write_map(path_agree, title_agree, draw_agree, lines)
    write_map(path_stab, title_stab, draw_stab, lines)

    text = "\n".join(lines) + "\n"
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
