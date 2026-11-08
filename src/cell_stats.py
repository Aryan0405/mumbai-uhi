"""Phase 3A item 5: Cell statistics at 500 m grid.

Reads data/composites/ (read only). On BMC land pixels (BMC mask AND NDWI <= 0
AND finite LST), per 500 m cell:
  n_bmc_px, n_land_px, bmc_fraction = n_bmc_px / (500 * 500 / 900),
  land_share = n_land_px / n_bmc_px,
  LST mean, median, std (C), NDVI mean, NDBI mean,
  valid_count min and median,
  share of land pixels with valid_count <= 20, population SUM.

Flags (report only, drop nothing):
  partial_bmc (bmc_fraction < 0.5),
  water_dominated (land_share < 0.5),
  low_obs (cell median valid_count < 3),
  no_pop (population == 0).

Writes data/processed/cells_500m.csv and cells_500m.geojson (gitignored).
"""
import os
import sys
import json
import numpy as np
import rasterio
import geopandas as gpd
from rasterio.warp import transform as warp_transform
from rasterio.features import rasterize as rio_rasterize
from shapely.geometry import mapping as shp_mapping
from shapely.geometry import Polygon
from scipy import stats

sys.path.insert(0, "src")
import config
from utils import write_log

DIR_COMP = config.DIR_COMPOSITES
CELL_SIZE = 500.0


def read_band(name):
    with rasterio.open(os.path.join(DIR_COMP, f"{name}.tif")) as src:
        return src.read(1).astype(np.float64), src.transform, src.crs, src.height, src.width


