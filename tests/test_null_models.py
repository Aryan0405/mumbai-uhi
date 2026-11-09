"""Unit tests for src/null_models.py (Phase 3B round 2).

Functions are called directly; no tautologies. Working shown in comments.
"""
import os
import sys

try:  # allow import both from repo root and from tests/
    import null_models  # noqa: F401
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))
    import null_models  # noqa: F401

import numpy as np
from scipy.special import ndtri

import stats_utils

from null_models import copula_null, gaussian_null


def test_same_seed_identical_output():
    # (i) same seed gives identical output.
    X = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
    rng_a = np.random.default_rng(42)
    rng_b = np.random.default_rng(42)
    out_a = gaussian_null(X, 100, rng_a)
    out_b = gaussian_null(X, 100, rng_b)
    assert np.array_equal(out_a, out_b)
    rng_c = np.random.default_rng(42)
    rng_d = np.random.default_rng(42)
    out_c = copula_null(X, 100, rng_c)
    out_d = copula_null(X, 100, rng_d)
    assert np.array_equal(out_c, out_d)


def test_output_shape():
    # (ii) output shape is (n_rows, n_cols).
    X = np.random.default_rng(0).standard_normal(size=(50, 4))
    g = gaussian_null(X, 7, np.random.default_rng(1))
    assert g.shape == (7, 4)
    c = copula_null(X, 7, np.random.default_rng(1))
    assert c.shape == (7, 4)


def test_gaussian_null_covariance_matches():
    # (iii) n_rows = 50000: sample covariance of gaussian_null matches the
    # input covariance (ddof=1) within 0.03 per element.
    rng_x = np.random.default_rng(123)
    Z = rng_x.standard_normal(size=(1000, 3))
    Z[:, 1] = Z[:, 0] * 0.5 + rng_x.standard_normal(1000) * 0.5  # correlate col 1
    input_cov = np.cov(Z, rowvar=False, ddof=1)
    null_draws = gaussian_null(Z, 50000, np.random.default_rng(7))
    sample_cov = np.cov(null_draws, rowvar=False, ddof=1)
    diff = np.abs(sample_cov - input_cov)
    assert np.all(diff <= 0.03), diff


def test_copula_null_marginals_and_correlation():
    # (iv) copula_null with n_rows = 50000.
    # Working for the target correlation: convert each column of X to normal
    # scores via average ranks: u = rank/(n+1), score = ndtri(u); the target
    # Pearson matrix is np.corrcoef of those scores (computed in this test from
    # the same helper used by copula_null).
    rng_x = np.random.default_rng(5)
    X = np.empty((1000, 3))
    X[:, 0] = rng_x.exponential(1.0, 1000) + 5.0   # median far from zero
    X[:, 1] = X[:, 0] * 2.0 + rng_x.standard_normal(1000) * 0.5
    X[:, 2] = rng_x.uniform(1.0, 3.0, 1000)        # median far from zero

    n = X.shape[0]
    scores = np.empty((n, 3), dtype=np.float64)
    for j in range(3):
        ranks = stats_utils.rank_average(X[:, j])
        scores[:, j] = ndtri(ranks / (n + 1.0))
    target_corr = np.corrcoef(scores, rowvar=False)

    null_draws = copula_null(X, 50000, np.random.default_rng(11))

    # every column's min and max stay inside the real column's min and max
    for j in range(3):
        assert null_draws[:, j].min() >= X[:, j].min()
        assert null_draws[:, j].max() <= X[:, j].max()
        # sample medians within 2 percent of real medians
        real_med = float(np.median(X[:, j]))
        null_med = float(np.median(null_draws[:, j]))
        if real_med != 0.0:
            assert abs(null_med - real_med) <= 0.02 * abs(real_med)

    # sample Pearson matrix within 0.03 of target
    sample_corr = np.corrcoef(null_draws, rowvar=False)
    assert np.all(np.abs(sample_corr - target_corr) <= 0.03), sample_corr - target_corr
