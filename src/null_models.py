"""Null-model generators for K-Means silhouette testing (Phase 3B round 2).

Pure functions with docstrings. Spatial autocorrelation is NOT modelled; this
is stated wherever the results are reported.
"""
import numpy as np
from scipy.special import ndtri, ndtr

import stats_utils


def gaussian_null(Z, n_rows, rng):
    """Multivariate normal draws with the sample mean and covariance of Z.

    Args:
        Z: 2-D float64 array (n, p), already standardised.
        n_rows: number of draws.
        rng: numpy random generator.

    Returns:
        2-D float64 array (n_rows, p) with mean ~ mean(Z, ddof=1) and
        covariance ~ cov(Z, ddof=1).
    """
    Z = np.asarray(Z, dtype=np.float64)
    mean = np.mean(Z, axis=0)
    cov = np.cov(Z, rowvar=False, ddof=1)
    p = Z.shape[1]
    draws = rng.multivariate_normal(mean, cov, size=n_rows)
    return draws


def copula_null(X, n_rows, rng):
    """Gaussian copula draws with the exact empirical marginals of X.

    Each column of X is converted to normal scores via average ranks
    (stats_utils.rank_average) mapped through the normal quantile function
    (scipy.special.ndtri on rank/(n+1)). The correlation matrix of the scores
    is estimated with numpy; n_rows multivariate normal scores are drawn with
    that correlation; each column is mapped back through the empirical quantile
    function of the real column (numpy.quantile with linear interpolation on
    the sorted real values at the normal CDF of the scores, via
    scipy.special.ndtr). The output has the same marginal distributions as X
    by construction.

    Args:
        X: 2-D float64 array (n, p) of real raw features.
        n_rows: number of draws.
        rng: numpy random generator.

    Returns:
        2-D float64 array (n_rows, p).
    """
    X = np.asarray(X, dtype=np.float64)
    n, p = X.shape

    # Normal scores via average ranks.
    scores = np.empty((n, p), dtype=np.float64)
    for j in range(p):
        ranks = stats_utils.rank_average(X[:, j])
        u = ranks / (n + 1.0)
        scores[:, j] = ndtri(u)

    # Correlation matrix of the scores (numpy).
    score_corr = np.corrcoef(scores, rowvar=False)
    # Small jitter keeps the Cholesky factor numerically positive definite
    # when the score correlation is (near-)singular (e.g. perfectly collinear
    # toy data); the jitter is negligible for real data.
    score_corr = score_corr + 1e-10 * np.eye(p)

    # Draw multivariate normal scores with that correlation.
    mean = np.zeros(p)
    # Cholesky for stable drawing.
    L = np.linalg.cholesky(score_corr)
    standard = rng.standard_normal(size=(n_rows, p))
    draws_scores = mean[None, :] + standard @ L.T

    # Map back through empirical quantiles of each real column.
    sorted_X = np.sort(X, axis=0)
    probs = ndtr(draws_scores)
    out = np.empty((n_rows, p), dtype=np.float64)
    for j in range(p):
        out[:, j] = np.quantile(sorted_X[:, j], probs[:, j], method="linear")
    return out
