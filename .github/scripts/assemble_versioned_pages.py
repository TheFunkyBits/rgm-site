#!/usr/bin/env python3
"""Stage a versioned catalog's clean Pages checkout, without an artifact attestation."""

from __future__ import annotations

import argparse
from itertools import chain
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile


ARTIFACT_ROOTS = frozenset({
    ".nojekyll", "404.html", "index.html", "assets", "catalog", "privacy",
    "review", "spec", "titles", "trust",
})
METADATA_ROOTS = frozenset({
    ".git", ".github", ".gitattributes", ".gitignore", "AGENTS.md", "README.md",
})
GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
CUTOVER_MARKER = ".github/versioned-catalog-cutover.json"
CUTOVER_CONTRACT = "rgm-unsigned-catalog-v1"


class PagesAssemblyError(ValueError):
    """An untrusted or ambiguous site checkout must not become a Pages artifact."""


def git(repo: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), *arguments], capture_output=True, check=False,
    )
    if completed.returncode:
        raise PagesAssemblyError(f"Cannot inspect the site Git checkout: {' '.join(arguments)}")
    return completed.stdout


def artifact_path(value: str) -> bool:
    if not value or value.startswith("/") or "\\" in value:
        raise PagesAssemblyError(f"Unsafe site path: {value!r}")
    segments = value.split("/")
    if any(segment in ("", ".", "..") for segment in segments):
        raise PagesAssemblyError(f"Unsafe site path: {value!r}")
    if segments[0] not in ARTIFACT_ROOTS | METADATA_ROOTS:
        raise PagesAssemblyError(f"Site path outside the deployment boundary: {value!r}")
    return segments[0] in ARTIFACT_ROOTS


def require_authorized_cutover(root: Path, tracked: set[str]) -> None:
    """A workflow dispatch cannot substitute for coordinated owner readiness."""
    metadata = root / ".github"
    marker = root / CUTOVER_MARKER
    if CUTOVER_MARKER not in tracked or metadata.is_symlink() or not metadata.is_dir():
        raise PagesAssemblyError("Versioned catalog policy cutover is not active")
    try:
        attributes = os.lstat(marker)
        if (not stat.S_ISREG(attributes.st_mode) or marker.is_symlink() or
                getattr(attributes, "st_file_attributes", 0) &
                getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0) or
                not marker.resolve(strict=True).is_relative_to(root)):
            raise PagesAssemblyError("Versioned catalog policy cutover marker is not a regular site file")

        def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in pairs:
                if key in result:
                    raise PagesAssemblyError("Versioned catalog cutover marker repeats a key")
                result[key] = value
            return result

        value = json.loads(marker.read_text(encoding="utf-8"), object_pairs_hook=unique)
        if (type(value) is not dict or set(value) != {"contract", "enabled"} or
            value["contract"] != CUTOVER_CONTRACT or value["enabled"] is not True):
            raise PagesAssemblyError("Versioned catalog policy cutover marker is not approved")
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise PagesAssemblyError("Versioned catalog policy cutover marker is unreadable") from error


