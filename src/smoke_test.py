"""Phase 1 feasibility gate orchestrator. Runs all checks and writes a
timestamped log (never overwrites previous logs)."""
import os
import sys
from datetime import datetime

from check_network import run as check_network
from check_landsat import run as check_landsat
from check_lst import run as check_lst
from check_population import run as check_population
from check_env import run as check_env


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs("logs", exist_ok=True)
    log_path = os.path.join("logs", f"smoke_{ts}.log")

    class Tee:
        def __init__(self, *streams):
            self.streams = streams
        def write(self, data):
            for s in self.streams:
                s.write(data)
        def flush(self):
            for s in self.streams:
                s.flush()

    log_file = open(log_path, "w", encoding="utf-8")
    tee = Tee(sys.stdout, log_file)
    old_stdout = sys.stdout
    sys.stdout = tee

    print(f"Phase 1 feasibility gate - {ts}")
    overall = True

    try:
        r1 = check_network()
        overall &= all(v.get("ok", False) for v in r1.values())

        r2 = check_landsat()
        overall &= r2["ok"]

        r3 = check_lst()
        overall &= bool(r3)

        r4 = check_population()
        # population rule FAIL does NOT set overall False here;
        # it is reported honestly in FEASIBILITY.md per instructions.

        r5 = check_env()
        overall &= r5["ok"]

    finally:
        sys.stdout = old_stdout
        log_file.close()

    print(f"\nLog written to: {log_path}")
    print(f"OVERALL (network+landsat+lst+env): {'PASS' if overall else 'FAIL'}")
    print(f"Population check: {r4.get('rule_pass', 'N/A')} "
          f"(rule reported separately in FEASIBILITY.md)")
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
