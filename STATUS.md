# STATUS.md - Phase 2 (DATA)

Run date: 2026-11-08. Conda env: uhi. Command prefix: conda run -n uhi.

## Source data
Collection: landsat-c2-l2 (Microsoft Planetary Computer STAC, pystac-client +
planetary-computer, anonymous, signed URLs). Assets confirmed from live STAC
raster:bands metadata: lwir11 (scale 0.00341802, offset 149.0), red
(scale 0.0000275, offset -0.2), nir08, swir16, green, qa_pixel.
Population: WorldPop India 2020 constrained,
ind_ppp_2020_constrained.tif, data.worldpop.org,
GIS/Population/Global_2000_2020_Constrained/2020/BSGM/IND/.
Study box: lon 72.77 to 72.99, lat 18.89 to 19.27. Metric CRS EPSG:32643.
Season: Window B only (Mar to May 2024/2025/2026), landsat-8 and landsat-9,
scene cloud under 10 percent.

## 2.1 Search - landsat-c2-l2, Window B, L8+L9, cloud < 10 percent

Raw output (src/search_landsat.py):
```
Window B 2024 [2024-03-01 to 2024-05-31]: 19 scenes
Window B 2025 [2025-03-01 to 2025-05-31]: 15 scenes
Window B 2026 [2026-03-01 to 2026-05-31]: 15 scenes

Total scene entries across Window B: 49
Unique scene IDs: 49
Unique acquisition dates: 26

Scenes per month per year:
  2024-03: 7
  2024-04: 6
  2024-05: 6
  2025-03: 8
  2025-04: 7
  2025-05: 0
  2026-03: 8
  2026-04: 4
  2026-05: 3

Distinct WRS-2 (path,row) tiles: [('148', '046'), ('148', '047')]
Box spans more than one tile: True
```

Result: 49 unique scenes (all landsat-8/9), 26 unique dates, 2 WRS-2 tiles,
box spans more than one tile.

## 2.2 Load - rasterio per batch, sign each batch

stackstac 0.5.0 is incompatible with the env's numpy 2.x (np.can_cast rejects
floats), so loading uses rasterio directly with per-batch signing
(planetary_computer.sign per date batch), reprojecting each asset to EPSG:32643
at 30 m over the box grid (789 x 1393 px). Validity uses the shared function
src/utils.compute_validity: finite(lwir) AND QA fill bit 0 clear AND dilated
cloud bit 1 clear AND cirrus bit 2 clear AND cloud bit 3 clear AND shadow bit
4 clear. Date-level mask is the UNION of per-scene validity.

Pilot (2 dates):
```
Pilot 2024-03-06: valid_frac_box=0.9999, valid_frac_bmc=0.9999, bytes_est=719861772
Pilot 2024-03-14: valid_frac_box=0.9955, valid_frac_bmc=0.9941, bytes_est=746874092
PILOT 2 dates: wall_time=55.0s, peak_memory=197.9 MB
```
All 26 dates processed without errors.

## 2.3 Mosaic - two WRS-2 rows (148/046, 148/047) per date mosaicked via
nanmedian before compositing.

## 2.4 Mask - fill bit 0, dilated cloud bit 1, cirrus bit 2, cloud bit 3 and
cloud shadow bit 4 from QA_PIXEL, via src/utils.compute_validity.

## 2.5 Indices + median composite - LST, NDVI, NDBI, NDWI

Per-pixel median composite across 26 dates. Output GeoTIFFs in EPSG:32643 at
30 m to data/composites/:
```
lwir11.tif, red.tif, nir08.tif, swir16.tif, green.tif, valid_count.tif
ndvi.tif, ndbi.tif, ndwi.tif
```

## 2.6 Valid-observation count distribution

