"""Assemble the final reply from a template with {{file:path}} placeholders.

Each placeholder is replaced with the complete verbatim content of that file
inside a fenced block. Fails loudly if a referenced file is missing.
"""
import re
import sys


def main():
    template_path = sys.argv[1]
    output_path = sys.argv[2]
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    def replacer(match):
        path = match.group(1)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            raise SystemExit("ERROR: referenced file not found: " + path)
        return "```\n" + content.rstrip() + "\n```\n"

    pattern = re.compile(r"\{\{file:([^}]+)\}\}")
    output, count = pattern.subn(replacer, template)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output)
    print("Assembled " + output_path + " (" + str(count) + " placeholders replaced)")


if __name__ == "__main__":
    main()
