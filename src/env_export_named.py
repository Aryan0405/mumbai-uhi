"""Export a named conda environment to a yml file.

Usage: python src/env_export_named.py <env_name> <output_path>
  output_path must start with env/ and must not already exist (exit 2 otherwise).
"""
import os
import shutil
import subprocess
import sys


def main():
    args = sys.argv[1:]
    if len(args) != 2:
        print("usage: python src/env_export_named.py <env_name> <output_path>")
        raise SystemExit(2)
    name, out_path = args
    if not out_path.startswith("env/"):
        print("error: output path must start with env/: " + out_path)
        raise SystemExit(2)
    if os.path.exists(out_path):
        print("error: output path already exists, will not overwrite: " + out_path)
        raise SystemExit(2)
    conda_exe = shutil.which("conda")
    if conda_exe is None:
        conda_exe = os.environ.get("CONDA_EXE")
    if conda_exe is None:
        print("error: conda executable not found (shutil.which('conda') and CONDA_EXE are both missing)")
        raise SystemExit(1)
    result = subprocess.run(
        [conda_exe, "env", "export", "-n", name, "--no-builds"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr)
        raise SystemExit(1)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result.stdout)
    lines = result.stdout.splitlines()
    for line in lines[:5]:
        print(line)
    print("total lines:", len(lines))


if __name__ == "__main__":
    main()
