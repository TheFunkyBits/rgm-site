"""Reviewed static-site Git and Pages phases with durable, non-replay controls."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import sys
import tempfile

from .publication_lock import publication_lock, _run_process
from .static_pages_gateway import COMMIT


def regular(path: Path, *, directory=False) -> Path:
    if not path.is_absolute():
        raise ValueError("Publication paths must be explicit and absolute")
    info = os.lstat(path)
    if (
        path.is_symlink()
        or path.resolve(strict=True) != path
        or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
    ):
        raise ValueError("Publication input is linked, nonregular or noncanonical")
    return path


def unique(pairs):
    document = {}
    for key, value in pairs:
        if key in document:
            raise ValueError("Operation control repeats a field")
        document[key] = value
    return document


class CanonicalGit:
    def __init__(self, root: Path, git: Path, runner=_run_process):
        self.root = regular(root, directory=True)
        self.git = regular(git)
        self.origin = b"https://github.com/TheFunkyBits/rgm-site.git\n"
        self.runner = runner

    def command(self, *arguments):
        result = self.runner([str(self.git), "-C", str(self.root), *arguments], cwd=self.root)
        if result.returncode:
            raise ValueError("Git operation stopped; inspect before retry")
        return result.stdout

    def ensure_main(self):
        if (
            self.command("remote", "get-url", "origin") != self.origin
            or self.command("remote", "get-url", "--push", "--all", "origin") != self.origin
            or self.command("symbolic-ref", "--quiet", "--short", "HEAD") != b"main\n"
            or self.command("status", "--porcelain=v1", "--untracked-files=all")
        ):
            raise ValueError("Publication needs clean canonical main and one canonical push destination")
        mirror = self.runner(
            [str(self.git), "-C", str(self.root), "config", "--get", "--bool", "remote.origin.mirror"],
            cwd=self.root,
        )
        if (
            mirror.returncode not in (0, 1)
            or mirror.returncode == 0
            and mirror.stdout != b"false\n"
            or mirror.returncode == 1
            and mirror.stdout
        ):
            raise ValueError("Publication origin must not mirror other refs")

    def head(self):
        value = self.command("rev-parse", "--verify", "HEAD").decode("ascii").strip()
        if not COMMIT.fullmatch(value):
            raise ValueError("Site HEAD is not a commit")
        return value

    def remote_main(self):
        fields = self.command("ls-remote", "origin", "refs/heads/main").decode("ascii").split("\t")
        if len(fields) != 2 or fields[1] != "refs/heads/main\n" or not COMMIT.fullmatch(fields[0]):
            raise ValueError("Canonical remote main is missing or ambiguous")
        return fields[0]

    def git_directory(self):
        directory = Path(
            self.command("rev-parse", "--path-format=absolute", "--git-dir").decode("utf-8").strip()
        )
        return regular(directory, directory=True)


class SiteOperationControl:
    def __init__(self, git_directory: Path, commit: str):
        if not COMMIT.fullmatch(commit):
            raise ValueError("Static site control requires a selected Git commit")
        self.root = regular(git_directory, directory=True)
        self.path = self.root / f"rgm-site-{commit}.operation.json"

    def read(self):
        if not os.path.lexists(self.path):
            return None
        regular(self.path)
        if os.lstat(self.path).st_nlink != 1:
            raise ValueError("Static site operation control is shared")
        value = json.loads(self.path.read_text(encoding="utf-8"), object_pairs_hook=unique)
        if (
            type(value) is not dict
            or set(value) != {"siteCommit", "siteBase", "phase"}
            or any(
                type(value[key]) is not str or not COMMIT.fullmatch(value[key])
                for key in ("siteCommit", "siteBase")
            )
            or value["phase"] not in {"selected", "push-attempted", "site-pushed", "dispatch-attempted"}
        ):
            raise ValueError("Static site operation control is malformed")
        return value

    def write(self, value, *, create=False):
        if create and os.path.lexists(self.path):
            raise ValueError("Static site operation was already selected; inspect")
        if not create and self.read() is None:
            raise ValueError("Static site operation has no original selection")
        encoded = (json.dumps(value, sort_keys=True) + "\n").encode("utf-8")
        if create:
            descriptor = os.open(
                self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600
            )
            with os.fdopen(descriptor, "wb") as output:
                output.write(encoded)
                output.flush()
                os.fsync(output.fileno())
        else:
            descriptor, name = tempfile.mkstemp(prefix=".rgm-site-control-", dir=self.root)
            temporary = Path(name)
            try:
                with os.fdopen(descriptor, "wb") as output:
                    output.write(encoded)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, self.path)
            finally:
                if temporary.exists():
                    temporary.unlink()
        if os.name != "nt":
            descriptor = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)


class StaticSiteRelease:
    def __init__(
        self,
        site_root: Path,
        git: Path,
        gateway,
        *,
        runner=_run_process,
        validate_site=None,
        lock=None,
    ):
        self.site = CanonicalGit(site_root, git, runner)
        self.gateway = gateway
        self.runner = runner
        self.validate_site = validate_site or self._validate_site
        self.lock = lock or (lambda: publication_lock(site_root, git, runner=runner))

    def _validate_site(self, commit):
        script = regular(self.site.root / ".github/scripts/assemble_static_pages.py")
        executable = regular(Path(sys.executable).absolute())
        result = self.runner(
            [str(executable), "-B", str(script), "--site-root", str(self.site.root), "--site-commit", commit],
            cwd=self.site.root,
        )
        if result.returncode:
            raise ValueError("Site-owner pages-only readiness/semantic preflight failed")
        value = json.loads(result.stdout.decode("utf-8"), object_pairs_hook=unique)
        if (
            type(value) is not dict
            or set(value) != {"status", "fileCount"}
            or value["status"] != "static-pages-ready"
        ):
            raise ValueError("Site owner did not validate the selected static commit")

    def _preflight(self, commit):
        if not COMMIT.fullmatch(commit):
            raise ValueError("Selected site commit is invalid")
        self.site.ensure_main()
        if self.site.head() != commit:
            raise ValueError("Reviewed site commit drifted")
        self.validate_site(commit)

    def _control(self, commit):
        return SiteOperationControl(self.site.git_directory(), commit)

    def _dispatch(self, control, selected):
        self._preflight(selected["siteCommit"])
        if self.site.remote_main() != selected["siteCommit"]:
            raise ValueError("Site main drifted before Pages dispatch")
        if selected["phase"] == "dispatch-attempted":
            raise ValueError("Pages was already attempted; inspect, never redispatch")

        def record(commit):
            if commit != selected["siteCommit"]:
                raise ValueError("Dispatch selects another Git commit")
            control.write({**selected, "phase": "dispatch-attempted"})

        self.gateway.dispatch(selected["siteCommit"], record_attempt=record)
        return {"status": "dispatch-attempted", "siteCommit": selected["siteCommit"]}

    def begin(self, commit, base):
        with self.lock():
            self._preflight(commit)
            self.gateway.require_dispatch_token()
            self.gateway.require_vacant_dispatch(commit)
            control = self._control(commit)
            if control.read() is not None:
                raise ValueError("Static site operation exists; inspect, never restart")
            if not COMMIT.fullmatch(base) or self.site.remote_main() != base:
                raise ValueError("Reviewed site fast-forward base drifted")
            if self.site.command("merge-base", "--is-ancestor", base, commit):
                raise ValueError("Site selection is not a fast-forward")
            selected = {"siteCommit": commit, "siteBase": base, "phase": "selected"}
            control.write(selected, create=True)
            self._preflight(commit)
            if self.site.remote_main() != base:
                raise ValueError("Site remote main drifted before push")
            control.write({**selected, "phase": "push-attempted"})
            if base != commit:
                self.site.command("push", "--no-follow-tags", "origin", f"{commit}:refs/heads/main")
            if self.site.remote_main() != commit:
                raise ValueError("Site push is ambiguous; inspect, never replay")
            selected = {**selected, "phase": "site-pushed"}
            control.write(selected)
            return self._dispatch(control, selected)

    def reconcile(self, commit):
        with self.lock():
            control = self._control(commit)
            selected = control.read()
            if selected is None:
                raise ValueError("No original static-site selection exists")
            if selected["phase"] not in {"push-attempted", "site-pushed"}:
                raise ValueError("Only an observed pre-dispatch interruption can reconcile; never replay")
            self._preflight(commit)
            if self.site.remote_main() != commit:
                raise ValueError("Original site push is unconfirmed; inspection only")
            return self._dispatch(control, selected)

    def inspect(self, commit):
        selected = self._control(commit).read()
        if selected is None:
            return {"status": "no-recorded-operation", "siteCommit": commit}
        self._preflight(commit)
        if self.site.remote_main() != commit:
            return {"status": "site-push-unconfirmed-inspect-only", "siteCommit": commit}
        if selected["phase"] != "dispatch-attempted":
            return {"status": "site-pushed-await-dispatch-approval", "siteCommit": commit}
        return {"status": self.gateway.inspect_deployment(commit), "siteCommit": commit}
