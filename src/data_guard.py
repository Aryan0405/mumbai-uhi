"""Data guard (Phase 3B round 1).

Prints and logs the sha256 and row count of data/processed/cells_500m.csv,
and the sha256 of data/processed/cells_500m.geojson.
"""
import hashlib
import os
import sys


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    out_path = sys.argv[1]
    csv_path = os.path.join("data", "processed", "cells_500m.csv")
    geojson_path = os.path.join("data", "processed", "cells_500m.geojson")
    lines = []
    lines.append("csv: " + csv_path)
    lines.append("csv sha256: " + sha256_file(csv_path))
    with open(csv_path, "r", encoding="utf-8") as f:
        row_count = sum(1 for _ in f) - 1
    lines.append("csv row count (excl header): " + str(row_count))
    lines.append("geojson: " + geojson_path)
    lines.append("geojson sha256: " + sha256_file(geojson_path))
    text = "\n".join(lines) + "\n"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
