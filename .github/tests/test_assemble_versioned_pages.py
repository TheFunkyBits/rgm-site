from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock


MODULE = Path(__file__).parents[1] / "scripts" / "assemble_versioned_pages.py"
SPEC = importlib.util.spec_from_file_location("assemble_versioned_pages", MODULE)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load {MODULE}")
ASSEMBLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ASSEMBLER)


class VersionedPagesAssemblyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.site = self.root / "site"
        self.site.mkdir()
        self.output = self.root / "pages-artifact"
        self.write("index.html", "<main>RGM</main>\n")
        self.write(".nojekyll", "")
        self.write("catalog/v8/index.json", '{"catalogVersion":8}\n')
        self.write("catalog/v9/index.json", '{"catalogVersion":9}\n')
        self.write("trust/catalog-keys.json", '{"keys":[]}\n')
        self.write(".gitattributes", "* text=auto eol=lf\ncatalog/v8/objects/sha256/* -text -eol\n")
        self.write(".github/versioned-catalog-cutover.json",
               '{"contract":"rgm-unsigned-catalog-v1","enabled":true}\n')
        self.git("init", "--initial-branch=main")
        self.git("config", "user.name", "Pages Test")
        self.git("config", "user.email", "pages@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.git("add", ".")
        self.git("commit", "-m", "original served site")
        self.write("catalog/v10/index.json", '{"catalogVersion":10}\n')
        self.write("catalog/v10/objects/catalog.json", '{"titles":[]}\n')
        self.git("add", ".")
        self.git("commit", "-m", "new versioned catalog")
        self.commit = self.git("rev-parse", "HEAD").strip()

    def write(self, relative: str, data: str) -> None:
        path = self.site / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8")

    def git(self, *arguments: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(self.site), *arguments], check=True,
            capture_output=True, text=True, encoding="utf-8",
        )
        return completed.stdout

    def test_stages_only_public_checkout_paths_with_no_publication_state(self) -> None:
        count = ASSEMBLER.assemble(self.site, self.commit, 10, self.output)

        self.assertEqual(7, count)
        self.assertTrue((self.output / "catalog/v10/index.json").is_file())
        self.assertTrue((self.output / "catalog/v8/index.json").is_file())
        self.assertTrue((self.output / "catalog/v9/index.json").is_file())
        self.assertFalse((self.output / ".github").exists())
        self.assertFalse((self.output / ".gitattributes").exists())
        self.assertEqual(self.commit, self.git("rev-parse", "HEAD").strip())

    def test_clean_crlf_checkout_stages_git_selected_legacy_paths_without_identity_receipts(self) -> None:
        self.git("config", "core.autocrlf", "true")
        (self.site / "index.html").write_bytes(b"<main>RGM</main>\r\n")
        self.assertEqual("", self.git("status", "--porcelain=v1"))
        binary = self.site / "catalog/v9/objects/sha256/old"
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_bytes(b"still-served-binary\r\n")
        self.write(".gitattributes", (self.site / ".gitattributes").read_text(encoding="utf-8") +
                   "catalog/v9/objects/sha256/* -text -eol\n")
        self.git("add", ".")
        self.git("commit", "-m", "preserve synthetic served v9 bytes")
        self.write("catalog/v11/index.json", '{"catalogVersion":11}\n')
        self.write("catalog/v11/objects/catalog.json", '{"titles":[]}\n')
        self.git("add", ".")
        self.git("commit", "-m", "introduce another version without changing v9")
        self.commit = self.git("rev-parse", "HEAD").strip()
        (self.site / "index.html").write_bytes(b"<main>RGM</main>\r\n")
        self.assertEqual("", self.git("status", "--porcelain=v1"))

        ASSEMBLER.assemble(self.site, self.commit, 11, self.output)

        self.assertTrue((self.output / "index.html").is_file())
        self.assertTrue((self.output / "catalog/v9/objects/sha256/old").is_file())
        self.assertEqual(self.commit, self.git("rev-parse", "HEAD").strip())

    def test_rejects_wrong_commit_old_version_and_absent_version_without_output(self) -> None:
        for commit, version in (("a" * 40, 10), (self.commit, 9), (self.commit, 11)):
            with self.subTest(commit=commit[:8], version=version):
                with self.assertRaises(ASSEMBLER.PagesAssemblyError):
                    ASSEMBLER.assemble(self.site, commit, version, self.output)
                self.assertFalse(self.output.exists())

    def test_rejects_redispatch_of_existing_version_or_unrelated_commit(self) -> None:
        self.git("commit", "--allow-empty", "-m", "unrelated site commit")
        latest = self.git("rev-parse", "HEAD").strip()
        with self.assertRaisesRegex(ASSEMBLER.PagesAssemblyError, "already existed"):
            ASSEMBLER.assemble(self.site, latest, 10, self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_a_new_version_commit_with_an_unrelated_change(self) -> None:
        self.write("catalog/v11/index.json", '{"catalogVersion":11}\n')
        self.write("catalog/v11/objects/catalog.json", '{"titles":[]}\n')
        self.write("index.html", "unrelated rewrite\n")
        self.git("add", ".")
        self.git("commit", "-m", "mix a new version with unrelated content")
        latest = self.git("rev-parse", "HEAD").strip()
        with self.assertRaisesRegex(ASSEMBLER.PagesAssemblyError, "does not add exactly"):
            ASSEMBLER.assemble(self.site, latest, 11, self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_dirty_and_untracked_paths_instead_of_packaging_them(self) -> None:
        self.write("index.html", "changed\n")
        with self.assertRaisesRegex(ASSEMBLER.PagesAssemblyError, "local or untracked"):
            ASSEMBLER.assemble(self.site, self.commit, 10, self.output)
        self.git("checkout", "--", "index.html")
        self.write("assets/untracked.txt", "untracked\n")
        with self.assertRaisesRegex(ASSEMBLER.PagesAssemblyError, "local or untracked"):
            ASSEMBLER.assemble(self.site, self.commit, 10, self.output)
        self.assertFalse(self.output.exists())

    def test_refuses_occupied_output_and_untrusted_root_paths(self) -> None:
        self.output.mkdir()
        with self.assertRaisesRegex(ASSEMBLER.PagesAssemblyError, "output must be unused"):
            ASSEMBLER.assemble(self.site, self.commit, 10, self.output)
        self.assertFalse(any(self.output.iterdir()))
        with self.assertRaisesRegex(ASSEMBLER.PagesAssemblyError, "outside the deployment boundary"):
            ASSEMBLER.artifact_path("private/sensitive.txt")
        with self.assertRaisesRegex(ASSEMBLER.PagesAssemblyError, "Unsafe site path"):
            ASSEMBLER.artifact_path("catalog/v10/../v9/index.json")

    def test_dispatch_cannot_bypass_current_prepared_gate_before_policy_cutover(self) -> None:
        self.git("rm", "--", ASSEMBLER.CUTOVER_MARKER)
        self.git("commit", "-m", "synthetic pre-cutover site")
        self.commit = self.git("rev-parse", "HEAD").strip()
        with self.assertRaisesRegex(ASSEMBLER.PagesAssemblyError, "cutover is not active"):
            ASSEMBLER.assemble(self.site, self.commit, 10, self.output)
        with self.assertRaisesRegex(ASSEMBLER.PagesAssemblyError, "cutover is not active"):
            ASSEMBLER.preflight_cutover(self.site, self.commit)
        self.assertFalse(self.output.exists())

    def test_tracked_site_marker_can_be_preflighted_without_assembling_or_mutating(self) -> None:
        ASSEMBLER.preflight_cutover(self.site, self.commit)
        self.assertFalse(self.output.exists())
        self.assertEqual("", self.git("status", "--porcelain=v1"))

    def test_preflight_for_interrupted_staging_only_allows_the_selected_untracked_version(self) -> None:
        self.write("catalog/v11/index.json", '{"catalogVersion":11}\n')
        self.write("catalog/v11/objects/catalog.json", '{"titles":[]}\n')
        with self.assertRaisesRegex(ASSEMBLER.PagesAssemblyError, "local or untracked"):
            ASSEMBLER.preflight_cutover(self.site, self.commit)
        ASSEMBLER.preflight_cutover(self.site, self.commit, 11)
        with self.assertRaisesRegex(ASSEMBLER.PagesAssemblyError, "besides the selected"):
            ASSEMBLER.preflight_cutover(self.site, self.commit, 12)
        self.write("README.md", "unrelated\n")
        with self.assertRaisesRegex(ASSEMBLER.PagesAssemblyError, "besides the selected"):
            ASSEMBLER.preflight_cutover(self.site, self.commit, 11)
        (self.site / "README.md").unlink()
        self.write(ASSEMBLER.CUTOVER_MARKER, '{"contract":"invalid","enabled":true}\n')
        with self.assertRaisesRegex(ASSEMBLER.PagesAssemblyError, "besides the selected"):
            ASSEMBLER.preflight_cutover(self.site, self.commit, 11)

    def test_staged_only_preflight_refuses_a_linked_new_version_file(self) -> None:
        self.write("catalog/v11/index.json", '{"catalogVersion":11}\n')
        outside = self.root / "outside.json"
        outside.write_text("private", encoding="utf-8")
        objects = self.site / "catalog/v11/objects"
        objects.mkdir()
        linked = objects / "catalog.json"
        try:
            linked.symlink_to(outside)
        except (NotImplementedError, OSError) as unsupported:
            self.skipTest(f"This filesystem cannot create symbolic links: {unsupported}")

        with self.assertRaisesRegex(ASSEMBLER.PagesAssemblyError, "linked or nonregular"):
            ASSEMBLER.preflight_cutover(self.site, self.commit, 11)
        self.assertFalse(self.output.exists())

    def test_malformed_or_duplicate_policy_marker_cannot_activate_the_workflow(self) -> None:
        marker = self.site / ASSEMBLER.CUTOVER_MARKER
        for content in (
            '{"contract":"rgm-unsigned-catalog-v1","enabled":false}\n',
            '{"contract":"rgm-unsigned-catalog-v1","enabled":1}\n',
            '{"contract":"rgm-unsigned-catalog-v1","enabled":"true"}\n',
            '{"contract":"rgm-unsigned-catalog-v1","enabled":true,"enabled":true}\n',
            '{"contract":"rgm-unsigned-catalog-v1","enabled":true,"extra":true}\n',
        ):
            with self.subTest(content=content):
                marker.write_text(content, encoding="utf-8")
                self.git("add", "--", ASSEMBLER.CUTOVER_MARKER)
                self.git("commit", "-m", "synthetic unapproved cutover marker")
                self.commit = self.git("rev-parse", "HEAD").strip()
                with self.assertRaises(ASSEMBLER.PagesAssemblyError):
                    ASSEMBLER.assemble(self.site, self.commit, 10, self.output)
                self.assertFalse(self.output.exists())

    def test_refuses_a_symlinked_catalog_path(self) -> None:
        (self.site / "catalog/v10/index.json").unlink()
        outside = self.root / "external-index.json"
        outside.write_text("outside", encoding="utf-8")
        try:
            (self.site / "catalog/v10/index.json").symlink_to(outside)
        except (NotImplementedError, OSError) as unsupported:
            self.skipTest(f"This filesystem cannot create symbolic links: {unsupported}")
        with self.assertRaises(ASSEMBLER.PagesAssemblyError):
            ASSEMBLER.assemble(self.site, self.commit, 10, self.output)
        self.assertTrue(outside.is_file())
        self.assertFalse(self.output.exists())

    def test_refuses_a_linked_artifact_root_without_walking_its_target(self) -> None:
        outside = self.root / "outside-tree"
        (self.site / "trust").rename(outside)
        try:
            (self.site / "trust").symlink_to(outside, target_is_directory=True)
        except (NotImplementedError, OSError) as unsupported:
            self.skipTest(f"This filesystem cannot create symbolic links: {unsupported}")
        with self.assertRaisesRegex(ASSEMBLER.PagesAssemblyError, "contains a link"):
            ASSEMBLER.collect_checkout(self.site)
        self.assertTrue((outside / "catalog-keys.json").is_file())

    def test_copy_interruption_cleans_staging_without_touching_site(self) -> None:
        actual_run = subprocess.run

        def interrupted(arguments, **kwargs):
            if "show" in arguments:
                raise OSError("interrupted")
            return actual_run(arguments, **kwargs)

        with mock.patch.object(ASSEMBLER.subprocess, "run", side_effect=interrupted):
            with self.assertRaisesRegex(OSError, "interrupted"):
                ASSEMBLER.assemble(self.site, self.commit, 10, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual([], list(self.root.glob(".pages-artifact.*")))
        self.assertTrue((self.site / "catalog/v10/index.json").is_file())

    def test_versioned_workflow_dispatch_requires_exact_commit_and_no_prepared_state(self) -> None:
        workflow = (MODULE.parents[1] / "workflows/pages-versioned.yml").read_text(encoding="utf-8")
        self.assertIn("run-name: Deploy RGM catalog v${{ inputs['catalog-version'] }} (${{ inputs['site-commit'] }})", workflow)
        self.assertIn("github.sha != inputs['site-commit']", workflow)
        self.assertIn("github.repository != 'TheFunkyBits/rgm-site'", workflow)
        self.assertIn("--site-commit \"$GITHUB_SHA\"", workflow)
        self.assertIn("assemble_versioned_pages.py", workflow)
        self.assertIn("fetch-depth: 2", workflow)
        self.assertLess(workflow.index("Stage versioned Pages artifact"), workflow.index("Upload Pages artifact"))
        self.assertNotIn("RGM_STATE_READ_TOKEN", workflow)
        self.assertNotIn("prepared", workflow.lower())
        self.assertFalse((MODULE.parents[1] / "workflows/pages.yml").exists())


if __name__ == "__main__":
    unittest.main()
