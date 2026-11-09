"""Read-only check of monthly LST rasters with rasterio (Phase 7a round).

Exits 2 if its log already exists. Prints numbers only.
"""
import hashlib
import os
import sys

import numpy as np
import rasterio

MARCH_TIF = os.path.join("data", "composites_months", "lst_march.tif")
APRMAY_TIF = os.path.join("data", "composites_months", "lst_aprmay.tif")
LOG_PATH = os.path.join("logs", "phase7a_rasterio.txt")


def describe_tif(path, lines):
    with rasterio.open(path, "r") as src:
        band = src.read(1)
        finite = band[np.isfinite(band)]
        lines.append(path)
        lines.append("  width=%d height=%d count=%d" % (src.width, src.height, src.count))
        lines.append("  dtype=%s" % str(src.dtypes[0]))
        lines.append("  crs=%s" % str(src.crs))
        lines.append("  transform=%s" % str(tuple(src.transform)))
        lines.append("  nodata=%s" % str(src.nodata))
        lines.append("  finite_pixels=%d min=%.6f max=%.6f mean=%.6f" % (
            int(finite.size), float(finite.min()), float(finite.max()), float(finite.mean())))


def main():
    if os.path.exists(LOG_PATH):
        print("error: log path already exists, will not overwrite: " + LOG_PATH)
        raise SystemExit(2)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    lines = []
    lines.append("python " + sys.version.split()[0])
    lines.append("numpy " + np.__version__)
    lines.append("rasterio %s gdal %s" % (rasterio.__version__, rasterio.__gdal_version__))
    lines.append("")
    describe_tif(MARCH_TIF, lines)
    lines.append("")
    describe_tif(APRMAY_TIF, lines)
    text = "\n".join(lines) + "\n"
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
