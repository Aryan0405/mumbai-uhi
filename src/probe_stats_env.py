"""Probe the interpreter environment under conda run (Phase 3A round R3).

Prints numpy, scipy and pandas versions; runs np.corrcoef and
scipy.stats.spearmanr and pandas Series.corr(method='spearman') on
[1,2,3,4] vs [1,3,2,4] (expect 0.8). Logs to logs/phase3a_env_probe.txt.
"""
import os

import numpy as np
import pandas as pd
import scipy

sys_executable_note = (
    "The same call through the env python.exe without conda run was observed "
    "by the user to exit with 0xC06D007F (even for small corrcoef calls). "
    "The cause was not diagnosed here; running through "
    "'conda run -n uhi python' works."
)


def main():
    os.makedirs("logs", exist_ok=True)
    log_path = os.path.join("logs", "phase3a_env_probe.txt")
    lines = []
    lines.append("numpy " + np.__version__)
    lines.append("scipy " + scipy.__version__)
    lines.append("pandas " + pd.__version__)
    a = np.array([1.0, 2.0, 3.0, 4.0])
    b = np.array([1.0, 3.0, 2.0, 4.0])
    cc = float(np.corrcoef(a, b)[0, 1])
    lines.append("np.corrcoef([1,2,3,4], [1,3,2,4]) = " + repr(cc) + " (expect 0.8)")
    from scipy import stats

    sr = float(stats.spearmanr(a, b).statistic)
    lines.append("scipy.stats.spearmanr([1,2,3,4], [1,3,2,4]) = " + repr(sr) + " (expect 0.8)")
    s1 = pd.Series(a)
    s2 = pd.Series(b)
    ps = float(s1.corr(s2, method="spearman"))
    lines.append("pandas Series.corr(method='spearman') = " + repr(ps) + " (expect 0.8)")
    lines.append("")
    lines.append(sys_executable_note)
    text = "\n".join(lines) + "\n"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
