#!/usr/bin/env python3
"""Serialize supported infrastructure operations for one selected site."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Iterator, Sequence


class SiteLockError(RuntimeError):
    """Raised when the selected site operation lock cannot be acquired safely."""


@contextmanager
def acquire_site_lock(lock_path: Path) -> Iterator[None]:
    """Hold one persistent, private, non-symlink lock file until context exit."""
    path = lock_path.expanduser()
    if not path.parent.is_dir():
        raise SiteLockError("site lock parent directory is unavailable")
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as error:
        raise SiteLockError("site lock file is unsafe or unavailable") from error
    try:
        mode = os.fstat(descriptor).st_mode
        if not stat.S_ISREG(mode):
            raise SiteLockError("site lock path is not a regular file")
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise SiteLockError("another operation already holds the selected site lock") from error
        yield
    finally:
        os.close(descriptor)


def run_locked(lock_path: Path, command: Sequence[str]) -> int:
    """Run one command while holding the selected site's lock."""
    if not command:
        raise SiteLockError("site lock command is required")
    with acquire_site_lock(lock_path):
        return subprocess.run(list(command), check=False).returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock-path", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        return run_locked(args.lock_path, command)
    except SiteLockError as error:
        print(f"site operation lock failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
