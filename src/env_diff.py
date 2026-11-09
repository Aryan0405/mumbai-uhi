"""Diff two conda env export yml files.

Usage: python src/env_diff.py <before.yml> <after.yml> <output_log>
  output_log must be under logs/ and must not already exist (exit 2 otherwise).
Parses dependency lines of the form "  - name=version[=build]",
builds name->version dicts, and prints packages only in before, only in
after, and packages in both with different versions, sorted by name.
"""
import os
import sys


def parse_yml(path):
    versions = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped.startswith("- "):
                continue
            body = stripped[2:]
            if body.startswith("pip:"):
                continue
            if "=" not in body:
                continue
            parts = body.split("=")
            name = parts[0]
            version = parts[1] if len(parts) > 1 else ""
            versions[name] = version
    return versions


def main():
    args = sys.argv[1:]
    if len(args) != 3:
        print("usage: python src/env_diff.py <before.yml> <after.yml> <output_log>")
        raise SystemExit(2)
    before_path, after_path, out_path = args
    if not out_path.startswith("logs/"):
        print("error: output log must start with logs/: " + out_path)
        raise SystemExit(2)
    if os.path.exists(out_path):
        print("error: output log already exists, will not overwrite: " + out_path)
        raise SystemExit(2)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    before = parse_yml(before_path)
    after = parse_yml(after_path)

    before_names = set(before.keys())
    after_names = set(after.keys())

    only_before = sorted(before_names - after_names)
    only_after = sorted(after_names - before_names)
    both = sorted(before_names & after_names)
    changed = [(n, before[n], after[n]) for n in both if before[n] != after[n]]

    lines = []
    lines.append("packages only in before (%d):" % len(only_before))
    for n in only_before:
        lines.append("  %s=%s" % (n, before[n]))
    lines.append("packages only in after (%d):" % len(only_after))
    for n in only_after:
        lines.append("  %s=%s" % (n, after[n]))
    lines.append("packages in both with different versions (%d):" % len(changed))
    for n, bv, av in changed:
        lines.append("  %s: %s -> %s" % (n, bv, av))

    text = "\n".join(lines) + "\n"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
