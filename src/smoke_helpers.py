"""Shared helpers for Phase 1 smoke test modules."""
import json
import re
from shapely.geometry import box
from pystac_client import Client

CATALOG_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "landsat-c2-l2"
WP_BASE = "https://data.worldpop.org/GIS/Population/Global_2000_2020_Constrained/2020"
PC_HOST = "https://planetarycomputer.microsoft.com"
WP_HOST = "https://data.worldpop.org"

BOX = {"lon_min": 72.77, "lat_min": 18.89, "lon_max": 72.99, "lat_max": 19.27}
LON_BUILDUP, LAT_BUILDUP = 72.85, 19.05
LON_PARK, LAT_PARK = 72.91, 19.22

WINDOWS = {
    "A_Nov2023-Mar2024": ("2023-11-01", "2024-03-31"),
    "A_Nov2024-Mar2025": ("2024-11-01", "2025-03-31"),
    "A_Nov2025-Mar2026": ("2025-11-01", "2026-03-31"),
    "B_Mar-May2024": ("2024-03-01", "2024-05-31"),
    "B_Mar-May2025": ("2025-03-01", "2025-05-31"),
    "B_Mar-May2026": ("2026-03-01", "2026-05-31"),
}

LANDSAT_89_PLATFORMS = {"landsat-8", "landsat-9"}


def banner(msg):
    print("\n" + "=" * 70)
    print(msg)
    print("=" * 70)


def landsat_geom():
    return box(BOX["lon_min"], BOX["lat_min"], BOX["lon_max"], BOX["lat_max"])


def search_landsat(start, end, platforms=None):
    catalog = Client.open(CATALOG_URL)
    query = {"eo:cloud_cover": {"lt": 10}}
    if platforms:
        query["platform"] = {"in": list(platforms)}
    search = catalog.search(
        collections=[COLLECTION],
        intersects=landsat_geom(),
        datetime=f"{start}/{end}",
        query=query,
        limit=None,
    )
    return list(search.item_collection())


def wrs(item):
    p = item.properties.get("landsat:wrs_path")
    r = item.properties.get("landsat:wrs_row")
    return p, r


def band_fragment(item, asset_name):
    asset = item.assets.get(asset_name)
    if asset is None:
        return None
    return asset.extra_fields.get("raster:bands")


def qa_asset_key(item):
    for k in ("QA_PIXEL", "qa_pixel"):
        if k in item.assets:
            return k
    return None


def qa_bitfield_fragment(item):
    key = qa_asset_key(item)
    if key is None:
        return None
    ef = item.assets[key].extra_fields
    for key2 in ("classification:bitfields", "bitfields"):
        if key2 in ef:
            return key2, ef[key2]
    return "extra_fields", ef


def scene_contains_points(item, lon1, lat1, lon2, lat2):
    b = item.bbox
    if b is None:
        return False
    minx, miny, maxx, maxy = b
    return (minx <= lon1 <= maxx and miny <= lat1 <= maxy
            and minx <= lon2 <= maxx and miny <= lat2 <= maxy)


def find_scene_for_points(all_items, lon1, lat1, lon2, lat2):
    for items in all_items.values():
        for it in items:
            if scene_contains_points(it, lon1, lat1, lon2, lat2):
                return it
    return None


def unique_scenes(all_items):
    seen = {}
    for items in all_items.values():
        for it in items:
            seen.setdefault(it.id, it)
    return seen


def filter_platforms(items, platforms):
    return [it for it in items
            if it.properties.get("platform") in platforms]


def wp_discover():
    """Return (resolved_url, content_length) for India 2020 constrained TIF."""
    import requests
    r = requests.get(WP_BASE + "/", timeout=60)
    subfolders = re.findall(r'href="([^"/]+)/"', r.text)
    sub = None
    for cand in subfolders:
        if cand.lower() in ("maxar_v1", "bsgm"):
            sub = cand
            break
    if sub is None:
        raise RuntimeError("No maxar_v1/BSGM subfolder under 2020/")
    r2 = requests.get(f"{WP_BASE}/{sub}/", timeout=60)
    folders2 = re.findall(r'href="([^"/]+)/"', r2.text)
    if "IND" not in folders2:
        raise RuntimeError("No IND folder")
    r3 = requests.get(f"{WP_BASE}/{sub}/IND/", timeout=60)
    tifs = re.findall(r'href="(ind_ppp_2020_constrained\.tif)"', r3.text)
    if not tifs:
        raise RuntimeError("ind_ppp_2020_constrained.tif not found")
    resolved_url = f"{WP_BASE}/{sub}/IND/{tifs[0]}"
    hr = requests.head(resolved_url, timeout=30, allow_redirects=True)
    return resolved_url, int(hr.headers.get("Content-Length", 0) or 0), hr.status_code
