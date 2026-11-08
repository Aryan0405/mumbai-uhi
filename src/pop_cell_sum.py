"""Phase 3A item 4: Population SUM per 500 m cell over BMC land.

Reads cropped WorldPop raster (data/population/worldpop_box_crop.tif), which is
in EPSG:4326. Projects WorldPop pixel centres from EPSG:4326 to EPSG:32643,
assigns each pixel to a 500 m cell via src/aggregate.assign_cell, and SUMs per
cell via src/aggregate.sum_per_cell.

Gate A: inside-BMC total (centre-point rule, same as src/crop_population.py)
must equal 13,661,494 within 1.
Gate B: sum over 500 m cells equals inside-BMC total within 1 percent.
Reports: cells with population above 0, max cell population, top-10 cell share.
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
from aggregate import assign_cell, sum_per_cell

RAW = config.RAW_WORLDPOP_TIF
CROP = os.path.join(config.DIR_POPULATION, "worldpop_box_crop.tif")
OUT_DIR = os.path.join(config.DIR_DATA, "population")


def main():
    with rasterio.open(CROP) as src:
        arr = src.read(1).astype(np.float64)
        nodata = src.nodata
        crop_transform = src.transform
        height, width = src.shape

    # Dissolved BMC polygon, rasterized onto the crop grid (centre-point rule),
    # same method as src/crop_population.py.
    bmc = gpd.read_file(config.BMC_GEOJSON).dissolve().to_crs(config.CRS_LONLAT)
    bmc_mask = rio_rasterize(
        [shp_mapping(g) for g in bmc.geometry],
        out_shape=(height, width),
        transform=crop_transform,
        fill=0,
        default_value=1,
        dtype="uint8",
    ).astype(bool)

    valid = arr[arr != nodata] if nodata is not None else arr
    valid = valid[np.isfinite(valid)]
    total_box = float(valid.sum())

    inside = float(arr[bmc_mask & (arr != nodata)].sum()) if nodata is not None \
        else float(arr[bmc_mask].sum())
    outside = total_box - inside

    in_range = config.POP_INSIDE_BMC_MIN_M <= inside <= config.POP_INSIDE_BMC_MAX_M
    gate_a = abs(inside - 13661494.0) <= 1.0

    print(f"WorldPop crop: shape={arr.shape}, nodata={nodata}")
    print(f"  valid_pixels={valid.size}, sum_box={total_box:.2f}")
    print(f"  sum_inside_BMC={inside:.2f}")
    print(f"  sum_outside_BMC_within_box={outside:.2f}")
    print(f"  Gate A (inside BMC 12.0M-14.5M): {'PASS' if in_range else 'FAIL'} "
          f"(inside={inside:.2f})")
    print(f"  Gate A exact (inside == 13,661,494 within 1): {'PASS' if gate_a else 'FAIL'} "
          f"(diff={abs(inside - 13661494.0):.2f})")
    print("  Population is 2020 data; imagery is 2024-2026 (year mismatch).")

    # Grid anchor from the 30 m composite (EPSG:32643), NOT the WorldPop crop
    # (which is EPSG:4326 degrees).
    with rasterio.open(os.path.join(config.DIR_COMPOSITES, "lwir11.tif")) as src:
        ct = src.transform
        minx = ct.c
        maxy = ct.f
        maxx = ct.c + src.width * ct.a
        miny = ct.f + src.height * ct.e
    n_cols = int(np.ceil((maxx - minx) / 500.0))
    n_rows = int(np.ceil((maxy - miny) / 500.0))

    # Project WorldPop pixel centres from EPSG:4326 to EPSG:32643.
    cols = np.arange(width)
    rows = np.arange(height)
    xx, yy = np.meshgrid(cols, rows)
    xs = crop_transform.c + (xx + 0.5) * crop_transform.a
    ys = crop_transform.f + (yy + 0.5) * crop_transform.e  # e is negative
    proj_xs, proj_ys = warp_transform(
        config.CRS_LONLAT, config.CRS_METRIC, xs.ravel(), ys.ravel())
    proj_xs = np.asarray(proj_xs, dtype=float)
    proj_ys = np.asarray(proj_ys, dtype=float)

    # Assign each pixel to a 500 m cell.
    cell_rows = np.floor((maxy - proj_ys) / 500.0).astype(int)
    cell_cols = np.floor((proj_xs - minx) / 500.0).astype(int)
    cell_rows = np.clip(cell_rows, 0, n_rows - 1)
    cell_cols = np.clip(cell_cols, 0, n_cols - 1)

    # SUM population per cell (only valid, finite pixels inside BMC).
    valid_mask = (arr != nodata) if nodata is not None else np.ones_like(arr, dtype=bool)
    valid_mask = valid_mask & np.isfinite(arr) & bmc_mask
    flat_arr = arr.ravel()[valid_mask.ravel()]
    flat_rows = cell_rows.ravel()[valid_mask.ravel()]
    flat_cols = cell_cols.ravel()[valid_mask.ravel()]
    cell_sum = sum_per_cell(flat_arr, flat_rows, flat_cols, n_rows, n_cols)

    grid_sum = float(cell_sum.sum())
    diff = abs(grid_sum - inside)
    gate_b = diff <= 1.0

    print(f"  Grid sum over cells={grid_sum:.2f}")
    print(f"  Gate B (cell sum == inside-BMC within 1): {'PASS' if gate_b else 'FAIL'} "
          f"(diff={diff:.2f})")

    pos = cell_sum > 0
    n_pos = int(pos.sum())
    max_cell = float(cell_sum.max()) if n_pos > 0 else 0.0
    top10 = np.sort(cell_sum[pos])[::-1][:10]
    top10_sum = float(top10.sum())
    top10_share = float(top10_sum / grid_sum) if grid_sum > 0 else 0.0

    print(f"  Cells with population > 0: {n_pos}")
    print(f"  Max cell population: {max_cell:.2f}")
    print(f"  Top 10 cells sum: {top10_sum:.2f}, share of total: {100*top10_share:.2f}%")

    os.makedirs(os.path.join(config.DIR_DATA, "processed"), exist_ok=True)
    out_path = os.path.join(config.DIR_DATA, "processed", "cells_population.npy")
    np.save(out_path, cell_sum)
    print(f"  Cell population array written to {out_path}")

    log_path = os.path.join(config.DIR_LOGS, "round4c_pop_cell_sum.txt")
    lines = [
        f"WorldPop crop: shape={arr.shape}, nodata={nodata}",
        f"  valid_pixels={valid.size}, sum_box={total_box:.2f}",
        f"  sum_inside_BMC={inside:.2f}",
        f"  sum_outside_BMC_within_box={outside:.2f}",
        f"  Gate A (inside BMC 12.0M-14.5M): {'PASS' if in_range else 'FAIL'} "
        f"(inside={inside:.2f})",
        f"  Gate A exact (inside == 13,661,494 within 1): {'PASS' if gate_a else 'FAIL'} "
        f"(diff={abs(inside - 13661494.0):.2f})",
        f"  Grid sum over cells={grid_sum:.2f}",
        f"  Gate B (cell sum == inside-BMC within 1): {'PASS' if gate_b else 'FAIL'} "
        f"(diff={diff:.2f})",
        f"  Cells with population > 0: {n_pos}",
        f"  Max cell population: {max_cell:.2f}",
        f"  Top 10 cells sum: {top10_sum:.2f}, share of total: {100*top10_share:.2f}%",
    ]
    write_log(log_path, "\n".join(lines))
    print(f"  Log written to {log_path}")
    return {"gate_a": bool(gate_a), "gate_b": bool(gate_b),
            "inside_bmc": inside, "grid_sum": grid_sum, "diff": diff,
            "n_pos": int(n_pos), "max_cell": float(max_cell),
            "top10_share": float(top10_share)}


if __name__ == "__main__":
    main()
