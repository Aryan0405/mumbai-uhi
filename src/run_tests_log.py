"""Run pytest in process and write full output to a log file (Phase 3B round 1).

Takes an optional log file name from argv[1] (default logs/phase3b_tests.txt).
Runs pytest.main with output captured into a string via
contextlib.redirect_stdout on tests/ with -v. Writes the full output with
Python in utf-8.
"""
import contextlib
import io
import os
import sys

import pytest

DEFAULT_LOG = os.path.join("logs", "phase3b_tests.txt")


def main():
    log_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_LOG
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = pytest.main(["tests", "-v"])
    output = buf.getvalue()
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(output)
    print(output)
    print("pytest return code: " + str(rc))
    print("Log written to " + log_path)


if __name__ == "__main__":
    main()