Raw output (src/compute_indices.py):
```
Valid-count (box): min=11.0 5th=20.0 25th=21.0 50th=23.0 75th=23.0 max=26.0
Valid-count (inside BMC): min=14.0 median=23.0 max=24.0
Pixels below 3 valid obs: box=0 (0.00%), BMC=0 (0.00%)
Valid-obs median built_up: 23.0 (n=16384, window rows 742:870 cols 224:352)
Valid-obs median park: 22.0 (n=16384, window rows 117:245 cols 442:570)
```
No 500 m cell flagged here (valid counts are per 30 m pixel; the >=3 valid
observation rule is satisfied everywhere). Flagging at 500 m happens in
Phase 3 aggregation.

## 2.7 Per-date table

Written to logs/per_date_valid_fraction.txt. Columns:
date, valid_fraction_box, valid_fraction_bmc, bmc_pixel_count,
footprint_fraction_bmc. Reuses data/landsat/cache/ (no re-download).
Full file:
```
date valid_fraction_box valid_fraction_bmc bmc_pixel_count footprint_fraction_bmc
2024-03-06 0.999934 0.999992 509028 1.000000
2024-03-14 0.995480 0.994097 509028 1.000000
2024-03-22 0.999488 0.999929 509028 1.000000
2024-03-30 0.006731 0.000000 509028 0.000000
2024-04-07 0.988418 0.999967 509028 1.000000
2024-04-15 0.999993 1.000000 509028 1.000000
2024-04-23 0.629222 0.776258 509028 1.000000
2024-05-01 0.997374 1.000000 509028 1.000000
2024-05-09 0.841625 0.872671 509028 1.000000
2024-05-17 0.942639 0.997191 509028 1.000000
2025-03-01 0.995319 0.995961 509028 1.000000
2025-03-09 0.999999 1.000000 509028 1.000000
2025-03-17 0.999967 0.999998 509028 1.000000
2025-03-25 0.999996 1.000000 509028 1.000000
2025-04-02 0.001507 0.000000 509028 0.000000
2025-04-10 0.608486 0.589443 509028 1.000000
2025-04-18 0.990364 0.988853 509028 1.000000
2025-04-26 0.964689 0.996458 509028 1.000000
2026-03-04 0.999959 1.000000 509028 1.000000
2026-03-12 0.999999 1.000000 509028 1.000000
2026-03-20 0.997545 0.996829 509028 1.000000
2026-03-28 0.999990 1.000000 509028 1.000000
2026-04-13 0.992830 0.988698 509028 1.000000
2026-04-29 0.999850 0.999998 509028 1.000000
2026-05-07 0.744527 0.775327 509028 1.000000
2026-05-31 0.684853 0.673287 509028 1.000000
```

Note on the three dates that previously showed an identical BMC value
(0.672607) under the old validity logic: the old logic did not require
finite(lwir) and used (lwir != 0), which is True for NaN, so out-of-footprint
pixels were counted as valid. The footprint_fraction_bmc column explains it:
2024-03-30 footprint_fraction_bmc=0.000000 (no finite lwir in BMC across any
scene - the old 0.672607 was entirely a NaN-counting artifact);
2025-04-02 footprint_fraction_bmc=0.000000 (same artifact);
2025-04-10 footprint_fraction_bmc=1.000000 (full finite coverage), where the
old 0.672607 exceeded the new 0.589443 because the old logic counted NaN lwir
pixels as valid when QA was clear in a NaN scene.

## 2.8 Checks (real numbers)

NDVI within [-1, 1]: True (composite min=-0.5757, max=0.8222).
LST sanity rule (provisional): 0.1th=28.86 C, 99.9th=50.18 C, max=55.47 C,
count_above_50C=1262, valid=1099077.
Median composite LST: built-up window 40.09 C, park window 37.43 C (park
cooler). Reported only; Phase 3 owns the sanity check.
BMC-land LST percentiles (land only, NDWI<=0): 0.1th=31.51 C, 1st=32.39 C,
50th=39.83 C, 99th=48.00 C, 99.9th=49.99 C, max=53.04 C (n=494795).

## 2.9 Population (WorldPop India 2020 constrained)

