"""Run pytest in process and write full output to logs/phase3a_tests.txt
(Phase 3A round R4).
"""
import contextlib
import io
import os

import pytest

LOG_PATH = os.path.join("logs", "phase3a_tests.txt")


def main():
    os.makedirs("logs", exist_ok=True)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = pytest.main(["tests", "-v"])
    output = buf.getvalue()
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write(output)
    print(output)
    print(f"pytest return code: {rc}")
    print(f"Log written to {LOG_PATH}")


if __name__ == "__main__":
    main()
