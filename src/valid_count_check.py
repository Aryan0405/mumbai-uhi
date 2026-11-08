"""Item 2B: valid_count versus LST/NDVI/NDBI over BMC land pixels.
Reads data/composites/ (read only). Writes logs/round4c_valid_count_check.txt.
"""
import os
import sys
import numpy as np
import rasterio
from rasterio.warp import transform as warp_transform
from rasterio.features import rasterize as rio_rasterize
from shapely.geometry import mapping as shp_mapping
import geopandas as gpd
from scipy import stats

sys.path.insert(0, "src")
import config
from utils import write_log

DIR_COMP = config.DIR_COMPOSITES


def read_band(name):
    with rasterio.open(os.path.join(DIR_COMP, f"{name}.tif")) as src:
        return src.read(1).astype(np.float64), src.transform, src.crs, src.height, src.width


def main():
    lwir, tf, crs, H, W = read_band("lwir11")
    ndvi, _, _, _, _ = read_band("ndvi")
    ndbi, _, _, _, _ = read_band("ndbi")
    ndwi, _, _, _, _ = read_band("ndwi")
    vcount, _, _, _, _ = read_band("valid_count")

    bmc = gpd.read_file(config.BMC_GEOJSON).dissolve().to_crs(config.CRS_METRIC)
    bmc_mask = rio_rasterize(
        [shp_mapping(g) for g in bmc.geometry],
        out_shape=(H, W), transform=tf, fill=0, default_value=1, dtype="uint8",
    ).astype(bool)

    water_mask = ndwi > 0
    lst = lwir - 273.15
    valid_land = bmc_mask & (~water_mask) & ~np.isnan(lst) & ~np.isnan(vcount)

    lines = []
    lines.append(f"BMC land pixels (finite LST, valid_count): {int(valid_land.sum())}")

    # a. Table grouped by valid_count value
    vals, counts = np.unique(vcount[valid_land], return_counts=True)
    lines.append("")
    lines.append("a. Table grouped by valid_count value (BMC land):")
    lines.append(f"  {'valid_count':>12} {'n_pixels':>10} {'median_LST_C':>14} {'median_NDVI':>14} {'median_NDBI':>14}")
    for v, c in zip(vals, counts):
        m = valid_land & (vcount == v)
        med_lst = float(np.median(lst[m]))
        med_ndvi = float(np.median(ndvi[m]))
        med_ndbi = float(np.median(ndbi[m]))
        lines.append(f"  {int(v):>12} {int(c):>10} {med_lst:>14.2f} {med_ndvi:>14.4f} {med_ndbi:>14.4f}")

    # b. Spearman correlations
    mask_b = valid_land
    vc = vcount[mask_b].astype(float)
    l = lst[mask_b].astype(float)
    n_ = ndvi[mask_b].astype(float)
    b_ = ndbi[mask_b].astype(float)
    n_pixels = int(vc.size)
    lines.append("")
    lines.append(f"b. Spearman correlation (BMC land pixels, n={n_pixels}):")
    if n_pixels < 1000:
        lines.append("  NOTE: computed on fewer than 1000 pixels.")
    rho_lst, _ = stats.spearmanr(vc, l)
    rho_ndvi, _ = stats.spearmanr(vc, n_)
    rho_ndbi, _ = stats.spearmanr(vc, b_)
    lines.append(f"  valid_count vs LST:   rho={rho_lst:.4f}")
    lines.append(f"  valid_count vs NDVI:  rho={rho_ndvi:.4f}")
    lines.append(f"  valid_count vs NDBI:  rho={rho_ndbi:.4f}")
    lines.append("  Coefficients reported only; no statistical significance claim "
                 "(30 m neighbouring pixels are spatially autocorrelated).")

    # c. Median LST for valid_count <= 20 versus >= 23
    m_le20 = valid_land & (vcount <= 20)
    m_ge23 = valid_land & (vcount >= 23)
    med_le20 = float(np.median(lst[m_le20])) if m_le20.sum() > 0 else None
    med_ge23 = float(np.median(lst[m_ge23])) if m_ge23.sum() > 0 else None
    lines.append("")
    lines.append("c. Median LST by valid_count group:")
    lines.append(f"  valid_count <= 20: median LST = {med_le20:.2f} C, n = {int(m_le20.sum())}")
    lines.append(f"  valid_count >= 23: median LST = {med_ge23:.2f} C, n = {int(m_ge23.sum())}")

    # d. Count of BMC land pixels with valid_count < 18, bounding box
    m_lt18 = valid_land & (vcount < 18)
    n_lt18 = int(m_lt18.sum())
    lines.append("")
    lines.append(f"d. BMC land pixels with valid_count < 18: {n_lt18}")
    if n_lt18 > 0:
        rows_idx, cols_idx = np.where(m_lt18)
        xs = tf.c + (cols_idx + 0.5) * tf.a
        ys = tf.f + (rows_idx + 0.5) * tf.e
        lons, lats = warp_transform(config.CRS_METRIC, config.CRS_LONLAT, xs.tolist(), ys.tolist())
        lons = np.asarray(lons, dtype=float)
        lats = np.asarray(lats, dtype=float)
        lines.append(f"  lon range: {float(lons.min()):.6f} to {float(lons.max()):.6f}")
        lines.append(f"  lat range: {float(lats.min()):.6f} to {float(lats.max()):.6f}")

    log_path = os.path.join(config.DIR_LOGS, "round4c_valid_count_check.txt")
    write_log(log_path, "\n".join(lines))
    print(f"  Valid count check written to {log_path}")


if __name__ == "__main__":
    main()
