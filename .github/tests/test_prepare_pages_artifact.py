from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "prepare_pages_artifact.py"
MODULE_SPEC = importlib.util.spec_from_file_location("prepare_pages_artifact", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Cannot load {MODULE_PATH}")
ASSEMBLER = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(ASSEMBLER)


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class PreparePagesArtifactTest(unittest.TestCase):
    def setUp(self) -> None:
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

    def test_refuses_a_prepared_record_for_another_site_commit(self) -> None:
        output = self.root / "artifact"
        record = self.prepared_record()
        record["site"]["commit"] = "a" * 40

        with self.assertRaisesRegex(SystemExit, "does not bind this exact rgm-site commit"):
            self.run_assembler(record, output)
        self.assertFalse(output.exists())

    def test_reads_exact_historical_v8_record_but_not_a_new_old_name_record(self) -> None:
        container = Path(__file__).resolve().parents[3]
        state = container / "rgm-publication"
        if not state.is_dir():
            state = container / "rgm"
        record = json.loads((state / "site-publications/prepared/catalog-v8.json").read_bytes())
        original = ASSEMBLER.require_prepared_manifest(record, "catalog-v8", record["site"]["commit"])
        self.assertTrue(original)

        forged = self.prepared_record()
        forged["schemaVersion"] = 1
        forged["state"]["repository"] = "TheFunkyBits/rgm"
        with self.assertRaisesRegex(SystemExit, "Prepared historical record is not one of the exact"):
            ASSEMBLER.require_prepared_manifest(forged, "site-v9", self.commit)

    def test_refuses_old_state_repository_as_a_new_workflow_input(self) -> None:
        output = self.root / "artifact"
        with self.assertRaisesRegex(SystemExit, "only the canonical rgm-publication"):
            self.run_assembler(self.prepared_record(), output, repository="TheFunkyBits/rgm")
        self.assertFalse(output.exists())

    def prepared_record(self) -> dict:
        return {
            "schemaVersion": 2,
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
                "files": self.files,
            },
        }

    def run_assembler(self, record: dict, output: Path, *, repository: str = "TheFunkyBits/rgm-publication") -> None:
        response = FakeResponse(json.dumps(record).encode("utf-8"))
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
        with mock.patch.object(ASSEMBLER, "urlopen", return_value=response):
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
