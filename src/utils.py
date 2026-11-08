"""Pure math helpers used by the pipeline and tests.
No rasterio/stac dependency; safe to unit test.
"""
import numpy as np


def apply_scale_offset(dn, scale, offset):
    """LST/Reflectance = DN * scale + offset."""
    return dn.astype("float64") * scale + offset


def kelvin_to_celsius(k):
    return k - 273.15


def qa_valid(qa, bits=(1, 2, 3, 4)):
    """True where fill bit 0 and none of the given QA bits are set."""
    valid = ((qa >> 0) & 1) == 0
    for b in bits:
        valid &= ((qa >> b) & 1) == 0
    return valid


def ndvi(nir, red):
    return (nir - red) / (nir + red)


def ndbi(swir, nir):
    return (swir - nir) / (swir + nir)


def ndwi(green, nir):
    return (green - nir) / (green + nir)


def compute_validity(lwir_dn, qa_dn):
    """valid = finite(lwir_dn) AND fill bit 0 clear AND dilated cloud bit 1
    clear AND cirrus bit 2 clear AND cloud bit 3 clear AND shadow bit 4 clear.
    Missing QA (NaN -> 0) is cleared by the finite(lwir_dn) requirement because
    out-of-footprint lwir_dn is NaN. fill DN 0 is covered by fill bit 0.
    """
    valid = np.isfinite(lwir_dn)
    qa_i = np.nan_to_num(qa_dn, nan=0).astype(np.uint16)
    valid &= ((qa_i >> 0) & 1) == 0   # fill bit 0
    valid &= ((qa_i >> 1) & 1) == 0   # dilated cloud bit 1
    valid &= ((qa_i >> 2) & 1) == 0   # cirrus bit 2
    valid &= ((qa_i >> 3) & 1) == 0   # cloud bit 3
    valid &= ((qa_i >> 4) & 1) == 0   # shadow bit 4
    return valid
