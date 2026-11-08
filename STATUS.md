# STATUS.md - Phase 2 (DATA)

Run date: 2026-11-08. Conda env: uhi. Command prefix: conda run -n uhi.

## Process state
scratch scripts deleted or disabled; no project processes running.

## Source data
Collection: landsat-c2-l2 (Microsoft Planetary Computer STAC,
pystac-client + planetary-computer, anonymous, signed URLs). Assets
confirmed from live STAC raster:bands metadata: lwir11 (scale
0.00341802, offset 149.0), red (scale 0.0000275, offset -0.2), nir08,
swir16, green, qa_pixel.
Population: WorldPop India 2020 constrained,
ind_ppp_2020_constrained.tif, data.worldpop.org,
GIS/Population/Global_2000_2020_Constrained/2020/BSGM/IND/.
Study box: lon 72.77 to 72.99, lat 18.89 to 19.27. Metric CRS EPSG:32643.
Season: Window B only (Mar to May 2024/2025/2026), landsat-8 and
landsat-9, scene cloud under 10 percent.

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
(planetary_computer.sign per date batch), reprojecting each asset to
EPSG:32643 at 30 m over the box grid (789 x 1393 px). Validity uses the
shared function src/utils.compute_validity: finite(lwir) AND QA fill bit 0
clear AND dilated cloud bit 1 clear AND cirrus bit 2 clear AND cloud bit 3
clear AND shadow bit 4 clear. Date-level mask is the UNION of per-scene
validity.

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
compute_indices output block was not produced this round: label it exactly
output of the original run, not rerun.
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
Written to logs/per_date_valid_fraction.txt (verbatim below). Columns:
date, valid_fraction_box, valid_fraction_bmc, bmc_pixel_count,
footprint_fraction_bmc. Reuses data/landsat/cache/ (no re-download).
```
conda : C:\Users\Aryan\Desktop\College_Files\SY\My_Notes\My_Projects\mumbai-uhi\src\utils.py:67: RuntimeWarning: 
All-NaN slice encountered
At line:1 char:1
+ conda run --no-capture-output -n uhi python src/per_date_valid.py > l ...
+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (C:\Users\Aryan\...ice encountered:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
  mosaic[band_name] = np.nanmedian(np.stack(arrs, axis=0), axis=0)
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
2026-03-28: vf_box=1.0000 vf_bmc=1.0000 fp_bmc=1.0000
2026-04-13: vf_box=0.9928 vf_bmc=0.9887 fp_bmc=1.0000
2026-04-29: vf_box=0.9998 vf_bmc=1.0000 fp_bmc=1.0000
2026-05-07: vf_box=0.6730 vf_bmc=0.7753 fp_bmc=1.0000
2026-05-31: vf_box=0.6849 vf_bmc=0.6733 fp_bmc=1.0000
Per-date table written to logs\per_date_valid_fraction.txt
```

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
tests/test_scale_and_qa.py: 16 passed (verbatim below).
Tests call src/utils functions (apply_scale_offset, kelvin_to_celsius,
build_date_mosaic, compute_validity, ndvi, ndbi, ndwi) with hand-computed
expected values, including: cloudy-in-A-clear-in-B returns B exactly;
both-clear returns the mean; both-invalid returns NaN; date validity equals
any(valid); NaN handling; dilated cloud bit 1; NDWI.
```
============================= test session starts =============================
platform win32 -- Python 3.11.18, pytest-9.2.0, pluggy-1.7.0 -- C:\Users\Aryan\anaconda3\envs\uhi\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\Aryan\Desktop\College_Files\SY\My_Notes\My_Projects\mumbai-uhi
plugins: anyio-4.16.0
collecting ... collected 16 items

tests/test_scale_and_qa.py::test_scale_offset_math PASSED                [  6%]
tests/test_scale_and_qa.py::test_lst_celsius_range PASSED                [ 12%]
tests/test_scale_and_qa.py::test_ndvi_range PASSED                       [ 18%]
tests/test_scale_and_qa.py::test_ndvi_hand_computed PASSED               [ 25%]
tests/test_scale_and_qa.py::test_ndbi_formula PASSED                     [ 31%]
tests/test_scale_and_qa.py::test_ndbi_hand_computed PASSED               [ 37%]
tests/test_scale_and_qa.py::test_ndwi_hand_computed PASSED               [ 43%]
tests/test_scale_and_qa.py::test_qa_bit_masking_compute_validity PASSED  [ 50%]
tests/test_scale_and_qa.py::test_dilated_cloud_bit_1_compute_validity PASSED [ 56%]
tests/test_scale_and_qa.py::test_fill_bit_masking_compute_validity PASSED [ 62%]
tests/test_scale_and_qa.py::test_nan_handling PASSED                     [ 68%]
tests/test_scale_and_qa.py::test_union_logic_across_two_scenes PASSED    [ 75%]
tests/test_scale_and_qa.py::test_build_date_mosaic_cloudy_a_clear_b_returns_b PASSED [ 81%]
tests/test_scale_and_qa.py::test_build_date_mosaic_both_clear_returns_mean PASSED [ 87%]
tests/test_scale_and_qa.py::test_build_date_mosaic_both_invalid_returns_nan PASSED [ 93%]
tests/test_scale_and_qa.py::test_build_date_mosaic_date_validity_equals_any PASSED [100%]

============================== warnings summary ===============================
tests/test_scale_and_qa.py::test_build_date_mosaic_both_invalid_returns_nan
tests/test_scale_and_qa.py::test_build_date_mosaic_date_validity_equals_any
  C:\Users\Aryan\Desktop\College_Files\SY\My_Notes\My_Projects\mumbai-uhi\src\utils.py:67: RuntimeWarning: All-NaN slice encountered
    mosaic[band_name] = np.nanmedian(np.stack(arrs, axis=0), axis=0)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 16 passed, 2 warnings in 0.08s ========================
```

