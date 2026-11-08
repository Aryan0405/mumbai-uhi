"""Aggregate composites to a 500 m grid anchored at the top-left corner
(MINX, MAXY) of the existing 30 m grid, row 0 at the top.

Pure functions:
  assign_cell(x, y, minx, maxy, cellsize) -> (row, col)
      col = floor((x - minx) / cellsize)
      row = floor((maxy - y) / cellsize)
  sum_per_cell(values, rows, cols, n_rows, n_cols) -> per-cell sum (np.bincount)
  mean_per_cell(values, rows, cols, n_rows, n_cols) -> (mean array, count array)
      NaN excluded from the mean but counted separately.

Also prints grid info: n_rows, n_cols, total cells, cells with >=1 BMC pixel.
Writes log to logs/round4c_grid.txt.
"""
import os
import sys
import numpy as np
import rasterio
from rasterio.features import rasterize as rio_rasterize
from shapely.geometry import mapping as shp_mapping
import geopandas as gpd

sys.path.insert(0, "src")
import config
from utils import write_log, silence_all_nan_warning

silence_all_nan_warning()

CELL_SIZE = 500.0


def assign_cell(x, y, minx, maxy, cellsize):
    """Cell (row, col) containing the centre (x, y).

    col = floor((x - minx) / cellsize)
    row = floor((maxy - y) / cellsize)
    Row 0 is at the top (maxy).
    """
    col = int(np.floor((x - minx) / cellsize))
    row = int(np.floor((maxy - y) / cellsize))
    return row, col


def sum_per_cell(values, rows, cols, n_rows, n_cols):
    """Sum values per cell. Cells with no values are 0."""
    flat = rows * n_cols + cols
    out = np.zeros(n_rows * n_cols, dtype=np.float64)
    np.add.at(out, flat, values)
    return out.reshape(n_rows, n_cols)


def mean_per_cell(values, rows, cols, n_rows, n_cols):
    """Mean per cell excluding NaN; also returns count of non-NaN values."""
    flat = rows * n_cols + cols
    n_rows_n = n_rows * n_cols
    sums = np.zeros(n_rows_n, dtype=np.float64)
    counts = np.zeros(n_rows_n, dtype=np.float64)
    valid = ~np.isnan(values)
    np.add.at(sums, flat[valid], values[valid])
    np.add.at(counts, flat[valid], 1.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        means = sums / counts
    means = np.where(counts > 0, means, np.nan)
    return sums.reshape(n_rows, n_cols), counts.reshape(n_rows, n_cols), means.reshape(n_rows, n_cols)


def main():
    # Read the existing 30 m grid transform from the composites.
    with rasterio.open(os.path.join(config.DIR_COMPOSITES, "lwir11.tif")) as src:
        transform = src.transform
        height = src.height
        width = src.width

    minx = transform.c
    maxy = transform.f
    maxx = transform.c + width * transform.a
    miny = transform.f + height * transform.e  # transform.e is negative

    n_cols = int(np.ceil((maxx - minx) / CELL_SIZE))
    n_rows = int(np.ceil((maxy - miny) / CELL_SIZE))
    total_cells = n_rows * n_cols

    print(f"Source grid: {width}x{height} @30m EPSG:32643")
    print(f"Grid origin (minx, maxy) = ({minx:.2f}, {maxy:.2f})")
    print(f"Grid extent (minx, maxx, miny, maxy) = ({minx:.2f}, {maxx:.2f}, {miny:.2f}, {maxy:.2f})")
    print(f"500 m grid: n_rows={n_rows}, n_cols={n_cols}, total_cells={total_cells}")

    # Rasterize dissolved BMC to the 30 m grid to find cells with >=1 BMC pixel.
    bmc = gpd.read_file(config.BMC_GEOJSON).dissolve().to_crs(config.CRS_METRIC)
    bmc_mask_30m = rio_rasterize(
        [shp_mapping(g) for g in bmc.geometry],
        out_shape=(height, width),
        transform=transform,
        fill=0,
        default_value=1,
        dtype="uint8",
    ).astype(bool)

    # Map each 30 m pixel to a cell; mark cells that contain >=1 BMC pixel.
    xs = minx + (np.arange(width) + 0.5) * transform.a
    ys = maxy + (np.arange(height) + 0.5) * transform.e  # e is negative
    xx, yy = np.meshgrid(xs, ys)
    rows = np.floor((maxy - yy) / CELL_SIZE).astype(int)
    cols = np.floor((xx - minx) / CELL_SIZE).astype(int)
    # Clip to valid cell range (boundary pixels on the max edge).
    rows = np.clip(rows, 0, n_rows - 1)
    cols = np.clip(cols, 0, n_cols - 1)
    cell_has_bmc = np.zeros((n_rows, n_cols), dtype=bool)
    cell_has_bmc[rows[bmc_mask_30m], cols[bmc_mask_30m]] = True
    cells_with_bmc = int(cell_has_bmc.sum())

    print(f"Cells with >=1 BMC pixel: {cells_with_bmc}")

    log_path = os.path.join(config.DIR_LOGS, "round4c_grid.txt")
    lines = [
        f"Grid origin (minx, maxy) = ({minx:.2f}, {maxy:.2f})",
        f"Grid extent (minx, maxx, miny, maxy) = ({minx:.2f}, {maxx:.2f}, {miny:.2f}, {maxy:.2f})",
        f"Cell size = {CELL_SIZE} m",
        f"n_rows = {n_rows}",
        f"n_cols = {n_cols}",
        f"total_cells = {total_cells}",
        f"cells with >=1 BMC pixel = {cells_with_bmc}",
    ]
    write_log(log_path, "\n".join(lines))
    print(log_path)


if __name__ == "__main__":
    main()
