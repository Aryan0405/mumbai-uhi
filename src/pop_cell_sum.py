"""Phase 3A round R2: WorldPop population summed per 500 m cell.

Reads the cropped WorldPop raster data/population/worldpop_box_crop.tif
(EPSG:4326). Reuses the inside-BMC rule from src/crop_population.py
(dissolved BMC rasterized onto the crop grid, centre-point rule).
Projects WorldPop pixel centres from EPSG:4326 to EPSG:32643, assigns cells
with src/aggregate.assign_cells (no clipping; out-of-grid centres stay
in_range False), and sums population per cell with
src/aggregate.sum_per_cell.

Gate A: inside-BMC total (centre-point rule) equals 13,661,494 within 1.
Gate B: sum over 500 m cells equals the inside-BMC total within 1 percent.
"""
import os
import sys

import numpy as np
import rasterio
from rasterio.warp import transform as warp_transform
from rasterio.features import rasterize as rio_rasterize
from shapely.geometry import mapping as shp_mapping
import geopandas as gpd

sys.path.insert(0, "src")
import config
from utils import write_log
from aggregate import assign_cells, sum_per_cell

CROP = os.path.join(config.DIR_POPULATION, "worldpop_box_crop.tif")
GRID_BAND = os.path.join(config.DIR_COMPOSITES, "lwir11.tif")
OUT_PATH = os.path.join(config.DIR_DATA, "population", "cells_population.npy")
CELL_SIZE = 500.0
INSIDE_BMC_TARGET = 13661494.0


def dissolved_bmc_mask(transform, height, width, crs):
    """Inside-BMC rule from src/crop_population.py: centre point, EPSG:4326."""
    bmc = gpd.read_file(config.BMC_GEOJSON).dissolve().to_crs(crs)
    return rio_rasterize(
        [shp_mapping(g) for g in bmc.geometry],
        out_shape=(height, width),
        transform=transform,
        fill=0,
        default_value=1,
        dtype="uint8",
    ).astype(bool)


def bmc_cell_counts(n_rows, n_cols, n_cells, minx, maxy):
    """Count of BMC 30 m pixels per 500 m cell (vectorised, no clipping)."""
    with rasterio.open(GRID_BAND) as src:
        tf = src.transform
        height, width = src.shape
    bmc = gpd.read_file(config.BMC_GEOJSON).dissolve().to_crs(config.CRS_METRIC)
    bmc_mask = rio_rasterize(
        [shp_mapping(g) for g in bmc.geometry],
        out_shape=(height, width), transform=tf,
        fill=0, default_value=1, dtype="uint8",
    ).astype(bool)
    xs = tf.c + (np.arange(width) + 0.5) * tf.a
    ys = tf.f + (np.arange(height) + 0.5) * tf.e
    xx, yy = np.meshgrid(xs, ys)
    r, c, in_range = assign_cells(xx.ravel(), yy.ravel(), minx, maxy,
                                  CELL_SIZE, n_rows, n_cols)
    flat = r * n_cols + c
    return np.bincount(flat[bmc_mask.ravel() & in_range], minlength=n_cells)


