"""Pure numpy silhouette score (Phase 3B round 1).

Pairwise distances, no sklearn. silhouette_score(X, labels) returns the mean
silhouette over all samples. Samples in a singleton cluster get silhouette 0.
"""
import numpy as np


def silhouette_score(X, labels):
    """Mean silhouette width for samples X with cluster labels.

    Args:
        X: 2-D float64 array (n_samples, n_features).
        labels: 1-D int array (n_samples,).

    Returns:
        float: mean silhouette width.
    """
    X = np.asarray(X, dtype=np.float64)
    labels = np.asarray(labels).ravel()
    n = X.shape[0]
    if n == 0:
        return 0.0
    # Squared pairwise distances via (a-b)^2 = a^2 + b^2 - 2ab.
    sq = np.sum(X * X, axis=1)
    dist_sq = sq[:, None] + sq[None, :] - 2.0 * (X @ X.T)
    np.maximum(dist_sq, 0.0, out=dist_sq)
    dist = np.sqrt(dist_sq)
    np.fill_diagonal(dist, 0.0)
    silhouettes = np.zeros(n, dtype=np.float64)
    unique_labels = np.unique(labels)
    if unique_labels.size == 1:
        # No other cluster to compare against; silhouette is 0 by definition.
        return 0.0
    for lab in unique_labels:
        members = np.where(labels == lab)[0]
        if members.size == 1:
            silhouettes[members[0]] = 0.0
            continue
        same = dist[np.ix_(members, members)]
        a = same.sum(axis=1) / (members.size - 1)
        other_means = []
        for other in unique_labels:
            if other == lab:
                continue
            other_members = np.where(labels == other)[0]
            d = dist[np.ix_(members, other_members)]
            other_means.append(d.mean(axis=1))
        b = np.min(np.stack(other_means, axis=1), axis=1)
        denom = np.maximum(a, b)
        silhouettes[members] = (b - a) / denom
    return float(np.mean(silhouettes))


def silhouette_samples(X, labels):
    """Per-sample silhouette widths.

    Returns a 1-D float64 array of length n_samples. Singleton clusters get 0.
    """
    X = np.asarray(X, dtype=np.float64)
    labels = np.asarray(labels).ravel()
    n = X.shape[0]
    silhouettes = np.zeros(n, dtype=np.float64)
    if n == 0:
        return silhouettes
    unique_labels = np.unique(labels)
    if unique_labels.size == 1:
        # No other cluster to compare against; silhouette is 0 by definition.
        return silhouettes
    sq = np.sum(X * X, axis=1)
    dist_sq = sq[:, None] + sq[None, :] - 2.0 * (X @ X.T)
    np.maximum(dist_sq, 0.0, out=dist_sq)
    dist = np.sqrt(dist_sq)
    np.fill_diagonal(dist, 0.0)
    unique_labels = np.unique(labels)
    for lab in unique_labels:
        members = np.where(labels == lab)[0]
        if members.size == 1:
            silhouettes[members[0]] = 0.0
            continue
        same = dist[np.ix_(members, members)]
        a = same.sum(axis=1) / (members.size - 1)
        other_means = []
        for other in unique_labels:
            if other == lab:
                continue
            other_members = np.where(labels == other)[0]
            d = dist[np.ix_(members, other_members)]
            other_means.append(d.mean(axis=1))
        b = np.min(np.stack(other_means, axis=1), axis=1)
        denom = np.maximum(a, b)
        silhouettes[members] = (b - a) / denom
    return silhouettes

