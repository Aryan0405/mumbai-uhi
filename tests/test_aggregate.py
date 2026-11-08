"""Unit tests for src/aggregate.py pure functions.

Tests use hand-computed tiny arrays (not recomputed by the function under test).
"""
import numpy as np
import pytest

from aggregate import assign_cell, sum_per_cell, mean_per_cell


def test_assign_cell_boundary_goes_right_and_below():
    # Cell size 1, origin minx=0, maxy=10.
    # Cell (row=0, col=0) covers x in [0,1), y in (9,10].
    # A centre exactly on x=1.0 (right edge of col 0) -> col 1 (right).
    # A centre exactly on y=9.0 (bottom edge of row 0) -> row 1 (below).
    r, c = assign_cell(1.0, 9.0, 0.0, 10.0, 1.0)
    assert c == 1
    assert r == 1


def test_assign_cell_interior():
    r, c = assign_cell(0.3, 9.7, 0.0, 10.0, 1.0)
    assert c == 0
    assert r == 0


def test_sum_per_cell():
    # Cell (0,0): values [1,2,3,4] -> sum 10. Cell (0,1): values [5,6] -> sum 11.
    rows = np.array([0, 0, 0, 0, 0, 0], dtype=int)
    cols = np.array([0, 0, 0, 0, 1, 1], dtype=int)
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    sums = sum_per_cell(values, rows, cols, n_rows=1, n_cols=2)
    assert sums.shape == (1, 2)
    assert sums[0, 0] == 10.0
    assert sums[0, 1] == 11.0


def test_mean_per_cell_excludes_nan():
    # Cell (0,0): values [1,2,nan,4] -> mean (1+2+4)/3 = 7/3, count 3.
    rows = np.array([0, 0, 0, 0], dtype=int)
    cols = np.array([0, 0, 0, 0], dtype=int)
    values = np.array([1.0, 2.0, np.nan, 4.0])
    sums, counts, means = mean_per_cell(values, rows, cols, n_rows=1, n_cols=1)
    assert means[0, 0] == pytest.approx(7.0 / 3.0)
    assert counts[0, 0] == 3


def test_total_conserved():
    # Total of cell sums equals total of input values.
    rng = np.random.default_rng(0)
    n_rows, n_cols = 5, 7
    n_points = 200
    rows = rng.integers(0, n_rows, size=n_points)
    cols = rng.integers(0, n_cols, size=n_points)
    values = rng.uniform(0, 100, size=n_points)
    sums = sum_per_cell(values, rows, cols, n_rows, n_cols)
    assert sums.sum() == pytest.approx(values.sum())


def test_mean_per_cell_all_nan():
    # All-NaN cell -> mean NaN, count 0.
    rows = np.array([0, 0], dtype=int)
    cols = np.array([0, 0], dtype=int)
    values = np.array([np.nan, np.nan])
    sums, counts, means = mean_per_cell(values, rows, cols, n_rows=1, n_cols=1)
    assert np.isnan(means[0, 0])
    assert counts[0, 0] == 0
