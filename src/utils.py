"""Pure math helpers used by the pipeline and tests.
No rasterio/stac dependency; safe to unit test.
"""
import os
import warnings

import numpy as np


def write_log(path, text):
    """Write text to path with utf-8 encoding, overwriting any existing file."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(text if text.endswith("\n") else text + "\n")


def silence_all_nan_warning():
    """Suppress the known np.nanmedian \"All-NaN slice\" warning on fully masked
    scenes, which is expected and harmless here."""
    warnings.filterwarnings("ignore", message="All-NaN slice encountered",
                            category=RuntimeWarning)


def apply_scale_offset(dn, scale, offset):
    """LST/Reflectance = DN * scale + offset."""
    return dn.astype("float64") * scale + offset


def kelvin_to_celsius(k):
    return k - 273.15


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


def build_date_mosaic(scenes):
    """Build one date's mosaic from a list of scenes.

    Each scene is a dict {band_name: raw float32 array}. For each scene:
      - validity = compute_validity(lwir11, qa_pixel)
      - mask EVERY band with THAT scene's own validity, setting masked pixels
        to NaN BEFORE anything else.
    Mosaic scenes with nanmedian over the masked arrays (NaN ignored).
    Date validity = valid in at least one scene (union across scenes).
    Scale and offset are applied by the caller AFTER masking.
    Returns (mosaic: dict {band_name: array}, date_validity: bool array).
    """
    scene_validity = []
    scene_masked = {}
    for scene in scenes:
        validity = compute_validity(scene["lwir11"], scene["qa_pixel"])
        scene_validity.append(validity)
        for band_name, arr in scene.items():
            masked = np.where(validity, arr, np.nan)
            scene_masked.setdefault(band_name, []).append(masked)
    date_validity = np.any(np.stack(scene_validity, axis=0), axis=0)
    mosaic = {}
    for band_name, arrs in scene_masked.items():
        mosaic[band_name] = np.nanmedian(np.stack(arrs, axis=0), axis=0)
    return mosaic, date_validity