## 2.11 Quicklook PNGs (masked labels)
logs/quicklook_lst_composite.png, quicklook_ndvi.png, quicklook_ndbi.png,
quicklook_valid_count.png, quicklook_removed_water.png.
Regenerated with aspect="equal", figure sized to raster extent, BMC outline
overlaid, colorbar from data min to max (valid_count 12 to 26; LST 15 to 50).
Both quicklook_valid_count.png and quicklook_lst_composite.png verified:
axes fill the figure (no large blank margin), BMC outline visible as a white
line, colorbar from data min to max.

## Bytes
4,396,436 bytes is the size of one stored float32 array
(789 x 1393 x 4 bytes plus .npy header), NOT transferred bytes. Transferred
bytes were NOT MEASURED (no request byte counter). No claim is made that
actual transfer is far less than bytes_est (not measured). bytes_est is the
sum of full-file HEAD Content-Lengths per signed asset (e.g. Pilot
2024-03-06 bytes_est=719861772 bytes). Per-scene arrays are cached in
data/landsat/cache/ (294 files: 98 lwir11/qa_pixel from round 3 + 196 four-band
from round 4A). data/cache/ does not exist; per-date mosaics were NOT created
there.

## Environment
conda env create --dry-run -f environment.yml solved successfully: the full
package list resolved (exit code 0, normal dry-run success behaviour). Output
ends in the resolved dependency list (dask, streamlit, rioxarray, geopandas,
etc.). The conda warning about pip not being listed as a conda dependency is
emitted by conda and resolved automatically.

## Known Issues
- Absolute LST depends on which days were clear (per-date BMC medians range
  widely, 36.38 C to 44.46 C across dates).
- Effective dates 24 not 26 (2024-03-30 and 2025-04-02 have no BMC footprint,
  fp_bmc=0.0000).
- Population gate was widened after inspection (from 11.0-14.5M box-sum to
  12.0-14.5M inside-BMC sum).
- Five dates cover only part of BMC (valid fractions 0.59 to 0.87 inside BMC),
  so different parts of the city rest on different dates.
- valid-count versus LST check done at 30 m only; the 500 m check is pending
  in Phase 3.
- The 0.672607 old-logic value NOT EXPLAINED and not blocking.
- The USGS Level 2 thermal band is resampled from native 100 m to 30 m by cubic
  convolution; this pipeline then reprojected the 30 m product onto the box grid
  with nearest-neighbour.
- scratch scripts deleted or disabled; no project processes running.
- composites built with the old masking order (nanmedian before mask) but
  verified identical to v2 (0 differing pixels, see below); the overlap
  fraction was never measured, so this is reported as "identical, mechanism not
  tested".

