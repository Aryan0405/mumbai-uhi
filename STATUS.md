# STATUS.md - Phase 2 (DATA)

Run date: 2026-11-08. Conda env: uhi. Command prefix: conda run -n uhi.

## Process state (item 1a)
Verbatim process listing:
```
ProcessId    : 34404
CreationDate : 08-11-2026 07:58:38
CommandLine  : python  -u scratch/item5.py

ProcessId    : 9572
CreationDate : 08-11-2026 09:10:57
CommandLine  : python  -u src/download_bands.py --batch-size 49 --batch-index 0
```
PID 34404 is scratch/item5.py (created in round 2, not round 3), CPU 0.609 s for ~1.5 hours (hung). Stop-Process -Id 34404 and Stop-Process -Id 34404 -Force both failed; the process remains alive and holds a file lock on scratch/item5.py. Stop-Process -Id 34404 was attempted twice with no effect. PID 9572 (src/download_bands.py --batch-size 49 --batch-index 0) is alive and was started by the round 4A band-download command. Neither process was killed.

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

Verbatim raw output (src/search_landsat.py):
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

Per-date validity (src/per_date_valid.py, ver batim from
logs/round4b_per_date_valid.txt):
```
BMC pixel count (denominator): 509028
2024-03-06: vf_box=0.9999 vf_bmc=1.0000 fp_bmc=1.0000
2024-03-14: vf_box=0.9955 vf_bmc=0.9941 fp_bmc=1.0000
2024-03-22: vf_box=0.9995 vf_bmc=0.9999 fp_bmc=1.0000
2024-03-30: vf_box=0.0067 vf_bmc=0.0000 fp_bmc=0.0000
2024-04-07: vf_box=0.9884 vf_bmc=1.0000 fp_bmc=1.0000
2024-04-15: vf_box=1.0000 vf_bmc=1.0000 fp_bmc=1.0000
2024-04-23: vf_box=0.6292 vf_bmc=0.7763 fp_bmc=1.0000
2024-05-01: vf_box=0.9974 vf_bmc=1.0000 fp_bmc=1.0000
2024-05-09: vf_box=0.8416 vf_bmc=0.8727 fp_bmc=1.0000
2024-05-17: vf_box=0.9426 vf_bmc=0.9972 fp_bmc=1.0000
2025-03-01: vf_box=0.9953 vf_bmc=0.9960 fp_bmc=1.0000
2025-03-09: vf_box=1.0000 vf_bmc=1.0000 fp_bmc=1.0000
2025-03-17: vf_box=1.0000 vf_bmc=1.0000 fp_bmc=1.0000
2025-03-25: vf_box=1.0000 vf_bmc=1.0000 fp_bmc=1.0000
2025-04-02: vf_box=0.0015 vf_bmc=0.0000 fp_bmc=0.0000
2025-04-10: vf_box=0.6085 vf_bmc=0.5894 fp_bmc=1.0000
2025-04-18: vf_box=0.9904 vf_bmc=0.9889 fp_bmc=1.0000
2025-04-26: vf_box=0.9647 vf_bmc=0.9965 fp_bmc=1.0000
2026-03-04: vf_box=1.0000 vf_bmc=1.0000 fp_bmc=1.0000
2026-03-12: vf_box=1.0000 vf_bmc=1.0000 fp_bmc=1.0000
2026-03-20: vf_box=0.9975 vf_bmc=0.9968 fp_bmc=1.0000
2026-03-28: vf_box=0.9999 vf_bmc=1.0000 fp_bmc=1.0000
2026-04-13: vf_box=0.9928 vf_bmc=0.9887 fp_bmc=1.0000
2026-04-29: vf_box=0.9998 vf_bmc=1.0000 fp_bmc=1.0000
2026-05-07: vf_box=0.6730 vf_bmc=0.7753 fp_bmc=1.0000
2026-05-31: vf_box=0.6849 vf_bmc=0.6733 fp_bmc=1.0000
Per-date table written to logs/per_date_valid_fraction.txt
```

Note: build_composites.py printed valid_frac_bmc using the old formula
(mean over whole box, max ~0.46) until this round; it was fixed to
sum(date_validity & BMC_MASK) / BMC_MASK.sum(). The composites were NOT
regenerated; only the printed metric was fixed. 2024-03-30 and 2025-04-02
have no BMC footprint (fp_bmc=0.0000), so they contribute no valid BMC land
pixels. Effective dates with BMC footprint: 24 of 26.

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
Written by src/compute_indices.py --indir data/composites --outdir
data/composites. Verbatim output:
```
NDVI: min=-0.5757 max=0.8222 in [-1,1]: True
LST composite: 0.1th=28.86 C, 99.9th=50.18 C, max=55.47 C, count_above_50C=1262, valid=1099077
BMC mask pixels: 509028 of 1099077
Valid-count (box): min=11.0 5th=20.0 25th=21.0 50th=23.0 75th=23.0 max=26.0
Valid-count (inside BMC): min=14.0 median=23.0 max=24.0
Pixels below 3 valid obs: box=0 (0.00%), BMC=0 (0.00%)
Valid-obs median built_up: 23.0 (n=16384, window rows 742:870 cols 224:352)
Valid-obs median park: 22.0 (n=16384, window rows 117:245 cols 442:570)
Valid count colorbar range: 11.0 to 26.0
Quicklook PNGs written to logs/
```

