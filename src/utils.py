"""Pure math helpers used by the pipeline and tests.
No rasterio/stac dependency; safe to unit test.
"""


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
