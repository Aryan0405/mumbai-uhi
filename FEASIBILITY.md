# FEASIBILITY.md - Phase 1 Gate Results

Run timestamp: 20261107_165144
Command: `conda run --no-capture-output -n uhi python src/smoke_test.py`
Raw log: logs/smoke_20261107_165144.log

## Summary

| Check | Result |
|-------|--------|
| 1. Network | PASS |
| 2. Landsat scene search | PASS |
| 3. LST window reads | PASS |
| 4. Population (WorldPop) | DOWNLOAD PASS, RULE FAIL |
| 5. Environment imports | PASS |

Overall gate on checks 1, 2, 3, 5: PASS.
Population check 4: download succeeded; numeric rule failed (see below). Reported honestly, not widened.

---

## Check 1 - Network

Raw output:
```
planetarycomputer.microsoft.com: HTTP 200, response_size=5087 bytes, url=https://planetarycomputer.microsoft.com
data.worldpop.org: HTTP 200, response_size=1548 bytes, url=https://data.worldpop.org
```

Result: PASS. Both hosts reachable over HTTPS with HTTP 200.

---

## Check 2 - Landsat C2 L2 scene search (cloud < 10%, landsat-8 + landsat-9 only)

Restricted to platforms landsat-8 and landsat-9. LE07 scenes excluded.

Per-window scene counts:
```
Window A_Nov2023-Mar2024: 31 scenes
Window A_Nov2024-Mar2025: 27 scenes
Window A_Nov2025-Mar2026: 29 scenes
Window B_Mar-May2024: 19 scenes
Window B_Mar-May2025: 15 scenes
Window B_Mar-May2026: 15 scenes
```

Unique scene IDs (deduplicated across windows; March appears in both Window A and Window B): 113
Total scene entries across all windows: 136

All scene IDs printed in raw log (lines 12-153).

Distinct WRS-2 (path,row) tiles: [('148', '046'), ('148', '047')]
Box spans more than one tile: True (two tiles)

REQUIRED: at least 5 usable scenes total in at least one window → PASSED (113 unique, every window well above 5).

---

## Check 3 - LST window reads via signed URLs

Two 128x128 windows per season scene, centred on:
- Dense built-up near lon 72.85, lat 19.05
- Sanjay Gandhi National Park near lon 72.91, lat 19.22

Coordinates transformed from EPSG:4326 to the raster CRS (EPSG:32643) before indexing.

Scale and offset pulled from live STAC item JSON `raster:bands` fragment:
```
lwir11 raster:bands: {"unit": "kelvin", "scale": 0.00341802, "nodata": 0, "offset": 149, ...}
red raster:bands: {"scale": 2.75e-05, "nodata": 0, "offset": -0.2, ...}
```
Confirmed: lwir11 scale=0.00341802, offset=149.0; reflectance scale=0.0000275, offset=-0.2.

QA_PIXEL bitfield fragment from live metadata (classification:bitfields):
- cloud = bit offset 3, cloud_shadow = bit offset 4. Confirmed from metadata.

Masked: fill (bit 0), dilated cloud (bit 1), cirrus (bit 2), cloud (bit 3), cloud shadow (bit 4).

### Feb 2024 scene: LC09_L2SP_148047_20240227_02_T1
```
built_up: valid_fraction=0.722, valid_count=11835
  QA bit masks {fill:0, dil_cloud:349, cirrus:0, cloud:335, shadow:3880}
  built_up LST C: min=26.88 max=43.32 mean=35.93
park: valid_fraction=0.092, valid_count=1509
  QA bit masks {fill:0, dil_cloud:1722, cirrus:88, cloud:12443, shadow:1873}
  park LST C: min=29.05 max=38.93 mean=33.84
```
Park mean (33.84 C) lower than built-up mean (35.93 C): True.
All values within 15-50 C: PASS.

### Apr 2024 scene: LC08_L2SP_148047_20240423_02_T1
```
built_up: valid_fraction=0.798, valid_count=13081
  QA bit masks {fill:0, dil_cloud:1333, cirrus:0, cloud:1151, shadow:1315}
  built_up LST C: min=30.29 max=49.53 mean=41.04
park: valid_fraction=0.976, valid_count=15998
  QA bit masks {fill:0, dil_cloud:209, cirrus:0, cloud:36, shadow:141}
  park LST C: min=33.36 max=48.52 mean=38.60
```
Park mean (38.60 C) lower than built-up mean (41.04 C): True.
All values within 15-50 C: PASS.

REQUIRED: plausible land values 15-50 C → PASS.
REQUIRED: park mean LST lower than built-up mean LST → PASS (both seasons).

---

## Check 4 - Population (WorldPop India 2020 constrained)

### Discovery
Directory listing read at `https://data.worldpop.org/GIS/Population/Global_2000_2020_Constrained/2020/`.
Subfolders: `['0_mosaicked', 'BSGM', 'maxar_v1']`. Selected: `BSGM` (first match in `maxar_v1`/`bsgm`, not guessed).
IND folder confirmed. TIF: `ind_ppp_2020_constrained.tif`.

