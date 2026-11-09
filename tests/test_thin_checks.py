"""Unit tests for src/thin_checks.py (Phase 6 round).

Plain asserts with hand-computed working in comments. Arrays compared with
.tolist().
"""
import numpy as np

sys_path_inserted = False
try:
    import thin_checks  # noqa: F401
except ImportError:
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))
    import thin_checks  # noqa: F401


def test_neighbour_count_centre():
    # (i) 3x3 mask with only the centre True:
    # centre has 0 True neighbours; each of its 8 neighbours has 1 (the centre).
    mask = np.zeros((3, 3), dtype=bool)
    mask[1, 1] = True
    expected = [[1, 1, 1], [1, 0, 1], [1, 1, 1]]
    assert thin_checks.neighbour_count(mask).tolist() == expected


def test_neighbour_count_corner():
    # (ii) 3x3 mask with only [0,0] True:
    # cell [0,0] has 0 True neighbours; its 3 existing neighbours each have 1.
    mask = np.zeros((3, 3), dtype=bool)
    mask[0, 0] = True
    expected = [[0, 1, 0], [1, 1, 0], [0, 0, 0]]
    assert thin_checks.neighbour_count(mask).tolist() == expected


def test_mean_neighbour_count():
    # (iii) mask = [[T,T,F],[F,F,F],[F,F,F]], member = mask:
    # each True cell has one True neighbour (the other), so mean = 1.0.
    mask = np.array([[True, True, False],
                     [False, False, False],
                     [False, False, False]], dtype=bool)
    assert thin_checks.mean_neighbour_count(mask, mask) == 1.0
    # member only the top-left cell: its neighbour count is 1.
    member = np.array([[True, False, False],
                       [False, False, False],
                       [False, False, False]], dtype=bool)
    assert thin_checks.mean_neighbour_count(mask, member) == 1.0
    # member all False: no True cells -> nan.
    assert np.isnan(thin_checks.mean_neighbour_count(mask, np.zeros((3, 3), dtype=bool)))
