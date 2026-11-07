"""Check 2: Landsat C2 L2 scene search over Mumbai box, cloud < 10%, L8+L9."""
from smoke_helpers import (
    search_landsat, wrs, WINDOWS, LANDSAT_89_PLATFORMS,
    unique_scenes, filter_platforms, banner,
)


def run():
    banner("2. LANDSAT SCENE SEARCH (cloud < 10%%, landsat-8 and landsat-9)")
    all_items = {}
    for wname, (s, e) in WINDOWS.items():
        try:
            items = search_landsat(s, e, platforms=LANDSAT_89_PLATFORMS)
            items = filter_platforms(items, LANDSAT_89_PLATFORMS)
            all_items[wname] = items
            print(f"Window {wname} [{s} to {e}]: {len(items)} scenes")
            for it in items:
                print(f"  id={it.id} platform={it.properties.get('platform')} "
                      f"cloud={it.properties.get('eo:cloud_cover')} "
                      f"path_row={wrs(it)}")
        except Exception as e:
            print(f"Window {wname}: ERROR {type(e).__name__}: {e}")
            all_items[wname] = []

    unique = unique_scenes(all_items)
    total_per_window = {k: len(v) for k, v in all_items.items()}
    print(f"\nUnique scene IDs (deduplicated across windows): {len(unique)}")
    print(f"Per-window counts: {total_per_window}")
    print(f"Total scene entries across all windows: {sum(total_per_window.values())}")

    paths_rows = set()
    for it in unique.values():
        p, r = wrs(it)
        if p is not None and r is not None:
            paths_rows.add((p, r))
    print(f"Distinct WRS-2 (path,row) tiles: {sorted(paths_rows)}")
    print(f"Box spans more than one tile: {len(paths_rows) > 1}")

    ok = len(unique) >= 5
    print(f"REQUIRED {'PASSED' if ok else 'FAILED'}: "
          f"{'at least' if ok else 'only'} 5 usable L8/L9 scenes total "
          f"({len(unique)} unique)")
    return {"unique": len(unique), "per_window": total_per_window,
            "tiles": sorted(paths_rows), "ok": ok}
