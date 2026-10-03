#!/usr/bin/env python3
"""Fail a queued Pages workflow if canonical site main has advanced."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys


COMMIT = re.compile(r"[0-9a-f]{40}\Z")
CANONICAL_ORIGINS = frozenset(
    {
        b"https://github.com/TheFunkyBits/rgm-site\n",
        b"https://github.com/TheFunkyBits/rgm-site.git\n",
    }
)


def _process(arguments: list[str], *, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(arguments, cwd=cwd, capture_output=True, shell=False, check=False)


def require_current_site_main(site: Path, git: Path, expected_commit: str, *, runner=_process) -> None:
    root = site.absolute()
    if (
        not root.is_dir()
        or root.is_symlink()
        or root.resolve(strict=True) != root
        or not git.is_absolute()
        or not git.is_file()
        or git.is_symlink()
        or not COMMIT.fullmatch(expected_commit)
    ):
        raise ValueError("Site workflow needs a canonical checkout, Git executable and selected commit")

    def read(*arguments: str) -> bytes:
        result = runner([str(git), "-C", str(root), *arguments], cwd=root)
        if result.returncode:
            raise ValueError("Cannot inspect site Git before Pages deployment")
        return result.stdout

    if read("remote", "get-url", "origin") not in CANONICAL_ORIGINS:
        raise ValueError("Pages checkout has a noncanonical origin")
    if read("rev-parse", "--verify", "HEAD") != f"{expected_commit}\n".encode("ascii"):
        raise ValueError("Pages checkout is not the selected site commit")
    if read("ls-remote", "origin", "refs/heads/main") != (
        f"{expected_commit}\trefs/heads/main\n".encode("ascii")
    ):
        raise ValueError("Site remote main advanced; queued Pages deployment must stop")


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only current-site-main Pages preflight")
    parser.add_argument("--site-root", type=Path, required=True)
    parser.add_argument("--site-commit", required=True)
    options = parser.parse_args(arguments)
    executable = shutil.which("git")
    try:
        if executable is None:
            raise ValueError("Git executable is unavailable")
        require_current_site_main(
            options.site_root, Path(executable).resolve(strict=True), options.site_commit
        )
    except (OSError, ValueError) as error:
        print(f"Pages deployment preflight stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
