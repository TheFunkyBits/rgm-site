"""Cross-operation lock in the site repository's Git directory."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
from typing import BinaryIO


ProcessRunner = Callable[..., subprocess.CompletedProcess[bytes]]


@contextmanager
def publication_lock(
    site_root: Path,
    git: Path,
    *,
    runner: ProcessRunner | None = None,
) -> Iterator[None]:
    active_runner = runner or _run_process
    lock_path = _git_lock_path(site_root, git, active_runner)
    with _exclusive_lock(lock_path, "static-site publication"):
        yield


def _git_lock_path(site_root: Path, git: Path, runner: ProcessRunner) -> Path:
    result = runner(
        [
            str(git),
            "-C",
            str(site_root),
            "rev-parse",
            "--path-format=absolute",
            "--git-path",
            "rgm-site-publication.lock",
        ],
        cwd=site_root,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git rev-parse --git-path failed: {detail}")
    path = Path(result.stdout.decode("utf-8", errors="replace").strip())
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _run_process(
    arguments: Sequence[str | os.PathLike[str]],
    *,
    cwd: Path,
    stdin: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    if isinstance(arguments, (str, bytes)):
        raise TypeError("process arguments must be a sequence")
    command = [os.fspath(argument) for argument in arguments]
    if not command or any(not argument for argument in command):
        raise ValueError("process arguments must be nonempty")
    return subprocess.run(
        command,
        cwd=cwd,
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        check=False,
    )


@contextmanager
def _exclusive_lock(path: Path, label: str) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock:
        if lock.tell() == 0:
            lock.write(b"\0")
            lock.flush()
        lock.seek(0)
        _lock_file(lock, label)
        try:
            yield
        finally:
            _unlock_file(lock)


def _lock_file(lock: BinaryIO, label: str) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        raise RuntimeError(f"another {label} holds the lock") from error


def _unlock_file(lock: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