Resolved URL: `https://data.worldpop.org/GIS/Population/Global_2000_2020_Constrained/2020/BSGM/IND/ind_ppp_2020_constrained.tif`
HEAD: HTTP 200, Content-Length=531062384 (531 MB).

### Download
Server does not support ranged reads (`/vsicurl` failed: `Range downloading not supported by this server!`).
Full file downloaded once to `data/population/raw/ind_ppp_2020_constrained.tif` (531,062,384 bytes).
**Original kept** - not deleted, per instruction to wait for user decision.
DOWNLOAD: PASS.

### Crop to study box
Cropped to box lon 72.77-72.99, lat 18.89-19.27:
```
shape=(457, 265), nodata=-99999.0
valid_pixels=48538
sum=15029088.00
min=4.86, max=560.52
```
Nodata (-99999) masked before summing. Max=560.52 people/pixel is plausible for constrained WorldPop.

### Numeric rule
Rule: cropped WorldPop sum must be between 11.0 and 14.5 million.
Result: **FAIL** - sum = 15,029,088.00, outside the range.

This was expected to fail because the study box (~973 km²) includes sea and extends beyond the BMC boundary (483.14 km²). The sum includes population outside BMC and over water-adjacent areas.

### BMC boundary polygon (inside/outside analysis)
Attempted to find and download a citable BMC boundary polygon from:
- `sanjanakrishnan/mumbai_spatial_data` (BMC_admin_wards.geojson on GitHub)
- GADM India (biogeo.ucdavis.edu, gadm41_IND_2.json)
- OpenStreetMap Overpass API
- Bharatlas/OpenCity BMC wards GeoJSON

All external hosts other than planetarycomputer.microsoft.com and data.worldpop.org were unreachable from this environment (requests timed out). **Could not download a citable BMC boundary polygon.** Cannot report WorldPop sum inside vs outside BMC boundary.

Per plan instruction: "If you cannot find a citable boundary, say so and stop." Stated here. Awaiting user decision before proceeding.

---

## Check 5 - Environment imports

All imports clean inside `uhi` conda env:
```
geopandas: OK version=1.2.0
rasterio: OK version=1.4.4
scikit-learn: OK version=1.9.1
streamlit: OK version=1.67.0
pystac_client: OK version=0.9.1
planetary_computer: OK version=1.0.0
```
REQUIRED: PASS.

---

## Files created in Phase 1 (not committed pending review)

- environment.yml (conda spec, conda-forge + pip)
- src/smoke_helpers.py, src/check_network.py, src/check_landsat.py,
  src/check_lst.py, src/check_population.py, src/check_env.py,
  src/smoke_test.py
- logs/smoke_20261107_165144.log
- data/population/raw/ind_ppp_2020_constrained.tif (531 MB, gitignored, kept)

Not committed: FEASIBILITY.md, src/, logs/, data/. Awaiting review per instructions.

---

## Phase 1 follow-up (boundary, cloud explanation, 6-scene LST, subfolders)

### Follow-up 1 - BMC boundary and WorldPop inside/outside

Boundary file: `data/boundary/BMC_Wards.geojson` (pre-existing in repo).
- CRS: EPSG:4326 (CRS84)
- Feature count: 24 (BMC wards, dissolved to one MultiPolygon)
- Dissolved BMC area (reprojected to EPSG:32643): 458.28 km²
- Study box area (EPSG:32643): 974.31 km²
- BMC ∩ box area: 458.28 km² (~100% of BMC lies inside the box)
- Share of box covered by BMC: 47.0%

Note on sources: MCGM vital statistics table gives 483.14 km²; other sources cite ~437 km² land or ~603 km² gross. The dissolved boundary (458.28 km²) falls within that range of disagreement.

WorldPop (cached raster `data/population/raw/ind_ppp_2020_constrained.tif`, NOT re-downloaded), cropped to the box, nodata (-99999) masked:
- Population inside dissolved BMC (within box): 13,661,494
- Population outside BMC (within box): 1,367,594
- Total: 15,029,088 (matches crop sum)
- Share inside BMC: 90.9%
- Share outside BMC: 9.1%

### Follow-up 2 - Cloud flag explanation (Feb scene park window)

Feb 2024 scene `LC09_L2SP_148047_20240227_02_T1` has scene-level `eo:cloud_cover` = 4.3 %, yet the park 128x128 window had bit 3 (cloud) = 12,443 of 16,384 pixels (76 %).

Explanation: scene-level cloud cover is a whole-scene average over the full Landsat scene (~185 x 180 km). A 128x128 window at 30 m covers only ~3.8 x 3.8 km. The Sanjay Gandhi National Park sub-window fell under a local cloud bank, so ~76 % of its pixels are high-confidence cloud (bit 3) even though the scene-wide average is only 4.3 %. Local window cloud cover is not bounded by the scene average. Bits 1 (dilated cloud, 1,722 px) and 4 (cloud shadow, 1,873 px) add further masked pixels, but bit 3 alone is 12,443. Park valid fraction was only 0.092 (1,509 px), consistent with heavy local cloud.