def main():
    with rasterio.open(CROP) as src:
        arr = src.read(1).astype(np.float64)
        nodata = src.nodata
        crop_transform = src.transform
        height, width = src.shape

    # Inside-BMC rule: same as src/crop_population.py (centre point, EPSG:4326).
    bmc_mask = dissolved_bmc_mask(crop_transform, height, width, config.CRS_LONLAT)
    valid = np.isfinite(arr)
    if nodata is not None:
        valid = valid & (arr != nodata)
    total_box = float(arr[valid].sum())
    inside = float(arr[bmc_mask & valid].sum())

    gate_a = abs(inside - INSIDE_BMC_TARGET) <= 1.0
    print(f"WorldPop crop: shape={arr.shape}, nodata={nodata}")
    print(f"  valid_pixels={int(valid.sum())}, sum_box={total_box:.2f}")
    print(f"  sum_inside_BMC={inside:.2f}")
    print(f"  Gate A (inside BMC == 13,661,494 within 1): {bool(gate_a)} "
          f"(diff={abs(inside - INSIDE_BMC_TARGET):.2f})")

    # Grid anchor from the 30 m composite (EPSG:32643), not the WorldPop crop.
    with rasterio.open(GRID_BAND) as src:
        ct = src.transform
        minx = ct.c
        maxy = ct.f
        maxx = ct.c + src.width * ct.a
        miny = ct.f + src.height * ct.e
    n_cols = int(np.ceil((maxx - minx) / CELL_SIZE))
    n_rows = int(np.ceil((maxy - miny) / CELL_SIZE))
    n_cells = n_rows * n_cols
    print(f"  500 m grid: n_rows={n_rows}, n_cols={n_cols}, n_cells={n_cells}")

    # Project WorldPop pixel centres EPSG:4326 -> EPSG:32643.
    cols = np.arange(width)
    rows = np.arange(height)
    xx, yy = np.meshgrid(cols, rows)
    xs = crop_transform.c + (xx + 0.5) * crop_transform.a
    ys = crop_transform.f + (yy + 0.5) * crop_transform.e
    proj_xs, proj_ys = warp_transform(config.CRS_LONLAT, config.CRS_METRIC,
                                      xs.ravel(), ys.ravel())
    proj_xs = np.asarray(proj_xs, dtype=np.float64)
    proj_ys = np.asarray(proj_ys, dtype=np.float64)

    # Assign cells (no clipping; out-of-grid centres stay in_range False).
    cell_rows, cell_cols, in_range = assign_cells(proj_xs, proj_ys, minx, maxy,
                                                  CELL_SIZE, n_rows, n_cols)
    n_centres = int(proj_xs.size)
    n_out_of_range = int((~in_range).sum())
    print(f"  WorldPop centres total={n_centres}, in_range False={n_out_of_range}")

    inside_flat = (bmc_mask & valid).ravel()
    n_inside = int(inside_flat.sum())
    n_inside_out_of_range = int((inside_flat & (~in_range)).sum())
    print(f"  inside-BMC centres total={n_inside}, "
          f"in_range False among them={n_inside_out_of_range}")

    if n_inside_out_of_range > 0:
        msg = (f"STOP: inside-BMC WorldPop centres with in_range False = "
               f"{n_inside_out_of_range} (> 0).")
        print(msg)
        raise SystemExit(msg)

    flat_ids = (cell_rows * n_cols + cell_cols)[in_range & inside_flat]
    values = arr.ravel()[in_range & inside_flat]
    cell_sums, _ = sum_per_cell(values, flat_ids, n_cells)
    cell_sum = cell_sums.reshape(n_rows, n_cols)

    grid_sum = float(cell_sum.sum())
    diff = abs(grid_sum - inside)
    gate_b = diff <= 0.01 * inside
    print(f"  Grid sum over cells={grid_sum:.2f}")
    print(f"  Gate B (cell sum == inside-BMC within 1 percent): {bool(gate_b)} "
          f"(actual diff={diff:.2f}, limit={0.01 * inside:.2f})")

    pos = cell_sum > 0
    n_pos = int(pos.sum())
    max_cell = float(cell_sum.max()) if n_pos > 0 else 0.0
    top10 = np.sort(cell_sum[pos])[::-1][:10]
    top10_sum = float(top10.sum())
    top10_share = float(top10_sum / grid_sum) if grid_sum > 0 else 0.0
    print(f"  Cells with population > 0: {n_pos}")
    print(f"  Max cell population: {max_cell:.2f}")
    print(f"  Top 10 cells sum: {top10_sum:.2f}, share of total: {100 * top10_share:.2f}%")

    # Cross-check with the BMC cell grid from cell_stats.py (R3): cells with
    # population above 0 but n_bmc_px equal to 0.
    n_bmc_per_cell = bmc_cell_counts(n_rows, n_cols, n_cells, minx, maxy)
    cross = int(((pos) & (n_bmc_per_cell.reshape(n_rows, n_cols) == 0)).sum())
    print(f"  Cells with population > 0 but n_bmc_px == 0: {cross}")

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    np.save(OUT_PATH, cell_sum)
    print(f"  Cell population array written to {OUT_PATH}")

    log_path = os.path.join(config.DIR_LOGS, "phase3a_population.txt")
    lines = [
        f"WorldPop crop: shape={arr.shape}, nodata={nodata}",
        f"  valid_pixels={int(valid.sum())}, sum_box={total_box:.2f}",
        f"  sum_inside_BMC={inside:.2f}",
        f"  Gate A (inside BMC == 13,661,494 within 1): {bool(gate_a)} "
        f"(diff={abs(inside - INSIDE_BMC_TARGET):.2f})",
        f"  500 m grid: n_rows={n_rows}, n_cols={n_cols}, n_cells={n_cells}",
        f"  WorldPop centres total={n_centres}, in_range False={n_out_of_range}",
        f"  inside-BMC centres total={n_inside}, "
        f"in_range False among them={n_inside_out_of_range}",
        f"  Grid sum over cells={grid_sum:.2f}",
        f"  Gate B (cell sum == inside-BMC within 1 percent): {bool(gate_b)} "
        f"(actual diff={diff:.2f}, limit={0.01 * inside:.2f})",
        f"  Cells with population > 0: {n_pos}",
        f"  Max cell population: {max_cell:.2f}",
        f"  Top 10 cells sum: {top10_sum:.2f}, share of total: {100 * top10_share:.2f}%",
        f"  Cells with population > 0 but n_bmc_px == 0: {cross}",
        f"  Cell population array written to {OUT_PATH}",
    ]
    write_log(log_path, "\n".join(lines))
    print(f"  Log written to {log_path}")
    return {"gate_a": bool(gate_a), "gate_b": bool(gate_b),
            "inside_bmc": inside, "grid_sum": grid_sum, "diff": diff,
            "n_out_of_range": n_out_of_range,
            "n_inside_out_of_range": n_inside_out_of_range,
            "n_pos": int(n_pos), "max_cell": float(max_cell),
            "top10_share": float(top10_share), "cross_check": int(cross)}


if __name__ == "__main__":
    main()
