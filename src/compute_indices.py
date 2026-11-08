"""Phase 2 compute indices + checks: reads existing band composites
(data/composites/*.tif, valid_count.tif), computes NDVI/NDBI/NDWI, writes them,
runs validity checks, reports LST percentiles, valid-observation distribution,
and saves quicklook PNGs with 'masked' labels.
"""
import os
import numpy as np
import rasterio
from rasterio.warp import transform
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config

DIR_COMP = config.DIR_COMPOSITES
LOGS = config.DIR_LOGS
os.makedirs(LOGS, exist_ok=True)


def read_band(name):
    with rasterio.open(os.path.join(DIR_COMP, f"{name}.tif")) as src:
        return src.read(1).astype("float64"), src.transform, src.crs


def write_band(name, arr, transform, crs):
    profile = {
        "driver": "GTiff", "dtype": "float32", "width": arr.shape[1],
        "height": arr.shape[0], "count": 1, "crs": crs,
        "transform": transform, "nodata": np.nan,
    }
    with rasterio.open(os.path.join(DIR_COMP, f"{name}.tif"), "w", **profile) as dst:
        dst.write(arr.astype("float32"), 1)


def quicklook(name, arr, vmin, vmax, cmap, label, extent=None, bmc4326=None,
              mask_nan=True):
    fig, ax = plt.subplots(figsize=(7, 6))
    show = np.where(np.isnan(arr), np.nan, arr) if mask_nan else arr
    im = ax.imshow(show, cmap=cmap, vmin=vmin, vmax=vmax, extent=extent,
                   origin="upper", aspect="auto")
    ax.set_title(f"{label} (masked)")
    ax.set_axis_off()
    if bmc4326 is not None:
        for geom in bmc4326.geometry:
            if geom.is_empty:
                continue
            geoms = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
            for g in geoms:
                xs, ys = g.exterior.xy
                ax.plot(xs, ys, color="white", linewidth=0.8, alpha=0.9)
    plt.colorbar(im, ax=ax, fraction=0.046)
    plt.tight_layout()
    out = os.path.join(LOGS, f"quicklook_{name}.png")
    plt.savefig(out, dpi=100)
    plt.close(fig)
    return out


def lonlat_to_rowcol(lon, lat, transform):
    from rasterio.transform import rowcol
    from rasterio.warp import transform as tform
    xs, ys = tform(config.CRS_LONLAT, config.CRS_METRIC, [lon], [lat])
    r, c = rowcol(transform, xs=xs, ys=ys, op=round)
    return int(r[0]), int(c[0])


