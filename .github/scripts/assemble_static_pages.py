#!/usr/bin/env python3
"""Validate and stage a reviewed intro/privacy site without catalog publication."""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit


REQUIRED_FILES = frozenset({"index.html", "privacy/index.html", "assets/styles.css", ".nojekyll"})
OPTIONAL_FILES = frozenset({"assets/app-icon.png", "assets/favicon.ico"})
METADATA_ROOTS = frozenset({".git", ".github", ".gitattributes", ".gitignore", "AGENTS.md", "README.md"})
CUTOVER_MARKER = ".github/static-pages-cutover.json"
CUTOVER_CONTRACT = "rgm-static-pages-v1"
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
GIT = shutil.which("git")


class PagesAssemblyError(ValueError):
    pass


def _regular(path: Path, *, directory: bool = False) -> None:
    info = os.lstat(path)
    if (
        path.is_symlink()
        or path.resolve(strict=True) != path
        or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
    ):
        raise PagesAssemblyError("Site path is linked, noncanonical or nonregular")


def git(root: Path, *arguments: str) -> bytes:
    if GIT is None:
        raise PagesAssemblyError("Git executable is unavailable")
    result = subprocess.run([GIT, "-C", str(root), *arguments], capture_output=True, check=False)
    if result.returncode:
        raise PagesAssemblyError("Site Git inspection failed")
    return result.stdout


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PagesAssemblyError("Readiness marker repeats a field")
        result[key] = value
    return result