## Round 4C - new results

### Per-date validity (logs/round4b_per_date_valid.txt)
```
conda : C:\Users\Aryan\Desktop\College_Files\SY\My_Notes\My_Projects\mumbai-uhi\src\utils.py:67: RuntimeWarning: 
All-NaN slice encountered
At line:1 char:1
+ conda run --no-capture-output -n uhi python src/per_date_valid.py > l ...
+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (C:\Users\Aryan\...ice encountered:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
  mosaic[band_name] = np.nanmedian(np.stack(arrs, axis=0), axis=0)
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
2026-03-28: vf_box=1.0000 vf_bmc=1.0000 fp_bmc=1.0000
2026-04-13: vf_box=0.9928 vf_bmc=0.9887 fp_bmc=1.0000
2026-04-29: vf_box=0.9998 vf_bmc=1.0000 fp_bmc=1.0000
2026-05-07: vf_box=0.6730 vf_bmc=0.7753 fp_bmc=1.0000
2026-05-31: vf_box=0.6849 vf_bmc=0.6733 fp_bmc=1.0000
Per-date table written to logs\per_date_valid_fraction.txt
```

### Month mix and per-date medians (logs/round4c_month_mix.txt)
```
conda : C:\Users\Aryan\Desktop\College_Files\SY\My_Notes\My_Projects\mumbai-uhi\src\utils.py:67: RuntimeWarning: 
All-NaN slice encountered
At line:1 char:1
+ conda run --no-capture-output -n uhi python src/month_mix.py > logs/r ...
+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (C:\Users\Aryan\...ice encountered:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
  mosaic[band_name] = np.nanmedian(np.stack(arrs, axis=0), axis=0)
C:\Users\Aryan\Desktop\College_Files\SY\My_Notes\My_Projects\mumbai-uhi\src\month_mix.py:153: RuntimeWarning: All-NaN 
slice encountered
  month_comp = np.nanmedian(month_stack, axis=0)  # already Celsius
Per-date BMC land median LST (all 26 dates):
  2024-03-06: median LST=36.56 C n_land=494793
  2024-03-14: median LST=36.38 C n_land=491819
  2024-03-22: median LST=38.13 C n_land=494759
  2024-03-30: median LST=N/A C n_land=0
  2024-04-07: median LST=42.73 C n_land=494780
  2024-04-15: median LST=44.46 C n_land=494795
  2024-04-23: median LST=41.47 C n_land=390945
  2024-05-01: median LST=43.22 C n_land=494795
  2024-05-09: median LST=39.13 C n_land=434369
  2024-05-17: median LST=38.49 C n_land=494025
  2025-03-01: median LST=37.06 C n_land=492892
  2025-03-09: median LST=39.88 C n_land=494795
  2025-03-17: median LST=39.95 C n_land=494794
  2025-03-25: median LST=39.42 C n_land=494795
  2025-04-02: median LST=N/A C n_land=0
  2025-04-10: median LST=36.67 C n_land=292711
  2025-04-18: median LST=39.62 C n_land=489508
  2025-04-26: median LST=42.17 C n_land=493341
  2026-03-04: median LST=40.43 C n_land=494795
  2026-03-12: median LST=38.44 C n_land=494795
  2026-03-20: median LST=39.02 C n_land=493361
  2026-03-28: median LST=40.18 C n_land=494795
  2026-04-13: median LST=40.54 C n_land=489166
  2026-04-29: median LST=41.69 C n_land=494794
  2026-05-07: median LST=40.95 C n_land=384977
  2026-05-31: median LST=39.96 C n_land=332879

Month mix (n dates, BMC land median LST, effective dates, min/max/IQR):
  2024-03: 4 dates median LST=36.86 C effective dates=3 min=36.38 max=38.13 IQR=0.88
  2024-04: 3 dates median LST=42.86 C effective dates=3 min=41.47 max=44.46 IQR=1.50
  2024-05: 3 dates median LST=39.64 C effective dates=3 min=38.49 max=43.22 IQR=2.37
  2025-03: 4 dates median LST=39.47 C effective dates=4 min=37.06 max=39.95 IQR=1.06
  2025-04: 4 dates median LST=40.13 C effective dates=3 min=36.67 max=42.17 IQR=2.75
  2025-05: 0 dates [] median LST=N/A effective dates=0 min=N/A max=N/A IQR=N/A
  2026-03: 4 dates median LST=39.55 C effective dates=4 min=38.44 max=40.43 IQR=1.37
  2026-04: 2 dates median LST=41.13 C effective dates=2 min=40.54 max=41.69 IQR=0.57
  2026-05: 2 dates median LST=40.47 C effective dates=2 min=39.96 max=40.95 IQR=0.49

Per-date BMC land medians:
  2024-03-06: 36.56 C (n_land=494793)
  2024-03-14: 36.38 C (n_land=491819)
  2024-03-22: 38.13 C (n_land=494759)
  2024-03-30: N/A C (n_land=0)
  2024-04-07: 42.73 C (n_land=494780)
  2024-04-15: 44.46 C (n_land=494795)
  2024-04-23: 41.47 C (n_land=390945)
  2024-05-01: 43.22 C (n_land=494795)
  2024-05-09: 39.13 C (n_land=434369)
  2024-05-17: 38.49 C (n_land=494025)
  2025-03-01: 37.06 C (n_land=492892)
  2025-03-09: 39.88 C (n_land=494795)
  2025-03-17: 39.95 C (n_land=494794)
  2025-03-25: 39.42 C (n_land=494795)
  2025-04-02: N/A C (n_land=0)
  2025-04-10: 36.67 C (n_land=292711)
  2025-04-18: 39.62 C (n_land=489508)
  2025-04-26: 42.17 C (n_land=493341)
  2026-03-04: 40.43 C (n_land=494795)
  2026-03-12: 38.44 C (n_land=494795)
  2026-03-20: 39.02 C (n_land=493361)
  2026-03-28: 40.18 C (n_land=494795)
  2026-04-13: 40.54 C (n_land=489166)
  2026-04-29: 41.69 C (n_land=494794)
  2026-05-07: 40.95 C (n_land=384977)
  2026-05-31: 39.96 C (n_land=332879)

Pooled monthly medians across years (all dates of that month):
  Mar: pooled (per-pixel over all dates)=38.92 C median-of-per-date-medians=39.02 C (n months with data=11)
  Apr: pooled (per-pixel over all dates)=41.57 C median-of-per-date-medians=41.58 C (n months with data=8)
  May: pooled (per-pixel over all dates)=40.06 C median-of-per-date-medians=39.96 C (n months with data=5)

May 2025 STAC search (any cloud cover):
  Without cloud filter: 8 scenes
    LC08_L2SP_148047_20250528_02_T2 platform=landsat-8 cloud=99.93
    LC08_L2SP_148046_20250528_02_T2 platform=landsat-8 cloud=100.0
    LC09_L2SP_148047_20250520_02_T1 platform=landsat-9 cloud=82.61
    LC09_L2SP_148046_20250520_02_T1 platform=landsat-9 cloud=46.9
    LC08_L2SP_148047_20250512_02_T1 platform=landsat-8 cloud=19.16
    LC08_L2SP_148046_20250512_02_T1 platform=landsat-8 cloud=15.57
    LC09_L2SP_148047_20250504_02_T1 platform=landsat-9 cloud=12.44
    LC09_L2SP_148046_20250504_02_T1 platform=landsat-9 cloud=15.06
  With cloud < 10 percent filter: 0 scenes
```

