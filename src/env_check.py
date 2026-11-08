"""Environment check (Phase 3B round 2).

Prints versions of numpy, scipy, pandas, matplotlib, scikit-learn and
threadpool info. If scikit-learn is missing, says so and writes the exact
install command; does not install anything.
"""
import os
import sys

import numpy as np
import pandas as pd
import scipy

try:
    import sklearn
    sklearn_available = True
    sklearn_version = sklearn.__version__
except ImportError as exc:  # noqa: BLE001 - report environment state only
    sklearn_available = False
    sklearn_version = None
    sklearn_import_error = repr(exc)

try:
    from threadpoolctl import threadpool_info
    threadpool_available = True
    tpu_entries = threadpool_info()
except Exception as exc:  # noqa: BLE001 - report environment state only
    threadpool_available = False
    tpu_entries = []
    threadpoolctl_error = repr(exc)


def main():
    os.makedirs("logs", exist_ok=True)
    log_path = os.path.join("logs", "phase3b2_env.txt")
    lines = []
    lines.append("numpy " + np.__version__)
    lines.append("scipy " + scipy.__version__)
    lines.append("pandas " + pd.__version__)
    lines.append("matplotlib " + __import__("matplotlib").__version__)
    if sklearn_available:
        lines.append("scikit-learn " + sklearn_version)
    else:
        lines.append("scikit-learn: MISSING")
        lines.append("import error: " + sklearn_import_error)
        lines.append("Install command: pip install scikit-learn")
    if threadpool_available:
        lines.append("threadpoolctl:")
        for entry in tpu_entries:
            lines.append("  " + str(entry))
    else:
        lines.append("threadpoolctl: unavailable")
        lines.append("error: " + threadpoolctl_error)
    text = "\n".join(lines) + "\n"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    if not sklearn_available:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
