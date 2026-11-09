"""Redraw index maps with verified orientation (Phase 5B round).

NEW file; src/make_index_maps.py is not edited. Writes _r2 PNGs to docs/figures
and a verification log to logs/phase5b_maps.txt. Existing outputs are never
overwritten (exit 2 if any output already exists).
"""
import hashlib
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.path as mpath
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd
import pyproj

CSV = os.path.join("data", "processed", "cells_500m.csv")
INDEX_CSV = os.path.join("data", "processed", "cells_index.csv")
SENS_CSV = os.path.join("data", "processed", "cells_index_sens.csv")
FIG_DIR = os.path.join("docs", "figures")
LOG_PATH = os.path.join("logs", "phase5b_maps.txt")
ROWS = 84
COLS = 48
N_TOP = 180
DPI = 100
WIDTH_PX = 1000
CELL_SIZE = 500.0
BOX_PARK_LAT_MIN = 19.17
BOX_PARK_LAT_MAX = 19.25
BOX_PARK_LON_MIN = 72.89
BOX_PARK_LON_MAX = 72.93


def grid_from_all(values, all_rows, all_cols, fill=np.nan):
    out = np.full((ROWS, COLS), fill, dtype=float)
    out[all_rows, all_cols] = values
    return out


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def cmap_hex_list(cmap):
    return [mcolors.to_hex(c) for c in cmap.colors]