def main():
    lwir, tf, crs = read_band("lwir11")
    red, _, _ = read_band("red")
    nir, _, _ = read_band("nir08")
    swir, _, _ = read_band("swir16")
    green, _, _ = read_band("green")
    with rasterio.open(os.path.join(DIR_COMP, "valid_count.tif")) as src:
        vcount = src.read(1).astype("float64")

    # ---- Indices ----
    ndvi = (nir - red) / (nir + red)
    ndbi = (swir - nir) / (swir + nir)
    ndwi = (green - nir) / (green + nir)
    write_band("ndvi", ndvi, tf, crs)
    write_band("ndbi", ndbi, tf, crs)
    write_band("ndwi", ndwi, tf, crs)

    # ---- Checks ----
    nv = ndvi[~np.isnan(ndvi)]
    print(f"NDVI: min={float(np.nanmin(ndvi)):.4f} max={float(np.nanmax(ndvi)):.4f} "
          f"in [-1,1]: {bool(np.all((nv >= -1) & (nv <= 1)))}")

    # ---- LST percentiles (provisional rule) ----
    lst = lwir - 273.15
    finite = lst[~np.isnan(lst)]
    p01, p999 = np.percentile(finite, [config.LST_PERCENTILES[0], config.LST_PERCENTILES[1]])
    mx = float(finite.max())
    n_hot = int((finite > config.LST_HOT_THRESHOLD_C).sum())
    print(f"LST composite: 0.1th={p01:.2f} C, 99.9th={p999:.2f} C, max={mx:.2f} C, "
          f"count_above_50C={n_hot}, valid={finite.size}")

    # ---- BMC mask ----
    import geopandas as gpd
    from rasterio.features import rasterize as rio_rasterize
    from shapely.geometry import mapping as shp_mapping
    bmc = gpd.read_file(config.BMC_GEOJSON).dissolve().to_crs(config.CRS_METRIC)
    bmc_mask = rio_rasterize(
        [shp_mapping(g) for g in bmc.geometry],
        out_shape=lwir.shape, transform=tf, fill=0, default_value=1, dtype="uint8",
    ).astype(bool)
    print(f"BMC mask pixels: {int(bmc_mask.sum())} of {bmc_mask.size}")

    # ---- Valid observation distribution ----
    vc = vcount[~np.isnan(vcount)]
    print(f"Valid-count (box): min={float(np.nanmin(vcount))} "
          f"5th={np.percentile(vc,5):.1f} 25th={np.percentile(vc,25):.1f} "
          f"50th={np.percentile(vc,50):.1f} 75th={np.percentile(vc,75):.1f} "
          f"max={float(np.nanmax(vcount))}")
    vc_bmc = vcount[bmc_mask & ~np.isnan(vcount)]
    print(f"Valid-count (inside BMC): min={float(np.nanmin(vc_bmc))} "
          f"median={np.percentile(vc_bmc,50):.1f} max={float(np.nanmax(vc_bmc))}")
    below3 = int((vc < 3).sum())
    below3_bmc = int((vc_bmc < 3).sum())
    print(f"Pixels below 3 valid obs: box={below3} ({100*below3/vc.size:.2f}%), "
          f"BMC={below3_bmc} ({100*below3_bmc/vc_bmc.size:.2f}%)")

    # ---- Valid-obs medians: park vs built-up windows ----
    for label, lon, lat in [("built_up", config.LON_BUILDUP, config.LAT_BUILDUP),
                            ("park", config.LON_PARK, config.LAT_PARK)]:
        r, c = lonlat_to_rowcol(lon, lat, tf)
        h = w = 64
        r0, r1 = max(0, r - h), min(lwir.shape[0], r + h)
        c0, c1 = max(0, c - h), min(lwir.shape[1], c + h)
        win = vcount[r0:r1, c0:c1]
        win = win[~np.isnan(win)]
        print(f"Valid-obs median {label}: {float(np.median(win)):.1f} "
              f"(n={win.size}, window rows {r0}:{r1} cols {c0}:{c1})")

    # ---- Quicklooks ----
    # Extent in EPSG:32643 meters (left, right, bottom, top), origin="upper".
    H, W = lwir.shape
    extent = (tf.c, tf.c + tf.a * W, tf.f + tf.e * H, tf.f)
    bmc32643 = gpd.read_file(config.BMC_GEOJSON).dissolve().to_crs(config.CRS_METRIC)
    vcount_min = float(np.nanmin(vcount))
    vcount_max = float(np.nanmax(vcount))
    quicklook("lst_composite", lst, 15, 50, "hot", "LST composite", extent=extent,
              bmc4326=bmc32643)
    quicklook("ndvi", ndvi, -1, 1, "RdYlGn", "NDVI", extent=extent,
              bmc4326=bmc32643)
    quicklook("ndbi", ndbi, -1, 1, "RdYlBu_r", "NDBI", extent=extent,
              bmc4326=bmc32643)
    quicklook("valid_count", vcount, vcount_min, vcount_max, "YlGn",
              "Valid observation count", extent=extent, bmc4326=bmc32643)
    print(f"Valid count colorbar range: {vcount_min} to {vcount_max}")
    print("Quicklook PNGs written to logs/")


if __name__ == "__main__":
    main()
