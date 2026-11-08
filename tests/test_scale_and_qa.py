"""Phase 2 unit tests.
Calls the real shared functions in src/utils (does not re-implement the math).
Tests cover: scale-offset math, LST Celsius range, NDVI range, NDBI formula,
QA bit masking via compute_validity (fill bit 0, cloud bit 3, shadow bit 4,
cirrus bit 2, dilated cloud bit 1), NaN handling, union logic across two
scenes, NDWI, and the shared date mosaic builder build_date_mosaic.
Expected values are hand-computed.
"""
import numpy as np
import pytest

from utils import (
    apply_scale_offset,
    kelvin_to_celsius,
    build_date_mosaic,
    compute_validity,
    ndvi,
    ndbi,
    ndwi,
)


def test_scale_offset_math():
    dn = np.array([0, 1000, 65535], dtype="uint16")
    scale = 0.00341802
    offset = 149.0
    out = apply_scale_offset(dn, scale, offset)
    assert np.isclose(out[0], 149.0)
    assert np.isclose(out[1], 149.0 + 1000 * scale)
    assert np.isclose(out[2], 149.0 + 65535 * scale)


def test_lst_celsius_range():
    k = apply_scale_offset(np.array([42000, 48000], dtype="uint16"),
                           0.00341802, 149.0)
    c = kelvin_to_celsius(k)
    assert np.all((c >= 15) & (c <= 50))


def test_ndvi_range():
    nir = np.array([0.2, 0.8])
    red = np.array([0.1, 0.2])
    assert np.all((ndvi(nir, red) >= -1) & (ndvi(nir, red) <= 1))


def test_ndvi_hand_computed():
    # (0.8 - 0.2) / (0.8 + 0.2) = 0.6
    assert np.isclose(ndvi(np.array([0.8]), np.array([0.2]))[0], 0.6)


def test_ndbi_formula():
    swir = np.array([0.5, 0.1])
    nir = np.array([0.2, 0.4])
    assert np.isclose(ndbi(swir, nir)[0], (0.5 - 0.2) / (0.5 + 0.2))
    assert np.isclose(ndbi(swir, nir)[1], (0.1 - 0.4) / (0.1 + 0.4))


def test_ndbi_hand_computed():
    # (0.6 - 0.3) / (0.6 + 0.3) = 1/3
    assert np.isclose(ndbi(np.array([0.6]), np.array([0.3]))[0], 1 / 3.0)


def test_ndwi_hand_computed():
    # (0.4 - 0.8) / (0.4 + 0.8) = -0.4 / 1.2 = -1/3
    assert np.isclose(ndwi(np.array([0.4]), np.array([0.8]))[0], -1 / 3.0)


def _clear_qa():
    return np.zeros((2, 2), dtype="uint16")


def test_qa_bit_masking_compute_validity():
    # compute_validity is the only bit-masking implementation.
    lwir = np.full((4, 4), 42000.0)  # all finite
    qa = np.zeros((4, 4), dtype="uint16")
    qa[0, 0] |= (1 << 3)   # cloud bit 3
    qa[1, 1] |= (1 << 4)   # shadow bit 4
    qa[2, 2] |= (1 << 2)   # cirrus bit 2
    valid = compute_validity(lwir, qa)
    assert not valid[0, 0]
    assert not valid[1, 1]
    assert not valid[2, 2]
    assert valid[3, 3]
    assert valid.sum() == 13


def test_dilated_cloud_bit_1_compute_validity():
    lwir = np.full((3, 3), 42000.0)
    qa = np.zeros((3, 3), dtype="uint16")
    qa[0, 0] |= (1 << 1)   # dilated cloud bit 1
    qa[1, 1] |= (1 << 3)   # cloud bit 3 (different bit)
    valid = compute_validity(lwir, qa)
    assert not valid[0, 0]   # dilated cloud set -> invalid
    assert not valid[1, 1]   # cloud set -> invalid
    assert valid[2, 2]       # all clear -> valid
    assert valid.sum() == 7


def test_fill_bit_masking_compute_validity():
    lwir = np.full((2, 2), 42000.0)
    qa = np.ones((2, 2), dtype="uint16")  # fill bit 0 set everywhere
    valid = compute_validity(lwir, qa)
    assert valid.sum() == 0


def test_nan_handling():
    # NaN lwir must be invalid even when QA is all clear.
    lwir = np.full((2, 2), np.nan)
    qa = np.zeros((2, 2), dtype="uint16")
    valid = compute_validity(lwir, qa)
    assert valid.sum() == 0
    assert not valid.any()


