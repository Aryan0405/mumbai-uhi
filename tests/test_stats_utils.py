"""Unit tests for src/stats_utils.py (pure numpy rank / correlation).

All expected values are hand-computed (not recomputed by the function under
test) and the working is shown in comments.
"""
import math

import numpy as np
import pytest

sys_path_inserted = False
try:
    import stats_utils  # noqa: F401  (pytest run from repo root with src on path)
except ImportError:
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))
    import stats_utils  # noqa: F401

from stats_utils import rank_average, spearman_rho


def test_perfectly_increasing_gives_one():
    # (i) a and b perfectly increasing -> rho = 1.0
    a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    b = np.array([2.0, 4.0, 6.0, 8.0, 10.0])
    rho, n = spearman_rho(a, b)
    assert n == 5
    assert rho == pytest.approx(1.0)


def test_perfectly_decreasing_gives_minus_one():
    # (ii) a increasing, b perfectly decreasing -> rho = -1.0
    a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    b = np.array([5.0, 4.0, 3.0, 2.0, 1.0])
    rho, n = spearman_rho(a, b)
    assert n == 5
    assert rho == pytest.approx(-1.0)


def test_tie_in_one_array():
    # (iii) tie in one array.
    # a = [1, 2, 3, 4] -> ranks [1, 2, 3, 4], mean 2.5
    # b = [1, 2, 2, 4] -> ranks [1, 2.5, 2.5, 4], mean 2.5
    # numerator = sum((a-2.5)(b-2.5)) = 2.25 + 0 + 0 + 2.25 = 4.5
    # sum((a-2.5)^2) = 5.0; sum((b-2.5)^2) = 4.5
    # rho = 4.5 / sqrt(5.0 * 4.5) = 4.5 / sqrt(22.5) = 0.9486832980505138
    a = np.array([1.0, 2.0, 3.0, 4.0])
    b = np.array([1.0, 2.0, 2.0, 4.0])
    rho, n = spearman_rho(a, b)
    assert n == 4
    assert rho == pytest.approx(4.5 / math.sqrt(22.5))


def test_nan_pairs_dropped_and_n_pairs_reported():
    # (iv) NaN pairs dropped; n_pairs counts only complete pairs.
    # index 0: (1, 1) valid; index 1: (2, nan) dropped; index 2: (nan, 3)
    # dropped; index 3: (4, 4) valid. Two valid pairs, perfectly increasing.
    a = np.array([1.0, 2.0, np.nan, 4.0])
    b = np.array([1.0, np.nan, 3.0, 4.0])
    rho, n = spearman_rho(a, b)
    assert n == 2
    assert rho == pytest.approx(1.0)


def test_constant_input_gives_nan():
    # (v) constant input -> NaN (either side constant after dropping).
    a = np.array([1.0, 1.0, 1.0, 1.0])
    b = np.array([1.0, 2.0, 3.0, 4.0])
    rho, n = spearman_rho(a, b)
    assert n == 4
    assert np.isnan(rho)


def test_length_one_gives_nan():
    # (vi) length 1 -> n_pairs < 2 -> NaN.
    rho, n = spearman_rho(np.array([5.0]), np.array([7.0]))
    assert n == 1
    assert np.isnan(rho)


def test_rank_average_ties():
    # (vii) rank_average of [10, 20, 20, 30] equals [1, 2.5, 2.5, 4].
    v = np.array([10.0, 20.0, 20.0, 30.0])
    ranks = rank_average(v)
    assert ranks.tolist() == pytest.approx([1.0, 2.5, 2.5, 4.0])


def test_rank_average_no_ties():
    ranks = rank_average(np.array([30.0, 10.0, 20.0]))
    assert ranks.tolist() == pytest.approx([3.0, 1.0, 2.0])


def test_all_nan_gives_nan_pairs_zero():
    rho, n = spearman_rho(np.array([np.nan, np.nan]), np.array([1.0, 2.0]))
    assert n == 0
    assert np.isnan(rho)