def preflight_cutover(root: Path, expected_commit: str,
                      staged_catalog_version: int | None = None) -> None:
    root = root.absolute()
    if not root.is_dir() or root.is_symlink() or root.resolve() != root:
        raise PagesAssemblyError("Site checkout must be a real, canonical directory")
    if not GIT_COMMIT.fullmatch(expected_commit):
        raise PagesAssemblyError("Expected site commit must be a full Git commit ID")
    if git(root, "rev-parse", "HEAD").decode("ascii").strip() != expected_commit:
        raise PagesAssemblyError("Site checkout is not the expected commit")
    status = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if staged_catalog_version is None:
        if status:
            raise PagesAssemblyError("Site checkout has local or untracked changes")
    else:
        if type(staged_catalog_version) is not int or staged_catalog_version <= 9:
            raise PagesAssemblyError("Staged catalog cutover preflight needs a successor version")
        prefix = f"catalog/v{staged_catalog_version}/"
        try:
            untracked = [entry.decode("utf-8") for entry in status.split(b"\0") if entry]
        except UnicodeDecodeError as error:
            raise PagesAssemblyError("Staged site paths must be UTF-8") from error
        if (not untracked or any(not entry.startswith("?? " + prefix) or
                                 not artifact_path(entry[3:]) for entry in untracked) or
                "?? " + prefix + "index.json" not in untracked or
                not any(entry.startswith("?? " + prefix + "objects/") for entry in untracked)):
            raise PagesAssemblyError("Site checkout has changes besides the selected staged version")
        for entry in untracked:
            candidate = root / entry[3:]
            info = os.lstat(candidate)
            if (not stat.S_ISREG(info.st_mode) or candidate.is_symlink() or
                    getattr(info, "st_file_attributes", 0) &
                    getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0) or
                    not candidate.resolve(strict=True).is_relative_to(root)):
                raise PagesAssemblyError("Staged site catalog contains a linked or nonregular file")
    marker = git(root, "ls-tree", "-r", "--name-only", "-z", expected_commit,
                 "--", CUTOVER_MARKER).split(b"\0")
    if marker != [CUTOVER_MARKER.encode("ascii"), b""]:
        raise PagesAssemblyError("Versioned catalog policy cutover is not active")
    require_authorized_cutover(root, {CUTOVER_MARKER})


def collect_checkout(root: Path) -> list[str]:
    files: list[str] = []
    for entry in root.iterdir():
        artifact_path(entry.name)
        if entry.name in METADATA_ROOTS:
            continue
        if entry.is_symlink():
            raise PagesAssemblyError(f"Site artifact contains a link: {entry.name}")
        paths = chain((entry,), entry.rglob("*")) if entry.is_dir() else (entry,)
        for path in paths:
            relative = path.relative_to(root).as_posix()
            artifact_path(relative)
            if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root):
                raise PagesAssemblyError(f"Site artifact contains a link: {relative}")
            if path.is_file():
                files.append(relative)
            elif not path.is_dir():
                raise PagesAssemblyError(f"Site artifact is not a regular file or directory: {relative}")
    return sorted(files)


def require_new_version_commit(root: Path, commit: str, version: int,
                               new_paths: set[str]) -> None:
    parents = git(root, "rev-list", "--parents", "-n", "1", commit).decode("ascii").split()
    if len(parents) != 2 or parents[0] != commit or not GIT_COMMIT.fullmatch(parents[1]):
        raise PagesAssemblyError("Versioned Pages commit needs its single original parent")
    prefix = f"catalog/v{version}/"
    if (git(root, "ls-tree", "-r", "--name-only", "-z", parents[1], "--", prefix)
            or f"{prefix}index.json" not in new_paths or
            not any(path.startswith(prefix + "objects/") for path in new_paths)):
        raise PagesAssemblyError("Selected catalog version already existed or has no objects")
    changed = git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z",
                  parents[1], commit).split(b"\0")
    try:
        paths = [path.decode("utf-8") for path in changed if path]
    except UnicodeDecodeError as error:
        raise PagesAssemblyError("Versioned Pages commit has a non-UTF-8 path") from error
    if len(paths) != len(set(paths)) or set(paths) != new_paths:
        raise PagesAssemblyError("Site commit does not add exactly the selected catalog version")


