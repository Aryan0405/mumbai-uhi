"""Candidate index schemes for cell-level heat exposure (Phase 3B round 3).

Pure functions with docstrings. Reads nothing from disk; operates on arrays.
Population density is the primary density (WorldPop 2020, on core cells);
this module takes density arrays as input and takes no stance on which
density definition is final -- no weights, no exposure-transform choice,
no index is selected here.

Candidate set (fixed, not tuned to the data):
    W1 = (1/3, 1/3, 1/3), W2 = (0.5, 0.25, 0.25), W3 = (0.4, 0.4, 0.2),
    each combined with exposure kinds raw, sqrt, pct  -> W1_raw ... W3_pct
    W4 = (0.5, 0.5, 0) with no exposure term               -> W4_noexp
Total: 10 candidates.
"""
import numpy as np

from stats_utils import rank_average


def standardise(v):
    """Standardise v: (v - mean) / std with ddof=0."""
    v = np.asarray(v, dtype=np.float64)
    mean = float(np.mean(v))
    std = float(np.std(v, ddof=0))
    if std == 0.0:
        std = 1.0
    return (v - mean) / std


def exposure(density, kind):
    """Exposure transform of a density array.

    kind "raw": density unchanged.
    kind "sqrt": sqrt(density).
    kind "pct": average-rank percentile = rank_average(density) / n;
                tied values (including zeros) share the average rank.
    Returns a float64 array of the same shape.
    """
    density = np.asarray(density, dtype=np.float64)
    if kind == "raw":
        return density.copy()
    if kind == "sqrt":
        return np.sqrt(np.maximum(density, 0.0))
    if kind == "pct":
        n = density.size
        ranks = rank_average(density)
        return ranks / float(n)
    raise ValueError("unknown exposure kind: %r" % (kind,))


def components(lst, ndvi, ndbi, density, kind):
    """Component scores H, S, E.

    H = standardise(lst)                        hotness
    S = standardise(-z_ndvi + z_ndbi)           built-up-ish vs vegetated-ish
    E = standardise(exposure(density, kind))    population exposure
    Returns (H, S, E) as float64 arrays.
    """
    lst = np.asarray(lst, dtype=np.float64)
    ndvi = np.asarray(ndvi, dtype=np.float64)
    ndbi = np.asarray(ndbi, dtype=np.float64)
    z_ndvi = standardise(ndvi)
    z_ndbi = standardise(ndbi)
    H = standardise(lst)
    S = standardise(-z_ndvi + z_ndbi)
    E = standardise(exposure(density, kind))
    return H, S, E


def index(H, S, E, wH, wS, wE):
    """Weighted index: wH*H + wS*S + wE*E on same-shaped arrays."""
    H = np.asarray(H, dtype=np.float64)
    S = np.asarray(S, dtype=np.float64)
    E = np.asarray(E, dtype=np.float64)
    return float(wH) * H + float(wS) * S + float(wE) * E


# Candidate set (fixed, not data-dependent): names like W1_raw ... W3_pct,
# plus W4_noexp with no exposure term.
CANDIDATES = {
    "W1_raw": (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0, "raw"),
    "W1_sqrt": (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0, "sqrt"),
    "W1_pct": (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0, "pct"),
    "W2_raw": (0.5, 0.25, 0.25, "raw"),
    "W2_sqrt": (0.5, 0.25, 0.25, "sqrt"),
    "W2_pct": (0.5, 0.25, 0.25, "pct"),
    "W3_raw": (0.4, 0.4, 0.2, "raw"),
    "W3_sqrt": (0.4, 0.4, 0.2, "sqrt"),
    "W3_pct": (0.4, 0.4, 0.2, "pct"),
    "W4_noexp": (0.5, 0.5, 0.0, None),
}


def component_sets(lst, ndvi, ndbi, density):
    """Return (H, S, E_by_kind).

    H and S come from components(..., "raw"). E_by_kind is a dict
    {"raw": E, "sqrt": E, "pct": E} of standardised exposure transforms.
    """
    lst = np.asarray(lst, dtype=np.float64)
    ndvi = np.asarray(ndvi, dtype=np.float64)
    ndbi = np.asarray(ndbi, dtype=np.float64)
    density = np.asarray(density, dtype=np.float64)
    H, S, E_raw = components(lst, ndvi, ndbi, density, "raw")
    E_sqrt = standardise(exposure(density, "sqrt"))
    E_pct = standardise(exposure(density, "pct"))
    E_by_kind = {"raw": E_raw, "sqrt": E_sqrt, "pct": E_pct}
    return H, S, E_by_kind


def candidate_scores(lst, ndvi, ndbi, density):
    """Return dict name -> score array in CANDIDATES order.

    For a candidate whose kind is None the exposure term is skipped (weight
    0), never passed to exposure().
    """
    H, S, E_by_kind = component_sets(lst, ndvi, ndbi, density)
    scores = {}
    for name, (wH, wS, wE, kind) in CANDIDATES.items():
        if kind is None:
            score = float(wH) * H + float(wS) * S
        else:
            E = E_by_kind[kind]
            score = float(wH) * H + float(wS) * S + float(wE) * E
        scores[name] = score
    return scores


def top_set(scores, n):
    """Set of indices of the n largest scores; ties broken by lower index."""
    scores = np.asarray(scores, dtype=np.float64)
    order = np.argsort(-scores, kind="stable")
    return set(int(i) for i in order[:n])


def jaccard(a, b):
    """|a and b| / |a or b| for two sets."""
    a = set(a)
    b = set(b)
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / float(len(union))
