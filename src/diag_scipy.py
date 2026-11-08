"""Diagnose the scipy.stats.spearmanr Windows fatal exception.

Every probe runs in its OWN subprocess via subprocess.run so a crash in one
probe cannot kill this script. Records the exit code and the last 20 lines of
stderr for each probe. Logs to logs/phase3a_scipy_diag.txt.
"""
import os
import subprocess
import sys
import textwrap

PYTHON = r"C:\Users\Aryan\anaconda3\envs\uhi\python.exe"
ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(ROOT, os.pardir)


def run_probe(code, env_extra=None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [PYTHON, "-c", code],
        capture_output=True, text=True, env=env, cwd=REPO,
    )
    stderr_lines = proc.stderr.splitlines()
    tail = "\n".join(stderr_lines[-20:]) if stderr_lines else ""
    return proc.returncode, proc.stdout, tail


def probe_a():
    code = textwrap.dedent("""
    import numpy, scipy, pandas
    print("numpy", numpy.__version__)
    print("scipy", scipy.__version__)
    print("pandas", pandas.__version__)
    print(numpy.show_config())
    """)
    return run_probe(code)


def probe_b():
    code = textwrap.dedent("""
    import numpy as np
    a = np.arange(5, dtype=np.float64)
    b = np.arange(5, dtype=np.float64) * 2.0
    print(np.corrcoef(a, b))
    """)
    return run_probe(code)


def probe_c():
    code = textwrap.dedent("""
    import numpy as np
    rng = np.random.default_rng(0)
    a = rng.normal(size=1000)
    b = rng.normal(size=1000)
    print(np.corrcoef(a, b))
    """)
    return run_probe(code)


def probe_d():
    code = textwrap.dedent("""
    import numpy as np
    from scipy import stats
    rng = np.random.default_rng(1)
    a5 = rng.normal(size=5)
    b5 = rng.normal(size=5)
    print("spearmanr length 5:", stats.spearmanr(a5, b5))
    a1000 = rng.normal(size=1000)
    b1000 = rng.normal(size=1000)
    print("spearmanr length 1000:", stats.spearmanr(a1000, b1000))
    """)
    return run_probe(code)


def probe_real_code(env):
    code = textwrap.dedent("""
    import numpy as np
    import pandas as pd
    from scipy import stats
    df = pd.read_csv("data/processed/cells_500m.csv")
    m = (df["n_bmc_px"] > 0) & (~df["lst_mean"].isna())
    a = df.loc[m, "lst_mean"].to_numpy(dtype=np.float64)
    b = df.loc[m, "lst_median"].to_numpy(dtype=np.float64)
    print("n pairs:", int(m.sum()))
    print("np.corrcoef:", np.corrcoef(a, b))
    print("scipy.spearmanr:", stats.spearmanr(a, b))
    """)
    return run_probe(code, env_extra=env)


def probe_e():
    return probe_real_code({})


def probe_f():
    code = textwrap.dedent("""
    import pandas as pd
    df = pd.read_csv("data/processed/cells_500m.csv")
    m = (df["n_bmc_px"] > 0) & (~df["lst_mean"].isna())
    s1 = df.loc[m, "lst_mean"]
    s2 = df.loc[m, "lst_median"]
    print("pandas spearman:", s1.corr(s2, method="spearman"))
    """)
    return run_probe(code)


def probe_g_d():
    code = textwrap.dedent("""
    import numpy as np
    from scipy import stats
    rng = np.random.default_rng(1)
    a1000 = rng.normal(size=1000)
    b1000 = rng.normal(size=1000)
    print("scipy.spearmanr length 1000:", stats.spearmanr(a1000, b1000))
    """)
    return run_probe(code, env_extra={"OMP_NUM_THREADS": "1"})


def probe_g_e():
    return probe_real_code({"OMP_NUM_THREADS": "1"})


def main():
    os.makedirs(os.path.join(REPO, "logs"), exist_ok=True)
    log_path = os.path.join(REPO, "logs", "phase3a_scipy_diag.txt")
    lines = []
    results = []

    def record(name, rc, out, err_tail):
        results.append((name, rc))
        lines.append(f"=== {name} ===")
        lines.append(f"exit_code={rc}")
        if out.strip():
            lines.append("stdout:")
            lines.append(out.rstrip())
        if err_tail.strip():
            lines.append("stderr tail (last 20 lines):")
            lines.append(err_tail)
        lines.append("")

    rc, out, err = probe_a()
    record("probe a: versions and numpy.show_config()", rc, out, err)
    rc, out, err = probe_b()
    record("probe b: np.corrcoef length 5", rc, out, err)
    rc, out, err = probe_c()
    record("probe c: np.corrcoef length 1000", rc, out, err)
    rc, out, err = probe_d()
    record("probe d: scipy.stats.spearmanr length 5 then 1000", rc, out, err)
    rc, out, err = probe_e()
    record("probe e: real data np.corrcoef + scipy.spearmanr (env default)", rc, out, err)
    rc, out, err = probe_f()
    record("probe f: pandas Series.corr spearman on real data", rc, out, err)
    rc, out, err = probe_g_d()
    record("probe g: scipy.stats.spearmanr length 1000 with OMP_NUM_THREADS=1", rc, out, err)
    rc, out, err = probe_g_e()
    record("probe g: real data np.corrcoef + scipy.spearmanr with OMP_NUM_THREADS=1", rc, out, err)

    lines.append("Summary:")
    crashed = [n for n, rc in results if rc != 0]
    survived = [n for n, rc in results if rc == 0]
    lines.append(f"crashed probes ({len(crashed)}): " + ", ".join(crashed) if crashed else "none")
    lines.append(f"survived probes ({len(survived)}): " + ", ".join(survived) if survived else "none")

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Log written to {log_path}")
    for n, rc in results:
        print(f"  {n}: exit_code={rc}")


if __name__ == "__main__":
    main()
