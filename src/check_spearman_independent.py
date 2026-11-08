"""Compare src/stats_utils.spearman_rho against pandas Series.corr(method='spearman')
on real cell-table column pairs.

The pandas side runs in its own subprocess because scipy/numpy corrcoef has
been observed to crash in this environment (see logs/phase3a_scipy_diag.txt).
Prints both values and the absolute difference per pair. Logs to
logs/phase3a_spearman_check.txt. Stops if any difference exceeds 1e-9.
"""
import os
import subprocess
import sys
import textwrap

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
from stats_utils import spearman_rho

CSV = "data/processed/cells_500m.csv"
PYTHON = r"C:\Users\Aryan\anaconda3\envs\uhi\python.exe"
THRESHOLD = 1e-9

PAIRS = [
    ("lst_mean", "lst_median"),
    ("lst_mean", "ndvi_mean"),
    ("lst_mean", "ndbi_mean"),
]


def bmc_frame():
    df = pd.read_csv(CSV)
    m = (df["n_bmc_px"] > 0) & (df["n_land_px"] > 0)
    return df.loc[m]


def ours(a, b):
    rho, n = spearman_rho(a, b)
    return rho, n


def pandas_spearman_in_subprocess(col1, col2):
    code = textwrap.dedent(
        f"""
    import pandas as pd
    df = pd.read_csv("{CSV}")
    m = (df["n_bmc_px"] > 0) & (df["n_land_px"] > 0)
    s1 = df.loc[m, "{col1}"]
    s2 = df.loc[m, "{col2}"]
    print("pandas_spearman", s1.corr(s2, method="spearman"))
    print("n_pairs", int(m.sum()))
    """
    )
    proc = subprocess.run(
        [PYTHON, "-c", code],
        capture_output=True, text=True, cwd=os.getcwd(),
    )
    return proc


def main():
    os.makedirs("logs", exist_ok=True)
    log_path = os.path.join("logs", "phase3a_spearman_check.txt")
    lines = []
    lines.append(f"CSV: {CSV}")
    lines.append(f"spearman_rho threshold: {THRESHOLD}")
    lines.append("")

    df = bmc_frame()
    lines.append(f"BMC cells with n_land_px > 0: {int(len(df))}")
    worst = 0.0
    stop = False

    for col1, col2 in PAIRS:
        a = df[col1].to_numpy(dtype=np.float64)
        b = df[col2].to_numpy(dtype=np.float64)
        rho_ours, n_ours = ours(a, b)

        proc = pandas_spearman_in_subprocess(col1, col2)
        lines.append(f"=== {col1} vs {col2} ===")
        lines.append(f"  our n_pairs = {n_ours}")
        lines.append(f"  our spearman_rho = {rho_ours}")
        if proc.returncode != 0:
            tail = "\n".join(proc.stderr.splitlines()[-20:]) if proc.stderr else ""
            lines.append(f"  pandas subprocess exit_code = {proc.returncode}")
            if proc.stdout.strip():
                lines.append("  pandas stdout:")
                lines.append(proc.stdout.rstrip())
            if tail.strip():
                lines.append("  pandas stderr tail:")
                lines.append(tail)
            lines.append("  pandas spearman_rho = CRASHED (no value)")
            lines.append("  difference = NOT COMPUTABLE")
            stop = True
        else:
            value = None
            n_pandas = None
            for raw in proc.stdout.splitlines():
                raw = raw.strip()
                if raw.startswith("pandas_spearman"):
                    value = float(raw.split()[-1])
                elif raw.startswith("n_pairs"):
                    n_pandas = int(raw.split()[-1])
            lines.append(f"  pandas n_pairs = {n_pandas}")
            lines.append(f"  pandas spearman_rho = {value}")
            if value is not None:
                diff = abs(rho_ours - value)
                worst = max(worst, diff)
                lines.append(f"  absolute difference = {diff}")
                if diff > THRESHOLD:
                    lines.append(f"  STOP: difference {diff} exceeds threshold {THRESHOLD}")
                    stop = True
            else:
                lines.append("  pandas spearman_rho = NOT PARSED")
                stop = True
        lines.append("")

    lines.append(f"worst absolute difference across pairs: {worst}")
    if stop:
        lines.append("RESULT: STOP (pandas crash or difference above threshold).")
    else:
        lines.append("RESULT: all comparisons within threshold.")

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Log written to {log_path}")
    print("\n".join(lines))
    if stop:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
