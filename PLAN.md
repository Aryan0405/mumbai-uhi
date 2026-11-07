# PLAN.md - mumbai-uhi

Project: Urban Heat Island (UHI) vulnerability map of Greater Mumbai from open satellite data, with a Streamlit app.
Author: undergraduate data science student, Mumbai.
Role of agent: senior data engineer building end-to-end, running code, reading errors, fixing them.

## 0. Environment rules (conda)
- Environment name: `uhi` (project folder `mumbai-uhi` is unrelated; do not rename).
- Write `environment.yml` with channel conda-forge, python 3.11, packages:
  geopandas, rasterio, scikit-learn, scipy, numpy, pandas, matplotlib, folium,
  pydeck, streamlit, pytest, requests, tqdm, stackstac, rioxarray, xarray, dask.
  pystac-client and planetary-computer go in a pip section inside environment.yml.
- Create exactly with: `conda env create -f environment.yml`.
- Never use bare python or pip. Always: `conda run -n uhi python <script>`,
  `conda run -n uhi pytest`, `conda run -n uhi streamlit run ...`.
- Long-running commands use: `conda run --no-capture-output -n uhi <command>`.
- Phase 5: export final environment to `environment.yml` and write `requirements-conda.txt`
  via `conda list --export`.
- No em dashes anywhere (code, comments, README, messages).
- No secrets in the repo.
- Keep each file under 300 lines. Prefer small modules.

## 1. Environment creation (Phase 1)
- The `uhi` conda env is created at the start of Phase 1 with:
  `conda env create -f environment.yml`. The full output is logged to logs/.
- After creation, confirm `conda env list` shows `uhi`.

## 2. Data sources (open data only, no accounts, no GEE)
- Landsat 8 and 9 Collection 2 Level-2 from Microsoft Planetary Computer STAC
  using pystac-client + planetary-computer, anonymous read with signed URLs.
  Collection ID: `landsat-c2-l2` (to be confirmed by querying the catalog, not
  assumed from memory).
  Assets: `lwir11`, `nir08`, `red`, `swir16`, `QA_PIXEL`. Scale and offset read
  from live STAC item JSON `raster:bands` fragment. Never hardcode scale factors.
- WorldPop India population 2020 constrained:
  `ind_ppp_2020_constrained.tif` on `data.worldpop.org` under
  `GIS/Population/Global_2000_2020_Constrained/2020/`. Folder (maxar_v1 or BSGM)
  discovered by reading the directory listing; never guessed.
- Study box: lon 72.77 to 72.99, lat 18.89 to 19.27. Metric CRS EPSG:32643.
- Season: not chosen by agent. Gate measures both Window A (Nov to Mar) and
  Window B (Mar to May). User picks the window after the gate.
- Synthetic population: NOT allowed to run automatically. Only on explicit user
  approval if WorldPop fails the gate, with SYNTHETIC markers, fixed seed,
  generator script, cited sources, and README section. Never mixed with real
  numbers in one reported metric.
- Never synthesize LST, NDVI, or NDBI. If Landsat check fails, STOP and report.

## 3. Landsat loading and stacking
- Library: stackstac with rioxarray (and xarray).
  Justification: stackstac is purpose-built to load STAC items into a single
  xarray DataArray, handles reprojection/resampling to a common grid, works with
  rasterio and signed URLs, and keeps the dependency footprint small. odc-stac
  is a valid alternative but is a heavier ecosystem; stackstac fits the
  small-modules preference.
- Signed URLs expire (short-lived). Do not sign per-asset just before each read.
  Instead, process scenes in small batches and sign each batch when its stack is
  created, using planetary-computer's sign method on the batch's asset hrefs.
  Retry on HTTP 403 / 401 expiry by re-signing that batch. Prove it works in
  Phase 2 by loading at least two full scenes into one stackstac stack and
  printing the stack shape and a sample of finite (non-NaN) pixel values.

