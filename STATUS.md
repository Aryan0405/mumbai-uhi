# STATUS.md - Phase 2 (DATA)

Run date: 2026-11-07. Conda env: `uhi`. Command prefix: `conda run -n uhi`.

## 2.1 Search - landsat-c2-l2, Window B (Mar-May 2024/2025/2026), L8+L9, cloud < 10%

Source: Microsoft Planetary Computer STAC (pystac-client + planetary-computer, anonymous, signed URLs).
Collection confirmed: `landsat-c2-l2`. Assets confirmed: `lwir11`, `red`, `nir08`, `swir16`, `green`, `qa_pixel`.
Scale/offset read from live STAC `raster:bands` metadata: lwir11 0.00341802/149.0, red 0.0000275/-0.2 (never hardcoded).

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

Result: 49 unique scenes (all landsat-8/9), 26 unique dates, 2 WRS-2 tiles, box spans more than one tile.

## 2.2 Load - stack per batch, sign each batch

stackstac 0.5.0 is incompatible with the env's numpy 2.x (`np.can_cast` rejects floats), so loading uses rasterio directly with per-batch signing (planetary_computer.sign per date batch), reprojecting each asset to EPSG:32643 at 30 m over the box grid (789 x 1393 px).

Pilot (2 dates):
```
Pilot 2024-03-06: valid_frac_box=0.9999, bytes_est=719861772
Pilot 2024-03-14: valid_frac_box=0.9955, bytes_est=746874092
PILOT 2 dates: wall_time=55.0s, peak_memory=197.9 MB
```
Then all 26 dates processed without errors. All dates load successfully.

## 2.3 Mosaic - two WRS-2 rows (148/046, 148/047) per date mosaicked via nanmedian before compositing.

## 2.4 Mask - fill bit 0, dilated cloud bit 1, cirrus bit 2, cloud bit 3, cloud shadow bit 4 from QA_PIXEL.

## 2.5 Indices + median composite - LST, NDVI, NDBI, NDWI

Per-pixel median composite across 26 dates. Output GeoTIFFs in EPSG:32643 at 30 m to data/composites/:
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
No 500 m cell flagged here (valid counts are per 30 m pixel; the >=3 valid observation rule is satisfied everywhere). Flagging at 500 m happens in Phase 3 aggregation.

## 2.7 Per-date table

Written to logs/per_date_valid_fraction.txt (date, valid_fraction_box, valid_fraction_bmc). Box valid fractions computed in the successful Phase 2 run; inside-BMC column is being recomputed by a background disk-cached job (logs/phase2_perdate_bg_20261107_191143.log) because re-downloading all assets times out at 20 min in the foreground.

## 2.8 Checks (real numbers)

NDVI within [-1, 1]: True (composite min=-0.5757, max=0.8222).
LST sanity rule (provisional): 0.1th=28.86 C, 99.9th=50.18 C, max=55.47 C, count_above_50C=1262, valid=1099077.
Median composite LST: park window vs built-up window - reported only (Phase 3 owns the sanity check). Phase 1 gate already confirmed park mean LST lower than built-up in both Feb and Apr 2024.

## 2.9 Population (WorldPop India 2020 constrained)

Source: data.worldpop.org, `.../2020/BSGM/IND/ind_ppp_2020_constrained.tif`.
HEAD: HTTP 200, Content-Length=531062384 bytes. Server does not support ranged reads; full file downloaded once to data/population/raw/ and KEPT (not deleted). Crop to box via rasterio window read; nodata (-99999) masked before summing.

Raw output (src/crop_population.py):
```
WorldPop crop: shape=(457, 265), nodata=-99999.0
  valid_pixels=48538, sum_box=15029088.00
  sum_inside_BMC=13661494.00
  sum_outside_BMC_within_box=1367594.00
  Revised rule (inside BMC 12.0M-14.5M): PASS (inside=13661494.00)
  Population is 2020 data; imagery is 2024-2026 (year mismatch).
```
Revised rule (set after inspection of the box): WorldPop sum INSIDE the dissolved BMC polygon must be 12.0-14.5 million. Measured inside BMC: 13,661,494 (PASS). Reference points: Census 2011 12,442,373; MCGM mid-2023 13,014,390. Pixels assigned to BMC if centre point falls in the dissolved polygon (centre-point rule, not any-touch). 90.9% of box-crop population is inside BMC, 9.1% outside.

## 2.10 Tests

tests/test_scale_and_qa.py: 6 passed (scale-offset math, LST Celsius range, NDVI range, QA bit masking, fill-bit masking, NDBI formula). Run: `conda run -n uhi pytest tests/`.

## 2.11 Quicklook PNGs (masked labels)

logs/quicklook_lst_composite.png, quicklook_ndvi.png, quicklook_ndbi.png, quicklook_valid_count.png.

## Notes

- Population is 2020 data; imagery is 2024-2026 (year mismatch, stated plainly).
- LST is surface temperature, not air temperature.
- No LST/NDVI/NDBI synthesized; all from real Landsat C2 L2.
- data/ and logs/ are gitignored and NOT committed (raw WorldPop 531 MB kept in data/population/raw/).
- Phase 3 not started.