### Follow-up 3 - 6-scene LST comparison (3 cool Nov-Feb, 3 hot Mar-May)

All scenes landsat-8 or landsat-9, different dates, cloud < 10 %, each containing both points. Windows boxed in quicklook PNGs under `logs/quicklook_<label>_<scene_id>.png`.

| Season | Scene | Platform | Scene cloud % | Built-up mean C (vf) | Park mean C (vf) | Gap park-built_up C | Park lower? |
|--------|-------|----------|---------------|----------------------|------------------|---------------------|-------------|
| cool | LC09_L2SP_148047_20231209_02_T1 | L9 | 0.03 | 33.20 (1.00) | 27.76 (1.00) | -5.44 | Yes |
| cool | LC09_L2SP_148047_20240211_02_T1 | L9 | 0.00 | 35.18 (1.00) | 31.30 (1.00) | -3.88 | Yes |
| cool | LC09_L2SP_148047_20260115_02_T1 | L9 | 0.00 | 32.55 (0.998) | 28.75 (1.00) | -3.80 | Yes |
| hot | LC09_L2SP_148047_20240415_02_T1 | L9 | 0.04 | 44.27 (1.00) | 42.36 (1.00) | -1.91 | Yes |
| hot | LC08_L2SP_148047_20250410_02_T1 | L8 | 4.49 | 37.35 (0.624) | 33.84 (0.425) | -3.51 | Yes |
| hot | LC08_L2SP_148047_20260413_02_T1 | L8 | 1.03 | 40.52 (0.960) | 37.90 (1.00) | -2.62 | Yes |

Note: hot_2024 scene built-up max pixel = 53.40 C (single rooftop pixel, pre-monsoon heat); mean = 44.27 C remains in plausible range. All six scenes: park mean LST lower than built-up mean LST.

### Follow-up 4 - WorldPop subfolders under 2020/

Directory listing of `https://data.worldpop.org/GIS/Population/Global_2000_2020_Constrained/2020/`:
- `0_mosaicked` -> IND present: False
- `BSGM` -> IND present: True
- `maxar_v1` -> IND present: False

Only BSGM contains an IND folder. BSGM was used because it is the only subfolder that actually has the India file; it was not a free choice between BSGM and maxar_v1 (maxar_v1 has no IND). Listed only; no download of maxar_v1 performed.

### Follow-up 5 - environment.yml, line counts, git status

`environment.yml`:
```
name: uhi
channels:
  - conda-forge
dependencies:
  - python=3.11
  - geopandas
  - rasterio
  - scikit-learn
  - scipy
  - numpy
  - pandas
  - matplotlib
  - folium
  - pydeck
  - streamlit
  - pytest
  - requests
  - tqdm
  - stackstac
  - rioxarray
  - xarray
  - dask
  - pip:
    - pystac-client
    - planetary-computer
```

Line counts of src files:
- check_env.py: 25 lines
- check_landsat.py: 44 lines
- check_lst.py: 144 lines
- check_network.py: 21 lines
- check_population.py: 94 lines
- six_scene_lst.py: 195 lines
- smoke_helpers.py: 137 lines
- smoke_test.py: 66 lines

git status:
```
On branch main
Changes not staged for commit:
  modified:   .gitignore
Untracked files:
  FEASIBILITY.md
  environment.yml
  src/
```
Nothing committed yet (awaiting review). No push, no config changes.


## Phase 1 decisions (accepted)

Scope: Greater Mumbai. Analysis clipped to the BMC polygon
(data/boundary/BMC_Wards.geojson, dissolved, DataMeet Municipal_Spatial_Data,
CC BY 4.0, https://github.com/sanjanakrishnan/mumbai_spatial_data). Clipping happens
in Phase 3. Phase 2 keeps full-box rasters.

Season: Window B only, Mar to May 2024, Mar to May 2025, Mar to May 2026.
Landsat 8 and 9 only, scene cloud cover under 10 percent.

Population rule, REVISED AFTER INSPECTION (the original 11.0 to 14.5 million range
was a guess made before the box was understood): WorldPop sum INSIDE the BMC polygon
must be between 12.0 and 14.5 million. Reference points: Census 2011 Greater Mumbai
population 12,442,373 and MCGM mid-year 2023 estimate 13,014,390
(https://mcgm.gov.in/irj/portal/anonymous/qlCivicDemographics). Measured inside BMC:
13,661,494 (rule PASS). Outside BMC within the box: 1,367,594. Pixels assigned to the
polygon if their centre point falls within the dissolved BMC polygon (centre-point
rule, not any-touch).

LST sanity rule (provisional): report the 0.1th and 99.9th percentile and the max of
the composite, plus the count of pixels above 50 C. Report only, do not silently
loosen or tighten anything.

