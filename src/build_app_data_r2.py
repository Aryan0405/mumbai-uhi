"""Build slim app GeoJSON from existing CSVs and the master geojson (Read only).

Inputs (read only):
  data/processed/cells_500m.geojson
  data/processed/cells_index.csv
  data/processed/cells_index_sens.csv
  data/processed/cells_index_month.csv

Outputs (never overwrite):
  data/app/cells_app_r2.geojson   (mode "x", folder created if missing)
  logs/phase9_build.txt           (mode "x", always written on real run)

Optional argument --dry-run: run every stage in memory, write nothing, print
everything to stdout, exit. Structure: each stage in its own try/except. An
exception records "ERROR <stage>: <text>" and stops the run before any file is
written. The log is written in a finally block when not dry-run, so it always
exists after a real run. Exit nonzero on any FAIL or ERROR.
Every check prints: name, expected, observed, PASS or FAIL.
"""
import hashlib
import json
import os
import sys

import pandas as pd
from shapely.geometry import shape

GEOJSON = os.path.join("data", "processed", "cells_500m.geojson")
CSV_INDEX = os.path.join("data", "processed", "cells_index.csv")
CSV_SENS = os.path.join("data", "processed", "cells_index_sens.csv")
CSV_MONTH = os.path.join("data", "processed", "cells_index_month.csv")
OUT_DIR = os.path.join("data", "app")
OUT_GEOJSON = os.path.join(OUT_DIR, "cells_app_r2.geojson")
LOG_PATH = os.path.join("logs", "phase9_build.txt")

NUM_ROUND_4 = [
    "lst_mean", "ndvi_mean", "ndbi_mean", "H", "S", "E_raw",
    "index_primary", "index_noexp",
    "lst_march_c", "lst_aprmay_c",
    "index_primary_march", "index_primary_aprmay",
]
NUM_ROUND_2 = ["pop"]
NUM_ROUND_1 = ["pop_density_land"]

TOL = 1e-9

lines = []
failures = []
stop_requested = False


def check(name, expected, observed):
    status = "PASS" if observed == expected else "FAIL"
    if status == "FAIL":
        failures.append(name)
    lines.append("%s: expected=%s observed=%s %s" % (name, expected, observed, status))


def check_tol(name, expected, observed, tol):
    diff = abs(observed - expected)
    status = "PASS" if diff <= tol else "FAIL"
    if status == "FAIL":
        failures.append(name)
    lines.append("%s: expected=%.10g observed=%.10g diff=%.10g tol=%.10g %s" %
                 (name, expected, observed, diff, tol, status))


class StopRun(Exception):
    pass


def write_log():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    text = "\n".join(lines) + "\n"
    with open(LOG_PATH, "x", encoding="utf-8") as f:
        f.write(text)


def stage(name, fn):
    global stop_requested
    if stop_requested:
        return
    try:
        fn()
    except StopRun as e:
        lines.append(str(e))
        stop_requested = True
    except Exception as e:
        lines.append("ERROR %s: %r" % (name, e))
        stop_requested = True


# ---------------- B1 Load ----------------
def b1():
    global gj, gj_props, geom_by_id, gi, gs, gm, core_ids_gj
    with open(GEOJSON, "r", encoding="utf-8") as f:
        gj = json.load(f)
    feats = gj["features"]
    check("B1 geojson feature count", 2005, len(feats))
    non_polygon = sum(1 for ft in feats if ft.get("geometry", {}).get("type") != "Polygon")
    check("B1 all features Polygon", 0, non_polygon)
    gj_props = {}
    geom_by_id = {}
    for ft in feats:
        p = ft.get("properties", {}) or {}
        cid = p["cell_id"]
        gj_props[cid] = p
        geom_by_id[cid] = ft.get("geometry")
    core_ids_gj = set(cid for cid, p in gj_props.items() if p.get("core") is True)
    check("B1 geojson core features", 1794, len(core_ids_gj))
    # geometry present for every core feature
    missing_geom = sum(1 for cid in core_ids_gj if geom_by_id.get(cid) is None)
    check("B1 core feature geometry present", 0, missing_geom)
    gi = pd.read_csv(CSV_INDEX)
    gs = pd.read_csv(CSV_SENS)
    gm = pd.read_csv(CSV_MONTH)
    lines.append("B1 loaded cells_index.csv rows=%d cells_index_sens.csv rows=%d cells_index_month.csv rows=%d" %
                 (len(gi), len(gs), len(gm)))


