"""Git report helper (Phase 3B round 1).

Runs git via subprocess (git log --format="%h %s" -5 and git status) and
writes the raw output to the file path given as argv[1], utf-8.
"""
import subprocess
import sys


def main():
    out_path = sys.argv[1]
    parts = []
    p1 = subprocess.run(
        ["git", "log", "--format=%h %s", "-5"],
        capture_output=True, text=True,
    )
    parts.append("git log --format=%h %s -5")
    parts.append("exit code: " + str(p1.returncode))
    parts.append(p1.stdout)
    if p1.stderr:
        parts.append("stderr:")
        parts.append(p1.stderr)
    p2 = subprocess.run(["git", "status"], capture_output=True, text=True)
    parts.append("")
    parts.append("git status")
    parts.append("exit code: " + str(p2.returncode))
    parts.append(p2.stdout)
    if p2.stderr:
        parts.append("stderr:")
        parts.append(p2.stderr)
    text = "\n".join(parts) + "\n"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
