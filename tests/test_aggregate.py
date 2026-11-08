"""Unit tests for src/aggregate.py pure functions.

All expectations are hand-computed (not recomputed by the function under test).

Boundary rule (stated here): a centre exactly on a cell edge is assigned to
the cell on the right (vertical edge) or below (horizontal edge), because col
and row use floor(...) and row 0 is at the top (maxy). With cellsize 1,
minx 0, maxy 10: cell (row 0, col 0) spans x in [0, 1) and y in (9, 10]; a
centre at x = 1.0 goes to col 1 (right) and a centre at y = 9.0 goes to row
1 (below).
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

import numpy as np
import pytest

from aggregate import assign_cells, sum_per_cell, mean_per_cell


def test_assign_cell_boundary_goes_right_and_below():
    # Boundary rule: right and below (see module docstring).
    row, col, in_range = assign_cells(
        np.array([1.0, 0.3, 2.0, -0.1, 1.0]),
        np.array([9.0, 9.7, 9.7, 9.7, 10.1]),
        0.0, 10.0, 1.0, 2, 2,
    )
    assert in_range.tolist() == [True, True, False, False, False]
    assert (int(row[0]), int(col[0])) == (1, 1)   # x=1.0 right, y=9.0 below
    assert (int(row[1]), int(col[1])) == (0, 0)   # interior point


def test_sum_per_cell_hand_total():
    # (i) SUM of 4 values in one cell and 2 in another equals the hand total.
    flat_id = np.array([0, 0, 0, 0, 3, 3], dtype=np.int64)
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    sums, counts = sum_per_cell(values, flat_id, n_cells=5)
    assert sums.tolist() == [10.0, 0.0, 0.0, 11.0, 0.0]
    assert counts.tolist() == [4.0, 0.0, 0.0, 2.0, 0.0]
    assert sums.sum() == 21.0


def test_sum_per_cell_excludes_nan():
    flat_id = np.array([0, 0, 0], dtype=np.int64)
    values = np.array([1.0, np.nan, 3.0])
    sums, counts = sum_per_cell(values, flat_id, n_cells=1)
    assert sums[0] == 4.0
    assert counts[0] == 2.0


def test_mean_per_cell_excludes_nan_but_counts_it():
    # (iii) Cell: 1, 2, nan, 4 -> mean (1+2+4)/3 = 7/3, n = 3; NaN excluded.
    flat_id = np.array([0, 0, 0, 0], dtype=np.int64)
    values = np.array([1.0, 2.0, np.nan, 4.0])
    mean, n = mean_per_cell(values, flat_id, n_cells=1)
    assert mean[0] == pytest.approx(7.0 / 3.0)
    assert n[0] == 3


def test_mean_per_cell_all_nan_empty_cell():
    flat_id = np.array([0, 0], dtype=np.int64)
    values = np.array([np.nan, np.nan])
    mean, n = mean_per_cell(values, flat_id, n_cells=1)
    assert np.isnan(mean[0])
    assert n[0] == 0


def test_total_conserved():
    # (iv) Total of cell sums equals total of input values.
    rng = np.random.default_rng(0)
    n_rows, n_cols = 5, 7
    n_points = 200
    rows = rng.integers(0, n_rows, size=n_points)
    cols = rng.integers(0, n_cols, size=n_points)
    values = rng.uniform(0, 100, size=n_points)
    flat_id = rows * n_cols + cols
    sums, counts = sum_per_cell(values, flat_id, n_rows * n_cols)
    assert sums.sum() == pytest.approx(values.sum())
    assert counts.sum() == n_points


def test_out_of_range_point_not_added_to_any_cell():
    # (v) Point outside the grid: in_range False, not added to any cell.
    row, col, in_range = assign_cells(
        np.array([5.0, 0.3]), np.array([9.7, 9.7]), 0.0, 10.0, 1.0, 2, 2,
    )
    assert in_range.tolist() == [False, True]
    flat_id = np.array([1], dtype=np.int64)       # only the in-range point
    values = np.array([9.0])
    sums, counts = sum_per_cell(values, flat_id, n_cells=4)
    assert sums.tolist() == [0.0, 9.0, 0.0, 0.0]
    assert counts.tolist() == [0.0, 1.0, 0.0, 0.0]


def test_sum_per_cell_rejects_id_equal_to_n_cells():
    # (viii) an id equal to n_cells raises ValueError.
    flat_id = np.array([4], dtype=np.int64)       # n_cells == 4, valid ids 0..3
    values = np.array([9.0])
    with pytest.raises(ValueError):
        sum_per_cell(values, flat_id, n_cells=4)


def test_sum_per_cell_rejects_negative_id():
    # (ix) an id of -1 raises ValueError.
    flat_id = np.array([-1], dtype=np.int64)
    values = np.array([9.0])
    with pytest.raises(ValueError):
        sum_per_cell(values, flat_id, n_cells=4)