# ---------------- B2 ID agreement ----------------
def b2():
    global core_ids_gj, core_ids_gi, core_ids_gs, core_ids_gm
    core_ids_gi = set(gi["cell_id"].values)
    core_ids_gs = set(gs["cell_id"].values)
    gm_core = gm[gm["core"] == True]
    core_ids_gm = set(gm_core["cell_id"].values)
    lines.append("B2 core cell_id sizes: geojson=%d cells_index=%d sens=%d month=%d" %
                 (len(core_ids_gj), len(core_ids_gi), len(core_ids_gs), len(core_ids_gm)))
    check("B2 geojson core ids == cells_index ids", True, core_ids_gj == core_ids_gi)
    check("B2 geojson core ids == sens ids", True, core_ids_gj == core_ids_gs)
    check("B2 geojson core ids == month core ids", True, core_ids_gj == core_ids_gm)
    bad = []
    for ft in gj["features"]:
        p = ft.get("properties", {}) or {}
        if p.get("cell_id") != p.get("cell_row") * 48 + p.get("cell_col"):
            bad.append(p.get("cell_id"))
    check("B2 geojson cell_id == cell_row*48 + cell_col for every feature", 0, len(bad))


# ---------------- B3 Value agreement ----------------
def b3():
    index_by_id = gi.set_index("cell_id")
    cid_list = sorted(core_ids_gj)
    mismatches = {}
    for col in ["lst_mean", "ndvi_mean", "ndbi_mean", "pop", "pop_density_land"]:
        csv_vals = index_by_id.loc[cid_list, col].values
        mism = 0
        for cid, a in zip(cid_list, csv_vals):
            b = gj_props[cid][col]
            if abs(float(a) - float(b)) > TOL:
                mism += 1
        mismatches[col] = mism
        lines.append("B3 %s mismatches (expected 0): %d" % (col, mism))
        check("B3 " + col + " agrees within 1e-9", 0, mism)
    thin_by_id = index_by_id.loc[cid_list, "thin_obs"].values
    thin_mism = 0
    thin_bad = []
    for cid, a in zip(cid_list, thin_by_id):
        b = gj_props[cid]["thin_obs"]
        if bool(a) != bool(b):
            thin_mism += 1
            thin_bad.append(cid)
    lines.append("B3 thin_obs mismatches (expected 0): %d" % thin_mism)
    check("B3 thin_obs agrees", 0, thin_mism)
    if thin_mism > 0:
        lines.append("B3 thin_obs mismatching cell_ids: " + str(sorted(thin_bad)))
        raise StopRun("B3 thin_obs mismatch; stopping without choosing a source")


# ---------------- B4 Null check ----------------
def b4():
    core_list = sorted(core_ids_gj)
    index_by_id = gi.set_index("cell_id")
    gi_core = index_by_id.loc[core_list]
    for col in ["lst_mean", "ndvi_mean", "ndbi_mean", "pop", "pop_density_land",
                "H", "S", "E_raw", "index_primary", "index_noexp",
                "rank_primary", "rank_noexp", "zone_primary", "zone_noexp",
                "thin_obs", "zero_pop", "low_confidence", "cell_row", "cell_col"]:
        nulls = int(gi_core[col].isna().sum())
        check("B4 csv index " + col + " nulls on core cells", 0, nulls)
    sens_by_id = gs.set_index("cell_id")
    gs_core = sens_by_id.loc[core_list]
    for col in ["zone_robust", "zone_fragile", "zone_count"]:
        nulls = int(gs_core[col].isna().sum())
        check("B4 csv sens " + col + " nulls on core cells", 0, nulls)
    gm_core = gm[gm["cell_id"].isin(core_ids_gj)]
    for col in ["lst_march_c", "lst_aprmay_c", "index_primary_march",
                "index_primary_aprmay", "zone_primary_march", "zone_primary_aprmay"]:
        nulls = int(gm_core[col].isna().sum())
        check("B4 csv month " + col + " nulls on core cells", 0, nulls)
    gm_core_nz = gm_core[gm_core["zone_primary"] == True]
    nulls = int(gm_core_nz["month_class"].isna().sum())
    check("B4 csv month month_class nulls on zone_primary core cells", 0, nulls)
    # geojson geometry already checked present in B1; reaffirm no null geometry
    null_geom = sum(1 for cid in core_list if geom_by_id.get(cid) is None)
    check("B4 geojson geometry null on core cells", 0, null_geom)