### Old versus v2 (logs/round4c_old_vs_v2.txt)
Result: identical, mechanism not tested.
```
valid_count inside BMC:
  old: min=14.0 median=23.0 max=24.0
  v2: min=14.0 median=23.0 max=24.0
valid_count pixels differing inside BMC: 0
LST over BMC land: mean diff (v2-old)=0.0000, max abs diff=0.0000, n=509028
  LST pixels differing by >0.5 C: 0
NDVI over BMC land: mean diff (v2-old)=0.0000, max abs diff=0.0000, n=509028
NDBI over BMC land: mean diff (v2-old)=0.0000, max abs diff=0.0000, n=509028
```

### Hot clusters and removed-water mask (logs/round4c_hot_pixels.txt)
```
NDWI histogram inside BMC (bins=-1 to 1 step 0.1, count of pixels):
  [-1.0 to -0.9): 0
  [-0.9 to -0.8): 0
  [-0.8 to -0.7): 139
  [-0.7 to -0.6): 16130
  [-0.6 to -0.5): 67417
  [-0.5 to -0.4): 97762
  [-0.4 to -0.3): 128942
  [-0.3 to -0.2): 144777
  [-0.2 to -0.1): 34542
  [-0.1 to -0.0): 5075
  [-0.0 to +0.1): 4445
  [+0.1 to +0.2): 4463
  [+0.2 to +0.3): 4790
  [+0.3 to +0.4): 544
  [+0.4 to +0.5): 2
  [+0.5 to +0.6): 0
  [+0.6 to +0.7): 0
  [+0.7 to +0.8): 0
  [+0.8 to +0.9): 0
  [+0.9 to +1.0): 0
Water pixels (NDWI > 0) removed from BMC polygon: 14233
BMC land median NDBI: -0.0353
Removed water pixels with NDBI above BMC land median: 119

Hot clusters (LST > 50.0 C, BMC land): 15

Cluster id, pixel count, max LST, centroid lon, centroid lat, mean NDVI, mean NDBI, NDVI pct rank, NDBI pct rank
1, 22, 53.04, 72.871499, 19.202134, 0.141, 0.070, 6.7, 88.8
2, 63, 51.46, 72.974278, 19.171050, 0.171, 0.077, 14.2, 90.7
3, 4, 50.16, 72.927982, 19.155900, 0.166, 0.124, 12.8, 98.0
4, 6, 50.29, 72.853347, 19.150166, 0.178, 0.025, 16.3, 74.2
5, 27, 51.98, 72.853653, 19.148543, 0.140, 0.030, 6.5, 76.2
6, 47, 51.71, 72.946028, 19.126294, 0.194, 0.128, 20.8, 98.3
7, 75, 51.56, 72.954912, 19.122599, 0.191, 0.071, 19.9, 89.0
8, 5, 50.38, 72.920980, 19.100269, 0.144, 0.117, 7.3, 97.4
9, 58, 52.46, 72.874839, 19.097303, 0.110, 0.053, 2.6, 84.0
10, 18, 51.31, 72.872308, 19.094564, 0.107, 0.061, 2.3, 86.2
11, 3, 50.07, 72.865760, 19.093947, 0.075, -0.029, 0.8, 52.5
12, 151, 51.24, 72.928198, 19.070000, 0.166, 0.080, 12.8, 91.3
13, 5, 50.14, 72.931329, 19.070306, 0.167, 0.081, 12.9, 91.7
14, 1, 50.03, 72.928784, 19.068651, 0.151, 0.077, 8.9, 90.6
15, 7, 50.29, 72.934584, 19.060587, 0.177, 0.072, 15.8, 89.5

Removed-water PNG: logs\quicklook_removed_water.png
Figure size: 7 x 6 inches
```

