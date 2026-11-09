"""Unit tests for src/index_final.py (Phase 4 round).

Plain asserts with hand-computed working in comments.
"""
import numpy as np

sys_path_inserted = False
try:
    import index_final  # noqa: F401
except ImportError:
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))
    import index_final  # noqa: F401


def test_rank_desc():
    # (i) rank_desc([10,30,20]) == [3,1,2]: 30 highest gets rank 1 at index 1.
    assert list(index_final.rank_desc([10, 30, 20])) == [3, 1, 2]
    # Tie broken by lower index first: [5,5,1] -> [1,2,3], not [2,1,3].
    assert list(index_final.rank_desc([5, 5, 1])) == [1, 2, 3]


def test_zone_flag():
    # (ii) top 2 of [1,3,2,3]: indices 1 and 3 are the two largest (tie at 3
    # broken by lower index, so index 1 before index 3).
    assert list(index_final.zone_flag([1, 3, 2, 3], 2)) == [False, True, False, True]


def test_changed_membership():
    # (iii) XOR of [T,T,F,F] and [T,F,T,F] = [F,T,T,F].
    a = [True, True, False, False]
    b = [True, False, True, False]
    assert list(index_final.changed_membership(a, b)) == [False, True, True, False]