# ---------------- B5 Build features ----------------
def b5():
    global features_out, props_out
    sens_by_id = gs.set_index("cell_id")
    month_by_id = gm.set_index("cell_id")
    index_by_id = gi.set_index("cell_id")
    core_list = sorted(core_ids_gj)
    crs = gj.get("crs", None)
    features_out = []
    props_out = []
    seen = set()
    for cid in core_list:
        geom = geom_by_id.get(cid)
        if geom is None:
            raise StopRun("B5 feature %d has no geometry" % cid)
        new_rings = []
        for ring in geom["coordinates"]:
            new_ring = [[round(float(x), 5), round(float(y), 5)] for x, y in ring]
            new_rings.append(new_ring)
        new_geom = {"type": "Polygon", "coordinates": new_rings}
        for ring in new_rings:
            if ring[0] != ring[-1]:
                raise StopRun("B5 feature %d ring not closed after rounding" % cid)
        if not shape(new_geom).is_valid:
            raise StopRun("B5 feature %d polygon invalid after rounding" % cid)
        if cid in seen:
            raise StopRun("B5 duplicate cell_id %d" % cid)
        seen.add(cid)
        iv = index_by_id.loc[cid]
        sv = sens_by_id.loc[cid]
        mv = month_by_id.loc[cid]
        month_class = mv["month_class"]
        if pd.isna(month_class):
            month_class_out = None
        else:
            month_class_out = str(month_class)
        props = {
            "cell_id": int(cid),
            "row": int(iv["cell_row"]),
            "col": int(iv["cell_col"]),
            "lst_mean": round(float(iv["lst_mean"]), 4),
            "ndvi_mean": round(float(iv["ndvi_mean"]), 4),
            "ndbi_mean": round(float(iv["ndbi_mean"]), 4),
            "pop": round(float(iv["pop"]), 2),
            "pop_density_land": round(float(iv["pop_density_land"]), 1),
            "H": round(float(iv["H"]), 4),
            "S": round(float(iv["S"]), 4),
            "E_raw": round(float(iv["E_raw"]), 4),
            "index_primary": round(float(iv["index_primary"]), 4),
            "index_noexp": round(float(iv["index_noexp"]), 4),
            "rank_primary": int(iv["rank_primary"]),
            "rank_noexp": int(iv["rank_noexp"]),
            "zone_primary": bool(iv["zone_primary"]),
            "zone_noexp": bool(iv["zone_noexp"]),
            "thin_obs": bool(iv["thin_obs"]),
            "zero_pop": bool(iv["zero_pop"]),
            "low_confidence": bool(iv["low_confidence"]),
            "lst_march_c": round(float(mv["lst_march_c"]), 4),
            "lst_aprmay_c": round(float(mv["lst_aprmay_c"]), 4),
            "index_primary_march": round(float(mv["index_primary_march"]), 4),
            "index_primary_aprmay": round(float(mv["index_primary_aprmay"]), 4),
            "zone_primary_march": bool(mv["zone_primary_march"]),
            "zone_primary_aprmay": bool(mv["zone_primary_aprmay"]),
            "month_class": month_class_out,
            "zone_robust": bool(sv["zone_robust"]),
            "zone_fragile": bool(sv["zone_fragile"]),
            "zone_count": int(sv["zone_count"]),
        }
        features_out.append({"type": "Feature", "geometry": new_geom, "properties": props})
        props_out.append(props)
    check("B5 feature count", 1794, len(features_out))


