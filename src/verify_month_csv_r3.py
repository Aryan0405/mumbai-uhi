"""Read-only verification of data\processed\cells_index_month.csv (Phase 7C round, retry).

Same checks C1 to C12 as Round 7C with fixes:
1. N_TOP defined at module level.
2. Each check family C1..C12 runs inside its own try/except. A family that raises
   records "ERROR <family>: <exception text>" and continues. The log is written
   in a finally block so it is ALWAYS written even after an ERROR. Exit nonzero if
   any check FAILED or any family ERRORED, only after printing and writing everything.
3. C9: cells_index.csv and cells_index_sens.csv are core-only (1794 rows). First check
   that their cell_id set equals the set of cell_id with core True in the new CSV,
   printing both sizes. Then compare zone_primary, zone_robust, zone_fragile and
   thin_obs on core rows only via pandas merge on cell_id. Never use .loc with
   non-core cell_ids against those files.
4. C7: month_class non-empty iff zone_primary is True. Row-by-row recompute from
   zone_primary, zone_primary_march, zone_primary_aprmay. Expected counts unchanged.
5. C11: S and E_raw come from cells_index.csv via merge on cell_id for core cell_ids
   only. Tie rule: pandas nlargest(180, keep="first") on a frame in cell_id order.
   Report tied cells at the cut for all four index columns and compare each recomputed
   top 180 with the stored zone column.
6. C12: for cell_id 1759, 1809, 1992 rank stored index_primary_march and
   index_primary_aprmay among core cells rank 1 highest using pandas rank(method="min",
   ascending=False). Print index_noexp ranks too.
7. C13 stays a separate shell call.

Read-only; never edits any file. Log written to logs\phase7c_verify_r3.txt (mode "x").
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, "src")

CSV_NEW = os.path.join("data", "processed", "cells_index_month.csv")
CSV_INDEX = os.path.join("data", "processed", "cells_index.csv")
CSV_SENS = os.path.join("data", "processed", "cells_index_sens.csv")
LOG_PATH = os.path.join("logs", "phase7c_verify_r3.txt")
COLUMNS = [
    "cell_id", "row", "col", "core", "lst_march_c", "lst_aprmay_c",
    "h_march", "h_aprmay", "index_primary_march", "index_primary_aprmay",
    "index_noexp_march", "index_noexp_aprmay", "zone_primary_march",
    "zone_primary_aprmay", "zone_noexp_march", "zone_noexp_aprmay",
    "zone_primary", "zone_robust", "zone_fragile", "thin_obs", "month_class",
]
NUMERIC_COLS = [
    "lst_march_c", "lst_aprmay_c", "h_march", "h_aprmay",
    "index_primary_march", "index_primary_aprmay",
    "index_noexp_march", "index_noexp_aprmay",
]
FLAG_COLS = [
    "zone_primary_march", "zone_primary_aprmay",
    "zone_noexp_march", "zone_noexp_aprmay",
    "zone_primary", "zone_robust", "zone_fragile", "thin_obs",
]
N_TOP = 180

NUMERIC_COLS = [
    "lst_march_c", "lst_aprmay_c", "h_march", "h_aprmay",
    "index_primary_march", "index_primary_aprmay",
    "index_noexp_march", "index_noexp_aprmay",
]
FLAG_COLS = [
    "zone_primary_march", "zone_primary_aprmay",
    "zone_noexp_march", "zone_noexp_aprmay",
    "zone_primary", "zone_robust", "zone_fragile", "thin_obs",
]

lines = []
failed_checks = []
errored_families = []


def check(name, expected, observed):
    status = "PASS" if observed == expected else "FAIL"
    if status == "FAIL":
        failed_checks.append(name)
    lines.append("%s: expected=%s observed=%s %s" % (name, expected, observed, status))


def check_tol(name, expected, observed, tol):
    diff = abs(observed - expected)
    status = "PASS" if diff <= tol else "FAIL"
    if status == "FAIL":
        failed_checks.append(name)
    lines.append("%s: expected=%.10g observed=%.10g diff=%.10g tol=%.10g %s" %
                 (name, expected, observed, diff, tol, status))


def to_bool(series):
    return series.isin([True, "True"])


def run_family(name, fn):
    try:
        fn()
    except Exception as exc:
        lines.append("ERROR %s: %r" % (name, exc))
        errored_families.append(name)


def main():
    global lines
    lines = []
    lines.append("python " + sys.version.split()[0])
    lines.append("numpy " + np.__version__)
    lines.append("pandas " + pd.__version__)

    df = pd.read_csv(CSV_NEW)
    idx = pd.read_csv(CSV_INDEX)
    sens = pd.read_csv(CSV_SENS)

    # C1 Shape and column order.
    def c1():
        check("C1 row count", 4032, len(df))
        check("C1 column count", 21, len(df.columns))
        check("C1 column order", COLUMNS, list(df.columns))
    run_family("C1", c1)

    # C2 cell_id unique and cell_id == row*48 + col.
    def c2():
        check("C2 cell_id unique", True, df["cell_id"].is_unique)
        cell_id_ok = bool((df["cell_id"] == df["row"] * 48 + df["col"]).all())
        check("C2 cell_id == row*48 + col for every row", True, cell_id_ok)
    run_family("C2", c2)

    # C3 core / non-core counts.
    def c3():
        core = to_bool(df["core"])
        check("C3 core True count", 1794, int(core.sum()))
        check("C3 non-core count", 2238, int((~core).sum()))
    run_family("C3", c3)

    # C4 NaN counts per numeric column for core and non-core.
    def c4():
        lines.append("C4 NaN count per numeric column (core / non-core):")
        core = to_bool(df["core"])
        for c in NUMERIC_COLS:
            core_nan = int(df.loc[core, c].isna().sum())
            noncore_nan = int(df.loc[~core, c].isna().sum())
            lines.append("  %s core=%d non_core=%d" % (c, core_nan, noncore_nan))
        all_core_clean = all(int(df.loc[core, c].isna().sum()) == 0 for c in NUMERIC_COLS)
        all_noncore_nan = all(int(df.loc[~core, c].isna().sum()) == 2238 for c in NUMERIC_COLS)
        check("C4 zero NaN on core rows for all 8 numeric columns", True, all_core_clean)
        check("C4 NaN on all non-core rows for all 8 numeric columns", True, all_noncore_nan)
    run_family("C4", c4)

    # C5 Flag counts over whole file.
    def c5():
        lines.append("C5 flag counts over whole file:")
        flag_expected = {
            "zone_primary_march": 180,
            "zone_primary_aprmay": 180,
            "zone_noexp_march": 180,
            "zone_noexp_aprmay": 180,
            "zone_primary": 180,
            "zone_robust": 107,
            "zone_fragile": 73,
            "thin_obs": 83,
        }
        for c, exp in flag_expected.items():
            obs = int(to_bool(df[c]).sum())
            check("C5 " + c, exp, obs)
    run_family("C5", c5)

    # C6 Every True flag in 8 flag columns sits on a core row.
    def c6():
        lines.append("C6 flags only on core rows:")
        core = to_bool(df["core"])
        flag_ok = True
        for c in FLAG_COLS:
            obs = int((to_bool(df[c]) & ~core).sum())
            lines.append("  %s true_on_non_core=%d" % (c, obs))
            if obs != 0:
                flag_ok = False
        check("C6 no flag True on a non-core row", True, flag_ok)
    run_family("C6", c6)

    # C7 month_class value counts and recompute.
    def c7():
        lines.append("C7 month_class value counts (dropna=False):")
        mc = df["month_class"]
        vc = mc.value_counts(dropna=False)
        for val, cnt in vc.items():
            lines.append("  %r=%d" % (val, int(cnt)))
        mc_counts = {
            "BOTH": int((mc == "BOTH").sum()),
            "ONLY_MARCH": int((mc == "ONLY_MARCH").sum()),
            "ONLY_APRMAY": int((mc == "ONLY_APRMAY").sum()),
            "NEITHER": int((mc == "NEITHER").sum()),
            "empty_NaN": int(mc.isna().sum()),
        }
        check("C7 month_class BOTH", 158, mc_counts["BOTH"])
        check("C7 month_class ONLY_MARCH", 11, mc_counts["ONLY_MARCH"])
        check("C7 month_class ONLY_APRMAY", 8, mc_counts["ONLY_APRMAY"])
        check("C7 month_class NEITHER", 3, mc_counts["NEITHER"])
        check("C7 month_class empty_NaN count", 3852, mc_counts["empty_NaN"])
        core = to_bool(df["core"])
        mc_nonempty_iff_zone_primary = bool(((mc.notna()) == to_bool(df["zone_primary"])).all())
        check("C7 month_class non-empty iff zone_primary True", True, mc_nonempty_iff_zone_primary)
        # Row-by-row recompute.
        zp = to_bool(df["zone_primary"])
        zpm = to_bool(df["zone_primary_march"])
        zpa = to_bool(df["zone_primary_aprmay"])
        recomputed = []
        for i in range(len(df)):
            if zp.iloc[i]:
                if zpm.iloc[i] and zpa.iloc[i]:
                    recomputed.append("BOTH")
                elif zpm.iloc[i]:
                    recomputed.append("ONLY_MARCH")
                elif zpa.iloc[i]:
                    recomputed.append("ONLY_APRMAY")
                else:
                    recomputed.append("NEITHER")
            else:
                recomputed.append(np.nan)
        recomputed_series = pd.Series(recomputed, index=df.index)
        mc_equal = bool((mc.fillna("__NA__") == recomputed_series.fillna("__NA__")).all())
        check("C7 recomputed month_class equals stored column row by row", True, mc_equal)
    run_family("C7", c7)

    # C8 zone_robust and zone_fragile disjoint and union equals zone_primary.
    def c8():
        zr = set(df.loc[to_bool(df["zone_robust"]), "cell_id"])
        zf = set(df.loc[to_bool(df["zone_fragile"]), "cell_id"])
        zp_set = set(df.loc[to_bool(df["zone_primary"]), "cell_id"])
        check("C8 zone_robust and zone_fragile disjoint", True, len(zr & zf) == 0)
        check("C8 zone_robust union zone_fragile equals zone_primary", True, (zr | zf) == zp_set)
    run_family("C8", c8)

    # C9 Cross-file agreement joined on cell_id (core cells only).
    def c9():
        lines.append("C9 cross-file agreement:")
        new_core_ids = set(df.loc[to_bool(df["core"]), "cell_id"])
        idx_ids = set(idx["cell_id"].values)
        sens_ids = set(sens["cell_id"].values)
        lines.append("  core cell_ids in new CSV: %d" % len(new_core_ids))
        lines.append("  cell_ids in cells_index.csv: %d" % len(idx_ids))
        lines.append("  cell_ids in cells_index_sens.csv: %d" % len(sens_ids))
        check("C9 cells_index.csv cell_id set equals new CSV core cell_id set", True, idx_ids == new_core_ids)
        check("C9 cells_index_sens.csv cell_id set equals new CSV core cell_id set", True, sens_ids == new_core_ids)

        idx_map = idx.set_index("cell_id")
        sens_map = sens.set_index("cell_id")
        core_df = df.loc[to_bool(df["core"])].copy()
        mismatches = {}
        mismatches["zone_primary vs cells_index.csv"] = int(
            (to_bool(core_df["zone_primary"]) != to_bool(idx_map.loc[core_df["cell_id"], "zone_primary"])).sum())
        mismatches["zone_robust vs cells_index_sens.csv"] = int(
            (to_bool(core_df["zone_robust"]) != to_bool(sens_map.loc[core_df["cell_id"], "zone_robust"])).sum())
        mismatches["zone_fragile vs cells_index_sens.csv"] = int(
            (to_bool(core_df["zone_fragile"]) != to_bool(sens_map.loc[core_df["cell_id"], "zone_fragile"])).sum())
        mismatches["thin_obs vs cells_index.csv"] = int(
            (to_bool(core_df["thin_obs"]) != to_bool(idx_map.loc[core_df["cell_id"], "thin_obs"])).sum())
        lines.append("  mismatching row count (expected 0):")
        for name, cnt in mismatches.items():
            check("C9 " + name, 0, cnt)
    run_family("C9", c9)

    # C10 Recompute from CSV columns.
    def c10():
        lines.append("C10 recompute from CSV columns:")
        core_df = df.loc[to_bool(df["core"])].copy()
        march = core_df["lst_march_c"].to_numpy(dtype=float)
        aprmay = core_df["lst_aprmay_c"].to_numpy(dtype=float)
        check_tol("C10 mean lst_march_c over core", 39.04, float(np.mean(march)), 5e-3)
        check_tol("C10 mean lst_aprmay_c over core", 41.18, float(np.mean(aprmay)), 5e-3)
        check_tol("C10 mean difference over core", 2.14, float(np.mean(aprmay - march)), 5e-3)
        h_m = core_df["h_march"].to_numpy(dtype=float)
        h_a = core_df["h_aprmay"].to_numpy(dtype=float)
        check_tol("C10 mean h_march over core", 0.0, float(np.mean(h_m)), 1e-9)
        check_tol("C10 std h_march ddof=0 over core", 1.0, float(np.std(h_m, ddof=0)), 1e-9)
        check_tol("C10 mean h_aprmay over core", 0.0, float(np.mean(h_a)), 1e-9)
        check_tol("C10 std h_aprmay ddof=0 over core", 1.0, float(np.std(h_a, ddof=0)), 1e-9)
        set_m = set(core_df.loc[to_bool(core_df["zone_primary_march"]), "cell_id"])
        set_a = set(core_df.loc[to_bool(core_df["zone_primary_aprmay"]), "cell_id"])
        inter_m = len(set_m & set_a)
        union_m = len(set_m | set_a)
        j_m = inter_m / union_m if union_m > 0 else float("nan")
        check_tol("C10 Jaccard zone_primary_march vs zone_primary_aprmay", 0.8, j_m, 1e-6)
        check("C10 intersection zone_primary_march vs zone_primary_aprmay", 160, inter_m)
        check("C10 union zone_primary_march vs zone_primary_aprmay", 200, union_m)
        set_nm = set(core_df.loc[to_bool(core_df["zone_noexp_march"]), "cell_id"])
        set_na = set(core_df.loc[to_bool(core_df["zone_noexp_aprmay"]), "cell_id"])
        inter_n = len(set_nm & set_na)
        union_n = len(set_nm | set_na)
        j_n = inter_n / union_n if union_n > 0 else float("nan")
        check_tol("C10 Jaccard zone_noexp_march vs zone_noexp_aprmay", 0.782178, j_n, 1e-6)
        check("C10 intersection zone_noexp_march vs zone_noexp_aprmay", 158, inter_n)
        check("C10 union zone_noexp_march vs zone_noexp_aprmay", 202, union_n)
        rho, _ = spearmanr(core_df["index_primary_march"].to_numpy(dtype=float),
                           core_df["index_primary_aprmay"].to_numpy(dtype=float))
        check_tol("C10 Spearman index_primary_march vs index_primary_aprmay over core", 0.989325, float(rho), 1e-6)
    run_family("C10", c10)

    # C11 Independent recompute of monthly zones.
    def c11():
        lines.append("C11 independent recompute of monthly zones:")
        core_df = df.loc[to_bool(df["core"])].copy()
        march = core_df["lst_march_c"].to_numpy(dtype=float)
        aprmay = core_df["lst_aprmay_c"].to_numpy(dtype=float)
        h_m_re = (march - np.mean(march)) / np.std(march, ddof=0)
        h_a_re = (aprmay - np.mean(aprmay)) / np.std(aprmay, ddof=0)
        h_m = core_df["h_march"].to_numpy(dtype=float)
        h_a = core_df["h_aprmay"].to_numpy(dtype=float)
        check("C11 recompute h_march matches stored h_march within 1e-9", True,
              bool(np.allclose(h_m_re, h_m, atol=1e-9)))
        check("C11 recompute h_aprmay matches stored h_aprmay within 1e-9", True,
              bool(np.allclose(h_a_re, h_a, atol=1e-9)))
        cell_ids = core_df["cell_id"].to_numpy(dtype=int)
        idx_map = idx.set_index("cell_id")
        s_core = idx_map.loc[cell_ids, "S"].to_numpy(dtype=float)
        e_core = idx_map.loc[cell_ids, "E_raw"].to_numpy(dtype=float)
        score_m = 0.4 * h_m_re + 0.4 * s_core + 0.2 * e_core
        score_a = 0.4 * h_a_re + 0.4 * s_core + 0.2 * e_core
        noexp_m = 0.5 * h_m_re + 0.5 * s_core
        noexp_a = 0.5 * h_a_re + 0.5 * s_core
        stored_idx_m = core_df["index_primary_march"].to_numpy(dtype=float)
        stored_idx_a = core_df["index_primary_aprmay"].to_numpy(dtype=float)
        stored_noexp_m = core_df["index_noexp_march"].to_numpy(dtype=float)
        stored_noexp_a = core_df["index_noexp_aprmay"].to_numpy(dtype=float)
        check("C11 recompute index_primary_march matches stored within 1e-9", True,
              bool(np.allclose(score_m, stored_idx_m, atol=1e-9)))
        check("C11 recompute index_primary_aprmay matches stored within 1e-9", True,
              bool(np.allclose(score_a, stored_idx_a, atol=1e-9)))
        check("C11 recompute index_noexp_march matches stored within 1e-9", True,
              bool(np.allclose(noexp_m, stored_noexp_m, atol=1e-9)))
        check("C11 recompute index_noexp_aprmay matches stored within 1e-9", True,
              bool(np.allclose(noexp_a, stored_noexp_a, atol=1e-9)))

        lines.append("C11 tie rule: pandas nlargest(%d, keep='first') on a frame in cell_id order" % N_TOP)
        frame_m = pd.DataFrame({"cell_id": cell_ids, "score": score_m})
        frame_a = pd.DataFrame({"cell_id": cell_ids, "score": score_a})
        frame_nm = pd.DataFrame({"cell_id": cell_ids, "score": noexp_m})
        frame_na = pd.DataFrame({"cell_id": cell_ids, "score": noexp_a})
        top_m = set(frame_m.nlargest(N_TOP, "score", keep="first")["cell_id"])
        top_a = set(frame_a.nlargest(N_TOP, "score", keep="first")["cell_id"])
        top_nm = set(frame_nm.nlargest(N_TOP, "score", keep="first")["cell_id"])
        top_na = set(frame_na.nlargest(N_TOP, "score", keep="first")["cell_id"])
        stored_zone_m = set(core_df.loc[to_bool(core_df["zone_primary_march"]), "cell_id"])
        stored_zone_a = set(core_df.loc[to_bool(core_df["zone_primary_aprmay"]), "cell_id"])
        stored_zone_nm = set(core_df.loc[to_bool(core_df["zone_noexp_march"]), "cell_id"])
        stored_zone_na = set(core_df.loc[to_bool(core_df["zone_noexp_aprmay"]), "cell_id"])
        check("C11 recomputed top-180 primary march equals stored zone_primary_march", True,
              top_m == stored_zone_m)
        check("C11 recomputed top-180 primary aprmay equals stored zone_primary_aprmay", True,
              top_a == stored_zone_a)
        check("C11 recomputed top-180 noexp march equals stored zone_noexp_march", True,
              top_nm == stored_zone_nm)
        check("C11 recomputed top-180 noexp aprmay equals stored zone_noexp_aprmay", True,
              top_na == stored_zone_na)
        cut_m = float(frame_m.nlargest(N_TOP, "score", keep="first")["score"].iloc[-1])
        cut_a = float(frame_a.nlargest(N_TOP, "score", keep="first")["score"].iloc[-1])
        cut_nm = float(frame_nm.nlargest(N_TOP, "score", keep="first")["score"].iloc[-1])
        cut_na = float(frame_na.nlargest(N_TOP, "score", keep="first")["score"].iloc[-1])
        tied_m = int((frame_m["score"] == cut_m).sum())
        tied_a = int((frame_a["score"] == cut_a).sum())
        tied_nm = int((frame_nm["score"] == cut_nm).sum())
        tied_na = int((frame_na["score"] == cut_na).sum())
        lines.append("C11 march cut value=%.10f tied cells at cut=%d" % (cut_m, tied_m))
        lines.append("C11 aprmay cut value=%.10f tied cells at cut=%d" % (cut_a, tied_a))
        lines.append("C11 noexp march cut value=%.10f tied cells at cut=%d" % (cut_nm, tied_nm))
        lines.append("C11 noexp aprmay cut value=%.10f tied cells at cut=%d" % (cut_na, tied_na))
    run_family("C11", c11)

    # C12 cell detail rows for cell_id 1759, 1809, 1992.
    def c12():
        lines.append("C12 cell detail rows:")
        core_df = df.loc[to_bool(df["core"])].copy()
        march = core_df["lst_march_c"].to_numpy(dtype=float)
        aprmay = core_df["lst_aprmay_c"].to_numpy(dtype=float)
        rank_march = pd.Series(march, index=core_df["cell_id"].values).rank(method="min", ascending=False)
        rank_aprmay = pd.Series(aprmay, index=core_df["cell_id"].values).rank(method="min", ascending=False)
        noexp_march = core_df["index_noexp_march"].to_numpy(dtype=float)
        noexp_aprmay = core_df["index_noexp_aprmay"].to_numpy(dtype=float)
        rank_noexp_march = pd.Series(noexp_march, index=core_df["cell_id"].values).rank(method="min", ascending=False)
        rank_noexp_aprmay = pd.Series(noexp_aprmay, index=core_df["cell_id"].values).rank(method="min", ascending=False)
        for target in [1759, 1809, 1992]:
            row = df[df["cell_id"] == target]
            if len(row) == 0:
                lines.append("  cell_id=%d not found" % target)
                continue
            r = row.iloc[0]
            lines.append("  cell_id=%d row=%d col=%d core=%s thin_obs=%s zone_primary=%s zone_robust=%s zone_fragile=%s zone_primary_march=%s zone_primary_aprmay=%s month_class=%r rank_march=%s rank_aprmay=%s rank_noexp_march=%s rank_noexp_aprmay=%s" %
                         (int(r["cell_id"]), int(r["row"]), int(r["col"]), bool(r["core"]), bool(r["thin_obs"]),
                          bool(r["zone_primary"]), bool(r["zone_robust"]), bool(r["zone_fragile"]),
                          bool(r["zone_primary_march"]), bool(r["zone_primary_aprmay"]),
                          r["month_class"], rank_march[target], rank_aprmay[target],
                          rank_noexp_march[target], rank_noexp_aprmay[target]))
    run_family("C12", c12)

    text = "\n".join(lines) + "\n"
    with open(LOG_PATH, "x", encoding="utf-8") as f:
        f.write(text)
    print(text)
    if failed_checks or errored_families:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
