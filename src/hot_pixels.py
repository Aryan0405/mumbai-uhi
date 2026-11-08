"""Item 5: hot pixels as connected clusters; water mask NDWI histogram;
NDVI/NDBI percentile ranks within BMC land; PNG of removed pixels.
Reads data/composites/*.tif (read only).
"""
import os
import sys
import numpy as np
import rasterio
from scipy import ndimage
from shapely.geometry import mapping as shp_mapping
import geopandas as gpd
from rasterio.features import rasterize as rio_rasterize
from rasterio.warp import transform
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, "src")
import config

DIR_COMP = config.DIR_COMPOSITES


def read_band(name):
    with rasterio.open(os.path.join(DIR_COMP, f"{name}.tif")) as src:
        return src.read(1).astype("float64"), src.transform, src.crs, src.height, src.width


def rowcol_to_xy(r, c, transform):
    x = transform.c + c * transform.a + transform.a / 2.0
    y = transform.f + r * transform.e + transform.e / 2.0
    return x, y


def main():
    lwir, tf, crs, H, W = read_band("lwir11")
    ndvi, _, _, _, _ = read_band("ndvi")
    ndbi, _, _, _, _ = read_band("ndbi")
    ndwi, _, _, _, _ = read_band("ndwi")

    # BMC land mask in EPSG:32643 grid
    bmc = gpd.read_file(config.BMC_GEOJSON).dissolve().to_crs(config.CRS_METRIC)
    bmc_mask = rio_rasterize(
        [shp_mapping(g) for g in bmc.geometry],
        out_shape=(H, W), transform=tf, fill=0, default_value=1, dtype="uint8",
    ).astype(bool)
    water_mask = ndwi > 0
    removed_from_bmc = water_mask & bmc_mask
    bmc_land_mask = bmc_mask & (~water_mask)

    print(f"NDWI histogram inside BMC (bins=-1 to 1 step 0.1, count of pixels):")
    bmc_ndwi = ndwi[bmc_mask]
    hist, edges = np.histogram(bmc_ndwi, bins=np.arange(-1.0, 1.01, 0.1))
    for i in range(len(hist)):
        print(f"  [{edges[i]:+.1f} to {edges[i+1]:+.1f}): {int(hist[i])}")
    print(f"Water pixels (NDWI > 0) removed from BMC polygon: {int(removed_from_bmc.sum())}")

    # BMC land stats
    bmc_land_ndvi = ndvi[bmc_land_mask]
    bmc_land_ndbi = ndbi[bmc_land_mask]
    ndbi_median = float(np.median(bmc_land_ndbi))

    # Removed water pixels with NDBI above BMC land median
    removed_ndbi = ndbi[removed_from_bmc]
    n_removed_ndbi_above = int((removed_ndbi > ndbi_median).sum())
    print(f"BMC land median NDBI: {ndbi_median:.4f}")
    print(f"Removed water pixels with NDBI above BMC land median: {n_removed_ndbi_above}")

    # LST over BMC land
    lst = lwir - 273.15
    # Hot pixels: LST > 50 C, BMC land
    hot = (lst > config.LST_HOT_THRESHOLD_C) & bmc_land_mask & np.isfinite(lst)
    labeled, n_clusters = ndimage.label(hot)
    print(f"\nHot clusters (LST > {config.LST_HOT_THRESHOLD_C} C, BMC land): {n_clusters}")

    # Percentile rank helper
    def percentile_rank(values, x):
        return float((values <= x).mean() * 100.0)

    print(f"\nCluster id, pixel count, max LST, centroid lon, centroid lat, mean NDVI, mean NDBI, "
          f"NDVI pct rank, NDBI pct rank")
    for cid in range(1, n_clusters + 1):
        cells = labeled == cid
        coords = np.argwhere(cells)
        r_center = float(coords[:, 0].mean())
        c_center = float(coords[:, 1].mean())
        x, y = rowcol_to_xy(int(round(r_center)), int(round(c_center)), tf)
        lon, lat = transform(config.CRS_METRIC, config.CRS_LONLAT, [x], [y])
        max_lst = float(lst[cells].max())
        mean_ndvi = float(ndvi[cells].mean())
        mean_ndbi = float(ndbi[cells].mean())
        print(f"{cid}, {int(cells.sum())}, {max_lst:.2f}, {float(lon[0]):.6f}, "
              f"{float(lat[0]):.6f}, {mean_ndvi:.3f}, {mean_ndbi:.3f}, "
              f"{percentile_rank(bmc_land_ndvi, mean_ndvi):.1f}, "
              f"{percentile_rank(bmc_land_ndbi, mean_ndbi):.1f}")

    # PNG of removed pixels over BMC outline
    fig, ax = plt.subplots(figsize=(7, 6))
    show = np.where(removed_from_bmc, 1, np.nan)
    im = ax.imshow(show, cmap="Reds", vmin=0, vmax=1, extent=(
        tf.c, tf.c + tf.a * W, tf.f + tf.e * H, tf.f), origin="upper")
    ax.set_title("Water pixels removed from BMC (NDWI > 0)")
    ax.set_axis_off()
    for geom in bmc.geometry:
        geoms = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
        for g in geoms:
            xs, ys = g.exterior.xy
            ax.plot(xs, ys, color="white", linewidth=0.8, alpha=0.9)
    plt.colorbar(im, ax=ax, fraction=0.046)
    plt.tight_layout()
    out = os.path.join(config.DIR_LOGS, "quicklook_removed_water.png")
    plt.savefig(out, dpi=100)
    plt.close(fig)
    print(f"\nRemoved-water PNG: {out}")
    print(f"Figure size: 7 x 6 inches")


if __name__ == "__main__":
    main()