def test_union_logic_across_two_scenes():
    # Scene 1 valid only at (0,0); scene 2 valid only at (2,2).
    lwir1 = np.full((3, 3), np.nan)
    qa1 = np.zeros((3, 3), dtype="uint16")
    lwir1[0, 0] = 42000.0
    lwir2 = np.full((3, 3), np.nan)
    qa2 = np.zeros((3, 3), dtype="uint16")
    lwir2[2, 2] = 42000.0
    v1 = compute_validity(lwir1, qa1)
    v2 = compute_validity(lwir2, qa2)
    union = np.any(np.stack([v1, v2], axis=0), axis=0)
    expected = np.zeros((3, 3), dtype=bool)
    expected[0, 0] = True
    expected[2, 2] = True
    assert np.array_equal(union, expected)
    assert union.sum() == 2


def test_build_date_mosaic_cloudy_a_clear_b_returns_b():
    # Pixel cloudy in scene A (bit 3 set) and clear in scene B -> mosaic
    # returns exactly B's value, not an average.
    lwir_a = np.full((2, 2), 42000.0, dtype="float32")
    qa_a = np.zeros((2, 2), dtype="uint16")
    qa_a[0, 0] |= (1 << 3)  # cloud bit 3 at (0,0)
    lwir_b = np.full((2, 2), 46000.0, dtype="float32")
    qa_b = np.zeros((2, 2), dtype="uint16")
    scenes = [{"lwir11": lwir_a, "qa_pixel": qa_a},
              {"lwir11": lwir_b, "qa_pixel": qa_b}]
    mosaic, date_valid = build_date_mosaic(scenes)
    # (0,0): A cloudy (invalid), B clear -> exactly B's value 46000
    assert np.isclose(mosaic["lwir11"][0, 0], 46000.0)
    # date validity True where at least one scene valid
    assert bool(date_valid[0, 0])
    assert date_valid.all()


def test_build_date_mosaic_both_clear_returns_mean():
    # Both clear -> nanmedian of the two = mean.
    lwir_a = np.full((2, 2), 42000.0, dtype="float32")
    qa_a = np.zeros((2, 2), dtype="uint16")
    lwir_b = np.full((2, 2), 48000.0, dtype="float32")
    qa_b = np.zeros((2, 2), dtype="uint16")
    scenes = [{"lwir11": lwir_a, "qa_pixel": qa_a},
              {"lwir11": lwir_b, "qa_pixel": qa_b}]
    mosaic, _ = build_date_mosaic(scenes)
    assert np.isclose(mosaic["lwir11"][0, 0], 45000.0)


def test_build_date_mosaic_both_invalid_returns_nan():
    # Both invalid -> NaN.
    lwir_a = np.full((2, 2), 42000.0, dtype="float32")
    qa_a = np.ones((2, 2), dtype="uint16")  # fill bit 0 set everywhere
    lwir_b = np.full((2, 2), 48000.0, dtype="float32")
    qa_b = np.ones((2, 2), dtype="uint16")  # fill bit 0 set everywhere
    scenes = [{"lwir11": lwir_a, "qa_pixel": qa_a},
              {"lwir11": lwir_b, "qa_pixel": qa_b}]
    mosaic, date_valid = build_date_mosaic(scenes)
    assert np.isnan(mosaic["lwir11"][0, 0])
    assert not date_valid.any()


def test_build_date_mosaic_date_validity_equals_any():
    # Date validity equals any(valid across scenes).
    lwir_a = np.full((2, 2), np.nan, dtype="float32")
    qa_a = np.zeros((2, 2), dtype="uint16")
    lwir_b = np.full((2, 2), 42000.0, dtype="float32")
    qa_b = np.zeros((2, 2), dtype="uint16")
    qa_b[0, 0] |= (1 << 3)  # scene B cloudy at (0,0)
    scenes = [{"lwir11": lwir_a, "qa_pixel": qa_a},
              {"lwir11": lwir_b, "qa_pixel": qa_b}]
    _, date_valid = build_date_mosaic(scenes)
    # (0,0): scene A invalid (NaN lwir), scene B cloudy -> invalid
    assert not date_valid[0, 0]
    # (0,1): scene B clear -> valid
    assert date_valid[0, 1]
    expected = np.array([[False, True], [True, True]])
    assert np.array_equal(date_valid, expected)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
