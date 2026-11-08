"""Item 2B: valid_count versus LST/NDVI/NDBI over BMC land pixels.
Reads data/composites/ (read only). Writes logs/round4c_valid_count_check.txt.
"""
import os
import sys
import numpy as np
import rasterio
from scipy import stats
from rasterio.warp import reproject, Resampling
from rasterio.transform import from_origin
from rasterio.features import rasterize as rio_rasterize
from shapely.geometry import mapping as shp_mapping
import geopandas as gpd

sys.path.insert(0, "src")
import config

DIR_COMP = "data/composites"


def read_band(name):
    with rasterio.open(os.path.join(DIR_COMP, f"{name}.tif")) as src:
        return src.read(1).astype("float64"), src.transform, src.crs, src.height, src.width


def rowcol_to_xy(r, c, affine):
    x = affine.c + c * affine.a + affine.a / 2.0
    y = affine.f + r * affine.e + affine.e / 2.0
    return x, y


def main():
    lwir, affine, crs, H, W = read_band("lwir11")
    ndvi, _, _, _, _ = read_band("ndvi")
    ndbi, _, _, _, _ = read_band("ndbi")
    ndwi, _, _, _, _ = read_band("ndwi")
    vcount, _, _, _, _ = read_band("valid_count")

    bmc = gpd.read_file(config.BMC_GEOJSON).dissolve().to_crs(config.CRS_METRIC)
    bmc_mask = rio_rasterize(
        [shp_mapping(g) for g in bmc.geometry],
        out_shape=(H, W), transform=affine, fill=0, default_value=1, dtype="uint8",
    ).astype(bool)

    water_mask = ndwi > 0
    bmc_land = bmc_mask & (~water_mask)

    lst = lwir - 273.15
    valid_land = bmc_land & ~np.isnan(lst) & ~np.isnan(vcount)

    print(f"BMC land pixels (finite LST, valid_count): {int(valid_land.sum())}")

    # a. Table grouped by valid_count value
    vals, counts = np.unique(vcount[valid_land], return_counts=True)
    print("\na. Table grouped by valid_count value (BMC land):")
    print(f"  {'valid_count':>12} {'n_pixels':>10} {'median_LST_C':>14} {'median_NDVI':>14} {'median_NDBI':>14}")
    for v, c in zip(vals, counts):
        m = valid_land & (vcount == v)
        med_lst = float(np.median(lst[m]))
        med_ndvi = float(np.median(ndvi[m]))
        med_ndbi = float(np.median(ndbi[m]))
        print(f"  {int(v):>12} {int(c):>10} {med_lst:>14.2f} {med_ndvi:>14.4f} {med_ndbi:>14.4f}")

    # b. Spearman correlations
    mask_b = valid_land
    vc = vcount[mask_b].astype(float)
    l = lst[mask_b].astype(float)
    n_ = ndvi[mask_b].astype(float)
    b_ = ndbi[mask_b].astype(float)
    n_pixels = int(vc.size)
    print(f"\nb. Spearman correlation (BMC land pixels, n={n_pixels}):")
    if n_pixels < 1000:
        print("  NOTE: computed on fewer than 1000 pixels.")
    rho_lst, _ = stats.spearmanr(vc, l)
    rho_ndvi, _ = stats.spearmanr(vc, n_)
    rho_ndbi, _ = stats.spearmanr(vc, b_)
    print(f"  valid_count vs LST:   rho={rho_lst:.4f}")
    print(f"  valid_count vs NDVI:  rho={rho_ndvi:.4f}")
    print(f"  valid_count vs NDBI:  rho={rho_ndbi:.4f}")
    print("  Coefficients reported only; no statistical significance claim "
          "(30 m neighbouring pixels are spatially autocorrelated).")

    # c. Median LST for valid_count <= 20 versus >= 23
    m_le20 = valid_land & (vcount <= 20)
    m_ge23 = valid_land & (vcount >= 23)
    med_le20 = float(np.median(lst[m_le20])) if m_le20.sum() > 0 else None
    med_ge23 = float(np.median(lst[m_ge23])) if m_ge23.sum() > 0 else None
    print(f"\nc. Median LST by valid_count group:")
    print(f"  valid_count <= 20: median LST = {med_le20:.2f} C, n = {int(m_le20.sum())}")
    print(f"  valid_count >= 23: median LST = {med_ge23:.2f} C, n = {int(m_ge23.sum())}")

    # d. Count of BMC land pixels with valid_count < 18, bounding box
    m_lt18 = valid_land & (vcount < 18)
    n_lt18 = int(m_lt18.sum())
    print(f"\nd. BMC land pixels with valid_count < 18: {n_lt18}")
    if n_lt18 > 0:
        rows, cols = np.where(m_lt18)
        xs = affine.c + cols * affine.a + affine.a / 2.0
        ys = affine.f + rows * affine.e + affine.e / 2.0
        from rasterio.warp import transform as warp_transform
        lons, lats = warp_transform(config.CRS_METRIC, config.CRS_LONLAT, xs.tolist(), ys.tolist())
        print(f"  lon range: {float(np.min(lons)):.6f} to {float(np.max(lons)):.6f}")
        print(f"  lat range: {float(np.min(lats)):.6f} to {float(np.max(lats)):.6f}")


if __name__ == "__main__":
    main()
