"""Corrected index maps (_r3) with verified orientation (Phase 6 round).

NEW file; make_index_maps_r2.py is not edited. Writes two PNGs to
docs/figures and a verification log to logs/phase6_maps.txt.
Existing outputs are never overwritten (exit 2 if any exists).
"""
import hashlib
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd
import pyproj

CSV = os.path.join("data", "processed", "cells_500m.csv")
INDEX_CSV = os.path.join("data", "processed", "cells_index.csv")
SENS_CSV = os.path.join("data", "processed", "cells_index_sens.csv")
FIG_DIR = os.path.join("docs", "figures")
LOG_PATH = os.path.join("logs", "phase6_maps.txt")
ROWS = 84
COLS = 48
N_TOP = 180
DPI = 100
WIDTH_PX = 1000
CELL_SIZE = 500.0


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def cmap_hex_list(cmap):
    return [mcolors.to_hex(c) for c in cmap.colors]


def grid_from_all(values, rows, cols, fill=np.nan):
    out = np.full((ROWS, COLS), fill, dtype=float)
    out[rows, cols] = values
    return out


def main():
    outs = [
        os.path.join(FIG_DIR, "map_zone_agreement_r3.png"),
        os.path.join(FIG_DIR, "map_thin_obs_r3.png"),
    ]
    for p in outs + [LOG_PATH]:
        if os.path.exists(p):
            print("error: output already exists, will not overwrite: " + p)
            raise SystemExit(2)
    os.makedirs(FIG_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    lines = []
    lines.append("python " + sys.version.split()[0])
    lines.append("numpy " + np.__version__)
    lines.append("pandas " + pd.__version__)
    lines.append("matplotlib " + matplotlib.__version__)

    grid = pd.read_csv(CSV)
    if len(grid) != 4032:
        lines.append("EXPECTED 4032 grid rows, got " + str(len(grid)))
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    xmin_edge = float(grid["cell_minx"].min())
    ymax_edge = float(grid["cell_maxy"].max())
    col_pred = np.round((grid["cell_minx"].to_numpy(dtype=float) - xmin_edge) / CELL_SIZE).astype(int)
    row_pred = np.round((ymax_edge - grid["cell_maxy"].to_numpy(dtype=float)) / CELL_SIZE).astype(int)
    assert bool((col_pred == grid["cell_col"].to_numpy(dtype=int)).all())
    assert bool((row_pred == grid["cell_row"].to_numpy(dtype=int)).all())
    lines.append("xmin_edge=%.6f ymax_edge=%.6f" % (xmin_edge, ymax_edge))
    lines.append("grid alignment cell_col=True cell_row=True")

    idx = pd.read_csv(INDEX_CSV)
    sens = pd.read_csv(SENS_CSV)
    core_mask = (grid["in_bmc"] == True) & (grid["core"] == True) & (grid["n_land_px"] > 0)  # noqa: E712
    core_mask = core_mask & grid[["lst_mean", "ndvi_mean", "ndbi_mean"]].notna().all(axis=1)
    core_grid = grid.loc[core_mask].reset_index(drop=True)
    assert len(core_grid) == 1794
    assert list(idx["cell_id"].values) == list(core_grid["cell_id"].values)
    assert list(sens["cell_id"].values) == list(core_grid["cell_id"].values)

    core_rows = core_grid["cell_row"].to_numpy(dtype=int)
    core_cols = core_grid["cell_col"].to_numpy(dtype=int)
    all_rows = grid["cell_row"].to_numpy(dtype=int)
    all_cols = grid["cell_col"].to_numpy(dtype=int)
    core_idx = core_mask.to_numpy(dtype=bool)

    zone_primary = idx["zone_primary"].to_numpy(dtype=bool)
    zone_noexp = idx["zone_noexp"].to_numpy(dtype=bool)
    thin_obs = idx["thin_obs"].to_numpy(dtype=bool)
    zone_robust = sens["zone_robust"].to_numpy(dtype=bool)
    zone_fragile = sens["zone_fragile"].to_numpy(dtype=bool)

    fig_w_in = WIDTH_PX / DPI
    fig_h_in = fig_w_in * ROWS / COLS
    extent = [0, COLS, ROWS, 0]

    def draw_agree(ax, fig):
        agree = np.full(len(core_rows), 1, dtype=int)
        agree[zone_primary & zone_noexp] = 4
        agree[zone_primary & ~zone_noexp] = 2
        agree[~zone_primary & zone_noexp] = 3
        agree_grid = grid_from_all(agree, core_rows, core_cols, fill=0)
        cmap = mcolors.ListedColormap(["white", "lightgrey", "orange", "blue", "darkred"])
        norm = mcolors.BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5, 4.5], cmap.N)
        im = ax.imshow(agree_grid, origin="upper", cmap=cmap, norm=norm,
                       extent=extent, interpolation="nearest")
        ax.set_title("zone agreement (primary vs noexp), N_TOP=%d" % N_TOP)
        ax.set_xlabel("cell_col")
        ax.set_ylabel("cell_row (0 at top)")
        n_notcore = int((~core_idx).sum())
        n_neither = int((agree == 1).sum())
        n_primary_only = int((agree == 2).sum())
        n_noexp_only = int((agree == 3).sum())
        n_both = int((agree == 4).sum())
        patches = [
            mpatches.Patch(color=mcolors.to_hex(cmap.colors[0]),
                           label="not core (%d cells)" % n_notcore),
            mpatches.Patch(color=mcolors.to_hex(cmap.colors[1]),
                           label="neither (%d cells)" % n_neither),
            mpatches.Patch(color=mcolors.to_hex(cmap.colors[2]),
                           label="primary only (%d cells)" % n_primary_only),
            mpatches.Patch(color=mcolors.to_hex(cmap.colors[3]),
                           label="noexp only (%d cells)" % n_noexp_only),
            mpatches.Patch(color=mcolors.to_hex(cmap.colors[4]),
                           label="both zones (%d cells)" % n_both),
        ]
        ax.legend(handles=patches, loc="lower right", fontsize=7, framealpha=0.8)
        return cmap, norm, im

    def draw_thin(ax, fig):
        rf = np.full(len(core_rows), 1, dtype=int)
        rf[zone_robust] = 3
        rf[zone_fragile] = 2
        rf_grid = grid_from_all(rf, core_rows, core_cols, fill=0)
        cmap = mcolors.ListedColormap(["white", "lightgrey", "orange", "darkred"])
        norm = mcolors.BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], cmap.N)
        im = ax.imshow(rf_grid, origin="upper", cmap=cmap, norm=norm,
                       extent=extent, interpolation="nearest")
        ax.set_title("robust and fragile zone with thin_obs overlay, N_TOP=%d" % N_TOP)
        ax.set_xlabel("cell_col")
        ax.set_ylabel("cell_row (0 at top)")
        n_notcore = int((~core_idx).sum())
        n_neither = int((rf == 1).sum())
        n_fragile = int((rf == 2).sum())
        n_robust = int((rf == 3).sum())
        n_thin = int(thin_obs.sum())
        patches = [
            mpatches.Patch(color=mcolors.to_hex(cmap.colors[0]),
                           label="not core (%d cells)" % n_notcore),
            mpatches.Patch(color=mcolors.to_hex(cmap.colors[1]),
                           label="neither (%d cells)" % n_neither),
            mpatches.Patch(color=mcolors.to_hex(cmap.colors[2]),
                           label="fragile (%d cells)" % n_fragile),
            mpatches.Patch(color=mcolors.to_hex(cmap.colors[3]),
                           label="robust (%d cells)" % n_robust),
            Line2D([0], [0], marker="o", color="black", label="thin_obs (%d cells)" % n_thin,
                   markerfacecolor="white", markeredgecolor="black", markersize=3, linewidth=0),
        ]
        ax.legend(handles=patches, loc="lower right", fontsize=7, framealpha=0.8)
        thin_rows = core_rows[thin_obs]
        thin_cols = core_cols[thin_obs]
        ax.scatter(thin_cols + 0.5, thin_rows + 0.5, s=10, c="white",
                   edgecolor="black", linewidth=0.6, marker="o")
        return cmap, norm, im

    pos_by_cid = {int(c): p for p, c in enumerate(core_grid["cell_id"].values)}

    def orientation_check(path, ax, fig, cmap, norm, code_grid, categories, not_core_cell):
        fig.canvas.draw()
        buf = np.asarray(fig.canvas.buffer_rgba())
        bh, bw = buf.shape[:2]
        for cid, r, c, category in categories:
            val = int(code_grid[pos_by_cid[cid]])
            expected_rgb = np.array(mcolors.to_rgb(cmap.colors[val]))
            px, py = ax.transData.transform((c + 0.5, r + 0.5))
            pc = int(round(px))
            pr = int(round(bh - py))
            pc = min(max(pc, 0), bw - 1)
            pr = min(max(pr, 0), bh - 1)
            read_rgb = buf[pr, pc, :3].astype(float) / 255.0
            max_diff = float(np.max(np.abs(read_rgb - expected_rgb)))
            status = "MATCH" if max_diff <= 0.02 else "MISMATCH"
            lines.append("pixel cell_id=%d row=%d col=%d category=%s read RGB=(%.4f,%.4f,%.4f) "
                         "expected RGB=(%.4f,%.4f,%.4f) max diff=%.6f %s" %
                         (cid, r, c, category, read_rgb[0], read_rgb[1], read_rgb[2],
                          expected_rgb[0], expected_rgb[1], expected_rgb[2], max_diff, status))
        # one not-core cell (white) per map
        r, c = not_core_cell
        px, py = ax.transData.transform((c + 0.5, r + 0.5))
        pc = int(round(px)); pr = int(round(bh - py))
        pc = min(max(pc, 0), bw - 1); pr = min(max(pr, 0), bh - 1)
        read_rgb = buf[pr, pc, :3].astype(float) / 255.0
        expected_rgb = np.array(mcolors.to_rgb("white"))
        max_diff = float(np.max(np.abs(read_rgb - expected_rgb)))
        status = "MATCH" if max_diff <= 0.02 else "MISMATCH"
        lines.append("pixel cell_id=N/A row=%d col=%d category=not_core read RGB=(%.4f,%.4f,%.4f) "
                     "expected RGB=(1.0000,1.0000,1.0000) max diff=%.6f %s" %
                     (r, c, read_rgb[0], read_rgb[1], read_rgb[2], max_diff, status))

    def lowest_nonthin_in_category(zone_flag, cat_code_map):
        # returns (cid, row, col, code) for lowest cell_id non-thin cell matching cat_code_map
        cand = zone_flag & ~thin_obs
        if not cand.any():
            return None
        positions = np.where(cand)[0]
        best = positions[0]
        for p in positions:
            if core_grid["cell_id"].iloc[p] < core_grid["cell_id"].iloc[best]:
                best = p
        cid = int(core_grid["cell_id"].iloc[best])
        return (cid, int(core_rows[best]), int(core_cols[best]))

    # --- map 1: zone agreement ---
    path_agree = os.path.join(FIG_DIR, "map_zone_agreement_r3.png")
    fig1, ax1 = plt.subplots(figsize=(fig_w_in, fig_h_in), dpi=DPI)
    cmap1, norm1, im1 = draw_agree(ax1, fig1)
    agree = np.full(len(core_rows), 1, dtype=int)
    agree[zone_primary & zone_noexp] = 4
    agree[zone_primary & ~zone_noexp] = 2
    agree[~zone_primary & zone_noexp] = 3
    # map category -> code for colour lookup
    cat_codes = {
        "both zones": 4,
        "primary only": 2,
        "noexp only": 3,
        "neither": 1,
    }
    categories = []
    for cat_name, code in cat_codes.items():
        found = lowest_nonthin_in_category(agree == code, code)
        if found is not None:
            categories.append((found[0], found[1], found[2], cat_name))
    orientation_check(path_agree, ax1, fig1, cmap1, norm1, agree,
                      categories, (int(all_rows[~core_idx][0]), int(all_cols[~core_idx][0])))
    fig1.savefig(path_agree)
    plt.close(fig1)
    arr1 = plt.imread(path_agree)
    lines.append("wrote %s size %d x %d pixels" % (path_agree, arr1.shape[1], arr1.shape[0]))
    lines.append("map1 colormap name=%s colours=%s" % (cmap1.name, cmap_hex_list(cmap1)))
    leg1 = ax1.get_legend()
    for h in leg1.get_patches():
        lines.append("map1 legend label=%s facecolor=%s" %
                     (h.get_label(), mcolors.to_hex(h.get_facecolor())))
    lines.append("map1 sha256=" + sha256_file(path_agree))

    # --- map 2: thin obs ---
    path_thin = os.path.join(FIG_DIR, "map_thin_obs_r3.png")
    fig2, ax2 = plt.subplots(figsize=(fig_w_in, fig_h_in), dpi=DPI)
    cmap2, norm2, im2 = draw_thin(ax2, fig2)
    rf = np.full(len(core_rows), 1, dtype=int)
    rf[zone_robust] = 3
    rf[zone_fragile] = 2
    cat_codes2 = {
        "robust": 3,
        "fragile": 2,
        "neither": 1,
    }
    categories2 = []
    for cat_name, code in cat_codes2.items():
        found = lowest_nonthin_in_category(rf == code, code)
        if found is not None:
            categories2.append((found[0], found[1], found[2], cat_name))
    orientation_check(path_thin, ax2, fig2, cmap2, norm2, rf,
                      categories2, (int(all_rows[~core_idx][0]), int(all_cols[~core_idx][0])))
    fig2.savefig(path_thin)
    plt.close(fig2)
    arr2 = plt.imread(path_thin)
    lines.append("wrote %s size %d x %d pixels" % (path_thin, arr2.shape[1], arr2.shape[0]))
    lines.append("map2 colormap name=%s colours=%s" % (cmap2.name, cmap_hex_list(cmap2)))
    leg2 = ax2.get_legend()
    for h in leg2.get_patches():
        lines.append("map2 legend label=%s facecolor=%s" %
                     (h.get_label(), mcolors.to_hex(h.get_facecolor())))
    lines.append("map2 sha256=" + sha256_file(path_thin))

    text = "\n".join(lines) + "\n"
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
