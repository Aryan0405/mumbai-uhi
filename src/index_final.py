"""Pure index utility functions (Phase 4 round).

Ranking and zone membership helpers used by the index build script.
"""
import numpy as np


def rank_desc(scores):
    """Rank scores descending, rank 1 = highest.

    Ties broken by lower index first (stable argsort of -scores).
    Returns a 1-D int array of ranks 1..n aligned with the input order.
    """
    scores = np.asarray(scores, dtype=np.float64)
    order = np.argsort(-scores, kind="stable")
    ranks = np.empty(scores.size, dtype=int)
    ranks[order] = np.arange(1, scores.size + 1)
    return ranks


def zone_flag(scores, n):
    """Boolean array: True for the indices in index_candidates.top_set(scores, n)."""
    from index_candidates import top_set
    scores = np.asarray(scores, dtype=np.float64)
    members = top_set(scores, n)
    return np.array([i in members for i in range(scores.size)], dtype=bool)


def changed_membership(flag_a, flag_b):
    """Boolean array: True where exactly one of the two flags is True."""
    flag_a = np.asarray(flag_a, dtype=bool)
    flag_b = np.asarray(flag_b, dtype=bool)
    return (flag_a != flag_b)
