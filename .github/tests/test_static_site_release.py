from __future__ import annotations

from contextlib import nullcontext
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from rgm_site_tools.static_site_release import StaticSiteRelease


COMMIT, BASE = "a" * 40, "b" * 40


class FakeGit:
    def __init__(self, site):
        self.site = site
        self.site_remote = BASE
        self.site_head = COMMIT
        self.calls = []
        self.lose_push_ack = False

    def __call__(self, command, *, cwd, stdin=None):
        if cwd != self.site:
            raise AssertionError("Only the site checkout may be used")
        args = command[3:]
        self.calls.append((cwd, args))
        if args == ["config", "--get", "--bool", "remote.origin.mirror"]:
            return subprocess.CompletedProcess(command, 1, b"", b"")
        if args == ["remote", "get-url", "origin"] or args == [
            "remote",
            "get-url",
            "--push",
            "--all",
            "origin",
        ]:
            data = b"https://github.com/TheFunkyBits/rgm-site.git\n"
        elif args == ["symbolic-ref", "--quiet", "--short", "HEAD"]:
            data = b"main\n"
        elif args == ["status", "--porcelain=v1", "--untracked-files=all"]:
            data = b""
        elif args == ["rev-parse", "--verify", "HEAD"]:
            data = (self.site_head + "\n").encode()
        elif args == ["ls-remote", "origin", "refs/heads/main"]:
            data = (self.site_remote + "\trefs/heads/main\n").encode()
        elif args == ["rev-parse", "--path-format=absolute", "--git-dir"]:
            data = (str(cwd / ".git") + "\n").encode()
        elif args == ["rev-parse", "--path-format=absolute", "--git-path", "rgm-site-publication.lock"]:
            data = (str(cwd / ".git/rgm-site-publication.lock") + "\n").encode()
        elif args == ["merge-base", "--is-ancestor", BASE, COMMIT]:
            data = b""
        elif args == ["push", "--no-follow-tags", "origin", f"{COMMIT}:refs/heads/main"]:
            self.site_remote = COMMIT
            if self.lose_push_ack:
                return subprocess.CompletedProcess(command, 1, b"", b"lost acknowledgement")
            data = b""
        else:
            raise AssertionError(f"Unexpected Git operation: {args}")
        return subprocess.CompletedProcess(command, 0, data, b"")


class FakeGateway:
    def __init__(self):
        self.dispatches = 0
        self.lose_ack = False
        self.status = "run-not-visible"

    def require_dispatch_token(self):
        pass

    def require_vacant_dispatch(self, commit):
        pass

    def dispatch(self, commit, *, record_attempt):
        record_attempt(commit)
        self.dispatches += 1
        if self.lose_ack:
            raise ValueError("lost dispatch acknowledgement")

    def inspect_deployment(self, commit):
        return self.status


class StaticSiteReleaseTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.site = root / "site"
        (self.site / ".git").mkdir(parents=True)
        self.git = root / "git.exe"
        self.git.write_bytes(b"synthetic")
        self.transport = FakeGit(self.site)
        self.gateway = FakeGateway()
        self.route = StaticSiteRelease(
            self.site,
            self.git,
            self.gateway,
            runner=self.transport,
            validate_site=lambda commit: None,
            lock=nullcontext,
        )

    def test_reviewed_push_dispatch_and_inspection_need_only_site_and_do_not_create_catalog_tags(self):
        self.assertEqual("dispatch-attempted", self.route.begin(COMMIT, BASE)["status"])
        self.assertEqual(1, self.gateway.dispatches)
        self.assertEqual("run-not-visible", self.route.inspect(COMMIT)["status"])
        self.gateway.status = "served"
        self.assertEqual("served", self.route.inspect(COMMIT)["status"])
        self.assertFalse(any("tag" in args or "--force" in args for _, args in self.transport.calls))
        with self.assertRaises(ValueError):
            self.route.begin(COMMIT, BASE)
        with self.assertRaises(ValueError):
            self.route.reconcile(COMMIT)
        self.assertEqual(1, self.gateway.dispatches)

    def test_lost_dispatch_ack_is_durable_and_never_replayed(self):
        self.gateway.lose_ack = True
        with self.assertRaises(ValueError):
            self.route.begin(COMMIT, BASE)
        value = json.loads((self.site / ".git" / f"rgm-site-{COMMIT}.operation.json").read_text())
        self.assertEqual({"siteCommit", "siteBase", "phase"}, set(value))
        self.assertEqual("dispatch-attempted", value["phase"])
        with self.assertRaises(ValueError):
            self.route.reconcile(COMMIT)
        self.assertEqual(1, self.gateway.dispatches)

    def test_lost_push_ack_requires_observed_original_commit_and_only_dispatch_reconciliation(self):
        self.transport.lose_push_ack = True
        with self.assertRaises(ValueError):
            self.route.begin(COMMIT, BASE)
        self.assertEqual(0, self.gateway.dispatches)
        self.assertEqual("site-pushed-await-dispatch-approval", self.route.inspect(COMMIT)["status"])
        self.route.reconcile(COMMIT)
        self.assertEqual(1, self.gateway.dispatches)
        self.assertEqual(1, sum(args[0] == "push" for _, args in self.transport.calls))

    def test_site_head_or_remote_base_drift_stops_before_mutation(self):
        for attribute in ("site_head", "site_remote"):
            with self.subTest(drift=attribute):
                original = getattr(self.transport, attribute)
                setattr(self.transport, attribute, "d" * 40)
                with self.assertRaises(ValueError):
                    self.route.begin(COMMIT, BASE)
                self.assertEqual(0, self.gateway.dispatches)
                self.assertFalse(any(args[0] == "push" for _, args in self.transport.calls))
                setattr(self.transport, attribute, original)

    def test_readiness_failure_prevents_control_creation_push_and_dispatch(self):
        def unavailable(commit):
            raise ValueError("cutover not active")

        self.route.validate_site = unavailable
        with self.assertRaises(ValueError):
            self.route.begin(COMMIT, BASE)
        self.assertEqual([], list((self.site / ".git").iterdir()))
        self.assertEqual(0, self.gateway.dispatches)

    def test_default_lock_and_control_are_site_local(self):
        route = StaticSiteRelease(
            self.site,
            self.git,
            self.gateway,
            runner=self.transport,
            validate_site=lambda commit: None,
        )
        self.assertEqual("dispatch-attempted", route.begin(COMMIT, BASE)["status"])
        self.assertTrue((self.site / ".git/rgm-site-publication.lock").is_file())
        self.assertTrue((self.site / ".git" / f"rgm-site-{COMMIT}.operation.json").is_file())


if __name__ == "__main__":
    unittest.main()
