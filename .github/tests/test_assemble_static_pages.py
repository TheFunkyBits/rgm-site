from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


MODULE = Path(__file__).parents[1] / "scripts/assemble_static_pages.py"
SPEC = importlib.util.spec_from_file_location("assemble_static_pages", MODULE)
ASSEMBLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ASSEMBLER)


class StaticPagesAssemblyTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.site = self.root / "site"
        self.site.mkdir()
        self.write("index.html", '<h1>Example app</h1><a href="/rgm-site/privacy/">Privacy</a>')
        self.write("privacy/index.html", '<h1>Privacy</h1><a href="/rgm-site/">Home</a>')
        self.write("assets/styles.css", "body { color: black; }")
        self.write(".nojekyll", "")
        self.write(ASSEMBLER.CUTOVER_MARKER, '{"contract":"rgm-static-pages-v1","enabled":true}')
        self.git("init", "--initial-branch=main")
        self.git("config", "user.name", "Static Pages Test")
        self.git("config", "user.email", "pages@example.invalid")
        self.git("add", ".")
        self.git("commit", "-m", "reviewed synthetic static site")
        self.commit = self.git("rev-parse", "HEAD").strip()
        self.output = self.root / "artifact"

    def write(self, name, source):
        path = self.site / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    def git(self, *arguments):
        return subprocess.run(
            [ASSEMBLER.GIT, "-C", str(self.site), *arguments],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout

    def commit_changes(self):
        self.git("add", ".")
        self.git("commit", "-m", "synthetic changed site")
        self.commit = self.git("rev-parse", "HEAD").strip()

    def test_stages_exactly_intro_privacy_and_minimal_local_assets(self):
        self.write(".github/scripts/static_site_release.py", "pass\n")
        self.write(".github/scripts/rgm_site_tools/__init__.py", "")
        self.commit_changes()
        self.assertEqual(4, ASSEMBLER.assemble(self.site, self.commit, self.output))
        self.assertEqual(
            set(ASSEMBLER.REQUIRED_FILES),
            {path.relative_to(self.output).as_posix() for path in self.output.rglob("*") if path.is_file()},
        )
        self.assertEqual("static-pages-valid", ASSEMBLER.validate_artifact(self.output)["status"])
        self.assertFalse((self.output / ".github").exists())

    def test_wrong_or_dirty_commit_cannot_stage(self):
        with self.assertRaises(ASSEMBLER.PagesAssemblyError):
            ASSEMBLER.assemble(self.site, "a" * 40, self.output)
        self.write("index.html", "changed")
        with self.assertRaises(ASSEMBLER.PagesAssemblyError):
            ASSEMBLER.assemble(self.site, self.commit, self.output)
        self.assertFalse(self.output.exists())

    def test_undeclared_resources_are_rejected_without_removal(self):
        for name in ("extra/metadata.json", "other/keys.json"):
            with self.subTest(path=name):
                self.write(name, "{}")
                self.commit_changes()
                with self.assertRaisesRegex(ASSEMBLER.PagesAssemblyError, "outside the intro/privacy"):
                    ASSEMBLER.assemble(self.site, self.commit, self.output)
                self.assertTrue((self.site / name).is_file())
                self.assertFalse(self.output.exists())
                path = self.site / name
                path.unlink()
                while path.parent != self.site:
                    path = path.parent
                    path.rmdir()
                self.commit_changes()

    def test_wrong_or_duplicate_marker_cannot_activate_static_pages(self):
        for source in (
            '{"contract":"unexpected-contract","enabled":true}',
            '{"contract":"rgm-static-pages-v1","enabled":true,"enabled":true}',
        ):
            self.write(ASSEMBLER.CUTOVER_MARKER, source)
            self.commit_changes()
            with self.assertRaises(ASSEMBLER.PagesAssemblyError):
                ASSEMBLER.assemble(self.site, self.commit, self.output)
            self.assertFalse(self.output.exists())

    def test_broken_base_paths_and_external_media_are_rejected(self):
        for source in (
            '<a href="/privacy/">Wrong base path</a>',
            '<a href="/rgm-site/missing/">Missing</a>',
            '<img src="https://media.invalid/image.png">',
            '<iframe src="https://video.invalid/embed"></iframe>',
        ):
            self.write("index.html", source)
            self.commit_changes()
            with self.assertRaises(ASSEMBLER.PagesAssemblyError):
                ASSEMBLER.assemble(self.site, self.commit, self.output)
            self.assertFalse(self.output.exists())

    def test_occupied_output_is_never_replaced(self):
        self.output.mkdir()
        with self.assertRaises(ASSEMBLER.PagesAssemblyError):
            ASSEMBLER.assemble(self.site, self.commit, self.output)
        self.assertEqual([], list(self.output.iterdir()))

    def test_publication_refuses_an_empty_destination_created_at_the_final_boundary(self):
        publish = ASSEMBLER._publish_directory

        def occupy(source, destination):
            destination.mkdir()
            publish(source, destination)

        with mock.patch.object(ASSEMBLER, "_publish_directory", side_effect=occupy):
            with self.assertRaises(FileExistsError):
                ASSEMBLER.assemble(self.site, self.commit, self.output)
        self.assertTrue(self.output.is_dir())
        self.assertEqual([], list(self.output.iterdir()))
        self.assertFalse(list(self.root.glob(".artifact.*")))

    def test_no_output_preflight_rejects_invalid_pages_before_publication(self):
        for source in (
            '<a href="/rgm-site/missing/">Missing</a>',
            '<iframe src="https://video.invalid/embed"></iframe>',
        ):
            self.write("index.html", source)
            self.commit_changes()
            with self.assertRaises(ASSEMBLER.PagesAssemblyError):
                ASSEMBLER.preflight(self.site, self.commit)
            self.assertFalse(self.output.exists())

    def test_workflow_uses_only_reviewed_commit_and_preserves_two_drift_checks(self):
        workflow = (MODULE.parents[1] / "workflows/pages.yml").read_text(encoding="utf-8")
        self.assertIn("github.sha != inputs['site-commit']", workflow)
        self.assertIn("assemble_static_pages.py", workflow)
        self.assertIn("ref: main", workflow)
        self.assertEqual(2, workflow.count("require_current_site_main.py"))


if __name__ == "__main__":
    unittest.main()
