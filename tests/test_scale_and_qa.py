"""Phase 2 unit tests for scale-factor math and QA bit masking.
Calls functions from src.utils (does not re-implement the math).
"""
import numpy as np
import pytest

from utils import apply_scale_offset, kelvin_to_celsius, qa_valid, ndvi, ndbi


def test_scale_offset_math():
    dn = np.array([0, 1000, 65535], dtype="uint16")
    scale = 0.00341802
    offset = 149.0
    out = apply_scale_offset(dn, scale, offset)
    assert np.isclose(out[0], 149.0)
    assert np.isclose(out[1], 149.0 + 1000 * scale)
    assert np.isclose(out[2], 149.0 + 65535 * scale)


def test_lst_celsius_range():
    # Realistic lwir11 DN range that maps to ~19-40 C.
    k = apply_scale_offset(np.array([42000, 48000], dtype="uint16"),
                           0.00341802, 149.0)
    c = kelvin_to_celsius(k)
    assert np.all((c >= 15) & (c <= 50))


def test_ndvi_range():
    nir = np.array([0.2, 0.8])
    red = np.array([0.1, 0.2])
    assert np.all((ndvi(nir, red) >= -1) & (ndvi(nir, red) <= 1))


def test_ndbi_formula():
    swir = np.array([0.5, 0.1])
    nir = np.array([0.2, 0.4])
    assert np.isclose(ndbi(swir, nir)[0], (0.5 - 0.2) / (0.5 + 0.2))
    assert np.isclose(ndbi(swir, nir)[1], (0.1 - 0.4) / (0.1 + 0.4))


def test_qa_bit_masking():
    qa = np.zeros((4, 4), dtype="uint16")
    qa[0, 0] |= (1 << 3)   # cloud bit 3
    qa[1, 1] |= (1 << 4)   # shadow bit 4
    qa[2, 2] |= (1 << 2)   # cirrus bit 2
    valid = qa_valid(qa)
    assert not valid[0, 0]
    assert not valid[1, 1]
    assert not valid[2, 2]
    assert valid[3, 3]
    assert valid.sum() == 13


def test_fill_bit_masking():
    qa = np.ones((2, 2), dtype="uint16")  # fill bit 0 set everywhere
    assert qa_valid(qa).sum() == 0
