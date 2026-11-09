"""Unit tests for src/index_candidates.py.

Hand-computed tiny arrays with the working shown in comments.
"""
import numpy as np

sys_path_inserted = False
try:
    import index_candidates  # noqa: F401
except ImportError:
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))
    import index_candidates  # noqa: F401

from index_candidates import standardise, exposure, components, index, \
    component_sets, candidate_scores, top_set, jaccard


def approx_equal(a, b, tol=1e-12):
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    return bool(np.allclose(a, b, atol=tol))


def test_standardise_ddof0():
    # (i) standardise of [1, 2, 3]: mean = 2, std (ddof=0) = sqrt(2/3) = 0.8164966,
    # so values are [(1-2)/0.8164966, 0, (3-2)/0.8164966]
    #   = [-1.2247449, 0, 1.2247449].
    v = np.array([1.0, 2.0, 3.0])
    expected = np.array([-1.224744871, 0.0, 1.224744871])
    result = standardise(v)
    assert approx_equal(result, expected, tol=1e-8)


def test_standardise_constant():
    # Constant input: std = 0, result is all zeros (no division by zero).
    v = np.array([5.0, 5.0, 5.0])
    result = standardise(v)
    assert approx_equal(result, np.zeros(3))


def test_exposure_pct_ties():
    # (ii) exposure "pct" of [0, 0, 5, 10]: average ranks are 1.5, 1.5, 3, 4;
    # percentile = rank / n = [0.375, 0.375, 0.75, 1.0].
    v = np.array([0.0, 0.0, 5.0, 10.0])
    result = exposure(v, "pct")
    assert approx_equal(result, np.array([0.375, 0.375, 0.75, 1.0]))


def test_exposure_sqrt():
    # (iii) exposure "sqrt" of [0, 4, 9] equals [0, 2, 3].
    v = np.array([0.0, 4.0, 9.0])
    result = exposure(v, "sqrt")
    assert approx_equal(result, np.array([0.0, 2.0, 3.0]))


def test_exposure_raw_unchanged():
    v = np.array([0.0, 4.0, 9.0])
    result = exposure(v, "raw")
    assert approx_equal(result, v)


def test_index_hand_sum():
    # (iv) index with weights (0.5, 0.25, 0.25) on H=[1,2,3],
    # S=[3,2,1], E=[2,2,2] equals the hand sum:
    #   [0.5*1+0.25*3+0.25*2, 0.5*2+0.25*2+0.25*2,
    #    0.5*3+0.25*1+0.25*2] = [1.75, 2.0, 2.25].
    H = np.array([1.0, 2.0, 3.0])
    S = np.array([3.0, 2.0, 1.0])
    E = np.array([2.0, 2.0, 2.0])
    result = index(H, S, E, 0.5, 0.25, 0.25)
    assert approx_equal(result, np.array([1.75, 2.0, 2.25]))


def test_index_sign_S():
    # (v) S sign: a cell with high NDBI and low NDVI gets a higher S than
    # the reverse case (same LST, so H identical and irrelevant).
    lst = np.array([10.0, 20.0])
    ndvi_a = np.array([10.0, 20.0])   # low then high NDVI
    ndbi_a = np.array([20.0, 10.0])   # high then low NDBI
    ndvi_b = np.array([20.0, 10.0])   # high then low NDVI
    ndbi_b = np.array([10.0, 20.0])   # low then high NDBI
    H = standardise(lst)
    S_a = components(lst, ndvi_a, ndbi_a, np.ones(2), "raw")[1]
    S_b = components(lst, ndvi_b, ndbi_b, np.ones(2), "raw")[1]
    assert S_a[0] > S_a[1]
    assert S_b[0] < S_b[1]


def test_candidate_scores_w4_noexp():
    # W4_noexp has kind None, so exposure is skipped and the score is
    # 0.5*H + 0.5*S. With lst=[1,2,3], ndvi=[3,2,1], ndbi=[1,2,3]:
    #   H = standardise([1,2,3]) = [-1.224744871, 0, 1.224744871]
    #   z_ndvi = standardise([3,2,1]) = [1.2247, 0, -1.2247]
    #   z_ndbi = standardise([1,2,3]) = [-1.2247, 0, 1.2247]
    #   -z_ndvi + z_ndbi = [-2.4495, 0, 2.4495]
    #   S = standardise([-2.4495, 0, 2.4495]) = [-1.224744871, 0, 1.224744871]
    #   0.5*H + 0.5*S = [-1.224744871, 0, 1.224744871]
    lst = np.array([1.0, 2.0, 3.0])
    ndvi = np.array([3.0, 2.0, 1.0])
    ndbi = np.array([1.0, 2.0, 3.0])
    density = np.array([0.0, 5.0, 10.0])
    scores = candidate_scores(lst, ndvi, ndbi, density)
    expected = np.array([-1.224744871, 0.0, 1.224744871])
    assert approx_equal(scores["W4_noexp"], expected, tol=1e-8)


def test_candidate_scores_key_order():
    lst = np.array([1.0, 2.0, 3.0])
    ndvi = np.array([3.0, 2.0, 1.0])
    ndbi = np.array([1.0, 2.0, 3.0])
    density = np.array([0.0, 5.0, 10.0])
    scores = candidate_scores(lst, ndvi, ndbi, density)
    assert list(scores.keys()) == [
        "W1_raw", "W1_sqrt", "W1_pct",
        "W2_raw", "W2_sqrt", "W2_pct",
        "W3_raw", "W3_sqrt", "W3_pct",
        "W4_noexp",
    ]


def test_top_set():
    scores = [1, 3, 2, 3]
    assert top_set(scores, 2) == {1, 3}
    assert top_set(scores, 1) == {1}
    assert top_set(scores, 3) == {1, 3, 2}


def test_jaccard():
    assert approx_equal(jaccard({1, 3}, {1, 2}), 1.0 / 3.0, tol=1e-12)
    assert approx_equal(jaccard({1, 3}, {1, 3}), 1.0)
