"""Write and verify data/processed/cells_500m.geojson (Phase 3A round R2).

Reads data/processed/cells_500m.csv, keeps in_bmc cells only (expected 2005
features), builds geometry with shapely.box on arrays (no Python for loop over
cells), requires shapely >= 2.0, writes in EPSG:32643 then reprojects to
EPSG:4326 with geopandas GeoDataFrame.to_file with the CRS recorded. Every CSV
column is a feature property. Reads the file back and prints feature count, CRS,
bounding box (must lie inside lon 72.77-72.99 and lat 18.89-19.27), and the sum
of the pop property compared with the CSV. Stops if any check fails.
Logs to logs/phase3a_geojson_check.txt.
"""
import os
import sys

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely import box

sys.path.insert(0, "src")
import config

CSV = os.path.join(config.DIR_DATA, "processed", "cells_500m.csv")
OUT = os.path.join(config.DIR_DATA, "processed", "cells_500m.geojson")
MIN_SHAPEY = (2, 0)


def shapely_version_tuple():
    import shapely
    parts = shapely.__version__.split(".")
    return tuple(int(p) for p in parts[:3])


def main():
    os.makedirs(os.path.join(config.DIR_DATA, "processed"), exist_ok=True)
    os.makedirs(config.DIR_LOGS, exist_ok=True)
    log_path = os.path.join(config.DIR_LOGS, "phase3a_geojson_check.txt")
    lines = []

    if shapely_version_tuple() < MIN_SHAPEY:
        msg = f"STOP: shapely {'.'.join(map(str, shapely_version_tuple()))} < {MIN_SHAPEY}; box on arrays not supported."
        lines.append(msg)
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(msg)
        raise SystemExit(1)

    lines.append(f"shapely version: {__import__('shapely').__version__} (>= {MIN_SHAPEY} OK)")
    lines.append(f"Reading CSV: {CSV}")
    df = pd.read_csv(CSV)
    df_in_bmc = df[df["in_bmc"] == True].copy()  # noqa: E712
    n_in_bmc = int(len(df_in_bmc))
    lines.append(f"in_bmc cells in CSV: {n_in_bmc} (expected 2005)")
    if n_in_bmc != 2005:
        lines.append("STOP: expected 2005 in_bmc features.")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print("\n".join(lines))
        raise SystemExit(1)

    # Geometry built without a Python for loop over cells (shapely.box arrays).
    rows_arr = (df_in_bmc["cell_row"].to_numpy(dtype=np.float64))
    cols_arr = (df_in_bmc["cell_col"].to_numpy(dtype=np.float64))
    # cell_minx / cell_maxy are stored; derive box edges from them directly.
    x0 = df_in_bmc["cell_minx"].to_numpy(dtype=np.float64)
    y1 = df_in_bmc["cell_maxy"].to_numpy(dtype=np.float64)
    x1 = x0 + 500.0
    y0 = y1 - 500.0
    geometries = box(x0, y0, x1, y1)

    gdf = gpd.GeoDataFrame(df_in_bmc.drop(columns=["geometry"], errors="ignore"),
                           geometry=geometries, crs=config.CRS_METRIC)
    gdf = gdf.to_crs(config.CRS_LONLAT)
    gdf.to_file(OUT, driver="GeoJSON")
    lines.append(f"GeoJSON written to {OUT} ({len(gdf)} features, CRS {gdf.crs})")

    # Read back and verify.
    back = gpd.read_file(OUT)
    back = back.to_crs(config.CRS_LONLAT)
    n_features = int(len(back))
    crs = str(back.crs)
    bounds = back.total_bounds  # minx, miny, maxx, maxy
    lon_ok = bool((bounds[0] >= 72.77) and (bounds[2] <= 72.99))
    lat_ok = bool((bounds[1] >= 18.89) and (bounds[3] <= 19.27))
    csv_pop_sum = float(df_in_bmc["pop"].sum())
    geojson_pop_sum = float(back["pop"].sum()) if "pop" in back.columns else np.nan
    pop_match = abs(geojson_pop_sum - csv_pop_sum) < 1e-6
    all_columns = all(col in back.columns for col in df_in_bmc.columns if col != "geometry")

    lines.append(f"Read-back feature count: {n_features} (expected 2005)")
    lines.append(f"Read-back CRS: {crs}")
    lines.append(f"Read-back bounds (lon_min, lat_min, lon_max, lat_max) = "
                 f"({bounds[0]:.6f}, {bounds[1]:.6f}, {bounds[2]:.6f}, {bounds[3]:.6f})")
    lines.append(f"Bounds inside box (lon 72.77-72.99, lat 18.89-19.27): {bool(lon_ok and lat_ok)}")
    lines.append(f"CSV pop sum (in_bmc): {csv_pop_sum:.2f}")
    lines.append(f"GeoJSON pop property sum: {geojson_pop_sum:.2f}")
    lines.append(f"pop sums match: {bool(pop_match)}")
    lines.append(f"Every CSV column present as a feature property: {bool(all_columns)}")

    ok = (n_features == 2005 and lon_ok and lat_ok and pop_match and all_columns)
    lines.append("RESULT: " + ("ALL GEOJSON CHECKS OK" if ok else "STOP: a geojson check failed."))
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Log written to {log_path}")
    print("\n".join(lines))
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
