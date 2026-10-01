from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


MODULE = Path(__file__).parents[1] / "scripts/require_current_site_main.py"
SPEC = importlib.util.spec_from_file_location("require_current_site_main", MODULE)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load {MODULE}")
OWNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OWNER)


class CurrentSiteMainTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.site = self.root / "site"
        self.site.mkdir()
        self.git = self.root / "git.exe"
        self.git.write_text("synthetic Git\n")
        self.commit = "a" * 40
        self.head = self.commit
        self.remote_commit = self.commit
        self.origin = b"https://github.com/TheFunkyBits/rgm-site.git\n"
        self.commands: list[tuple[str, ...]] = []

    def invoke(self, arguments: list[str], *, cwd: Path) -> subprocess.CompletedProcess[bytes]:
        self.assertEqual([str(self.git), "-C", str(self.site)], arguments[:3])
        self.assertEqual(self.site, cwd)
        command = tuple(arguments[3:])
        self.commands.append(command)
        if command == ("remote", "get-url", "origin"):
            result = self.origin
        elif command == ("rev-parse", "--verify", "HEAD"):
            result = f"{self.head}\n".encode()
        elif command == ("ls-remote", "origin", "refs/heads/main"):
            result = f"{self.remote_commit}\trefs/heads/main\n".encode()
        else:
            self.fail(f"Unexpected or mutating Git command: {command}")
        return subprocess.CompletedProcess(arguments, 0, result, b"")

    def check(self) -> None:
        OWNER.require_current_site_main(self.site, self.git, self.commit, runner=self.invoke)

    def test_canonical_site_main_is_checked_with_only_read_only_git_calls(self) -> None:
        self.check()
        self.origin = b"https://github.com/TheFunkyBits/rgm-site\n"
        self.check()
        self.assertEqual(2, self.commands.count(("ls-remote", "origin", "refs/heads/main")))
        self.assertFalse(any(command[0] in {"fetch", "commit", "push", "tag"} for command in self.commands))

    def test_remote_drift_or_other_origin_rejects_stale_queued_pages(self) -> None:
        self.remote_commit = "b" * 40
        with self.assertRaisesRegex(ValueError, "advanced"):
            self.check()
        self.remote_commit = self.commit
        self.origin = b"https://example.invalid/rgm-site.git\n"
        with self.assertRaisesRegex(ValueError, "noncanonical"):
            self.check()
        self.assertFalse(any(command[0] in {"push", "tag"} for command in self.commands))

    def test_wrong_checkout_or_ambiguous_remote_ref_never_confirms_site_main(self) -> None:
        self.head = "b" * 40
        with self.assertRaisesRegex(ValueError, "not the selected"):
            self.check()
        self.head = self.commit
        self.remote_commit = self.commit + "\n" + "c" * 40
        with self.assertRaisesRegex(ValueError, "advanced"):
            self.check()

    def test_static_pages_workflow_rechecks_remote_main_around_deployment(self) -> None:
        workflows = MODULE.parents[1] / "workflows"
        for name, stage in (("pages.yml", "Stage intro and privacy artifact"),):
            with self.subTest(name=name):
                workflow = (workflows / name).read_text(encoding="utf-8")
                preflight = "python -B .github/scripts/require_current_site_main.py"
                self.assertEqual(2, workflow.count(preflight))
                self.assertLess(workflow.index(stage), workflow.index("Confirm current site main before Pages upload"))
                self.assertLess(workflow.index("Confirm current site main before Pages upload"),
                                workflow.index("Upload Pages artifact"))
                self.assertLess(workflow.index("Upload Pages artifact"),
                                workflow.index("Confirm current site main before Pages deployment"))
                self.assertLess(workflow.index("Confirm current site main before Pages deployment"),
                                workflow.index("Deploy to GitHub Pages"))


if __name__ == "__main__":
    unittest.main()
