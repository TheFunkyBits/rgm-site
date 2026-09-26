from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from urllib.error import HTTPError, URLError


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "prepare_pages_artifact.py"
MODULE_SPEC = importlib.util.spec_from_file_location("prepare_pages_artifact", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Cannot load {MODULE_PATH}")
ASSEMBLER = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(ASSEMBLER)


class FakeResponse:
    def __init__(self, body: bytes, url: str, status: int = 200) -> None:
        self.body = body
        self.url = url
        self.status = status

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.body[:size] if size >= 0 else self.body

    def geturl(self) -> str:
        return self.url


class FakeOpener:
    def __init__(self, body: bytes, *, url: str | None = None, error: HTTPError | URLError | None = None) -> None:
        self.body = body
        self.url = url
        self.error = error
        self.request = None
        self.timeout = None

    def open(self, request, timeout: int) -> FakeResponse:
        self.request = request
        self.timeout = timeout
        if self.error is not None:
            raise self.error
        return FakeResponse(self.body, self.url or request.full_url)


class PreparePagesArtifactTest(unittest.TestCase):
    def setUp(self) -> None:
        token_patch = mock.patch.dict(os.environ, {"RGM_STATE_READ_TOKEN": "fixture-app-token"})
        token_patch.start()
        self.addCleanup(token_patch.stop)
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.site = self.root / "site"
        self.git = shutil.which("git") or self.fail("git is required for this test")
        self.write(self.site / ".nojekyll", b"")
        self.write(self.site / "index.html", b"<main>RGM</main>\n")
        self.write(self.site / "assets/styles.css", b"body {}\n")
        self.write(self.site / "README.md", b"deployment metadata\n")
        self.write(self.site / "AGENTS.md", b"deployment metadata\n")
        self.write(self.site / ".github/workflows/pages.yml", b"name: ignored\n")
        self.git_command("init", "--initial-branch=main")
        self.git_command("config", "user.name", "RGM Test")
        self.git_command("config", "user.email", "rgm-test@example.invalid")
        self.git_command("add", ".")
        self.git_command("commit", "-m", "site fixture")
        self.commit = self.git_text("rev-parse", "HEAD")
        self.files = ASSEMBLER.observed_manifest(
            self.site,
            ASSEMBLER.collect_artifact_files(self.site),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_assembles_only_allowlisted_files_bound_to_the_prepared_commit(self) -> None:
        output = self.root / "artifact"

        self.run_assembler(self.prepared_record(), output)

        self.assertEqual(
            [".nojekyll", "assets/styles.css", "index.html"],
            sorted(path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()),
        )

    def test_materializes_committed_lf_bytes_from_a_clean_crlf_checkout(self) -> None:
        self.git_command("config", "core.autocrlf", "true")
        committed = subprocess.check_output([self.git, "-C", self.site, "show", "HEAD:index.html"])
        self.write(self.site / "index.html", committed.replace(b"\n", b"\r\n"))
        self.git_command("add", "--", "index.html")
        self.assertEqual("", self.git_text("status", "--porcelain=v1"))
        output = self.root / "artifact"

        self.run_assembler(self.prepared_record(), output)

        self.assertNotEqual(committed, (self.site / "index.html").read_bytes())
        self.assertEqual(committed, (output / "index.html").read_bytes())
        self.assertEqual(self.files, ASSEMBLER.observed_manifest(output, ASSEMBLER.collect_artifact_files(output)))

    def test_preserves_binary_crlf_catalog_object_from_committed_blob(self) -> None:
        catalog_object = "catalog/v9/objects/sha256/" + "a" * 64
        signed_bytes = b"signed payload\r\n"
        self.write(self.site / ".gitattributes", b"* text=auto eol=lf\ncatalog/v9/objects/sha256/* -text -eol\n")
        self.write(self.site / catalog_object, signed_bytes)
        self.git_command("add", ".")
        self.git_command("commit", "-m", "add byte-stable catalog object")
        self.commit = self.git_text("rev-parse", "HEAD")
        self.files = ASSEMBLER.observed_manifest(self.site, ASSEMBLER.collect_artifact_files(self.site))

        output = self.root / "artifact"
        self.run_assembler(self.prepared_record(), output)

        self.assertEqual(signed_bytes, (output / catalog_object).read_bytes())
        self.assertEqual(signed_bytes, subprocess.check_output([self.git, "-C", self.site, "show", f"HEAD:{catalog_object}"]))

    def test_refuses_worktree_derived_manifest_that_disagrees_with_committed_blob(self) -> None:
        committed = (self.site / "index.html").read_bytes()
        self.write(self.site / "index.html", committed.replace(b"\n", b"\r\n"))
        record = self.prepared_record()
        record["artifact"]["files"] = ASSEMBLER.observed_manifest(
            self.site, ASSEMBLER.collect_artifact_files(self.site),
        )
        record["artifact"]["manifestSha256"] = ASSEMBLER.artifact_manifest_sha256(record["artifact"]["files"])
        output = self.root / "artifact"

        with self.assertRaisesRegex(SystemExit, "exact committed site blobs: index.html"):
            self.run_assembler(record, output)

        self.assertFalse(output.exists())

    def test_rejects_nonregular_committed_artifact_modes(self) -> None:
        entry = b"120000 blob " + b"a" * 40 + b"\tindex.html\0"
        with mock.patch.object(ASSEMBLER, "git_bytes", return_value=entry):
            with self.assertRaisesRegex(SystemExit, "not a regular file: index.html"):
                ASSEMBLER.committed_artifact_paths(self.site, self.commit)

    def test_refuses_a_prepared_record_for_another_site_commit(self) -> None:
        output = self.root / "artifact"
        record = self.prepared_record()
        record["site"]["commit"] = "a" * 40

        with self.assertRaisesRegex(SystemExit, "does not bind this exact rgm-site commit"):
            self.run_assembler(record, output)
        self.assertFalse(output.exists())

    def test_future_reader_rejects_historical_prepared_records_without_rewriting_them(self) -> None:
        container = Path(__file__).resolve().parents[3]
        state = container / "publication"
        for version in (7, 8):
            with self.subTest(version=version):
                record = json.loads((state / f"site-publications/prepared/catalog-v{version}.json").read_bytes())
                with self.assertRaisesRegex(SystemExit, "invalid field set"):
                    ASSEMBLER.require_prepared_manifest(record, f"catalog-v{version}", record["site"]["commit"])

        forged = self.prepared_record()
        forged["schemaVersion"] = 1
        forged["state"]["repository"] = "TheFunkyBits/rgm"
        with self.assertRaisesRegex(SystemExit, "invalid field set"):
            ASSEMBLER.require_prepared_manifest(forged, "site-v9", self.commit)

    def test_rejects_supplied_old_field_unknown_inventory_field_and_boolean_byte_count(self) -> None:
        for mutation, expected in (
            (lambda record: record.update(schemaVersion=2), "invalid field set"),
            (lambda record: record["artifact"]["files"][0].update(extra=True), "invalid fields"),
            (lambda record: record["artifact"]["files"][0].update(bytes=True), "invalid byte count"),
        ):
            with self.subTest(expected=expected):
                record = self.prepared_record()
                mutation(record)
                output = self.root / "artifact"
                with self.assertRaisesRegex(SystemExit, expected):
                    self.run_assembler(record, output)
                self.assertFalse(output.exists())

    def test_rejects_duplicate_nested_keys_and_nonfinite_json(self) -> None:
        source = json.dumps(self.prepared_record())
        duplicate = source.replace('"parentCommit":', '"parentCommit": null, "parentCommit":', 1)
        nonfinite = source.replace('"root": "."', '"root": NaN', 1)
        for raw in (duplicate, nonfinite):
            with self.subTest(raw=raw[:45]):
                metadata = self.api_response(raw.encode("utf-8"))
                opener = FakeOpener(json.dumps(metadata).encode("utf-8"))
                with mock.patch.object(ASSEMBLER, "build_opener", return_value=opener):
                    with self.assertRaisesRegex(SystemExit, "Prepared state record is invalid"):
                        ASSEMBLER.read_prepared_record("TheFunkyBits/rgm-publication", "d" * 40, "site-v9")

    def test_authenticated_reader_requests_only_the_exact_commit_and_keeps_token_out_of_url(self) -> None:
        record = self.prepared_record()
        opener = FakeOpener(json.dumps(self.api_response(json.dumps(record).encode("utf-8"))).encode("utf-8"))
        with mock.patch.object(ASSEMBLER, "build_opener", return_value=opener) as factory:
            self.assertEqual(record, ASSEMBLER.read_prepared_record("TheFunkyBits/rgm-publication", "d" * 40, "site-v9"))

        self.assertEqual("Bearer fixture-app-token", opener.request.get_header("Authorization"))
        self.assertEqual(self.api_url(), opener.request.full_url)
        self.assertNotIn("fixture-app-token", opener.request.full_url)
        self.assertEqual(20, opener.timeout)
        self.assertIsInstance(factory.call_args.args[0], ASSEMBLER.RejectRedirects)

    def test_authenticated_reader_fails_closed_without_a_token_or_exact_identity(self) -> None:
        with mock.patch.object(ASSEMBLER, "build_opener") as factory:
            with mock.patch.dict(os.environ, {"RGM_STATE_READ_TOKEN": ""}):
                with self.assertRaisesRegex(SystemExit, "read token is unavailable"):
                    ASSEMBLER.read_prepared_record("TheFunkyBits/rgm-publication", "d" * 40, "site-v9")
            for repository, commit, transaction in (
                ("TheFunkyBits/rgm", "d" * 40, "site-v9"),
                ("TheFunkyBits/rgm-publication", "main", "site-v9"),
                ("TheFunkyBits/rgm-publication", "d" * 40, "../site-v9"),
            ):
                with self.subTest(repository=repository, commit=commit, transaction=transaction):
                    with self.assertRaisesRegex(SystemExit, "selection is invalid"):
                        ASSEMBLER.read_prepared_record(repository, commit, transaction)
            factory.assert_not_called()

    def test_authenticated_reader_rejects_wrong_file_identity_and_noncanonical_bytes(self) -> None:
        raw = json.dumps(self.prepared_record()).encode("utf-8")
        for field, value in (
            ("type", "symlink"),
            ("name", "other.json"),
            ("path", "site-publications/prepared/other.json"),
            ("url", self.api_url().replace("ref=" + "d" * 40, "ref=main")),
            ("sha", "0" * 40),
            ("size", len(raw) + 1),
            ("size", True),
            ("size", 1_048_577),
            ("encoding", "none"),
            ("content", "not-base64!"),
        ):
            with self.subTest(field=field, value=value):
                metadata = self.api_response(raw)
                metadata[field] = value
                opener = FakeOpener(json.dumps(metadata).encode("utf-8"))
                with mock.patch.object(ASSEMBLER, "build_opener", return_value=opener):
                    with self.assertRaisesRegex(SystemExit, "Prepared state API response is invalid"):
                        ASSEMBLER.read_prepared_record("TheFunkyBits/rgm-publication", "d" * 40, "site-v9")

    def test_authenticated_reader_rejects_redirects_and_http_errors_without_token_leak(self) -> None:
        for code in (302, 401, 403, 404):
            with self.subTest(code=code):
                error = HTTPError(self.api_url(), code, "unavailable", {}, None)
                opener = FakeOpener(b"", error=error)
                with mock.patch.object(ASSEMBLER, "build_opener", return_value=opener):
                    with self.assertRaises(SystemExit) as failed:
                        ASSEMBLER.read_prepared_record("TheFunkyBits/rgm-publication", "d" * 40, "site-v9")
                self.assertIn(str(code), str(failed.exception))
                self.assertNotIn("fixture-app-token", str(failed.exception))
        with mock.patch.object(ASSEMBLER, "build_opener", return_value=FakeOpener(
            b"", error=URLError("fixture-app-token network failure"),
        )):
            with self.assertRaisesRegex(SystemExit, "Prepared state API response is invalid") as failed:
                ASSEMBLER.read_prepared_record("TheFunkyBits/rgm-publication", "d" * 40, "site-v9")
        self.assertNotIn("fixture-app-token", str(failed.exception))
        self.assertIsNone(ASSEMBLER.RejectRedirects().redirect_request(None, None, 302, "Found", {}, "https://elsewhere.invalid"))
        record = self.api_response(json.dumps(self.prepared_record()).encode("utf-8"))
        redirected = FakeOpener(json.dumps(record).encode("utf-8"), url="https://elsewhere.invalid")
        with mock.patch.object(ASSEMBLER, "build_opener", return_value=redirected):
            with self.assertRaisesRegex(SystemExit, "Prepared state API response is invalid"):
                ASSEMBLER.read_prepared_record("TheFunkyBits/rgm-publication", "d" * 40, "site-v9")

    def test_authenticated_reader_rejects_duplicate_api_metadata(self) -> None:
        metadata = json.dumps(self.api_response(json.dumps(self.prepared_record()).encode("utf-8")))
        forged = metadata.replace('"path":', '"path": "forged", "path":', 1)
        opener = FakeOpener(forged.encode("utf-8"))
        with mock.patch.object(ASSEMBLER, "build_opener", return_value=opener):
            with self.assertRaisesRegex(SystemExit, "Prepared state API response is invalid"):
                ASSEMBLER.read_prepared_record("TheFunkyBits/rgm-publication", "d" * 40, "site-v9")

    def test_pages_workflow_scopes_private_token_to_publication_contents_read(self) -> None:
        workflow = (MODULE_PATH.parents[1] / "workflows/pages.yml").read_text(encoding="utf-8")
        token_step = workflow.split("      - name: Mint publication read token\n", 1)[1].split(
            "      - name: Assemble prepared artifact\n", 1
        )[0]
        assemble_step = workflow.split("      - name: Assemble prepared artifact\n", 1)[1].split(
            "      - name: Configure Pages\n", 1
        )[0]

        self.assertIn("environment:\n      name: github-pages", workflow)
        self.assertLess(workflow.index("- name: Require canonical site main"), workflow.index("- name: Mint publication read token"))
        self.assertIn("uses: actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1", token_step)
        self.assertIn("client-id: ${{ vars.RGM_PUBLICATION_READ_APP_CLIENT_ID }}", token_step)
        self.assertIn("private-key: ${{ secrets.RGM_PUBLICATION_READ_APP_PRIVATE_KEY }}", token_step)
        self.assertIn("owner: TheFunkyBits", token_step)
        self.assertIn("repositories: rgm-publication", token_step)
        self.assertIn("permission-contents: read", token_step)
        self.assertNotIn("permission-contents: write", token_step)
        self.assertIn("RGM_STATE_READ_TOKEN: ${{ steps.publication-read.outputs.token }}", assemble_step)
        self.assertEqual(1, workflow.count("steps.publication-read.outputs.token"))
        self.assertNotIn("--token", assemble_step)

    def test_refuses_old_state_repository_as_a_new_workflow_input(self) -> None:
        output = self.root / "artifact"
        with self.assertRaisesRegex(SystemExit, "only the canonical rgm-publication"):
            self.run_assembler(self.prepared_record(), output, repository="TheFunkyBits/rgm")
        self.assertFalse(output.exists())

    def prepared_record(self) -> dict:
        return {
            "kind": "rgm-site-prepared-publication",
            "transactionId": "site-v9",
            "predecessor": {"genesisSha256": "a" * 64, "activeSha256": None},
            "state": {"repository": "TheFunkyBits/rgm-publication", "sourceCommit": "b" * 40},
            "site": {
                "repository": "TheFunkyBits/rgm-site",
                "parentCommit": "d" * 40,
                "commit": self.commit,
            },
            "artifact": {
                "root": ".",
                "manifestSha256": ASSEMBLER.artifact_manifest_sha256(self.files),
                "files": [dict(item) for item in self.files],
            },
        }

    @staticmethod
    def api_url() -> str:
        return (
            "https://api.github.com/repos/TheFunkyBits/rgm-publication/contents/"
            "site-publications/prepared/site-v9.json?ref=" + "d" * 40
        )

    def api_response(self, raw: bytes) -> dict:
        return {
            "type": "file",
            "name": "site-v9.json",
            "path": "site-publications/prepared/site-v9.json",
            "url": self.api_url(),
            "size": len(raw),
            "encoding": "base64",
            "content": base64.b64encode(raw).decode("ascii"),
            "sha": hashlib.sha1(f"blob {len(raw)}\0".encode("ascii") + raw).hexdigest(),
        }

    def run_assembler(self, record: dict, output: Path, *, repository: str = "TheFunkyBits/rgm-publication") -> None:
        metadata = self.api_response(json.dumps(record).encode("utf-8"))
        opener = FakeOpener(json.dumps(metadata).encode("utf-8"))
        arguments = [
            str(MODULE_PATH),
            "--site-root",
            str(self.site),
            "--state-repository",
            repository,
            "--state-commit",
            "d" * 40,
            "--site-commit",
            self.commit,
            "--transaction-id",
            "site-v9",
            "--output",
            str(output),
        ]
        with mock.patch.object(ASSEMBLER, "build_opener", return_value=opener):
            with mock.patch.object(sys, "argv", arguments):
                self.assertEqual(0, ASSEMBLER.main())

    def git_command(self, *arguments: str) -> None:
        result = subprocess.run(
            [self.git, "-C", self.site, *arguments],
            cwd=self.site,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr.decode(errors="replace"))

    def git_text(self, *arguments: str) -> str:
        result = subprocess.run(
            [self.git, "-C", self.site, *arguments],
            cwd=self.site,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr.decode(errors="replace"))
        return result.stdout.decode().strip()

    @staticmethod
    def write(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


if __name__ == "__main__":
    unittest.main()