def main():
    lwir, tf, crs, H, W = read_band("lwir11")
    ndvi, _, _, _, _ = read_band("ndvi")
    ndbi, _, _, _, _ = read_band("ndbi")
    ndwi, _, _, _, _ = read_band("ndwi")
    vcount, _, _, _, _ = read_band("valid_count")

    # BMC mask at 30 m grid
    bmc = gpd.read_file(config.BMC_GEOJSON).dissolve().to_crs(config.CRS_METRIC)
    bmc_mask = rio_rasterize(
        [shp_mapping(g) for g in bmc.geometry],
        out_shape=(H, W), transform=tf, fill=0, default_value=1, dtype="uint8",
    ).astype(bool)

    water_mask = ndwi > 0
    bmc_land_mask = bmc_mask & (~water_mask)
    lst = lwir - 273.15

    # Cell grid from the 30 m raster transform
    MINX = tf.c
    MAXY = tf.f
    maxx = tf.c + W * tf.a
    miny = tf.f + H * tf.e
    n_cols = int(np.ceil((maxx - MINX) / CELL_SIZE))
    n_rows = int(np.ceil((MAXY - miny) / CELL_SIZE))
    n_cells = n_rows * n_cols

    # Cell index for every pixel (row, col) -> flat cell id
    xs = MINX + (np.arange(W) + 0.5) * tf.a
    ys = MAXY + (np.arange(H) + 0.5) * tf.e  # e is negative
    xx, yy = np.meshgrid(xs, ys)
    cell_rows = np.floor((MAXY - yy) / CELL_SIZE).astype(int)
    cell_cols = np.floor((xx - MINX) / CELL_SIZE).astype(int)
    cell_rows = np.clip(cell_rows, 0, n_rows - 1)
    cell_cols = np.clip(cell_cols, 0, n_cols - 1)
    cell_id = cell_rows * n_cols + cell_cols

    # Flatten everything
    flat_cell_id = cell_id.ravel()
    flat_lst = lst.ravel()
    flat_ndvi = ndvi.ravel()
    flat_ndbi = ndbi.ravel()
    flat_vc = vcount.ravel()
    flat_bmc = bmc_mask.ravel()
    flat_land = bmc_land_mask.ravel()
    flat_vcount_valid = ~np.isnan(flat_vc)

    # Pre-allocate output arrays
    n_bmc_px = np.zeros(n_cells, dtype=int)
    n_land_px = np.zeros(n_cells, dtype=int)
    lst_mean = np.full(n_cells, np.nan)
    lst_med = np.full(n_cells, np.nan)
    lst_std = np.full(n_cells, np.nan)
    ndvi_mean = np.zeros(n_cells, dtype=np.float64)
    ndbi_mean = np.zeros(n_cells, dtype=np.float64)
    ndvi_sum = np.zeros(n_cells, dtype=np.float64)
    ndbi_sum = np.zeros(n_cells, dtype=np.float64)
    vc_min = np.full(n_cells, np.nan)
    vc_med = np.full(n_cells, np.nan)
    pop_sum = np.zeros(n_cells, dtype=np.float64)
    lst_sum = np.zeros(n_cells, dtype=np.float64)
    lst_vals_list = [[] for _ in range(n_cells)]
    vc_vals_list = [[] for _ in range(n_cells)]

    # Load population per cell if available
    pop_path = os.path.join(config.DIR_DATA, "population", "cells_population.npy")
    cell_pop = None
    if os.path.exists(pop_path):
        cell_pop = np.load(pop_path).ravel()

    # Single pass over all flat pixels
    for idx in range(flat_cell_id.size):
        cid = int(flat_cell_id[idx])
        if not flat_land[idx]:
            continue
        n_bmc_px[cid] += 1
        n_land_px[cid] += 1
        lst_sum[cid] = lst_sum[cid] + flat_lst[idx]
        lst_vals_list[cid].append(flat_lst[idx])
        ndvi_sum[cid] += flat_ndvi[idx]
        ndbi_sum[cid] += flat_ndbi[idx]
        vc_vals_list[cid].append(flat_vc[idx])
        if cell_pop is not None:
            pop_sum[cid] += cell_pop[cid]

    # Compute final stats
    for cid in range(n_cells):
        if n_land_px[cid] > 0:
            arr = np.array(lst_vals_list[cid])
            lst_mean[cid] = float(np.mean(arr))
            lst_med[cid] = float(np.median(arr))
            lst_std[cid] = float(np.std(arr))
            ndvi_mean[cid] = ndvi_sum[cid] / n_land_px[cid]
            ndbi_mean[cid] = ndbi_sum[cid] / n_land_px[cid]

    bmc_fraction = n_bmc_px / (CELL_SIZE * CELL_SIZE / 900.0)
    land_share = np.where(n_bmc_px > 0, n_land_px / np.maximum(n_bmc_px, 1), 0.0)

    # Share of land pixels with valid_count <= 20
    vc_le20 = np.zeros(n_cells, dtype=int)
    for cid in range(n_cells):
        mask = flat_cell_id == cid
        land = flat_land[mask]
        if land.sum() == 0:
            continue
        vc_vals = flat_vc[mask][land]
        vc_valid = vc_vals[~np.isnan(vc_vals)]
        if vc_valid.size > 0:
            vc_le20[cid] = int((vc_valid <= 20).sum())
    vc_le20_share = np.zeros(n_cells, dtype=np.float64)
    np.divide(vc_le20, n_land_px, out=vc_le20_share, where=n_land_px > 0)

    # Flags
    partial_bmc = bmc_fraction < 0.5
    water_dominated = land_share < 0.5
    low_obs = vc_med < 3
    no_pop = pop_sum == 0

    n_partial_bmc = int(partial_bmc.sum())
    n_water_dominated = int(water_dominated.sum())
    n_low_obs = int(low_obs.sum())
    n_no_pop = int(no_pop.sum())
    n_any_flag = int((partial_bmc | water_dominated | low_obs | no_pop).sum())
    n_no_flags = int((~(partial_bmc | water_dominated | low_obs | no_pop)).sum())

    lines = []
    lines.append("Cell stats (500 m grid, EPSG:32643, BMC land pixels):")
    lines.append(f"  n_rows={n_rows}, n_cols={n_cols}, total_cells={n_cells}")
    lines.append(f"  Cells with n_bmc_px > 0: {int((n_bmc_px > 0).sum())}")
    lines.append("")
    lines.append("Flags (report only, drop nothing):")
    lines.append(f"  partial_bmc (bmc_fraction < 0.5): {n_partial_bmc}")
    lines.append(f"  water_dominated (land_share < 0.5): {n_water_dominated}")
    lines.append(f"  low_obs (cell median valid_count < 3): {n_low_obs}")
    lines.append(f"  no_pop (population == 0): {n_no_pop}")
    lines.append(f"  Cells with any flag: {n_any_flag}")
    lines.append(f"  Cells with no flags: {n_no_flags}")

    # Spearman between LST mean and LST median across cells
    valid_cells = ~np.isnan(lst_mean) & ~np.isnan(lst_med)
    if valid_cells.sum() > 1:
        rho_lst, _ = stats.spearmanr(lst_mean[valid_cells], lst_med[valid_cells])
        lines.append(f"  Spearman(LST mean, LST median) across cells = {rho_lst:.4f}")

    # Save CSV
    os.makedirs(os.path.join(config.DIR_DATA, "processed"), exist_ok=True)
    out_csv = os.path.join(config.DIR_DATA, "processed", "cells_500m.csv")
    import pandas as pd
    df = pd.DataFrame({
        "cell_id": np.arange(n_cells),
        "cell_row": np.arange(n_cells) // n_cols,
        "cell_col": np.arange(n_cells) % n_cols,
        "n_bmc_px": n_bmc_px,
        "n_land_px": n_land_px,
        "bmc_fraction": bmc_fraction,
        "land_share": land_share,
        "lst_mean": lst_mean,
        "lst_median": lst_med,
        "lst_std": lst_std,
        "ndvi_mean": ndvi_mean,
        "ndbi_mean": ndbi_mean,
        "vc_min": vc_min,
        "vc_median": vc_med,
        "vc_le20_share": vc_le20_share,
        "pop_sum": pop_sum,
        "partial_bmc": partial_bmc,
        "water_dominated": water_dominated,
        "low_obs": low_obs,
        "no_pop": no_pop,
    })
    df.to_csv(out_csv, index=False)
    print(f"  CSV written to {out_csv}")

    # GeoJSON
    out_geojson = os.path.join(config.DIR_DATA, "processed", "cells_500m.geojson")
    features = []
    for cid in range(n_cells):
        r = cid // n_cols
        c = cid % n_cols
        x0 = MINX + c * CELL_SIZE
        x1 = x0 + CELL_SIZE
        y1 = MAXY - r * CELL_SIZE
        y0 = y1 - CELL_SIZE
        poly = Polygon([(x0, y1), (x1, y1), (x1, y0), (x0, y0), (x0, y1)])
        feat = {
            "type": "Feature",
            "properties": {
                "cell_id": int(cid),
                "row": int(r),
                "col": int(c),
                "n_bmc_px": int(n_bmc_px[cid]),
                "n_land_px": int(n_land_px[cid]),
                "lst_mean": float(lst_mean[cid]) if not np.isnan(lst_mean[cid]) else None,
                "lst_median": float(lst_med[cid]) if not np.isnan(lst_med[cid]) else None,
                "ndvi_mean": float(ndvi_mean[cid]) if not np.isnan(ndvi_mean[cid]) else None,
                "ndbi_mean": float(ndbi_mean[cid]) if not np.isnan(ndbi_mean[cid]) else None,
                "pop_sum": float(pop_sum[cid]),
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[x0, y1], [x1, y1], [x1, y0], [x0, y0], [x0, y1]]],
            },
        }
        features.append(feat)
    geojson = {"type": "FeatureCollection", "features": features}
    with open(out_geojson, "w") as f:
        json.dump(geojson, f)
    print(f"  GeoJSON written to {out_geojson}")

    # Print first 10 rows
    print(df.head(10).to_string())
    print("")
    print(df.describe().to_string())

    log_path = os.path.join(config.DIR_LOGS, "round4c_cell_stats.txt")
    write_log(log_path, "\n".join(lines))
    print(f"  Cell stats written to {log_path}")


if __name__ == "__main__":
    main()