def main():
    outs = [
        os.path.join(FIG_DIR, "map_index_primary_r2.png"),
        os.path.join(FIG_DIR, "map_zone_agreement_r2.png"),
        os.path.join(FIG_DIR, "map_zone_stability_r2.png"),
        os.path.join(FIG_DIR, "map_zone_robust_fragile_r2.png"),
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
    lines.append("pyproj " + pyproj.__version__)
    lines.append("matplotlib " + matplotlib.__version__)

    grid = pd.read_csv(CSV)
    if len(grid) != 4032:
        lines.append("EXPECTED 4032 grid rows, got " + str(len(grid)))
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)

    idx = pd.read_csv(INDEX_CSV)
    sens = pd.read_csv(SENS_CSV)

    core_mask = (grid["in_bmc"] == True) & (grid["core"] == True)  # noqa: E712
    core_grid = grid.loc[core_mask].reset_index(drop=True)
    if len(core_grid) != 1794:
        lines.append("EXPECTED 1794 core cells, got " + str(len(core_grid)))
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    if list(idx["cell_id"].values) != list(core_grid["cell_id"].values):
        lines.append("cells_index.csv cell_id order mismatch")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    if list(sens["cell_id"].values) != list(core_grid["cell_id"].values):
        lines.append("cells_index_sens.csv cell_id order mismatch")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)

    # c. Grid alignment assertions over all 4032 cells.
    xmin_edge = float(grid["cell_minx"].min())
    ymax_edge = float(grid["cell_maxy"].max())
    lines.append("xmin_edge=%.6f ymax_edge=%.6f" % (xmin_edge, ymax_edge))
    col_pred = np.round((grid["cell_minx"].to_numpy(dtype=float) - xmin_edge) / CELL_SIZE).astype(int)
    row_pred = np.round((ymax_edge - grid["cell_maxy"].to_numpy(dtype=float)) / CELL_SIZE).astype(int)
    col_match = bool((col_pred == grid["cell_col"].to_numpy(dtype=int)).all())
    row_match = bool((row_pred == grid["cell_row"].to_numpy(dtype=int)).all())
    lines.append("grid alignment cell_col match: %s" % col_match)
    lines.append("grid alignment cell_row match: %s" % row_match)
    if not (col_match and row_match):
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)

    all_rows = grid["cell_row"].to_numpy(dtype=int)
    all_cols = grid["cell_col"].to_numpy(dtype=int)
    core_rows = core_grid["cell_row"].to_numpy(dtype=int)
    core_cols = core_grid["cell_col"].to_numpy(dtype=int)
    thin_obs = idx["thin_obs"].to_numpy(dtype=bool)
    index_primary = idx["index_primary"].to_numpy(dtype=float)
    zone_primary = idx["zone_primary"].to_numpy(dtype=bool)
    zone_noexp = idx["zone_noexp"].to_numpy(dtype=bool)
    zone_count = sens["zone_count"].to_numpy(dtype=int)
    zone_robust = sens["zone_robust"].to_numpy(dtype=bool)
    zone_fragile = sens["zone_fragile"].to_numpy(dtype=bool)

    # e. Park polygon in grid edge coordinates.
    to_32643 = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)
    corners_lon = [BOX_PARK_LON_MIN, BOX_PARK_LON_MAX, BOX_PARK_LON_MAX, BOX_PARK_LON_MIN]
    corners_lat = [BOX_PARK_LAT_MIN, BOX_PARK_LAT_MIN, BOX_PARK_LAT_MAX, BOX_PARK_LAT_MAX]
    corners_x, corners_y = to_32643.transform(corners_lon, corners_lat)
    corners_x = np.asarray(corners_x, dtype=float)
    corners_y = np.asarray(corners_y, dtype=float)
    corner_cols = (corners_x - xmin_edge) / CELL_SIZE
    corner_rows = (ymax_edge - corners_y) / CELL_SIZE
    verts = list(zip(corner_cols, corner_rows))
    lines.append("park polygon vertices (col, row):")
    for cv, rv in verts:
        lines.append("  (%.4f, %.4f)" % (cv, rv))
    polygon = mpath.Path(verts)

    # f. Box membership cross-check.
    x_centre = core_grid["cell_minx"].to_numpy(dtype=float) + CELL_SIZE / 2.0
    y_centre = core_grid["cell_maxy"].to_numpy(dtype=float) - CELL_SIZE / 2.0
    to_4326 = pyproj.Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True)
    lon_centre, lat_centre = to_4326.transform(x_centre, y_centre)
    lon_centre = np.asarray(lon_centre, dtype=float)
    lat_centre = np.asarray(lat_centre, dtype=float)
    latlon_box = (lat_centre >= BOX_PARK_LAT_MIN) & (lat_centre <= BOX_PARK_LAT_MAX) & \
                 (lon_centre >= BOX_PARK_LON_MIN) & (lon_centre <= BOX_PARK_LON_MAX)
    centres = np.column_stack([core_cols + 0.5, core_rows + 0.5])
    poly_inside = polygon.contains_points(centres)
    n_poly = int(poly_inside.sum())
    n_latlon = int(latlon_box.sum())
    n_disagree = int((poly_inside != latlon_box).sum())
    lines.append("box cross-check: polygon count=%d latlon count=%d disagree=%d" %
                 (n_poly, n_latlon, n_disagree))
    if n_disagree > 2:
        lines.append("box cross-check disagreement exceeds 2")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    n_box_zone = int((latlon_box & zone_primary).sum())
    med_box = float(np.median(index_primary[latlon_box]))
    lines.append("box cells zone_primary count=%d" % n_box_zone)
    lines.append("box cells median index_primary=%.6f" % med_box)

    # Common drawing helpers.
    non_core_mask = ~core_mask
    fig_w_in = WIDTH_PX / DPI
    fig_h_in = fig_w_in * ROWS / COLS

    def extent():
        return [0, COLS, ROWS, 0]

    def draw_primary(ax, fig):
        values_full = np.full(len(all_rows), np.nan)
        values_full[core_mask.values] = index_primary
        values_grid = grid_from_all(values_full, all_rows, all_cols, fill=np.nan)
        cmap = plt.get_cmap("inferno")
        cmap.set_bad("white")
        vmin = float(np.nanmin(index_primary))
        vmax = float(np.nanmax(index_primary))
        norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
        im = ax.imshow(values_grid, origin="upper", cmap=cmap, norm=norm,
                       extent=extent(), interpolation="nearest")
        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label("index_primary (primary = 0.4 H + 0.4 S + 0.2 E_raw)")
        thin_rows = core_rows[thin_obs]
        thin_cols = core_cols[thin_obs]
        ax.scatter(thin_cols + 0.5, thin_rows + 0.5, s=10, c="white",
                   edgecolor="black", linewidth=0.6, marker="o")
        verts_closed = verts + [verts[0]]
        ax.add_patch(mpatches.Polygon(verts_closed, fill=False, edgecolor="cyan",
                                      linewidth=1.5,
                                      label="approximate park box (unverified)"))
        ax.set_ylabel("cell_row (0 at top)")
        ax.set_xlabel("cell_col")
        ax.set_title("index_primary (primary = 0.4 H + 0.4 S + 0.2 E_raw), N_TOP=%d" % N_TOP)
        assert ax.yaxis_inverted() == True
        assert tuple(im.get_extent()) == (0, COLS, ROWS, 0)
        lines.append("map1 yaxis_inverted=%s imshow extent=%s" %
                     (ax.yaxis_inverted(), im.get_extent()))
        return cmap, norm, im

    def draw_agree(ax, fig):
        agree = np.full(len(core_rows), 1, dtype=int)  # neither
        agree[zone_primary & zone_noexp] = 4   # both
        agree[zone_primary & ~zone_noexp] = 2  # primary only
        agree[~zone_primary & zone_noexp] = 3  # noexp only
        agree_grid = grid_from_all(agree, core_rows, core_cols, fill=0)  # 0 = not core
        cmap = mcolors.ListedColormap(["white", "lightgrey", "orange", "blue", "darkred"])
        norm = mcolors.BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5, 4.5], cmap.N)
        im = ax.imshow(agree_grid, origin="upper", cmap=cmap, norm=norm,
                       extent=extent(), interpolation="nearest")
        ax.set_title("zone agreement (primary vs noexp), N_TOP=%d" % N_TOP)
        n_notcore = len(all_rows) - len(core_rows)
        n_neither = int((agree == 1).sum())
        n_primary_only = int((agree == 2).sum())
        n_noexp_only = int((agree == 3).sum())
        n_both = int((agree == 4).sum())
        patches = [
            mpatches.Patch(color=mcolors.to_hex(cmap.colors[0]), label="not core (%d cells)" % n_notcore),
            mpatches.Patch(color=mcolors.to_hex(cmap.colors[1]), label="neither (%d cells)" % n_neither),
            mpatches.Patch(color=mcolors.to_hex(cmap.colors[2]), label="primary only (%d cells)" % n_primary_only),
            mpatches.Patch(color=mcolors.to_hex(cmap.colors[3]), label="noexp only (%d cells)" % n_noexp_only),
            mpatches.Patch(color=mcolors.to_hex(cmap.colors[4]), label="both zones (%d cells)" % n_both),
        ]
        ax.legend(handles=patches, loc="lower right", fontsize=7, framealpha=0.8)
        ax.set_ylabel("cell_row (0 at top)")
        ax.set_xlabel("cell_col")
        return cmap, norm, im

    def draw_stab(ax, fig):
        code = np.full(len(all_rows), 0, dtype=int)  # 0 = not core -> white
        stab_codes = zone_count + 1  # count 0 -> 1, ..., count 5 -> 6
        code[core_mask.values] = stab_codes
        yl = plt.get_cmap("YlOrRd")
        colours = ["white", "#e6e6e6"] + [mcolors.to_hex(yl(t)) for t in (0.2, 0.4, 0.6, 0.8, 1.0)]
        cmap = mcolors.ListedColormap(colours)
        norm = mcolors.BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5], cmap.N)
        stab_grid = grid_from_all(code.astype(float), all_rows, all_cols, fill=0.0)
        im = ax.imshow(stab_grid, origin="upper", cmap=cmap, norm=norm,
                       extent=extent(), interpolation="nearest")
        ax.set_title("zone_count across 5 sensitivity schemes, N_TOP=%d" % N_TOP)
        counts = [int((zone_count == c).sum()) for c in range(6)]
        labels = ["not core (%d cells)" % (len(all_rows) - len(core_rows))]
        for c in range(6):
            labels.append("zone_count=%d (%d cells)" % (c, counts[c]))
        patches = []
        for c in range(7):
            patches.append(mpatches.Patch(color=mcolors.to_hex(cmap.colors[c]), label=labels[c]))
        ax.legend(handles=patches, loc="lower right", fontsize=7, framealpha=0.8)
        ax.set_ylabel("cell_row (0 at top)")
        ax.set_xlabel("cell_col")
        return cmap, norm, im

    def draw_rf(ax, fig):
        code = np.full(len(all_rows), 0, dtype=int)  # 0 = not core -> white
        rf = np.full(len(core_rows), 1, dtype=int)  # neither = 1 -> light grey
        rf[zone_robust] = 3   # robust = 3 -> dark red
        rf[zone_fragile] = 2  # fragile = 2 -> orange
        code[~non_core_mask.values] = rf
        cmap = mcolors.ListedColormap(["white", "lightgrey", "orange", "darkred"])
        norm = mcolors.BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], cmap.N)
        rf_grid = grid_from_all(code.astype(float), all_rows, all_cols, fill=0.0)
        im = ax.imshow(rf_grid, origin="upper", cmap=cmap, norm=norm,
                       extent=extent(), interpolation="nearest")
        ax.set_title("robust and fragile zone (primary zone), N_TOP=%d" % N_TOP)
        n_notcore = len(all_rows) - len(core_rows)
        n_neither = int((rf == 1).sum())
        n_fragile = int((rf == 2).sum())
        n_robust = int((rf == 3).sum())
        patches = [
            mpatches.Patch(color=mcolors.to_hex(cmap.colors[0]), label="not core (%d cells)" % n_notcore),
            mpatches.Patch(color=mcolors.to_hex(cmap.colors[1]), label="neither (%d cells)" % n_neither),
            mpatches.Patch(color=mcolors.to_hex(cmap.colors[2]), label="fragile (%d cells)" % n_fragile),
            mpatches.Patch(color=mcolors.to_hex(cmap.colors[3]), label="robust (%d cells)" % n_robust),
        ]
        ax.legend(handles=patches, loc="lower right", fontsize=7, framealpha=0.8)
        ax.set_ylabel("cell_row (0 at top)")
        ax.set_xlabel("cell_col")
        return cmap, norm, im

    # --- map 1: index_primary ---
    path_primary = os.path.join(FIG_DIR, "map_index_primary_r2.png")
    fig_w_in = WIDTH_PX / DPI
    fig_h_in = fig_w_in * ROWS / COLS
    fig1, ax1 = plt.subplots(figsize=(fig_w_in, fig_h_in), dpi=DPI)
    cmap1, norm1, im1 = draw_primary(ax1, fig1)
    fig1.canvas.draw()
    # h. Orientation check on map 1.
    non_thin = idx.loc[~thin_obs].copy()
    ranks = non_thin["rank_primary"].to_numpy(dtype=float)
    cell_ids = non_thin["cell_id"].to_numpy()
    rows_nt = non_thin["cell_row"].to_numpy(dtype=int)
    cols_nt = non_thin["cell_col"].to_numpy(dtype=int)
    index_nt = index_primary[~thin_obs]
    for target in (1, 450, 900, 1350, 1794):
        diff = np.abs(ranks - target)
        best = int(np.argmin(diff))
        ties = np.where(diff == diff[best])[0]
        if ties.size > 1:
            best = ties[np.argmin(cell_ids[ties])]
        cid = int(cell_ids[best])
        r = int(rows_nt[best])
        c = int(cols_nt[best])
        rank = float(ranks[best])
        val = float(index_nt[best])
        px, py = ax1.transData.transform((c + 0.5, r + 0.5))
        buf = np.asarray(fig1.canvas.buffer_rgba())
        bh, bw = buf.shape[:2]
        pc = int(round(px))
        pr = int(round(bh - py))
        pc = min(max(pc, 0), bw - 1)
        pr = min(max(pr, 0), bh - 1)
        read_rgb = buf[pr, pc, :3].astype(float) / 255.0
        exp_rgb = cmap1(norm1(val))[:3]
        max_diff = float(np.max(np.abs(read_rgb - exp_rgb)))
        status = "MATCH" if max_diff <= 0.02 else "MISMATCH"
        lines.append("orientation cell_id=%d row=%d col=%d rank=%.0f read RGB=(%.4f,%.4f,%.4f) "
                     "expected RGB=(%.4f,%.4f,%.4f) max diff=%.6f %s" %
                     (cid, r, c, rank, read_rgb[0], read_rgb[1], read_rgb[2],
                      exp_rgb[0], exp_rgb[1], exp_rgb[2], max_diff, status))
    fig1.savefig(path_primary)
    plt.close(fig1)
    arr1 = plt.imread(path_primary)
    lines.append("wrote %s size %d x %d pixels" % (path_primary, arr1.shape[1], arr1.shape[0]))
    lines.append("map1 colormap name=%s colours=%s" % (cmap1.name, cmap_hex_list(cmap1)))
    lines.append("map1 colorbar label=index_primary (primary = 0.4 H + 0.4 S + 0.2 E_raw)")
    lines.append("map1 marker: thin_obs face=white edge=black s=10 marker=o")
    lines.append("map1 park polygon label=approximate park box (unverified) edge=cyan")
    lines.append("map1 sha256=" + sha256_file(path_primary))

    # --- map 2: zone agreement ---
    path_agree = os.path.join(FIG_DIR, "map_zone_agreement_r2.png")
    fig2, ax2 = plt.subplots(figsize=(fig_w_in, fig_h_in), dpi=DPI)
    cmap2, norm2, im2 = draw_agree(ax2, fig2)
    fig2.savefig(path_agree)
    plt.close(fig2)
    arr2 = plt.imread(path_agree)
    lines.append("wrote %s size %d x %d pixels" % (path_agree, arr2.shape[1], arr2.shape[0]))
    lines.append("map2 colormap name=%s colours=%s" % (cmap2.name, cmap_hex_list(cmap2)))
    leg2 = ax2.get_legend()
    for h in leg2.get_patches():
        lines.append("map2 legend label=%s facecolor=%s" % (h.get_label(), mcolors.to_hex(h.get_facecolor())))
    lines.append("map2 sha256=" + sha256_file(path_agree))

    # --- map 3: zone stability ---
    path_stab = os.path.join(FIG_DIR, "map_zone_stability_r2.png")
    fig3, ax3 = plt.subplots(figsize=(fig_w_in, fig_h_in), dpi=DPI)
    cmap3, norm3, im3 = draw_stab(ax3, fig3)
    fig3.savefig(path_stab)
    plt.close(fig3)
    arr3 = plt.imread(path_stab)
    lines.append("wrote %s size %d x %d pixels" % (path_stab, arr3.shape[1], arr3.shape[0]))
    lines.append("map3 colormap name=%s colours=%s" % (cmap3.name, cmap_hex_list(cmap3)))
    leg3 = ax3.get_legend()
    for h in leg3.get_patches():
        lines.append("map3 legend label=%s facecolor=%s" % (h.get_label(), mcolors.to_hex(h.get_facecolor())))
    lines.append("map3 sha256=" + sha256_file(path_stab))

    # --- map 4: robust/fragile ---
    path_rf = os.path.join(FIG_DIR, "map_zone_robust_fragile_r2.png")
    fig4, ax4 = plt.subplots(figsize=(fig_w_in, fig_h_in), dpi=DPI)
    cmap4, norm4, im4 = draw_rf(ax4, fig4)
    fig4.savefig(path_rf)
    plt.close(fig4)
    arr4 = plt.imread(path_rf)
    lines.append("wrote %s size %d x %d pixels" % (path_rf, arr4.shape[1], arr4.shape[0]))
    lines.append("map4 colormap name=%s colours=%s" % (cmap4.name, cmap_hex_list(cmap4)))
    leg4 = ax4.get_legend()
    for h in leg4.get_patches():
        lines.append("map4 legend label=%s facecolor=%s" % (h.get_label(), mcolors.to_hex(h.get_facecolor())))
    lines.append("map4 sha256=" + sha256_file(path_rf))

    text = "\n".join(lines) + "\n"
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
