"""Invoke the public developer-tool owner with this repository as the target."""

import argparse
import os
from pathlib import Path
import subprocess
import sys


def main() -> int:
    root = next(parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists())
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("--dev-root", type=Path)
    arguments, selected = parser.parse_known_args()
    explicit = arguments.dev_root or os.environ.get("RGM_DEV_ROOT")
    owner = Path(explicit) if explicit else root.parent / "dev"
    if not owner.is_absolute():
        parser.error("The developer-tool checkout must be an absolute path")
    owner = owner.resolve()
    entry = owner / "scripts" / Path(__file__).name
    if not entry.is_file() or not entry.resolve().is_relative_to(owner):
        parser.error("Obtain the public rgm-dev checkout and select --dev-root or RGM_DEV_ROOT")
    if any(
        value == "--root"
        or value.startswith("--root=")
        or value == "--policy"
        or value.startswith("--policy=")
        for value in selected
    ):
        parser.error("Consumer source and policy roots are owned by this repository")
    command = [sys.executable, "-B", str(entry)]
    if Path(__file__).name == "style.py":
        command += ["--root", str(root), "--policy", str(root / "config" / "style.json")]
    return subprocess.run(command + selected, cwd=root, shell=False, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
