"""Central configuration for mumbai-uhi Phase 2.
All constants (box, CRS, window dates, thresholds, paths) live here.
Every pipeline script imports from this module.
"""
from datetime import date

# Study box: lon/lat in degrees (EPSG:4326). Metric CRS EPSG:32643 (Mumbai UTM zone 43N).
BOX = {"lon_min": 72.77, "lat_min": 18.89, "lon_max": 72.99, "lat_max": 19.27}
CRS_LONLAT = "EPSG:4326"
CRS_METRIC = "EPSG:32643"

# Season: Window B only, Mar to May 2024/2025/2026. Landsat 8 and 9 only.
WINDOW_B = {
    2024: ("2024-03-01", "2024-05-31"),
    2025: ("2025-03-01", "2025-05-31"),
    2026: ("2026-03-01", "2026-05-31"),
}
# Phase 1 analysis windows (lon/lat degrees).
LON_BUILDUP, LAT_BUILDUP = 72.85, 19.05
LON_PARK, LAT_PARK = 72.91, 19.22
PLATFORMS = {"landsat-8", "landsat-9"}
CLOUD_MAX = 10.0  # percent

# Collection and assets (verified against live STAC metadata in Phase 1).
COLLECTION = "landsat-c2-l2"
ASSETS = ["lwir11", "red", "nir08", "swir16", "green", "qa_pixel"]

# QA_PIXEL bit offsets (from live classification:bitfields metadata).
QA_BIT_FILL = 0
QA_BIT_DIL_CLOUD = 1
QA_BIT_CIRRUS = 2
QA_BIT_CLOUD = 3
QA_BIT_SHADOW = 4
QA_MASK_BITS = [QA_BIT_DIL_CLOUD, QA_BIT_CIRRUS, QA_BIT_CLOUD, QA_BIT_SHADOW]

# LST sanity rule (provisional, Phase 2 reports only).
LST_PERCENTILES = (0.1, 99.9)
LST_HOT_THRESHOLD_C = 50.0

# Population rule (REVISED AFTER INSPECTION, see FEASIBILITY.md).
POP_INSIDE_BMC_MIN_M = 12.0e6
POP_INSIDE_BMC_MAX_M = 14.5e6

# Paths.
DIR_DATA = "data"
DIR_COMPOSITES = "data/composites"
DIR_POPULATION = "data/population"
DIR_POPULATION_RAW = "data/population/raw"
RAW_WORLDPOP_TIF = "data/population/raw/ind_ppp_2020_constrained.tif"
DIR_LOGS = "logs"
DIR_BOUNDARY = "data/boundary"
BMC_GEOJSON = "data/boundary/BMC_Wards.geojson"
CATALOG_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
