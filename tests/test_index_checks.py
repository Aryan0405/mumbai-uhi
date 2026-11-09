"""Unit tests for src/index_checks.py (Phase 5 round).

Plain asserts with hand-computed working in comments.
"""
import numpy as np

sys_path_inserted = False
try:
    import index_checks  # noqa: F401
except ImportError:
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))
    import index_checks  # noqa: F401


def test_scheme_weights():
    # (i) scheme_weights(0.2) == (0.4, 0.4, 0.2)
    assert index_checks.scheme_weights(0.2) == (0.4, 0.4, 0.2)
    # scheme_weights(0.0) == (0.5, 0.5, 0.0)
    assert index_checks.scheme_weights(0.0) == (0.5, 0.5, 0.0)
    # scheme_weights(1/3) equals (1/3, 1/3, 1/3) at atol 1e-12
    w = index_checks.scheme_weights(1 / 3)
    assert all(abs(w[i] - (1 / 3)) <= 1e-12 for i in range(3))


def test_stability_count():
    # (ii) stability_count([[T,T,F],[T,F,F],[T,T,F]]) == [3,2,0]
    flags = [[True, True, False],
             [True, False, False],
             [True, True, False]]
    assert list(index_checks.stability_count(flags)) == [3, 2, 0]


def test_grid_from_cells():
    # (iii) grid_from_cells([0,1],[1,0],[5.0,7.0],(2,2),-1.0) == [[-1,5],[7,-1]]
    grid = index_checks.grid_from_cells([0, 1], [1, 0], [5.0, 7.0], (2, 2), -1.0)
    assert grid.tolist() == [[-1.0, 5.0], [7.0, -1.0]]


def test_neighbour_flag():
    # (iv) 3x3 mask with only the centre True gives all True except the centre.
    mask = np.zeros((3, 3), dtype=bool)
    mask[1, 1] = True
    expected = np.ones((3, 3), dtype=bool)
    expected[1, 1] = False
    assert index_checks.neighbour_flag(mask).tolist() == expected.tolist()

    # (iv) 3x3 mask with only [0,0] True gives True at (0,1),(1,0),(1,1) only.
    mask2 = np.zeros((3, 3), dtype=bool)
    mask2[0, 0] = True
    expected2 = np.zeros((3, 3), dtype=bool)
    expected2[0, 1] = True
    expected2[1, 0] = True
    expected2[1, 1] = True
    assert index_checks.neighbour_flag(mask2).tolist() == expected2.tolist()
