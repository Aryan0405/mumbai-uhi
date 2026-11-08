"""Pure numpy rank and correlation utilities (Phase 3A round R2).

No rasterio, geopandas, scipy, or pandas dependency. Safe to unit test.
"""
import numpy as np


def rank_average(v):
    """Average ranks for ties, 1-based.

    Args:
        v: 1-D array-like of numeric values.

    Returns:
        1-D float64 numpy array of ranks with the same length as v. Tied
        values receive the average of the ranks they would span.
    """
    v = np.asarray(v, dtype=np.float64).ravel()
    n = v.size
    order = np.argsort(v, kind="mergesort")
    sorted_v = v[order]
    is_start = np.concatenate(([True], sorted_v[1:] != sorted_v[:-1]))
    run_id = np.cumsum(is_start) - 1
    run_sum = np.bincount(run_id, weights=np.arange(1, n + 1, dtype=np.float64))
    run_count = np.bincount(run_id)
    ranks_sorted = run_sum / run_count
    ranks = np.empty(n, dtype=np.float64)
    ranks[order] = ranks_sorted[run_id]
    return ranks


def spearman_rho(a, b):
    """Spearman rank correlation with NaN-pair dropping.

    Args:
        a, b: 1-D array-like of numeric values, same length.

    Returns:
        (rho, n_pairs): rho is the Spearman correlation on the complete
        pairs (where neither value is NaN), or NaN when n_pairs < 2 or when
        either side is constant after dropping NaNs. n_pairs is the number
        of complete pairs.
    """
    a = np.asarray(a, dtype=np.float64).ravel()
    b = np.asarray(b, dtype=np.float64).ravel()
    valid = (~np.isnan(a)) & (~np.isnan(b))
    a = a[valid]
    b = b[valid]
    n_pairs = int(a.size)
    if n_pairs < 2:
        return (np.nan, n_pairs)
    ra = rank_average(a)
    rb = rank_average(b)
    if np.all(ra == ra[0]) or np.all(rb == rb[0]):
        return (np.nan, n_pairs)
    ca = ra - ra.mean()
    cb = rb - rb.mean()
    denom = np.sqrt(np.sum(ca * ca) * np.sum(cb * cb))
    if denom == 0.0:
        return (np.nan, n_pairs)
    return (float(np.sum(ca * cb) / denom), n_pairs)
