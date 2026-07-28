"""Transactional replacement of a generated output directory."""
from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path


class AtomicOutputError(OSError):
    """Raised when an output directory cannot be replaced safely."""


def atomic_output_directory(output_dir: Path, populate: Callable[[Path], None]) -> None:
    """Populate a sibling temporary directory, then install it as ``output_dir``.

    The previous directory is moved aside only after population succeeds. If the
    final replacement fails, it is restored before the original exception is
    re-raised. The output path must be absent or an actual directory; symlinks
    and other file types are rejected to avoid replacing an unexpected target.
    """
    output_dir = Path(output_dir)
    parent = output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)

    if output_dir.is_symlink() or (output_dir.exists() and not output_dir.is_dir()):
        raise AtomicOutputError(f"output path is not a directory: {output_dir}")

    staged = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=parent))
    staged.chmod(0o700)
    backup: Path | None = None
    installed = False
    try:
        populate(staged)

        if output_dir.exists():
            backup = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.backup-", dir=parent))
            backup.rmdir()
            os.replace(output_dir, backup)

        try:
            os.replace(staged, output_dir)
            installed = True
        except Exception:
            if backup is not None:
                os.replace(backup, output_dir)
                backup = None
            raise
    finally:
        if not installed:
            shutil.rmtree(staged, ignore_errors=True)
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)


__all__ = ["AtomicOutputError", "atomic_output_directory"]