## 4. Folder layout
```
mumbai-uhi/                      project root (environment name is uhi)
├── PLAN.md                      this file (Phase 0)
├── STATUS.md                    written after each phase; real numbers + raw output
├── environment.yml              conda env spec
├── requirements-conda.txt       conda list --export (Phase 5)
├── reproduce.sh                 one-command reproduce script (Phase 5)
├── README.md                    setup, real computed results, limitations (Phase 5)
├── logs/                        full stdout of important runs
├── src/                         pipeline scripts (each under 300 lines)
│   ├── config.py                box, CRS, thresholds, window dates; all scripts import from it
│   ├── smoke_test.py            Phase 1 feasibility gate
│   ├── fetch_landsat.py         Phase 2: search, download signed assets
│   ├── compute_indices.py       Phase 2: LST, NDVI, NDBI, QA mask, median composite, obs count
│   ├── crop_population.py       Phase 2: WorldPop HEAD, directory listing, crop to box, delete original
│   ├── aggregate_grid.py        Phase 3: reproject EPSG:32643, 500 m grid, land mask
│   ├── cluster_kmeans.py        Phase 3: K-Means, silhouette k-selection
│   ├── vulnerability.py         Phase 3: index, weights, sensitivity analysis
│   └── app.py                   Phase 4: Streamlit app
├── data/                        outputs (Phase 2+), kept under 100 MB total
│   ├── landsat/                 raw signed assets
│   ├── composites/              LST, NDVI, NDBI, obs-count GeoTIFFs
│   ├── population/              cropped WorldPop raster (original deleted after crop)
│   ├── grid/                    500 m grid GeoParquet / compressed GeoJSON
│   └── clusters/                cluster + vulnerability GeoParquet
└── tests/                       Phase 5 pytest tests
```

## 5. Acceptance checks per phase (measurable)

### Phase 0 (PLAN) - current
- PLAN.md written with architecture, data sources, folder layout, acceptance checks.
- No code files created in this phase (no smoke_test.py).
- STOP and wait for `next`.

### Phase 1 (FEASIBILITY GATE)
Write smoke_test.py and run via `conda run -n uhi`. Write FEASIBILITY.md with PASS/FAIL
plus measured numbers per item; paste raw output into it.
1. Network: HTTPS reaches planetarycomputer.microsoft.com and data.worldpop.org.
   Print HTTP status and response size for each. OPTIONAL fallback host only if
   data.worldpop.org fails, and say so.
2. Landsat: search `landsat-c2-l2` over box, cloud cover < 10%, platforms
   landsat-8 and landsat-9. Print scene counts and scene IDs per window:
   Window A: Nov 2023-Mar 2024, Nov 2024-Mar 2025, Nov 2025-Mar 2026.
   Window B: Mar-May 2024, Mar-May 2025, Mar-May 2026.
   REQUIRED: at least 5 usable scenes total in at least one window. Print WRS-2
   path and row per scene; say whether box spans more than one tile.
3. Read two 128x128 windows of `lwir11` from one scene via signed URLs:
   (a) dense built-up near lon 72.85, lat 19.05 (check land not water).
   (b) Sanjay Gandhi National Park near lon 72.91, lat 19.22 (check land).
   Mask fill value 0 and QA_PIXEL before statistics. LST (K) = DN * scale +
   offset, minus 273.15 = C. Print min, max, mean per window.
   REQUIRED: plausible land values in range 15 to 50 C. REQUIRED to report whether
   park mean LST is lower than built-up mean LST. If not, STOP and report.
   Print raster:bands scale/offset fragment from live STAC JSON for lwir11 and a
   reflectance band (confirm 0.00341802/149.0 and 0.0000275/-0.2 from metadata).
   Confirm QA_PIXEL bit 3 cloud, bit 4 cloud shadow from asset metadata
   (classification:bitfields or equivalent); print that fragment.
4. Population: HEAD `ind_ppp_2020_constrained.tif` on data.worldpop.org. Find India
   file by reading directory listing under .../2020/ (maxar_v1 or BSGM; do not
   guess). Print resolved URL and size. Crop to box, delete original, print cropped
   shape, nodata, sum, min/max. If fails: mark population FAILED in FEASIBILITY.md
   and STOP for user decision.
5. Environment: imports of geopandas, rasterio, scikit-learn, streamlit,
   pystac_client, planetary_computer clean inside `uhi`; print versions.

### Phase 2 (DATA) - scripts in src/, outputs in data/
- Landsat 8 and 9 C2 L2, cloud < 10%, season window chosen by user after gate.
- Compute LST (C), NDVI (nir08, red), NDBI (swir16, nir08) with scale/offset from
  metadata. Mask cloud and shadow with QA_PIXEL. Per-pixel median composite.
