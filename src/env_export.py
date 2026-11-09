"""Export the uhi_test conda environment to env/uhi_test.yml.
Uses subprocess.run with a list argument, never installs anything.
"""
import os
import subprocess


def main():
    os.makedirs("env", exist_ok=True)
    conda_exe = r"C:\Users\Aryan\anaconda3\Scripts\conda.exe"
    result = subprocess.run(
        [conda_exe, "env", "export", "-n", "uhi_test"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr)
        raise SystemExit(1)
    out_path = os.path.join("env", "uhi_test.yml")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result.stdout)
    lines = result.stdout.splitlines()
    for line in lines[:8]:
        print(line)
    print("total lines:", len(lines))


if __name__ == "__main__":
    main()