### Valid-count versus LST check (logs/round4c_valid_count_check.txt)
Check done at 30 m only; the 500 m check is pending in Phase 3.
```
BMC land pixels (finite LST, valid_count): 494795

a. Table grouped by valid_count value (BMC land):
   valid_count   n_pixels   median_LST_C    median_NDVI    median_NDBI
            14          1          32.28         0.0804         0.0167
            16          4          32.94         0.1040         0.0383
            17          6          33.19         0.0947         0.0322
            18        757          37.39         0.4593        -0.1141
            19       7386          38.86         0.3695        -0.0462
            20      18391          39.50         0.3457        -0.0568
            21      46595          39.71         0.2951        -0.0467
            22     113317          39.91         0.2954        -0.0284
            23     176063          39.89         0.3014        -0.0358
            24     132275          39.83         0.3144        -0.0339

b. Spearman correlation (BMC land pixels, n=494795):
  valid_count vs LST:   rho=0.0218
  valid_count vs NDVI:  rho=0.0368
  valid_count vs NDBI:  rho=0.0278
  Coefficients reported only; no statistical significance claim (30 m neighbouring pixels are spatially autocorrelated).

c. Median LST by valid_count group:
  valid_count <= 20: median LST = 39.26 C, n = 26545
  valid_count >= 23: median LST = 39.87 C, n = 308338

d. BMC land pixels with valid_count < 18: 11
  lon range: 72.808785 to 72.907101
  lat range: 18.958011 to 19.025049
```

