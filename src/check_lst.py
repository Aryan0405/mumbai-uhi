"""Check 3: LST window reads via signed URLs with QA_PIXEL masking.
Gate: 2 scenes (Feb + Apr 2024). Also supports 6-scene season comparison.
Quicklook titles say "unmasked" where the mean includes cloud pixels.
"""
import json
import os
import sys
import numpy as np
import planetary_computer as pc
import rasterio
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from rasterio.warp import transform
from rasterio.windows import Window
from smoke_helpers import (
    LON_BUILDUP, LAT_BUILDUP, LON_PARK, LAT_PARK,
    band_fragment, qa_bitfield_fragment, qa_asset_key,
    find_scene_for_points, search_landsat, LANDSAT_89_PLATFORMS,
    filter_platforms, banner,
)

WIN = 128
HALF = WIN // 2
LOGS = "logs"


def _bit_count(qa, bit):
    return int(((qa >> bit) & 1).sum())


def _read_lwir_window(scene, lon, lat):
    signed = pc.sign(scene.assets["lwir11"].href)
    with rasterio.open(signed) as src:
        xs, ys = transform("EPSG:4326", src.crs, [lon], [lat])
        r, c = src.index(float(xs[0]), float(ys[0]))
        w = Window(int(c) - HALF, int(r) - HALF, WIN, WIN)
        data = src.read(1, window=w, boundless=True, fill_value=0)
        return data, (int(r), int(c)), src


def _read_qa_window(signed_qa, src, lon, lat):
    xs, ys = transform("EPSG:4326", src.crs, [lon], [lat])
    r, c = src.index(float(xs[0]), float(ys[0]))
    w = Window(int(c) - HALF, int(r) - HALF, WIN, WIN)
    with rasterio.open(signed_qa) as src2:
        return src2.read(1, window=w, boundless=True, fill_value=0)


def _quicklook(scene, label, bu_data, bu_qa, park_data, park_qa, scale, offset):
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle("%s | %s" % (scene.id, label), fontsize=12)
    bu_c = bu_data * scale + offset - 273.15
    bu_c = np.where(bu_data == 0, np.nan, bu_c)
    park_c = park_data * scale + offset - 273.15
    park_c = np.where(park_data == 0, np.nan, park_c)
    bu_qa_mask = (((bu_qa >> 3) & 1) == 1) | (((bu_qa >> 4) & 1) == 1)
    park_qa_mask = (((park_qa >> 3) & 1) == 1) | (((park_qa >> 4) & 1) == 1)
    panels = [
        (axes[0, 0], bu_c, "built_up LST unmasked mean (fill only masked) = %.1f C" % float(np.nanmean(bu_c)), "hot"),
        (axes[0, 1], park_c, "park LST unmasked mean (fill only masked) = %.1f C" % float(np.nanmean(park_c)), "hot"),
        (axes[1, 0], bu_qa_mask.astype("uint8"), "built_up QA cloud(bit3)|shadow(bit4) frac=%.2f" % float(bu_qa_mask.mean()), "Reds"),
        (axes[1, 1], park_qa_mask.astype("uint8"), "park QA cloud(bit3)|shadow(bit4) frac=%.2f" % float(park_qa_mask.mean()), "Reds"),
    ]
    for ax, data, title, cmap in panels:
        im = ax.imshow(data, cmap=cmap, vmin=0, vmax=1 if cmap == "Reds" else None)
        if cmap == "hot":
            im.set_clim(15, 50)
        ax.set_title(title, fontsize=9)
        plt.colorbar(im, ax=ax, fraction=0.046)
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    out = os.path.join(LOGS, "quicklook_%s_%s.png" % (label, scene.id.replace(":", "_")))
    plt.savefig(out, dpi=100)
    plt.close(fig)
    return out


def _stats(data, qa_data, scale, offset):
    valid = (data != 0)
    for b in range(5):
        valid = valid & (((qa_data >> b) & 1) == 0)
    vfrac = float(valid.mean())
    vals = data[valid].astype("float64")
    if vals.size == 0:
        return None, vfrac
    celsius = vals * scale + offset - 273.15
    return {
        "mean": float(celsius.mean()),
        "min": float(celsius.min()),
        "max": float(celsius.max()),
        "valid_count": int(vals.size),
        "valid_fraction": vfrac,
    }, vfrac


