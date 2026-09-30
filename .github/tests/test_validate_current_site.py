from __future__ import annotations

from pathlib import Path
import subprocess
import json
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from validate_current_site import validate_site  # noqa: E402


class CurrentSiteValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.site = self.root / "site"
        for relative in (
            "index.html", "assets/styles.css", "catalog/v8/index.json",
            "catalog/v8/index.signatures.json", "catalog/v9/index.json",
            "catalog/v9/index.signatures.json", "trust/catalog-keys.json", "trust/keys.json",
        ):
            path = self.site / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("historical resource\n", encoding="utf-8")
        for version in (8, 9):
            (self.site / f"catalog/v{version}/index.json").write_text(json.dumps({
                "catalogVersion": version, "files": [{"objectPath": "objects/legacy-object"}]
            }), encoding="utf-8")
            obj = self.site / f"catalog/v{version}/objects/legacy-object"
            obj.parent.mkdir()
            obj.write_text("retained historical object\n", encoding="utf-8")

    def test_old_client_graph_paths_are_required_without_hashing_payloads(self) -> None:
        self.assertEqual({"status": "paths-present", "legacyCatalogs": [8, 9]},
                         validate_site(self.site))
        (self.site / "catalog/v9/index.json").unlink()
        with self.assertRaisesRegex(ValueError, "old-client site paths are missing"):
            validate_site(self.site)

    def test_index_presence_does_not_hide_a_missing_old_client_object(self) -> None:
        (self.site / "catalog/v8/objects/legacy-object").unlink()
        with self.assertRaisesRegex(ValueError, "graph is incomplete"):
            validate_site(self.site)

    def test_legacy_object_references_cannot_escape_the_served_version(self) -> None:
        (self.site / "catalog/v8/index.json").write_text(
            '{"files":[{"objectPath":"objects/../../outside"}]}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unsafe object-path"):
            validate_site(self.site)

    def test_linked_old_client_file_cannot_escape_site(self) -> None:
        file = self.site / "catalog/v8/index.json"
        file.unlink()
        outside = self.root / "outside"
        outside.write_text("outside", encoding="utf-8")
        try:
            file.symlink_to(outside)
        except (NotImplementedError, OSError):
            self.skipTest("Host cannot create a file symlink")
        with self.assertRaises(ValueError):
            validate_site(self.site)

    def test_new_catalog_uses_only_installed_client_semantic_verifier(self) -> None:
        index = self.site / "catalog/v10/index.json"
        index.parent.mkdir(parents=True)
        index.write_text("unparsed by site validator\n", encoding="utf-8")
        java = self.root / "java"
        java.write_bytes(b"java")
        library = self.root / "client/lib"
        library.mkdir(parents=True)
        (library / "catalog-publisher.jar").write_bytes(b"jar")
        seen: list[list[str]] = []

        def run(command, **kwargs):
            seen.append(command)
            self.assertEqual(self.site, kwargs["cwd"])
            return subprocess.CompletedProcess(command, 0,
                b'{"catalogVersion":10,"fileCount":3}\n', b"")

        with self.assertRaisesRegex(ValueError, "needs version >9"):
            validate_site(self.site, catalog_version=10)
        verified = validate_site(self.site, catalog_version=10, java=java,
                                 publisher_lib=library, runner=run)
        self.assertEqual(10, verified["catalogVersion"])
        self.assertEqual(1, len(seen))
        self.assertIn("verify-unsigned-release", seen[0])
        self.assertNotIn("org.gradle.wrapper.GradleWrapperMain", seen[0])

        def wrong(command, **kwargs):
            return subprocess.CompletedProcess(command, 0,
                b'{"catalogVersion":11,"fileCount":3}\n', b"")

        with self.assertRaisesRegex(ValueError, "did not verify"):
            validate_site(self.site, catalog_version=10, java=java,
                          publisher_lib=library, runner=wrong)


if __name__ == "__main__":
    unittest.main()
