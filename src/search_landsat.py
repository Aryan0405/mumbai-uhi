"""Phase 2 step 1: Search landsat-c2-l2 for Window B (Mar-May 2024/2025/2026),
landsat-8 and landsat-9 only, cloud < 10%. Report unique scene count, unique
acquisition dates, and scenes per month per year.
"""
import json
from collections import Counter, defaultdict
from datetime import datetime

from pystac_client import Client
from shapely.geometry import box

import config

SEARCH_BOX = box(config.BOX["lon_min"], config.BOX["lat_min"],
                 config.BOX["lon_max"], config.BOX["lat_max"])


def search_window_b():
    catalog = Client.open(config.CATALOG_URL)
    all_items = []
    per_year_month = defaultdict(int)
    for year, (start, end) in config.WINDOW_B.items():
        search = catalog.search(
            collections=[config.COLLECTION],
            intersects=SEARCH_BOX,
            datetime=f"{start}/{end}",
            query={
                "eo:cloud_cover": {"lt": config.CLOUD_MAX},
                "platform": {"in": list(config.PLATFORMS)},
            },
            limit=None,
        )
        items = list(search.item_collection())
        print(f"Window B {year} [{start} to {end}]: {len(items)} scenes")
        for it in items:
            all_items.append(it)
            dt = datetime.strptime(it.properties["datetime"][:10], "%Y-%m-%d")
            per_year_month[(year, dt.month)] += 1

    unique = {}
    for it in all_items:
        unique.setdefault(it.id, it)
    print(f"\nTotal scene entries across Window B: {len(all_items)}")
    print(f"Unique scene IDs: {len(unique)}")

    dates = sorted({it.properties["datetime"][:10] for it in unique.values()})
    print(f"Unique acquisition dates: {len(dates)}")

    print("\nScenes per month per year:")
    for year in sorted(config.WINDOW_B):
        for month in (3, 4, 5):
            print(f"  {year}-{month:02d}: {per_year_month.get((year, month), 0)}")

    # WRS-2 tiles
    tiles = set()
    for it in unique.values():
        p = it.properties.get("landsat:wrs_path")
        r = it.properties.get("landsat:wrs_row")
        if p is not None and r is not None:
            tiles.add((p, r))
    print(f"Distinct WRS-2 (path,row) tiles: {sorted(tiles)}")
    print(f"Box spans more than one tile: {len(tiles) > 1}")

    return unique


if __name__ == "__main__":
    search_window_b()