- MEASURABLE: NDVI values within [-1, 1]. LST values in range 15 to 50 C.
- Output per-pixel count of valid observations; report distribution; flag any
  500 m cell with fewer than 3 valid observations.
- MEASURABLE: expected 500 m grid cell count before land masking ~3,900
  (box ~973 km² / 0.25 km² per cell; computed exactly in Phase 2).
- MEASURABLE: pytest unit test for scale-factor math (DN * scale + offset)
  using small synthetic arrays; run in Phase 2.
  (box ~973 km² / 0.25 km² per cell; computed exactly in Phase 2).
- WorldPop crop via src/crop_population.py. Population from cropped WorldPop raster.
  State it is 2020 data while imagery is newer.
- MEASURABLE: cropped population sum compared against cited reference totals:
  Census 2011 Greater Mumbai population 12,442,373, and MCGM mid-year 2023 estimate
  13,014,390 (https://mcgm.gov.in/irj/portal/anonymous/qlCivicDemographics).
  The study box differs from the BMC boundary and includes sea, so exact match is
  not expected. Numeric rule: the cropped WorldPop sum must be between 11.0 and
  14.5 million. If it is outside that range, STOP and report.

### Phase 3 (ANALYSIS)
- Reproject to EPSG:32643. Aggregate onto 500 m grid clipped to land (exclude sea
  and large water via NDWI or WorldCover).
- WorldPop gives people per pixel: aggregate to 500 m cells by SUM and divide by
  cell area. Never average. Never resample counts with bilinear or average.
- MEASURABLE: total population before and after aggregation to the 500 m grid
  must agree within 1 percent.
- K-Means on standardized LST, NDVI, NDBI. Choose k by silhouette score; show
  evidence.
- Vulnerability Index = weighted z-scores of hazard (LST), sensitivity (low NDVI,
  high NDBI), exposure (population density). Document weights.
- Sensitivity analysis: several weight schemes; Spearman rank correlation between
  rankings; Jaccard overlap of top 20 hotspots between schemes. Report index with
  and without exposure term.
- Sanity checks, reported honestly: Sanjay Gandhi National Park cooler than dense
  built-up areas; coastal strips show cooling. If they fail, investigate and say so.

### Phase 4 (APP)
- Streamlit app: Folium or pydeck map with toggles for LST, NDVI, clusters,
  vulnerability. Table of top 20 hotspot cells with coordinates and metrics behind
  each. Methodology page stating limitations plainly: LST is surface temperature
  not air temperature; exact season window used and what it does/does not represent
  for human heat stress; composite of a few scenes; weights are judgment calls;
  population year mismatch; whether exposure is real or synthetic.
- Processed data under 100 MB total (GeoParquet or compressed GeoJSON).

### Phase 5 (QUALITY)
- pytest tests for grid aggregation, index computation on small synthetic arrays.
  (Scale-factor math test moved to Phase 2.)
- environment.yml, requirements-conda.txt (`conda list --export`), one-command
  reproduce script using `conda run -n uhi`, README with setup, real computed
  results, limitations, screenshots.
- DONE WHEN: fresh clone runs pipeline and app with documented conda commands,
  tests pass, README claims match actual outputs.

## 6. Scope note
- The study box (lon 72.77 to 72.99, lat 18.89 to 19.27, ~973 km²) likely extends
  beyond the Brihanmumbai Municipal Corporation (BMC) boundary (483.14 km²) and
  includes sea.
- Two options, do not decide now:
  (a) clip analysis to an administrative boundary (e.g., BMC or MMR), or
  (b) rename the study area to Mumbai metropolitan area.
- User will choose.

## 7. Key risks / notes
- conda shell may not keep activation between commands; always prefix with
  `conda run -n uhi`.
- `--no-capture-output` flag may not be supported by all conda versions; if it
  errors, report exact message.
- Download time, memory use (WorldPop full India raster is large; crop after
  ranged read or download then delete), and signed URL expiry (sign per batch).
- Do not choose season window; gate measures both.
- Do not synthesize LST/NDVI/NDBI. Real data first.
- WorldPop synthetic only on explicit approval after gate failure.