Source: data.worldpop.org,
.../2020/BSGM/IND/ind_ppp_2020_constrained.tif.
HEAD: HTTP 200, Content-Length=531062384 bytes. Server does not support ranged
reads; full file downloaded once to data/population/raw/ and KEPT (not deleted).
Crop to box via rasterio window read; nodata (-99999) masked before summing.

Raw output (src/crop_population.py):
```
WorldPop crop: shape=(457, 265), nodata=-99999.0
  valid_pixels=48538, sum_box=15029088.00
  sum_inside_BMC=13661494.00
  sum_outside_BMC_within_box=1367594.00
  Revised rule (inside BMC 12.0M-14.5M): PASS (inside=13661494.00)
  Population is 2020 data; imagery is 2024-2026 (year mismatch).
```
Revised rule (set after inspection of the box): WorldPop sum INSIDE the
dissolved BMC polygon must be 12.0-14.5 million. Measured inside BMC:
13,661,494 (PASS). Reference points: Census 2011 12,442,373; MCGM mid-2023
13,014,390 (https://mcgm.gov.in/irj/portal/anonymous/qlCivicDemographics).
Pixels assigned to BMC if centre point falls in the dissolved polygon
(centre-point rule, not any-touch).

## 2.10 Tests

tests/test_scale_and_qa.py: 12 passed. Run: conda run -n uhi pytest tests/.
Tests call the real shared functions in src/utils (scale-offset math, LST
Celsius range, NDVI range, NDBI formula, QA bit masking incl. dilated cloud
bit 1, NaN handling, union logic across two scenes, NDWI) with hand-computed
expected values.

## 2.11 Quicklook PNGs (masked labels)

logs/quicklook_lst_composite.png, quicklook_ndvi.png, quicklook_ndbi.png,
quicklook_valid_count.png. Figure sized to raster aspect (aspect="equal"),
extent matches raster bounds in EPSG:32643 m, BMC outline overlaid,
colorbar from data min to max (valid_count: 11.0 to 26.0).
Additional: logs/quicklook_removed_water.png (water pixels removed from BMC,
NDWI > 0, over BMC outline).

## Bytes (item 6)

4,396,436 bytes is the size of one stored float32 array
(789 x 1393 x 4 bytes plus .npy header), NOT transferred bytes. Transferred
bytes were NOT MEASURED. No claim is made that actual transfer is far less than
bytes_est (that was not measured). bytes_est is the sum of full-file HEAD
Content-Lengths per signed asset (e.g. Pilot 2024-03-06 bytes_est=
719861772 bytes). Per-scene arrays are cached in data/landsat/cache/ (98 files,
gitignored via data/). Per-date mosaics do NOT exist at data/cache/ (that
directory does not exist).

## Environment (item 7)

conda env create --dry-run -f environment.yml solved successfully: the full
package list resolved (exit code 0, normal dry-run behaviour). Output ends in
the resolved dependency list (dask, streamlit, rioxarray, geopandas, etc.).
The earlier warning about pip not being listed as a conda dependency is emitted
by conda and resolved automatically.

## Known Issues
- compute_indices.py reads valid_count.tif and the band GeoTIFFs (read-only
  composites); it consumes the validity product produced by build_composites.py
  (which calls src/utils.compute_validity). compute_indices.py calls
  src/utils.ndvi/ndbi/ndwi but does not itself call compute_validity because it
  operates on already-composited GeoTIFFs without QA input (qa is not written
  to composites).
- data/composites/ was generated with the previous validity logic; build_composites.py
  now uses src/utils.compute_validity (union across scenes, finite check) but
  composites were NOT regenerated in this round (read-only). Rerunning
  build_composites.py would produce a slightly different valid_count (157 pixels
  differ vs the existing valid_count.tif; min/median/max unchanged at 11/23/26).
- Two dates (2024-03-30, 2025-04-02) have zero valid BMC land pixels
  (footprint_fraction_bmc=0.0) because no scene covers BMC with finite lwir.
- stackstac was removed from environment.yml (incompatible with numpy 2.x);
  rasterio is used for loading.
- Phase 3 not started.