def run_season(sname, start, end):
    items = filter_platforms(search_landsat(start, end, platforms=LANDSAT_89_PLATFORMS),
                             LANDSAT_89_PLATFORMS)
    scene = find_scene_for_points({sname: items}, LON_BUILDUP, LAT_BUILDUP,
                                  LON_PARK, LAT_PARK)
    if scene is None:
        print(f"{sname}: no scene found containing both points; skipping")
        return None, None
    print(f"\n--- Season scene: {scene.id} ({sname}) ---")
    lwir_frag = band_fragment(scene, "lwir11")
    red_frag = band_fragment(scene, "red")
    print(f"lwir11 raster:bands: {json.dumps(lwir_frag)}")
    print(f"red raster:bands: {json.dumps(red_frag)}")
    qa_frag = qa_bitfield_fragment(scene)
    print(f"QA_PIXEL bitfield fragment: present={qa_frag is not None}")
    qa_key = qa_asset_key(scene)
    print(f"QA asset key: {qa_key}")
    signed_lwir = pc.sign(scene.assets["lwir11"].href)
    signed_qa = pc.sign(scene.assets[qa_key].href)
    scale = lwir_frag[0]["scale"] if lwir_frag else 0.00341802
    offset = lwir_frag[0]["offset"] if lwir_frag else 149.0
    season_result = {}
    for point_label, lon, lat in [("built_up", LON_BUILDUP, LAT_BUILDUP),
                                  ("park", LON_PARK, LAT_PARK)]:
        data, center, src = _read_lwir_window(scene, lon, lat)
        qa_data = _read_qa_window(signed_qa, src, lon, lat)
        raw_nnz = int(np.count_nonzero(data))
        print(f"  {point_label}: center={center}, "
              f"raw_min={float(np.min(data)):.2f}, "
              f"raw_max={float(np.max(data)):.2f}, raw_nnz={raw_nnz}")
        bit_counts = {b: _bit_count(qa_data, b) for b in range(5)}
        print(f"  QA bit masks (fill=0,dil_cloud=1,cirrus=2,cloud=3,shadow=4): {bit_counts}")
        stats, vfrac = _stats(data, qa_data, scale, offset)
        if stats is None:
            print(f"  {point_label}: NO VALID PIXELS after masking")
            season_result[point_label] = None
            continue
        print(f"  {point_label}: valid_fraction={vfrac:.3f}, valid_count={stats['valid_count']}")
        print(f"  {point_label} LST C (masked): min={stats['min']:.2f} "
              f"max={stats['max']:.2f} mean={stats['mean']:.2f}")
        if not (15 <= stats["mean"] <= 50):
            print(f"  REQUIRED FAILED: mean LST {stats['mean']:.2f} outside 15-50 C")
        season_result[point_label] = stats
    bu_data, bu_center, src_bu = _read_lwir_window(scene, LON_BUILDUP, LAT_BUILDUP)
    bu_qa = _read_qa_window(signed_qa, src_bu, LON_BUILDUP, LAT_BUILDUP)
    park_data, park_center, src_park = _read_lwir_window(scene, LON_PARK, LAT_PARK)
    park_qa = _read_qa_window(signed_qa, src_park, LON_PARK, LAT_PARK)
    png = _quicklook(scene, sname, bu_data, bu_qa, park_data, park_qa, scale, offset)
    print(f"  quicklook saved: {png}")
    return season_result, scene


def run():
    banner("3. LST WINDOW READS (signed URLs)")
    results = {}
    season_scenes = {
        "Feb_2024": ("2024-02-01", "2024-02-29"),
        "Apr_2024": ("2024-04-20", "2024-04-30"),
    }
    for sname, (s, e) in season_scenes.items():
        res, _ = run_season(sname, s, e)
        results[sname] = res if res else {}
    print("\n--- Cross-season comparison ---")
    ok = True
    for sname, res in results.items():
        bu = res.get("built_up")
        pk = res.get("park")
        if bu and pk:
            lower = pk["mean"] < bu["mean"]
            print(f"{sname}: park mean {pk['mean']:.2f} C vs built-up mean {bu['mean']:.2f} C -> park lower: {lower}")
            if not lower:
                print("  REQUIRED FAILED: park mean LST is NOT lower than built-up")
                ok = False
        else:
            print(f"{sname}: missing data for comparison")
            ok = False
    print(f"\nREQUIRED {'PASSED' if ok else 'FAILED'}: LST stats for all season scenes")
    return results


def run_six_scenes():
    banner("3b. SIX-SCENE LST COMPARISON (Window B season sample)")
    SEASON_WINDOWS = [
        ("cool_2023_Nov-Dec", "2023-11-01", "2023-12-15"),
        ("cool_2024_Jan-Feb", "2024-01-01", "2024-02-15"),
        ("cool_2025_Dec-2026_Jan", "2025-12-01", "2026-01-15"),
        ("hot_2024_Mar-Apr", "2024-03-01", "2024-04-15"),
        ("hot_2025_Mar-Apr", "2025-03-01", "2025-04-15"),
        ("hot_2026_Mar-Apr", "2026-03-01", "2026-04-15"),
    ]
    results = {}
    for label, s, e in SEASON_WINDOWS:
        print(f"\n=== {label} [{s} to {e}] ===")
        res, scene = run_season(label, s, e)
        results[label] = res if res else None
    print("\n=== SIX-SCENE SUMMARY ===")
    ok = True
    for label, res in results.items():
        if not res:
            print(f"{label}: no data")
            continue
        bu = res["built_up"]; pk = res["park"]
        gap = pk["mean"] - bu["mean"]
        print(f"{label}: built_up={bu['mean']:.1f} C (vf={bu['valid_fraction']:.2f}) "
              f"park={pk['mean']:.1f} C (vf={pk['valid_fraction']:.2f}) gap={gap:.1f} C")
        if gap >= 0:
            ok = False
    print(f"\nREQUIRED {'PASSED' if ok else 'FAILED'}: park lower than built-up in all six scenes")
    return results


if __name__ == "__main__":
    run()
    run_six_scenes()
    sys.exit(0)
