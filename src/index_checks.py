"""Pure index utility functions for checks (Phase 5 round).

numpy only. Docstrings included.
"""
import numpy as np


def scheme_weights(wE):
    """Return (wH, wS, wE) with wH = wS = (1 - wE) / 2."""
    wE = float(wE)
    wH = (1.0 - wE) / 2.0
    wS = wH
    return (wH, wS, wE)


def stability_count(flags):
    """Elementwise sum of a list of boolean arrays. Returns int array."""
    arr = np.asarray(flags, dtype=int)
    return arr.sum(axis=0)


def grid_from_cells(rows, cols, values, shape, fill):
    """Place values at [rows, cols] in a 2-D array of shape filled with fill."""
    rows = np.asarray(rows, dtype=int)
    cols = np.asarray(cols, dtype=int)
    values = np.asarray(values, dtype=float)
    out = np.full(shape, fill, dtype=float)
    out[rows, cols] = values
    return out


def neighbour_flag(mask2d):
    """True where at least one of the 8 neighbours (not the cell itself) is True.

    Edges handled without wraparound.
    """
    mask2d = np.asarray(mask2d, dtype=bool)
    rows, cols = mask2d.shape
    padded = np.pad(mask2d, 1, mode="constant")
    out = np.zeros((rows, cols), dtype=bool)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            out = out | padded[1 + dr:1 + dr + rows, 1 + dc:1 + dc + cols]
    return out