def artifact_path(value: str) -> bool:
    if (
        not value
        or "\\" in value
        or ":" in value
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise PagesAssemblyError("Unsafe static site path")
    if value.split("/")[0] in METADATA_ROOTS:
        return False
    if value not in REQUIRED_FILES | OPTIONAL_FILES:
        raise PagesAssemblyError("Site contains material outside the intro/privacy artifact")
    return True


class _PageLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        fields = dict(attrs)
        if tag in {"script", "iframe", "video", "audio", "object", "embed"}:
            raise PagesAssemblyError("Static pages cannot contain executable or embedded remote media")
        if any(name.startswith("on") for name in fields):
            raise PagesAssemblyError("Static pages cannot contain script event handlers")
        if tag == "img" and not fields.get("src", "").startswith("/rgm-site/assets/"):
            raise PagesAssemblyError("Static pages cannot load third-party images")
        if "srcset" in fields:
            raise PagesAssemblyError("Static images require a single reviewed local resource")
        for name in ("href", "src"):
            if fields.get(name):
                self.links.append(str(fields[name]))


def validate_artifact(root: Path) -> dict[str, object]:
    root = root.absolute()
    _regular(root, directory=True)
    files: set[str] = set()
    for parent, directories, names in os.walk(root, followlinks=False):
        for name in directories:
            path = Path(parent) / name
            _regular(path, directory=True)
            if path.relative_to(root).as_posix() not in {"assets", "privacy"}:
                raise PagesAssemblyError("Static artifact contains a forbidden directory")
        for name in names:
            path = Path(parent) / name
            _regular(path)
            relative = path.relative_to(root).as_posix()
            if relative not in REQUIRED_FILES | OPTIONAL_FILES:
                raise PagesAssemblyError("Static artifact contains a forbidden file")
            files.add(relative)
    if not REQUIRED_FILES <= files:
        raise PagesAssemblyError("Static artifact is missing intro, privacy or required resources")
    validate_page_content(root, files)
    return {"status": "static-pages-valid", "fileCount": len(files)}


def validate_page_content(root: Path, files: set[str]) -> None:
    for name in ("index.html", "privacy/index.html"):
        page = _PageLinks()
        page.feed((root / name).read_text(encoding="utf-8"))
        for link in page.links:
            uri = urlsplit(link)
            if uri.scheme in {"https", "mailto"}:
                if uri.scheme == "https" and (not uri.hostname or uri.username is not None):
                    raise PagesAssemblyError("Static page has an unsafe external link")
                continue
            if uri.scheme or uri.netloc:
                raise PagesAssemblyError("Static page has an unsafe link scheme")
            if not uri.path:
                continue
            if not uri.path.startswith("/rgm-site/"):
                raise PagesAssemblyError("Local links must use the GitHub Pages base path")
            relative = uri.path.removeprefix("/rgm-site/")
            if not relative or relative.endswith("/"):
                relative += "index.html"
            if relative not in files:
                raise PagesAssemblyError("Static page links to an absent resource")
    css = (root / "assets/styles.css").read_text(encoding="utf-8")
    if re.search(r"@import|url\(\s*['\"]?(?:https?:|//|data:)", css, re.IGNORECASE):
        raise PagesAssemblyError("Site styles cannot fetch remote resources")


def preflight(root: Path, expected_commit: str) -> list[str]:
    root = root.absolute()
    _regular(root, directory=True)
    if (
        not COMMIT.fullmatch(expected_commit)
        or git(root, "rev-parse", "HEAD").decode("ascii").strip() != expected_commit
        or git(root, "symbolic-ref", "--quiet", "--short", "HEAD") != b"main\n"
        or git(root, "status", "--porcelain=v1", "--untracked-files=all").strip()
    ):
        raise PagesAssemblyError("Static Pages needs the reviewed clean main commit")
    paths: set[str] = set()
    files: list[str] = []
    for record in git(root, "ls-tree", "-r", "--full-tree", "-z", expected_commit).split(b"\0"):
        if not record:
            continue
        metadata, separator, encoded = record.partition(b"\t")
        fields = metadata.split()
        relative = encoded.decode("utf-8")
        if (
            not separator
            or len(fields) != 3
            or fields[0] not in {b"100644", b"100755"}
            or fields[1] != b"blob"
        ):
            raise PagesAssemblyError("Site commit contains a nonregular entry")
        paths.add(relative)
        if artifact_path(relative):
            files.append(relative)
    if not REQUIRED_FILES <= set(files) or CUTOVER_MARKER not in paths:
        raise PagesAssemblyError("Static Pages readiness is not active or required pages are missing")
    marker = root / CUTOVER_MARKER
    _regular(marker)
    value = json.loads(marker.read_text(encoding="utf-8"), object_pairs_hook=_unique)
    if (
        type(value) is not dict
        or set(value) != {"contract", "enabled"}
        or value["contract"] != CUTOVER_CONTRACT
        or value["enabled"] is not True
    ):
        raise PagesAssemblyError("Static Pages readiness is not approved")
    for relative in files:
        _regular(root / relative)
    validate_page_content(root, set(files))
    return sorted(files)


def assemble(root: Path, expected_commit: str, output: Path) -> int:
    root, output = root.absolute(), output.absolute()
    files = preflight(root, expected_commit)
    _regular(output.parent, directory=True)
    if os.path.lexists(output) or output.is_relative_to(root):
        raise PagesAssemblyError("Pages output must be unused and outside the checkout")
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        for relative in files:
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as writer:
                result = subprocess.run(
                    [str(GIT), "-C", str(root), "show", f"{expected_commit}:{relative}"],
                    stdout=writer,
                    stderr=subprocess.PIPE,
                    check=False,
                )
            if result.returncode:
                raise PagesAssemblyError("Cannot stage the reviewed site commit")
        validate_artifact(staging)
        if os.path.lexists(output):
            raise PagesAssemblyError("Pages output became occupied")
        os.rename(staging, output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return len(files)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-root", type=Path, required=True)
    parser.add_argument("--site-commit")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-artifact", action="store_true")
    args = parser.parse_args()
    try:
        if args.validate_artifact:
            if args.site_commit is not None or args.output is not None:
                raise PagesAssemblyError("Artifact validation takes only an artifact root")
            result = validate_artifact(args.site_root)
        else:
            if args.site_commit is None:
                raise PagesAssemblyError("Reviewed site commit is required")
            files = preflight(args.site_root, args.site_commit)
            result = (
                {"status": "static-pages-ready", "fileCount": len(files)}
                if args.output is None
                else {
                    "status": "static-pages-staged",
                    "fileCount": assemble(args.site_root, args.site_commit, args.output),
                }
            )
    except (OSError, ValueError) as error:
        print(f"Static Pages validation failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
