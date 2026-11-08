"""Step 7: old vs v2 comparison (report only). Reads data/composites/ (old) and
data/composites_v2/ (new). Compares valid_count inside BMC, and LST/NDVI/NDBI
over BMC land. Does NOT switch any downstream file to v2.
"""
import os
import sys
import numpy as np
import rasterio
from rasterio.features import rasterize as rio_rasterize
from shapely.geometry import mapping as shp_mapping
import geopandas as gpd

sys.path.insert(0, "src")
import config

DIR_OLD = "data/composites"
DIR_NEW = "data/composites_v2"


def read_band(d, name):
    with rasterio.open(os.path.join(d, f"{name}.tif")) as src:
        return src.read(1).astype("float64"), src.transform, src.crs, src.height, src.width


def main():
    old_lwir, tf, crs, H, W = read_band(DIR_OLD, "lwir11")
    new_lwir, _, _, _, _ = read_band(DIR_NEW, "lwir11")
    old_ndvi, _, _, _, _ = read_band(DIR_OLD, "ndvi")
    new_ndvi, _, _, _, _ = read_band(DIR_NEW, "ndvi")
    old_ndbi, _, _, _, _ = read_band(DIR_OLD, "ndbi")
    new_ndbi, _, _, _, _ = read_band(DIR_NEW, "ndbi")
    with rasterio.open(os.path.join(DIR_OLD, "valid_count.tif")) as src:
        old_vc = src.read(1).astype("float64")
    with rasterio.open(os.path.join(DIR_NEW, "valid_count.tif")) as src:
        new_vc = src.read(1).astype("float64")

    bmc = gpd.read_file(config.BMC_GEOJSON).dissolve().to_crs(config.CRS_METRIC)
    bmc_mask = rio_rasterize(
        [shp_mapping(g) for g in bmc.geometry],
        out_shape=(H, W), transform=tf, fill=0, default_value=1, dtype="uint8",
    ).astype(bool)

    def stats(arr, mask):
        a = arr[mask & ~np.isnan(arr)]
        if a.size == 0:
            return None
        return float(np.nanmin(a)), float(np.median(a)), float(np.nanmax(a))

    print("valid_count inside BMC:")
    for name, arr in [("old", old_vc), ("v2", new_vc)]:
        s = stats(arr, bmc_mask)
        print(f"  {name}: min={s[0]:.1f} median={s[1]:.1f} max={s[2]:.1f}")

    diff_vc = new_vc - old_vc
    d = diff_vc[bmc_mask & ~np.isnan(diff_vc)]
    n_diff = int((d != 0).sum())
    print(f"valid_count pixels differing inside BMC: {n_diff}")

    for label, old_a, new_a in [("LST", old_lwir - 273.15, new_lwir - 273.15),
                                ("NDVI", old_ndvi, new_ndvi),
                                ("NDBI", old_ndbi, new_ndbi)]:
        mask = bmc_mask & ~np.isnan(old_a) & ~np.isnan(new_a)
        oa = old_a[mask]
        na = new_a[mask]
        md = float(np.nanmean(na - oa))
        mad = float(np.nanmax(np.abs(na - oa)))
        print(f"{label} over BMC land: mean diff (v2-old)={md:.4f}, "
              f"max abs diff={mad:.4f}, n={oa.size}")
        if label == "LST":
            n_gt50 = int(np.sum(np.abs(na - oa) > 0.5))
            print(f"  LST pixels differing by >0.5 C: {n_gt50}")


if __name__ == "__main__":
    main()
