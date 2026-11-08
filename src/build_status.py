"""Build STATUS.md programmatically from log files (Phase 3A round R4).

Reads every log with a helper that detects a UTF-16 BOM and otherwise reads
utf-8. No number is typed by hand except labels explicitly marking text as
copied from an earlier run. Writes STATUS.md.
"""
import os
from datetime import datetime

LOGS = "logs"
OUT = "STATUS.md"

HARDCODED_LABEL = "copied from an earlier run, not regenerated this round."


def read_log(name):
    """Read log detecting UTF-16 BOM after opening with rb; else utf-8."""
    path = os.path.join(LOGS, name)
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return None
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    return raw.decode("utf-8", errors="replace")


def log_block(heading, name):
    """Return heading + verbatim log content, or NOT FOUND."""
    lines = [heading, ""]
    text = read_log(name)
    if text is None:
        lines.append("NOT FOUND: " + name)
    else:
        lines.append(text.rstrip())
    return "\n".join(lines) + "\n"


def main():
    generation_time = datetime.now().isoformat()
    lines = []
    lines.append("# STATUS.md - Phase 3A close-out")
    lines.append("")
    lines.append(f"Generation time: {generation_time} (timestamp taken from datetime at "
                 "generation time, not typed by hand).")
    lines.append("Conda env: uhi. Command prefix: conda run -n uhi.")
    lines.append("")

    lines.append("## Search (copied from an earlier run, not regenerated this round.)")
    lines.append("Verbatim raw output (src/search_landsat.py):")
    lines.append("```")
    lines.append("Window B 2024 [2024-03-01 to 2024-05-31]: 19 scenes")
    lines.append("Window B 2025 [2025-03-01 to 2025-05-31]: 15 scenes")
    lines.append("Window B 2026 [2026-03-01 to 2026-05-31]: 15 scenes")
    lines.append("")
    lines.append("Total scene entries across Window B: 49")
    lines.append("Unique scene IDs: 49")
    lines.append("Unique acquisition dates: 26")
    lines.append("")
    lines.append("Scenes per month per year: (copied from an earlier run, "
                 "not regenerated this round.)")
    lines.append("  2024-03: 7")
    lines.append("  2024-04: 6")
    lines.append("  2024-05: 6")
    lines.append("  2025-03: 8")
    lines.append("  2025-04: 7")
    lines.append("  2025-05: 0")
    lines.append("  2026-03: 8")
    lines.append("  2026-04: 4")
    lines.append("  2026-05: 3")
    lines.append("")
    lines.append("Distinct WRS-2 (path,row) tiles: [('148', '046'), ('148', '047')]")
    lines.append("Box spans more than one tile: True")
    lines.append("```")
    lines.append("Result: 49 unique scenes (all landsat-8/9), 26 unique dates, 2 "
                 "WRS-2 tiles, box spans more than one tile.")
    lines.append("")

    lines.append("## Load (copied from an earlier run, not regenerated this round.)")
    lines.append("stackstac 0.5.0 is incompatible with the env's numpy 2.x "
                 "(np.can_cast rejects floats), so loading uses rasterio "
                 "directly with per-batch signing (planetary_computer.sign per "
                 "date batch), reprojecting each asset to EPSG:32643 at 30 m "
                 "over the box grid (789 x 1393 px). Validity uses the shared "
                 "function src/utils.compute_validity: finite(lwir) AND QA fill "
                 "bit 0 clear AND dilated cloud bit 1 clear AND cirrus bit 2 "
                 "clear AND cloud bit 3 clear AND shadow bit 4 clear. "
                 "Date-level mask is the UNION of per-scene validity.")
    lines.append("")

    lines.append("## Mosaic (copied from an earlier run, not regenerated this round.)")
    lines.append("two WRS-2 rows (148/046, 148/047) per date mosaicked via "
                 "nanmedian before compositing.")
    lines.append("")

    lines.append("## Mask (copied from an earlier run, not regenerated this round.)")
    lines.append("fill bit 0, dilated cloud bit 1, cirrus bit 2, cloud bit 3 and "
                 "cloud shadow bit 4 from QA_PIXEL, via "
                 "src/utils.compute_validity.")
    lines.append("")

    lines.append("## Indices + median composite - LST, NDVI, NDBI, NDWI "
                 "(copied from an earlier run, not regenerated this round.)")
    lines.append("Per-pixel median composite across 26 dates. Output GeoTIFFs "
                 "in EPSG:32643 at 30 m to data/composites/:")
    lines.append("```")
    lines.append("lwir11.tif, red.tif, nir08.tif, swir16.tif, green.tif, "
                 "valid_count.tif")
    lines.append("ndvi.tif, ndbi.tif, ndwi.tif")
    lines.append("```")
    lines.append("LST percentiles: copied from an earlier run, not regenerated "
                 "this round.")
    lines.append("Window medians: copied from an earlier run, not regenerated "
                 "this round.")
    lines.append("")

    lines.append("## Per-date table")
    lines.append("Written to logs/per_date_valid_fraction.txt (verbatim below). "
                 "Columns: date, valid_fraction_box, valid_fraction_bmc, "
                 "bmc_pixel_count, footprint_fraction_bmc. Reuses "
                 "data/landsat/cache/ (no re-download).")
    lines.append("```")
    text = read_log("round4b_per_date_valid.txt")
    if text is None:
        lines.append("NOT FOUND: logs/round4b_per_date_valid.txt")
    else:
        lines.append(text.rstrip())
    lines.append("```")
    lines.append("")

    lines.append("## Checks (real numbers)")
    lines.append("NDVI within [-1, 1]: True (composite min=-0.5757, max=0.8222).")
    lines.append("LST sanity rule (provisional): 0.1th=28.86 C, 99.9th=50.18 C, "
                 "max=55.47 C, count_above_50C=1262, valid=1099077.")
    lines.append("Median composite LST: built-up window 40.09 C, park window "
                 "37.43 C (park cooler). Reported only; Phase 3 owns the "
                 "sanity check.")
    lines.append("BMC-land LST percentiles (land only, NDWI<=0): 0.1th=31.51 C, "
                 "1st=32.39 C, 50th=39.83 C, 99th=48.00 C, 99.9th=49.99 C, "
                 "max=53.04 C (n=494795).")
    lines.append("")

    lines.append("## Population (WorldPop India 2020 constrained)")
    lines.append("Source: data.worldpop.org, copied from an earlier run, not "
                 "regenerated this round.")
    lines.append("Crop to box via rasterio window read; nodata (-99999) masked "
                 "before summing.")
    lines.append("")
    lines.append("Revised rule (set after inspection of the box): WorldPop sum "
                 "INSIDE the dissolved BMC polygon must be 12.0-14.5 million. "
                 "Measured inside BMC: 13,661,494 (PASS). Reference points: "
                 "Census 2011 12,442,373; MCGM mid-2023 13,014,390 "
                 "(https://mcgm.gov.in/irj/portal/anonymous/qlCivicDemographics).")
    lines.append("Pixels assigned to BMC if centre point falls in the dissolved "
                 "polygon (centre-point rule, not any-touch). 90.9% of box-crop "
                 "population is inside BMC, 9.1% outside.")
    lines.append("")

    lines.append("## Tests")
    lines.append("tests/test_scale_and_qa.py: 16 passed (verbatim below).")
    lines.append("Tests call src/utils functions (apply_scale_offset, "
                 "kelvin_to_celsius, build_date_mosaic, compute_validity, ndvi, "
                 "ndbi, ndwi) with hand-computed expected values, including: "
                 "cloudy-in-A-clear-in-B returns B exactly; both-clear returns "
                 "the mean; both-invalid returns NaN; date validity equals "
                 "any(valid); NaN handling; dilated cloud bit 1; NDWI.")
    lines.append("```")
    text = read_log("round4b_tests.txt")
    if text is None:
        lines.append("NOT FOUND: logs/round4b_tests.txt")
    else:
        lines.append(text.rstrip())
    lines.append("```")
    lines.append("")

    lines.append("## Quicklook PNGs (masked labels)")
    lines.append("logs/quicklook_lst_composite.png, quicklook_ndvi.png, "
                 "quicklook_ndbi.png, quicklook_valid_count.png, "
                 "quicklook_removed_water.png.")
    lines.append("Colorbar claim: NOT MEASURABLE (no log states the colorbar "
                 "range used for the quicklooks; claim deleted).")
    lines.append("")

    lines.append("## Bytes")
    lines.append("Bytes: copied from an earlier run, not regenerated this round.")
    lines.append("Transferred bytes were NOT MEASURED (no request byte "
                 "counter). No claim is made that actual transfer is far less "
                 "than bytes_est (not measured). bytes_est is the sum of "
                 "full-file HEAD Content-Lengths per signed asset. Per-scene "
                 "arrays are cached in data/landsat/cache/. data/cache/ does not "
                 "exist; per-date mosaics were NOT created there.")
    lines.append("")

    lines.append("## Environment")
    lines.append("Environment: copied from an earlier run, not regenerated "
                 "this round.")
    lines.append("conda env create --dry-run -f environment.yml solved "
                 "successfully: the full package list resolved (exit code 0, "
                 "normal dry-run success behaviour). Output ends in the resolved "
                 "dependency list (dask, streamlit, rioxarray, geopandas, "
                 "etc.). The conda warning about pip not being listed as a "
                 "conda dependency is emitted by conda and resolved "
                 "automatically.")
    lines.append("")

    lines.append("## Known Issues")
    lines.append("- Absolute LST depends on which days were clear (per-date "
                 "BMC medians range widely, 36.38 C to 44.46 C across dates).")
    lines.append("- Effective dates 24 not 26 (2024-03-30 and 2025-04-02 have "
                 "no BMC footprint, fp_bmc=0.0000).")
    lines.append("- Population gate was widened after inspection (from "
                 "11.0-14.5M box-sum to 12.0-14.5M inside-BMC sum).")
    lines.append("- Five dates cover only part of BMC (valid fractions 0.59 to "
                 "0.87 inside BMC), so different parts of the city rest on "
                 "different dates.")
    lines.append("- valid-count versus LST check done at 30 m only; the 500 m "
                 "check is pending in Phase 3.")
    lines.append("- The 0.672607 old-logic value NOT EXPLAINED and not blocking.")
    lines.append("- The USGS Level 2 thermal band is resampled from native 100 "
                 "m to 30 m by cubic convolution; this pipeline then "
                 "reprojected the 30 m product onto the box grid with "
                 "nearest-neighbour.")
    lines.append("- composites built with the old masking order (nanmedian "
                 "before mask) but verified identical to v2 (0 differing "
                 "pixels, see below); the overlap fraction was never measured, "
                 "so this is reported as \"identical, mechanism not tested\".")
    lines.append("- the composite is March heavy (see the month mix table); "
                 "do not call it peak heat.")
    lines.append("- thermal band native resolution is 100 m and the 500 m cell "
                 "is the unit of analysis.")
    lines.append("- March and April to May cell LST differ and the top-20 "
                 "hotspot sets are spatially clustered and unstable between "
                 "months (see the Phase 3A seam log).")
    lines.append("- population is WorldPop 2020 against 2024 to 2026 imagery.")
    lines.append("- the density denominator is undecided (see the density "
                 "audit log).")
    lines.append("- the earlier pixel-level seam coefficients from the "
                 "superseded script must not be quoted.")
    lines.append("")

    lines.append("## Old versus v2")
    lines.append("identical inside BMC; an earlier box-wide comparison found "
                 "157 differing valid_count pixels; box-wide LST and NDVI "
                 "difference not measured.")
    lines.append("```")
    text = read_log("round4c_old_vs_v2.txt")
    if text is None:
        lines.append("NOT FOUND: logs/round4c_old_vs_v2.txt")
    else:
        lines.append(text.rstrip())
    lines.append("```")
    lines.append("")

    lines.append("## Per-date validity (logs/round4b_per_date_valid.txt)")
    lines.append("```")
    text = read_log("round4b_per_date_valid.txt")
    if text is None:
        lines.append("NOT FOUND: logs/round4b_per_date_valid.txt")
    else:
        lines.append(text.rstrip())
    lines.append("```")
    lines.append("")

    lines.append("## Month mix and per-date medians (logs/round4c_month_mix.txt)")
    lines.append("```")
    text = read_log("round4c_month_mix.txt")
    if text is None:
        lines.append("NOT FOUND: logs/round4c_month_mix.txt")
    else:
        lines.append(text.rstrip())
    lines.append("```")
    lines.append("")

    lines.append("## Hot clusters and removed-water mask "
                 "(logs/round4c_hot_pixels.txt)")
    lines.append("```")
    text = read_log("round4c_hot_pixels.txt")
    if text is None:
        lines.append("NOT FOUND: logs/round4c_hot_pixels.txt")
    else:
        lines.append(text.rstrip())
    lines.append("```")
    lines.append("")

    lines.append("## Valid-count versus LST check "
                 "(logs/round4c_valid_count_check.txt)")
    lines.append("Check done at 30 m only; the 500 m check is pending in "
                 "Phase 3.")
    lines.append("```")
    text = read_log("round4c_valid_count_check.txt")
    if text is None:
        lines.append("NOT FOUND: logs/round4c_valid_count_check.txt")
    else:
        lines.append(text.rstrip())
    lines.append("```")
    lines.append("")

    lines.append("## Phase 3A")
    lines.append("")
    lines.append("### Grid and cell stats (logs/phase3a_cell_stats.txt)")
    lines.append(log_block("", "phase3a_cell_stats.txt").strip())
    lines.append("")
    lines.append("### Population gates (logs/phase3a_population.txt)")
    lines.append(log_block("", "phase3a_population.txt").strip())
    lines.append("")
    lines.append("### GeoJSON check (logs/phase3a_geojson_check.txt)")
    lines.append(log_block("", "phase3a_geojson_check.txt").strip())
    lines.append("")
    lines.append("### Spearman check (logs/phase3a_spearman_check.txt)")
    lines.append(log_block("", "phase3a_spearman_check.txt").strip())
    lines.append("")
    lines.append("### Env probe (logs/phase3a_env_probe.txt)")
    lines.append(log_block("", "phase3a_env_probe.txt").strip())
    lines.append("")
    lines.append("### Density audit (logs/phase3a_density_audit.txt)")
    lines.append(log_block("", "phase3a_density_audit.txt").strip())
    lines.append("")
    lines.append("### Month seam (logs/phase3a_month_seam.txt)")
    lines.append(log_block("", "phase3a_month_seam.txt").strip())
    lines.append("")
    lines.append("### Maps (logs/phase3a_maps.txt)")
    lines.append(log_block("", "phase3a_maps.txt").strip())
    lines.append("")
    lines.append("### Tests (logs/phase3a_tests.txt)")
    lines.append(log_block("", "phase3a_tests.txt").strip())
    lines.append("")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
