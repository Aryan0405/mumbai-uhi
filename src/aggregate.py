"""Vectorised aggregation helpers for the 500 m grid (Phase 3A round R1).

Pure functions: no I/O, no side effects.

assign_cells(x, y, minx, maxy, cellsize, n_rows, n_cols) -> (row, col, in_range)
    col = floor((x - minx) / cellsize)
    row = floor((maxy - y) / cellsize)        row 0 is at the top (maxy)
    Points outside the grid are flagged in_range False and are never moved
    into an edge cell: there is no clipping.

sum_per_cell(values, flat_cell_id, n_cells) -> (sums, counts)
    np.bincount with weights over flat cell ids in [0, n_cells).
    NaN values are excluded from the sums; counts is the number of
    non-NaN values per cell.

mean_per_cell(values, flat_cell_id, n_cells) -> (mean, n)
    NaN excluded from the mean; empty cell gives mean NaN and n = 0.
"""
import numpy as np


def assign_cells(x, y, minx, maxy, cellsize, n_rows, n_cols):
    """Cell (row, col) containing point centres (x, y), with an in-range flag.

    col = floor((x - minx) / cellsize)
    row = floor((maxy - y) / cellsize)        row 0 is at the top (maxy).
    No np.clip: points outside the grid keep their out-of-range row/col and
    are flagged in_range False, never moved into an edge cell.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    col = np.floor((x - minx) / cellsize).astype(np.int64)
    row = np.floor((maxy - y) / cellsize).astype(np.int64)
    in_range = (row >= 0) & (row < n_rows) & (col >= 0) & (col < n_cols)
    return row, col, in_range


def sum_per_cell(values, flat_cell_id, n_cells):
    """Sum values per flat cell id via np.bincount with weights.

    NaN values are excluded from the sums. Returns (sums, counts) where
    counts is the number of non-NaN values per cell. Raises ValueError if any
    flat cell id is below 0 or at/above n_cells: ids must come only from
    in_range points (see assign_cells).
    """
    values = np.asarray(values, dtype=np.float64)
    flat_cell_id = np.asarray(flat_cell_id, dtype=np.int64)
    n_cells = int(n_cells)
    if flat_cell_id.size:
        if int(flat_cell_id.min()) < 0 or int(flat_cell_id.max()) >= n_cells:
            raise ValueError(
                f"flat_cell_id out of range [0, {n_cells}): "
                f"min={int(flat_cell_id.min())}, max={int(flat_cell_id.max())}"
            )
    valid = ~np.isnan(values)
    sums = np.bincount(flat_cell_id[valid],
                       weights=values[valid],
                       minlength=n_cells).astype(np.float64)
    counts = np.bincount(flat_cell_id[valid],
                         minlength=n_cells).astype(np.float64)
    return sums, counts


def mean_per_cell(values, flat_cell_id, n_cells):
    """Mean per flat cell id excluding NaN; empty cell gives NaN mean, n = 0.

    Returns (mean, n) with n the number of non-NaN values per cell.
    """
    sums, counts = sum_per_cell(values, flat_cell_id, n_cells)
    with np.errstate(divide="ignore", invalid="ignore"):
        mean = sums / np.maximum(counts, 1.0)
    mean = np.where(counts > 0.0, mean, np.nan)
    return mean, counts