# ---------------- B6 Pre-write checks ----------------
def b6():
    zone_p_sum = sum(1 for f in features_out if f["properties"]["zone_primary"] is True)
    zone_r_sum = sum(1 for f in features_out if f["properties"]["zone_robust"] is True)
    zone_f_sum = sum(1 for f in features_out if f["properties"]["zone_fragile"] is True)
    thin_sum = sum(1 for f in features_out if f["properties"]["thin_obs"] is True)
    zm_sum = sum(1 for f in features_out if f["properties"]["zone_primary_march"] is True)
    za_sum = sum(1 for f in features_out if f["properties"]["zone_primary_aprmay"] is True)
    mc = [f["properties"]["month_class"] for f in features_out]
    mc_both = sum(1 for v in mc if v == "BOTH")
    mc_om = sum(1 for v in mc if v == "ONLY_MARCH")
    mc_oa = sum(1 for v in mc if v == "ONLY_APRMAY")
    mc_ne = sum(1 for v in mc if v == "NEITHER")
    mc_null = sum(1 for v in mc if v is None)
    lines.append("B6 zone_primary=%d zone_robust=%d zone_fragile=%d thin_obs=%d zm=%d za=%d" %
                 (zone_p_sum, zone_r_sum, zone_f_sum, thin_sum, zm_sum, za_sum))
    lines.append("B6 month_class BOTH=%d ONLY_MARCH=%d ONLY_APRMAY=%d NEITHER=%d null=%d" %
                 (mc_both, mc_om, mc_oa, mc_ne, mc_null))
    check("B6 feature count", 1794, len(features_out))
    check("B6 sum zone_primary", 180, zone_p_sum)
    check("B6 sum zone_robust", 107, zone_r_sum)
    check("B6 sum zone_fragile", 73, zone_f_sum)
    check("B6 sum thin_obs", 83, thin_sum)
    check("B6 sum zone_primary_march", 180, zm_sum)
    check("B6 sum zone_primary_aprmay", 180, za_sum)
    check("B6 month_class BOTH", 158, mc_both)
    check("B6 month_class ONLY_MARCH", 11, mc_om)
    check("B6 month_class ONLY_APRMAY", 8, mc_oa)
    check("B6 month_class NEITHER", 3, mc_ne)
    check("B6 month_class null", 1614, mc_null)
    r_set = set(f["properties"]["cell_id"] for f in features_out if f["properties"]["zone_robust"])
    f_set = set(f["properties"]["cell_id"] for f in features_out if f["properties"]["zone_fragile"])
    p_set = set(f["properties"]["cell_id"] for f in features_out if f["properties"]["zone_primary"])
    check("B6 zone_robust and zone_fragile disjoint", True, len(r_set & f_set) == 0)
    check("B6 zone_robust union zone_fragile equals zone_primary", True, (r_set | f_set) == p_set)


# ---------------- B7 Write ----------------
def b7():
    global dry_run, out_text
    if dry_run:
        return
    out = {"type": "FeatureCollection", "name": "cells_app_r2",
           "crs": gj.get("crs"), "features": features_out}
    out_text = json.dumps(out, allow_nan=False, ensure_ascii=True,
                          separators=(",", ":"))
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_GEOJSON, "x", encoding="utf-8") as f:
        f.write(out_text)
    size = os.path.getsize(OUT_GEOJSON)
    digest = hashlib.sha256(out_text.encode("utf-8")).hexdigest()
    lines.append("B7 wrote %s size bytes=%d" % (OUT_GEOJSON, size))
    lines.append("B7 sha256 %s" % digest)


# ---------------- B8 Round trip ----------------
def b8():
    global dry_run, out_text
    if dry_run:
        return
    raw = out_text
    for tok in ["NaN", "Infinity", "-Infinity"]:
        if tok in raw:
            raise StopRun("B8 raw text contains %s token" % tok)
    with open(OUT_GEOJSON, "r", encoding="utf-8") as f:
        back = json.load(f)
    check("B8 roundtrip feature count", 1794, len(back["features"]))
    for ft, mem in zip(back["features"], features_out):
        bp = ft.get("properties", {}) or {}
        mp = mem["properties"]
        for k in mp:
            if bp.get(k) != mp[k]:
                raise StopRun("B8 property %s differs for cell %d" % (k, mp["cell_id"]))


def main():
    global dry_run, stop_requested
    stages = [("B1 Load", b1), ("B2 ID agreement", b2), ("B3 Value agreement", b3),
              ("B4 Null check", b4), ("B5 Build features", b5), ("B6 Pre-write checks", b6),
              ("B7 Write", b7), ("B8 Round trip", b8)]
    dry_run = (sys.argv[1:] == ["--dry-run"])
    if len(sys.argv) > 1 and sys.argv[1] != "--dry-run":
        lines.append("usage: python src/build_app_data_r2.py [--dry-run]")
        stop_requested = True
    try:
        for name, fn in stages:
            if stop_requested:
                break
            stage(name, fn)
    finally:
        text = "\n".join(lines) + "\n"
        print(text)
        if not dry_run:
            write_log()
    if failures or stop_requested:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