def assemble(root: Path, expected_commit: str, catalog_version: int, output: Path) -> int:
    root = root.absolute()
    output = output.absolute()
    if not root.is_dir() or root.is_symlink() or root.resolve() != root:
        raise PagesAssemblyError("Site checkout must be a real, canonical directory")
    if not GIT_COMMIT.fullmatch(expected_commit):
        raise PagesAssemblyError("Expected site commit must be a full Git commit ID")
    if catalog_version <= 9:
        raise PagesAssemblyError("Only successor catalog versions can use this assembler")
    if not output.parent.is_dir() or output.parent.is_symlink() or output.exists() or output.is_symlink():
        raise PagesAssemblyError("Pages output parent must exist and output must be unused")
    if output == root or output.is_relative_to(root):
        raise PagesAssemblyError("Pages output must be outside the site checkout")
    if git(root, "rev-parse", "HEAD").decode("ascii").strip() != expected_commit:
        raise PagesAssemblyError("Site checkout is not the expected commit")
    if git(root, "status", "--porcelain=v1", "--untracked-files=all").strip():
        raise PagesAssemblyError("Site checkout has local or untracked changes")
    committed = git(root, "ls-tree", "-r", "--full-tree", "-z", expected_commit).split(b"\0")
    try:
        tracked_paths: set[str] = set()
        expected = []
        for entry in committed:
            if not entry:
                continue
            metadata, separator, encoded_path = entry.partition(b"\t")
            fields = metadata.split(b" ")
            if not separator or len(fields) != 3:
                raise PagesAssemblyError("Site commit contains an invalid tree entry")
            path = encoded_path.decode("utf-8")
            if artifact_path(path):
                if fields[0] not in (b"100644", b"100755") or fields[1] != b"blob":
                    raise PagesAssemblyError(f"Committed Pages artifact is not a regular file: {path}")
                expected.append(path)
            tracked_paths.add(path)
        expected.sort()
    except UnicodeDecodeError as error:
        raise PagesAssemblyError("Site checkout contains a non-UTF-8 path") from error
    require_authorized_cutover(root, tracked_paths)
    collect_checkout(root)
    index_path = f"catalog/v{catalog_version}/index.json"
    if index_path not in expected:
        raise PagesAssemblyError(f"Versioned catalog index is not part of this site commit: {index_path}")
    prefix = f"catalog/v{catalog_version}/"
    require_new_version_commit(root, expected_commit, catalog_version,
                               {path for path in expected if path.startswith(prefix)})

    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        for relative in expected:
            source = root / relative
            if not source.is_file() or source.is_symlink() or not source.resolve(strict=True).is_relative_to(root):
                raise PagesAssemblyError(f"Site artifact changed during assembly: {relative}")
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as writer:
                copied = subprocess.run(
                    ["git", "-C", str(root), "show", f"{expected_commit}:{relative}"],
                    stdout=writer, stderr=subprocess.PIPE, check=False,
                )
            if copied.returncode:
                raise PagesAssemblyError(f"Cannot stage a committed Pages artifact: {relative}")
        if output.exists() or output.is_symlink():
            raise PagesAssemblyError("Pages output became occupied during assembly")
        os.replace(staging, output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return len(expected)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-root", type=Path, required=True)
    parser.add_argument("--site-commit", required=True)
    parser.add_argument("--catalog-version", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--preflight-cutover", action="store_true")
    parser.add_argument("--allow-staged-catalog-version", type=int)
    arguments = parser.parse_args()
    try:
        if arguments.preflight_cutover:
            if arguments.catalog_version is not None or arguments.output is not None:
                raise PagesAssemblyError("Cutover preflight takes only the site checkout and commit")
            preflight_cutover(arguments.site_root, arguments.site_commit,
                              arguments.allow_staged_catalog_version)
            print(json.dumps({"status": "cutover-active"}, sort_keys=True))
            return 0
        if arguments.allow_staged_catalog_version is not None:
            raise PagesAssemblyError("Pages assembly cannot allow a staged version")
        if arguments.catalog_version is None or arguments.output is None:
            raise PagesAssemblyError("Pages artifact needs a catalog version and unused output")
        count = assemble(arguments.site_root, arguments.site_commit,
                         arguments.catalog_version, arguments.output)
    except (OSError, PagesAssemblyError) as error:
        print(f"Cannot assemble Pages artifact: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"catalogVersion": arguments.catalog_version, "fileCount": count}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
