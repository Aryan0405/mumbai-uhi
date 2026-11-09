"""Unit tests for src/silhouette_numpy.py.

Working shown in comments; expected values computed by hand.
"""
import math

import numpy as np

sys_path_inserted = False
try:
    import silhouette_numpy  # noqa: F401
except ImportError:
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))
    import silhouette_numpy  # noqa: F401

from silhouette_numpy import silhouette_score


def approx_equal(a, b, tol=1e-12):
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    return bool(np.allclose(a, b, atol=tol))


def test_two_clusters_two_points_one_dimension():
    # Points in 1D: [0.0, 0.1] in cluster 0, [10.0, 10.1] in cluster 1.
    X = np.array([[0.0], [0.1], [10.0], [10.1]])
    labels = np.array([0, 0, 1, 1])
    # Hand-computed working:
    # s(0.0): a=0.1, b=mean(10.0,10.1)=10.05 -> s=9.95/10.05=0.9900497512437811
    # s(0.1): a=0.1, b=mean(9.9,10.0)=9.95 -> s=9.85/9.95=0.9899497487437186
    # s(10.0): a=0.1, b=mean(10.0,9.9)=9.95 -> s=9.85/9.95=0.9899497487437186
    # s(10.1): a=0.1, b=mean(10.1,10.0)=10.05 -> s=9.95/10.05=0.9900497512437811
    # mean = (9.95/10.05 + 9.85/9.95) / 2 = 0.9899997499937498
    expected = (9.95 / 10.05 + 9.85 / 9.95) / 2.0
    result = silhouette_score(X, labels)
    assert approx_equal(result, expected)


def test_singleton_cluster_silhouette_is_zero():
    # Cluster 0 has a single point; its silhouette is 0 by definition.
    # Cluster 1 has points 1.0 and 2.0:
    #   x=1.0: a=1.0, b=|1.0-0.0|=1.0 → s=0.
    #   x=2.0: a=1.0, b=|2.0-0.0|=2.0 → s=(2.0-1.0)/2.0=0.5.
    # Mean = (0 + 0 + 0.5) / 3 = 0.16666666666666666.
    X = np.array([[0.0], [1.0], [2.0]])
    labels = np.array([0, 1, 1])
    expected = (0.0 + 0.0 + 0.5) / 3.0
    result = silhouette_score(X, labels)
    assert approx_equal(result, expected)


def test_all_one_cluster():
    # All points in one cluster: b is undefined; define silhouette as 0 for
    # every point (no other cluster to compare against).
    X = np.array([[0.0], [1.0], [2.0]])
    labels = np.array([0, 0, 0])
    assert silhouette_score(X, labels) == 0.0
