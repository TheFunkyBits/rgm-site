#!/usr/bin/env python3
"""Inspect served site paths without attesting historical or Pages-delivered bytes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

from assemble_versioned_pages import PagesAssemblyError, collect_checkout


OLD_CLIENT_PATHS = frozenset({
    "index.html",
    "assets/styles.css",
    "catalog/v8/index.json",
    "catalog/v8/index.signatures.json",
    "catalog/v9/index.json",
    "catalog/v9/index.signatures.json",
    "trust/catalog-keys.json",
    "trust/keys.json",
})
VERSION_INDEX = re.compile(r"catalog/v([1-9][0-9]*)/index\.json\Z")


def legacy_graph_paths(site: Path) -> set[str]:
    """Read only historical object-path references for continued URL availability."""
    required: set[str] = set()
    for version in (8, 9):
        index = json.loads((site / f"catalog/v{version}/index.json").read_text(encoding="utf-8"))
        if type(index) is not dict or type(index.get("files")) is not list or not index["files"]:
            raise ValueError("Still-served catalog has no readable object graph")
        for entry in index["files"]:
            path = entry.get("objectPath") if type(entry) is dict else None
            if (type(path) is not str or not path.startswith("objects/") or "\\" in path or
                    any(segment in ("", ".", "..") or
                        re.fullmatch(r"[A-Za-z0-9._-]+", segment) is None for segment in path.split("/"))):
                raise ValueError("Still-served catalog has an unsafe object-path reference")
            required.add(f"catalog/v{version}/{path}")
    return required


def validate_site(
    root: Path,
    *,
    catalog_version: int | None = None,
    java: Path | None = None,
    publisher_lib: Path | None = None,
    runner=subprocess.run,
) -> dict[str, object]:
    site = root.absolute()
    if not site.is_dir() or site.is_symlink() or site.resolve(strict=True) != site:
        raise ValueError("Site must be a canonical, regular directory")
    paths = set(collect_checkout(site))
    missing = OLD_CLIENT_PATHS - paths
    if missing:
        raise ValueError("Required old-client site paths are missing: " + ", ".join(sorted(missing)))
    missing_objects = legacy_graph_paths(site) - paths
    if missing_objects:
        raise ValueError("Still-served catalog graph is incomplete: " + ", ".join(sorted(missing_objects)))
    versions = {int(match.group(1)) for path in paths if (match := VERSION_INDEX.fullmatch(path))}
    if not {8, 9} <= versions:
        raise ValueError("Site has lost a still-served signed catalog URL")
    if catalog_version is None:
        if java is not None or publisher_lib is not None:
            raise ValueError("Client publisher options require a selected unsigned catalog version")
        return {"status": "paths-present", "legacyCatalogs": [8, 9]}

    if catalog_version <= 9 or java is None or publisher_lib is None:
        raise ValueError("Unsigned verification needs version >9, Java and an installed client publisher")
    if catalog_version not in versions:
        raise ValueError("Selected unsigned catalog index is absent")
    if (not java.is_file() or java.is_symlink() or java.resolve(strict=True) != java or
            not publisher_lib.is_dir() or publisher_lib.is_symlink() or
            publisher_lib.resolve(strict=True) != publisher_lib):
        raise ValueError("Java or client publisher distribution is not a regular path")
    jars = list(publisher_lib.glob("*.jar"))
    if not jars or any(not jar.is_file() or jar.is_symlink() for jar in jars):
        raise ValueError("Client publisher distribution has no installed JARs")
    command = [
        str(java), "-classpath", publisher_lib.as_posix() + "/*",
        "dev.thefunkybits.rgm.catalogpublisher.MainKt", "verify-unsigned-release",
        "--directory", str(site / f"catalog/v{catalog_version}"),
        "--catalog-version", str(catalog_version),
    ]
    result = runner(command, cwd=site, capture_output=True, check=False)
    if result.returncode:
        raise ValueError("Client-owned unsigned catalog semantic verification failed")
    try:
        def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
            parsed: dict[str, object] = {}
            for key, value in pairs:
                if key in parsed:
                    raise ValueError("Client publisher response repeats a field")
                parsed[key] = value
            return parsed

        verified = json.loads(result.stdout.decode("utf-8"), object_pairs_hook=unique)
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("Client publisher response is not valid JSON") from error
    if (type(verified) is not dict or set(verified) != {"catalogVersion", "fileCount"} or
            type(verified["catalogVersion"]) is not int or
            verified["catalogVersion"] != catalog_version or
            type(verified["fileCount"]) is not int or verified["fileCount"] < 1):
        raise ValueError("Client publisher did not verify the selected catalog version")
    return {"status": "semantic-catalog-verified", "catalogVersion": catalog_version,
            "legacyCatalogs": [8, 9]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-root", type=Path, required=True)
    parser.add_argument("--catalog-version", type=int)
    parser.add_argument("--java", type=Path)
    parser.add_argument("--publisher-lib", type=Path)
    arguments = parser.parse_args()
    try:
        result = validate_site(arguments.site_root, catalog_version=arguments.catalog_version,
                               java=arguments.java, publisher_lib=arguments.publisher_lib)
    except (OSError, ValueError, PagesAssemblyError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
