#!/usr/bin/env python3
"""Assemble a transaction-bound GitHub Pages artifact from the clean site tree."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ARTIFACT_ROOT_ENTRIES = frozenset(
    {
        ".nojekyll",
        "404.html",
        "index.html",
        "assets",
        "catalog",
        "privacy",
        "review",
        "spec",
        "titles",
        "trust",
    },
)
REPOSITORY_METADATA_ENTRIES = frozenset(
    {".git", ".github", ".gitattributes", ".gitignore", "AGENTS.md", "README.md"}
)
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
TRANSACTION_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
PREPARED_KIND = "rgm-site-prepared-publication"
STATE_REPOSITORY = "TheFunkyBits/rgm-publication"
HISTORICAL_STATE_REPOSITORY = "TheFunkyBits/rgm"
HISTORICAL_PREPARED_HASHES = {
    "base-site-v16": "41aa74f1ddc9b770cf5241f68199fee4115f60330ba24bab02e7923b519f998c",
    "base-site-v16-recovery-1": "798db9337c006931be20c0b16657bbb169db03ccbf8170f14ca1f3202ae3bc51",
    "catalog-v7": "db80e63048b45150a4be1738156b2689956c51f9ae83817bfbb838a8bc5acf2d",
    "catalog-v8": "4a0e2da12ce208c8da6390f77afa7399d67ac67c14233e08496f64aef60f16a2",
}


def fail(message: str) -> None:
    raise SystemExit(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_manifest_sha256(files: list[dict[str, object]]) -> str:
    source = json.dumps(files, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=True) + "\n"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def require_file(path: Path, description: str) -> None:
    if not path.is_file() or path.is_symlink():
        fail(f"{description} must be a regular file: {path}")


def require_safe_artifact_path(value: object) -> str:
    if not isinstance(value, str):
        fail("Prepared artifact path must be a string.")
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or path.parts[0] not in ARTIFACT_ROOT_ENTRIES:
        fail(f"Prepared artifact path is outside the public allowlist: {value!r}")
    return value


def read_prepared_record(repository: str, state_commit: str, transaction_id: str) -> dict[str, object]:
    url = (
        f"https://raw.githubusercontent.com/{repository}/{state_commit}/"
        f"site-publications/prepared/{transaction_id}.json"
    )
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "rgm-site-pages"})
    try:
        with urlopen(request, timeout=20) as response:
            document = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        fail(f"Prepared state record is unavailable ({error.code}): {url}")
    except (URLError, UnicodeDecodeError, json.JSONDecodeError) as error:
        fail(f"Prepared state record is invalid: {error}")
    if not isinstance(document, dict):
        fail("Prepared state record must be a JSON object.")
    return document


def require_prepared_manifest(
    record: dict[str, object],
    transaction_id: str,
    site_commit: str,
) -> list[dict[str, object]]:
    if set(record) != {"schemaVersion", "kind", "transactionId", "predecessor", "state", "site", "artifact"}:
        fail("Prepared state record has an invalid field set.")
    if record.get("schemaVersion") not in (1, 2) or record.get("kind") != PREPARED_KIND:
        fail("Prepared state record has an unsupported identity.")
    if record.get("transactionId") != transaction_id:
        fail("Prepared state record transaction identifier differs from the workflow input.")
    predecessor = record.get("predecessor")
    if not isinstance(predecessor, dict) or set(predecessor) != {"genesisSha256", "activeSha256"}:
        fail("Prepared state record has an invalid predecessor binding.")
    if not isinstance(predecessor["genesisSha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", predecessor["genesisSha256"]):
        fail("Prepared state record has an invalid genesis binding.")
    if predecessor["activeSha256"] is not None and (
        not isinstance(predecessor["activeSha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", predecessor["activeSha256"])
    ):
        fail("Prepared state record has an invalid active predecessor binding.")
    state = record.get("state")
    if not isinstance(state, dict) or set(state) != {"repository", "sourceCommit"}:
        fail("Prepared state record is missing its state binding.")
    expected_state = HISTORICAL_STATE_REPOSITORY if record["schemaVersion"] == 1 else STATE_REPOSITORY
    if (state.get("repository") != expected_state or
        not isinstance(state.get("sourceCommit"), str) or not GIT_SHA.fullmatch(state["sourceCommit"])):
        fail("Prepared state record has an invalid state binding.")
    if record["schemaVersion"] == 1:
        canonical = (json.dumps(record, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        if hashlib.sha256(canonical).hexdigest() != HISTORICAL_PREPARED_HASHES.get(transaction_id):
            fail("Prepared historical record is not one of the exact pre-rename publications.")
    site = record.get("site")
    if not isinstance(site, dict):
        fail("Prepared state record is missing its site binding.")
    if set(site) != {"repository", "parentCommit", "commit"}:
        fail("Prepared state record has an invalid site binding.")
    if (
        site.get("repository") != "TheFunkyBits/rgm-site"
        or site.get("commit") != site_commit
        or not isinstance(site.get("parentCommit"), str)
        or not GIT_SHA.fullmatch(site["parentCommit"])
        or site["parentCommit"] == site_commit
    ):
        fail("Prepared state record does not bind this exact rgm-site commit.")
    artifact = record.get("artifact")
    if not isinstance(artifact, dict) or set(artifact) != {"root", "manifestSha256", "files"} or artifact.get("root") != ".":
        fail("Prepared state record has an invalid artifact root.")
    if not isinstance(artifact["manifestSha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", artifact["manifestSha256"]):
        fail("Prepared state record has an invalid artifact manifest hash.")
    files = artifact.get("files")
    if not isinstance(files, list) or not files:
        fail("Prepared state record must contain a non-empty artifact file inventory.")
    expected: list[dict[str, object]] = []
    paths: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            fail("Prepared artifact inventory contains a non-object entry.")
        path = require_safe_artifact_path(item.get("path"))
        if path in paths:
            fail(f"Prepared artifact inventory duplicates {path}.")
        byte_count = item.get("bytes")
        digest = item.get("sha256")
        if not isinstance(byte_count, int) or byte_count < 0:
            fail(f"Prepared artifact inventory has an invalid byte count for {path}.")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            fail(f"Prepared artifact inventory has an invalid SHA-256 for {path}.")
        paths.add(path)
        expected.append({"path": path, "bytes": byte_count, "sha256": digest})
    if expected != sorted(expected, key=lambda item: str(item["path"])):
        fail("Prepared artifact inventory must be sorted by path.")
    if artifact["manifestSha256"] != artifact_manifest_sha256(expected):
        fail("Prepared artifact manifest hash differs from its file inventory.")
    return expected


def collect_artifact_files(site_root: Path) -> list[Path]:
    entries = {entry.name: entry for entry in site_root.iterdir()}
    unexpected = sorted(set(entries) - ARTIFACT_ROOT_ENTRIES - REPOSITORY_METADATA_ENTRIES)
    if unexpected:
        fail(f"Site root contains files outside the deployment boundary: {', '.join(unexpected)}")
    files: list[Path] = []
    for name in sorted(ARTIFACT_ROOT_ENTRIES):
        entry = entries.get(name)
        if entry is None:
            continue
        if entry.is_symlink():
            fail(f"Site artifact entry must not be a symbolic link: {entry}")
        if entry.is_file():
            files.append(entry)
            continue
        if not entry.is_dir():
            fail(f"Site artifact entry is neither a file nor a directory: {entry}")
        for child in sorted(entry.rglob("*")):
            if child.is_symlink():
                fail(f"Site artifact entry must not contain a symbolic link: {child}")
            if child.is_file():
                files.append(child)
            elif not child.is_dir():
                fail(f"Site artifact entry is neither a file nor a directory: {child}")
    return files


def observed_manifest(site_root: Path, files: list[Path]) -> list[dict[str, object]]:
    return [
        {
            "path": file.relative_to(site_root).as_posix(),
            "bytes": file.stat().st_size,
            "sha256": sha256_file(file),
        }
        for file in files
    ]


def checked_out_commit(site_root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(site_root), "rev-parse", "HEAD"],
        check=False,
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
    if result.returncode != 0:
        fail(f"Cannot identify checked-out site commit: {result.stderr.strip()}")
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-root", required=True, type=Path)
    parser.add_argument("--state-repository", required=True)
    parser.add_argument("--state-commit", required=True)
    parser.add_argument("--site-commit", required=True)
    parser.add_argument("--transaction-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()

    site_root = arguments.site_root.resolve()
    output = arguments.output.resolve()
    if arguments.state_repository != STATE_REPOSITORY:
        fail("The deployment workflow accepts only the canonical rgm-publication state repository.")
    if not GIT_SHA.fullmatch(arguments.state_commit) or not GIT_SHA.fullmatch(arguments.site_commit):
        fail("State and site commits must be full lowercase Git SHA-1 values.")
    if not TRANSACTION_ID.fullmatch(arguments.transaction_id):
        fail("Transaction identifier is invalid.")
    if not site_root.is_dir() or site_root.is_symlink():
        fail(f"Site root must be a real directory: {site_root}")
    if output.exists():
        fail(f"Pages artifact output already exists: {output}")
    if checked_out_commit(site_root) != arguments.site_commit:
        fail("Checked-out site commit differs from the workflow commit.")

    prepared = read_prepared_record(arguments.state_repository, arguments.state_commit, arguments.transaction_id)
    expected = require_prepared_manifest(prepared, arguments.transaction_id, arguments.site_commit)
    source_files = collect_artifact_files(site_root)
    observed = observed_manifest(site_root, source_files)
    if observed != expected:
        fail("Prepared artifact inventory differs from the exact site worktree.")

    output.mkdir(parents=True)
    for source in source_files:
        destination = output / source.relative_to(site_root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    print(json.dumps({"fileCount": len(observed), "siteCommit": arguments.site_commit, "transactionId": arguments.transaction_id}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
