"""Pre-registered sanity checks for the heat hazard and exposure index (Phase 5 round).

Imports only: index_checks, numpy, pandas, scipy, pyproj, os, sys.
"""
import os
import sys

import numpy as np
import pandas as pd
import pyproj
import scipy

sys.path.insert(0, "src")

import index_checks

CSV = os.path.join("data", "processed", "cells_500m.csv")
INDEX_CSV = os.path.join("data", "processed", "cells_index.csv")
LOG_PATH = os.path.join("logs", "phase5_sanity.txt")
ROWS = 84
COLS = 48
BOX_PARK_LAT_MIN = 19.17
BOX_PARK_LAT_MAX = 19.25
BOX_PARK_LON_MIN = 72.89
BOX_PARK_LON_MAX = 72.93


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
    lines.append("pyproj " + pyproj.__version__)

    # b. Read all 4032 grid cells and the core index table.
    grid = pd.read_csv(CSV)
    if len(grid) != 4032:
        lines.append("EXPECTED 4032 grid rows, got " + str(len(grid)))
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    core = grid[(grid["in_bmc"] == True) & (grid["core"] == True)].copy()  # noqa: E712
    core = core.reset_index(drop=True)
    n_core = len(core)
    lines.append("core cells: " + str(n_core))

    idx = pd.read_csv(INDEX_CSV)
    if list(idx["cell_id"].values) != list(core["cell_id"].values):
        lines.append("cell_id order mismatch between grid core and cells_index.csv")
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)
    if len(idx) != n_core:
        lines.append("cells_index.csv row count " + str(len(idx)) + " != " + str(n_core))
        text = "\n".join(lines) + "\n"
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        raise SystemExit(1)

    # Convert cell centres to EPSG:4326 to test the lat/lon box exactly.
    to_4326 = pyproj.Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True)
    x_centre = core["cell_minx"].to_numpy(dtype=float) + 250.0
    y_centre = core["cell_maxy"].to_numpy(dtype=float) - 250.0
    lon_centre, lat_centre = to_4326.transform(x_centre, y_centre)
    lon_centre = np.asarray(lon_centre, dtype=float)
    lat_centre = np.asarray(lat_centre, dtype=float)

    # Convert BOX_PARK corners to EPSG:32643 and print.
    to_32643 = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)
    corners_lon = [BOX_PARK_LON_MIN, BOX_PARK_LON_MAX, BOX_PARK_LON_MAX, BOX_PARK_LON_MIN]
    corners_lat = [BOX_PARK_LAT_MIN, BOX_PARK_LAT_MIN, BOX_PARK_LAT_MAX, BOX_PARK_LAT_MAX]
    corners_x, corners_y = to_32643.transform(corners_lon, corners_lat)
    lines.append("BOX_PARK corners in EPSG:32643 (x, y):")
    for cx, cy in zip(corners_x, corners_y):
        lines.append("  (%.2f, %.2f)" % (cx, cy))

    in_box = (lat_centre >= BOX_PARK_LAT_MIN) & (lat_centre <= BOX_PARK_LAT_MAX) & \
             (lon_centre >= BOX_PARK_LON_MIN) & (lon_centre <= BOX_PARK_LON_MAX)

    # Inner box: central half in both lat and lon.
    lat_mid = (BOX_PARK_LAT_MIN + BOX_PARK_LAT_MAX) / 2.0
    lon_mid = (BOX_PARK_LON_MIN + BOX_PARK_LON_MAX) / 2.0
    lat_half = (BOX_PARK_LAT_MAX - BOX_PARK_LAT_MIN) / 4.0
    lon_half = (BOX_PARK_LON_MAX - BOX_PARK_LON_MIN) / 4.0
    in_inner = (lat_centre >= lat_mid - lat_half) & (lat_centre <= lat_mid + lat_half) & \
               (lon_centre >= lon_mid - lon_half) & (lon_centre <= lon_mid + lon_half)

    index_primary = idx["index_primary"].to_numpy(dtype=float)
    ndvi_mean = core["ndvi_mean"].to_numpy(dtype=float)
    zone_primary = idx["zone_primary"].to_numpy(dtype=bool)
    thin_obs = core["thin_obs"].to_numpy(dtype=bool)
    med_index_all = float(np.median(index_primary))
    med_ndvi_all = float(np.median(ndvi_mean))

    # c. C1 park checks.
    def c1_report(name, sel):
        n = int(sel.sum())
        med_index = float(np.median(index_primary[sel])) if n > 0 else float("nan")
        med_ndvi = float(np.median(ndvi_mean[sel])) if n > 0 else float("nan")
        share_zone = float(zone_primary[sel].mean()) if n > 0 else float("nan")
        lines.append("")
        lines.append("%s: box cells=%d" % (name, n))
        cons1 = med_index < med_index_all
        lines.append("  C1 median index_primary: computed=%.6f expected=below core median=%.6f %s" %
                     (med_index, med_index_all, "CONSISTENT" if cons1 else "NOT CONSISTENT"))
        cons2 = med_ndvi > med_ndvi_all
        lines.append("  C1 median ndvi_mean: computed=%.6f expected=above core median=%.6f %s" %
                     (med_ndvi, med_ndvi_all, "CONSISTENT" if cons2 else "NOT CONSISTENT"))
        cons3 = share_zone <= 0.02
        lines.append("  C1 share in zone_primary: computed=%.6f expected=at most 0.02 %s" %
                     (share_zone, "CONSISTENT" if cons3 else "NOT CONSISTENT"))

    c1_report("C1 full park box", in_box)
    c1_report("C1 inner park box", in_inner)

    # d. Coastal flag from 2-D grid over all 4032 cells.
    water = (grid["water_dominated"] == True).to_numpy(dtype=int)  # noqa: E712
    water_grid = index_checks.grid_from_cells(
        grid["cell_row"].to_numpy(dtype=int),
        grid["cell_col"].to_numpy(dtype=int),
        water,
        (ROWS, COLS),
        0,
    )
    coastal_grid = index_checks.neighbour_flag(water_grid.astype(bool))
    row_all = grid["cell_row"].to_numpy(dtype=int)
    col_all = grid["cell_col"].to_numpy(dtype=int)
    is_coastal_all = coastal_grid[row_all, col_all]
    core_is_coastal = is_coastal_all[(grid["in_bmc"] == True) & (grid["core"] == True)]  # noqa: E712
    core_is_coastal = np.asarray(core_is_coastal, dtype=bool)
    n_coastal = int(core_is_coastal.sum())
    n_noncoastal = n_core - n_coastal
    lines.append("")
    lines.append("coastal core cells: %d" % n_coastal)
    lines.append("non-coastal core cells: %d" % n_noncoastal)

    # C2 checks: median H of coastal vs non-coastal core cells.
    # cells_index.csv has H column.
    h = idx["H"].to_numpy(dtype=float)
    med_h_coastal = float(np.median(h[core_is_coastal])) if n_coastal > 0 else float("nan")
    med_h_noncoastal = float(np.median(h[~core_is_coastal])) if n_noncoastal > 0 else float("nan")
    share_zone_coastal = float(zone_primary[core_is_coastal].mean()) if n_coastal > 0 else float("nan")
    share_zone_noncoastal = float(zone_primary[~core_is_coastal].mean()) if n_noncoastal > 0 else float("nan")
    cons4 = med_h_coastal < med_h_noncoastal
    lines.append("  C2 median H: computed coastal=%.6f non-coastal=%.6f %s" %
                 (med_h_coastal, med_h_noncoastal,
                  "CONSISTENT" if cons4 else "NOT CONSISTENT"))
    cons5 = share_zone_coastal < share_zone_noncoastal
    lines.append("  C2 share in zone_primary: computed coastal=%.6f non-coastal=%.6f %s" %
                 (share_zone_coastal, share_zone_noncoastal,
                  "CONSISTENT" if cons5 else "NOT CONSISTENT"))

    # e. Box summary.
    n_box = int(in_box.sum())
    n_box_thin = int((in_box & thin_obs).sum()) if n_box > 0 else 0
    n_box_zone = int((in_box & zone_primary).sum()) if n_box > 0 else 0
    lines.append("")
    lines.append("box cells: %d" % n_box)
    lines.append("box cells thin_obs: %d" % n_box_thin)
    lines.append("box cells inside zone_primary: %d" % n_box_zone)

    text = "\n".join(lines) + "\n"
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
