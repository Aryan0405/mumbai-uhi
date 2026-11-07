"""Phase 2 step 10: Unit tests for scale-factor math and QA bit masking
on small synthetic arrays. No real satellite data required.
"""
import numpy as np
import pytest


def apply_scale_offset(dn, scale, offset):
    return dn.astype("float64") * scale + offset


def kelvin_to_celsius(k):
    return k - 273.15


def qa_valid(qa, bits=(1, 2, 3, 4)):
    """True where none of the given QA bits are set (and fill bit 0 unset)."""
    valid = ((qa >> 0) & 1) == 0
    for b in bits:
        valid &= ((qa >> b) & 1) == 0
    return valid


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
    ndvi = (nir - red) / (nir + red)
    assert np.all((ndvi >= -1) & (ndvi <= 1))


def test_qa_bit_masking():
    qa = np.zeros((4, 4), dtype="uint16")
    # set cloud bit 3 on one pixel
    qa[0, 0] |= (1 << 3)
    # set shadow bit 4 on another
    qa[1, 1] |= (1 << 4)
    # set cirrus bit 2 on another
    qa[2, 2] |= (1 << 2)
    valid = qa_valid(qa)
    assert not valid[0, 0]
    assert not valid[1, 1]
    assert not valid[2, 2]
    assert valid[3, 3]
    assert valid.sum() == 13


def test_fill_bit_masking():
    qa = np.ones((2, 2), dtype="uint16")  # fill bit 0 set everywhere
    valid = qa_valid(qa)
    assert valid.sum() == 0


def test_ndbi_formula():
    swir = np.array([0.5, 0.1])
    nir = np.array([0.2, 0.4])
    ndbi = (swir - nir) / (swir + nir)
    assert np.isclose(ndbi[0], (0.5 - 0.2) / (0.5 + 0.2))
    assert np.isclose(ndbi[1], (0.1 - 0.4) / (0.1 + 0.4))
