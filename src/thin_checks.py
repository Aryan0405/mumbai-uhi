"""Pure neighbour-count utilities (Phase 6 round).

numpy only, docstrings included.
"""
import numpy as np


def neighbour_count(mask2d):
    """For each cell, count its 8 neighbours (not itself) that are True.

    Edges handled without wraparound via np.pad with zeros and slicing.
    Returns a 2-D int array of the same shape.
    """
    mask2d = np.asarray(mask2d, dtype=bool)
    rows, cols = mask2d.shape
    padded = np.pad(mask2d, 1, mode="constant")
    out = np.zeros((rows, cols), dtype=int)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            out = out + padded[1 + dr:1 + dr + rows, 1 + dc:1 + dc + cols].astype(int)
    return out


def mean_neighbour_count(mask2d, member2d):
    """Mean of neighbour_count(mask2d) over cells where member2d is True.

    Returns nan when member2d has no True cell.
    """
    mask2d = np.asarray(mask2d, dtype=bool)
    member2d = np.asarray(member2d, dtype=bool)
    counts = neighbour_count(mask2d)
    sel = counts[member2d]
    if sel.size == 0:
        return float("nan")
    return float(sel.mean())
