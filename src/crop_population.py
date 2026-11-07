"""Phase 2 step 9: Crop cached WorldPop raster to the box, report sum inside and
outside the dissolved BMC polygon against the revised rule (inside BMC 12.0-14.5M).
Population is 2020 data while imagery is 2024-2026. Does not delete the raw file.
Does not resample counts.
"""
import os
import numpy as np
import rasterio
import geopandas as gpd
from rasterio.features import rasterize as rio_rasterize
from shapely.geometry import mapping as shp_mapping

import config


def main():
    raw = config.RAW_WORLDPOP_TIF
    assert os.path.exists(raw), f"raw raster not found: {raw}"
    box = config.BOX
    with rasterio.open(raw) as src:
        nodata = src.nodata
        r0, c0 = src.index(box["lon_min"], box["lat_min"])
        r1, c1 = src.index(box["lon_max"], box["lat_max"])
        row_off = min(int(r0), int(r1))
        col_off = min(int(c0), int(c1))
        height = abs(int(r1) - int(r0)) + 1
        width = abs(int(c1) - int(c0)) + 1
        from rasterio.windows import Window
        window = Window(col_off, row_off, width, height)
        arr = src.read(1, window=window)
        transform = src.window_transform(window)

    # Dissolved BMC polygon, rasterized onto the crop grid (centre-point rule).
    bmc = gpd_read_dissolved()
    bmc_mask = rio_rasterize(
        [shp_mapping(g) for g in bmc.geometry],
        out_shape=arr.shape, transform=transform,
        fill=0, default_value=1, dtype="uint8",
    ).astype(bool)

    valid = arr[arr != nodata] if nodata is not None else arr
    valid = valid[np.isfinite(valid)]
    total_box = float(valid.sum())

    inside = float(arr[bmc_mask & (arr != nodata)].sum()) if nodata is not None else float(arr[bmc_mask].sum())
    outside = total_box - inside
    in_range = config.POP_INSIDE_BMC_MIN_M <= inside <= config.POP_INSIDE_BMC_MAX_M

    print(f"WorldPop crop: shape={arr.shape}, nodata={nodata}")
    print(f"  valid_pixels={valid.size}, sum_box={total_box:.2f}")
    print(f"  sum_inside_BMC={inside:.2f}")
    print(f"  sum_outside_BMC_within_box={outside:.2f}")
    print(f"  Revised rule (inside BMC 12.0M-14.5M): {'PASS' if in_range else 'FAIL'} "
          f"(inside={inside:.2f})")
    print("  Population is 2020 data; imagery is 2024-2026 (year mismatch).")
    os.makedirs(config.DIR_POPULATION, exist_ok=True)
    out_path = os.path.join(config.DIR_POPULATION, "worldpop_box_crop.tif")
    profile = {
        "driver": "GTiff", "dtype": "float32", "width": width, "height": height,
        "count": 1, "crs": config.CRS_LONLAT, "transform": transform, "nodata": nodata,
    }
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(arr.astype("float32"), 1)
    print(f"  Cropped raster written to {out_path} (raw file kept).")
    return {"sum_box": total_box, "sum_inside_bmc": inside,
            "sum_outside_bmc": outside, "rule_pass": bool(in_range)}


def gpd_read_dissolved():
    import geopandas as gpd
    return gpd.read_file(config.BMC_GEOJSON).dissolve()


if __name__ == "__main__":
    main()