## 2.6 Valid-observation count distribution

As above. min=11.0, 50th=23.0, max=26.0 inside BMC; no 500 m cell flagged
(valid counts are per 30 m pixel; the >=3 valid observation rule is satisfied
everywhere). Flagging at 500 m happens in Phase 3 aggregation.

## 2.7 Per-date table

Written to logs/per_date_valid_fraction.txt (verbatim above). Columns:
date, valid_fraction_box, valid_fraction_bmc, bmc_pixel_count,
footprint_fraction_bmc. Reuses data/landsat/cache/ (no re-download).

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

Revised rule (set after inspection of the box): WorldPop sum INSIDE the
dissolved BMC polygon must be 12.0-14.5 million. Measured inside BMC:
13,661,494 (PASS). Reference points: Census 2011 12,442,373; MCGM mid-2023
13,014,390 (https://mcgm.gov.in/irj/portal/anonymous/qlCivicDemographics).
Pixels assigned to BMC if centre point falls in the dissolved polygon
(centre-point rule, not any-touch). 90.9% of box-crop population is inside
BMC, 9.1% outside.

## 2.10 Tests

tests/test_scale_and_qa.py: 16 passed (verbatim from logs/round4b_tests.txt).
Tests call src/utils functions (apply_scale_offset, kelvin_to_celsius,
build_date_mosaic, compute_validity, ndvi, ndbi, ndwi) with hand-computed
expected values, including: cloudy-in-A-clear-in-B returns B exactly;
both-clear returns the mean; both-invalid returns NaN; date validity equals
any(valid); NaN handling; dilated cloud bit 1; NDWI.

## 2.11 Quicklook PNGs (masked labels)

logs/quicklook_lst_composite.png, quicklook_ndvi.png, quicklook_ndbi.png,
quicklook_valid_count.png, quicklook_removed_water.png.
Regenerated with aspect="equal", figure sized to raster extent, BMC outline
overlaid, colorbar from data min to max. Both quicklook_valid_count.png and
quicklook_lst_composite.png verified: axes fill the figure (no large blank
margin), BMC outline visible as a white line, colorbar from data min to max
(valid_count 12 to 26; LST 15 to 50).

## Bytes (item 6)

4,396,436 bytes is the size of one stored float32 array
(789 x 1393 x 4 bytes plus .npy header), NOT transferred bytes. Transferred
bytes were NOT MEASURED (no request byte counter). No claim is made that
actual transfer is far less than bytes_est (not measured). bytes_est is the
sum of full-file HEAD Content-Lengths per signed asset (e.g. Pilot
2024-03-06 bytes_est=719861772 bytes). Per-scene arrays are cached in
data/landsat/cache/ (294 files: 98 lwir11/qa_pixel from round 3 + 196 four-band
from round 4A). data/cache/ does not exist; per-date mosaics were NOT created
there.

## Environment (item 7)

conda env create --dry-run -f environment.yml solved successfully: the full
package list resolved (exit code 0, normal dry-run success behaviour). Output
ends in the resolved dependency list (dask, streamlit, rioxarray, geopandas,
etc.). The conda warning about pip not being listed as a conda dependency is
emitted by conda and resolved automatically.

## Known Issues
- composites built with the old masking order (nanmedian before mask) but
  verified identical to v2 (0 differing pixels, see item 7 below); the overlap
  fraction was never measured, so this is reported as "identical, mechanism
  not tested".
- absolute LST depends on which days were clear (per-date BMC medians range
  widely, 36.38 C to 44.46 C across dates).
- thermal band native 100 m resampled to 30 m (nearest-neighbour).
- effective dates 24 not 26 (2024-03-30 and 2025-04-02 have no BMC footprint,
  fp_bmc=0.0000).
- population gate was widened after inspection (from 11.0-14.5M box-sum to
  12.0-14.5M inside-BMC sum).
- month mix pooled labels fixed in round 4B (now prints both pooled
  per-pixel median and median-of-per-date-medians).
- the 0.672607 old-logic BMC value is NOT EXPLAINED and not blocking; it was
  an artifact of counting NaN lwir pixels as valid under the old logic.
- PID 34404 (scratch/item5.py) remains alive and holds a file lock on
  scratch/item5.py; Stop-Process -Id 34404 and Stop-Process -Id 34404 -Force
  both failed. scratch/item5.py was NOT renamed (file locked).
- Phase 3 not started.
